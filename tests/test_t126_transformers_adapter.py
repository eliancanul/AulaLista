"""Adaptador Transformers probado sin pesos, red ni dependencias opcionales reales."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from curriculum.tribunal import (
    MINILM_CANDIDATE,
    ModelUnavailableError,
    NLIClass,
    NLIModelConfig,
    RunStatus,
    Tribunal,
    Verdict,
)
from curriculum.tribunal_transformers import (
    TransformersNLIAdapter,
    checkpoint_label_mapping,
    load_cached_tribunal,
)
from tests.test_t126_tribunal_nli import inputs


REAL_LABELS = {0: "entailment", 1: "neutral", 2: "contradiction"}
REVISION = "0a71e92a985b6e1ad1828cf67ce9c459639c1dca"


class FakeTensor:
    def __init__(self, values):
        self.values = values

    def to(self, device):
        assert device == "cpu"
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def __call__(self, premises, hypotheses, **kwargs):
        self.calls.append((premises, hypotheses, kwargs))
        return {"input_ids": FakeTensor([len(premises)])}


class FakeModel:
    def __init__(self, id2label=REAL_LABELS):
        self.config = SimpleNamespace(id2label=id2label)
        self.calls = 0

    def to(self, device):
        assert device == "cpu"
        return self

    def eval(self):
        return self

    def __call__(self, input_ids):
        self.calls += 1
        rows = [
            [[5.0, 0.0, -1.0], [-1.0, 0.0, 5.0]],
            [[-1.0, 5.0, 0.0]],
        ][self.calls - 1][: input_ids.values[0]]
        return SimpleNamespace(logits=FakeTensor(rows))


def test_checkpoint_order_is_read_from_config_not_guessed():
    assert checkpoint_label_mapping(REAL_LABELS) == {
        "entailment": NLIClass.ENTAILMENT,
        "neutral": NLIClass.NEUTRAL,
        "contradiction": NLIClass.CONTRADICTION,
    }
    with pytest.raises(ValueError, match="índices"):
        checkpoint_label_mapping({0: "entailment", 1: "neutral"})
    with pytest.raises(ValueError, match="Label NLI incompatible"):
        checkpoint_label_mapping({0: "LABEL_0", 1: "neutral", 2: "contradiction"})
    with pytest.raises(ValueError, match="una vez"):
        checkpoint_label_mapping({0: "entailment", 1: "entailment", 2: "contradiction"})


def test_adapter_batches_raw_logits_and_preserves_shadow_state():
    tokenizer = FakeTokenizer()
    model = FakeModel()
    mapping = checkpoint_label_mapping(model.config.id2label)
    config = NLIModelConfig(MINILM_CANDIDATE, REVISION, mapping, 1.0)
    adapter = TransformersNLIAdapter(
        tokenizer=tokenizer, model=model,
        torch_module=SimpleNamespace(inference_mode=nullcontext),
        config=config, batch_size=2, max_length=64,
    )
    claim, retrieval = inputs(("Fragmento uno", "Fragmento dos", "Fragmento tres"))

    receipt = Tribunal(config, adapter).evaluate(claim, retrieval, "El campo es Lenguajes")

    assert receipt.status == RunStatus.COMPLETED
    assert receipt.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert receipt.reason == "disagreement"
    assert [decision.verdict for decision in receipt.decisions] == [
        Verdict.SUPPORT, Verdict.CONTRADICTION, Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert receipt.decisions[0].logits == {"entailment": 5.0, "neutral": 0.0, "contradiction": -1.0}
    assert [len(call[0]) for call in tokenizer.calls] == [2, 1]
    assert tokenizer.calls[0][2] == {
        "padding": True, "truncation": True, "max_length": 64, "return_tensors": "pt",
    }
    assert claim.state == "candidate"


def test_wrong_mapping_is_rejected_before_inference():
    mapping = checkpoint_label_mapping(REAL_LABELS)
    config = NLIModelConfig(MINILM_CANDIDATE, REVISION, mapping, 1.0)
    wrong = NLIModelConfig(
        MINILM_CANDIDATE, REVISION,
        {"entailment": NLIClass.CONTRADICTION, "neutral": NLIClass.NEUTRAL, "contradiction": NLIClass.ENTAILMENT},
        1.0,
    )
    with pytest.raises(ValueError, match="id2label"):
        TransformersNLIAdapter(
            tokenizer=FakeTokenizer(), model=FakeModel(),
            torch_module=SimpleNamespace(inference_mode=nullcontext), config=wrong,
        )
    adapter = TransformersNLIAdapter(
        tokenizer=FakeTokenizer(), model=FakeModel(),
        torch_module=SimpleNamespace(inference_mode=nullcontext), config=config,
    )
    with pytest.raises(ValueError, match="mapeo de labels"):
        Tribunal(wrong, adapter)


def test_factory_loads_only_cached_files_at_pinned_revision(tmp_path):
    tokenizer = FakeTokenizer()
    model = FakeModel()
    calls = []
    fake_hub = SimpleNamespace(
        hf_hub_download=lambda **kwargs: calls.append(("hub", kwargs)) or str(tmp_path / "config.json")
    )
    fake_transformers = SimpleNamespace(
        AutoModelForSequenceClassification=SimpleNamespace(
            from_pretrained=lambda *args, **kwargs: calls.append(("model", args, kwargs)) or model
        ),
        AutoTokenizer=SimpleNamespace(
            from_pretrained=lambda *args, **kwargs: calls.append(("tokenizer", args, kwargs)) or tokenizer
        ),
    )
    fake_torch = SimpleNamespace(inference_mode=nullcontext)
    with patch.dict(sys.modules, {
        "huggingface_hub": fake_hub, "transformers": fake_transformers, "torch": fake_torch,
    }):
        tribunal = load_cached_tribunal(MINILM_CANDIDATE, REVISION, batch_size=2)

    assert calls[0] == ("hub", {
        "repo_id": MINILM_CANDIDATE, "filename": "config.json",
        "revision": REVISION, "local_files_only": True,
    })
    assert calls[1][2]["local_files_only"] is True
    assert calls[1][2]["use_safetensors"] is True
    assert calls[1][2]["trust_remote_code"] is False
    assert calls[2][2]["local_files_only"] is True
    assert tribunal.config.version == REVISION
    assert tribunal.config.runtime_config["local_files_only"] is True
    claim, retrieval = inputs()
    receipt = tribunal.evaluate(claim, retrieval, "El campo es Lenguajes")
    assert receipt.status == RunStatus.COMPLETED
    assert receipt.verdict == Verdict.SUPPORT
    assert claim.state == "candidate"


def test_missing_checkpoint_reports_model_unavailable_without_network():
    fake_hub = SimpleNamespace(hf_hub_download=lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    fake_transformers = SimpleNamespace(
        AutoModelForSequenceClassification=object(), AutoTokenizer=object()
    )
    with patch.dict(sys.modules, {
        "huggingface_hub": fake_hub, "transformers": fake_transformers,
        "torch": SimpleNamespace(inference_mode=nullcontext),
    }):
        with pytest.raises(ModelUnavailableError, match="caché local"):
            load_cached_tribunal(MINILM_CANDIDATE, REVISION)
    with pytest.raises(ValueError, match="SHA completo"):
        load_cached_tribunal(MINILM_CANDIDATE, "main")
