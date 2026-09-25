"""Contrato del tribunal NLI en shadow mode con fragmentos y adaptadores sintéticos."""

from __future__ import annotations

import threading
import json
from dataclasses import replace

import pytest

from curriculum.atlas import AtlasIndex, create_synthetic_sep_fixture
from curriculum.atlas.models import AtlasDocumentFragment, EvidenceCandidate, RetrievalReceipt
from curriculum.claims import AtomicClaim, CLAIM_STATE_CANDIDATE, CLAIM_TYPE_FIELD
from curriculum.tribunal import (
    MDEBERTA_CANDIDATE,
    MINILM_CANDIDATE,
    ModelUnavailableError,
    NLIClass,
    NLIModelConfig,
    RawNLIOutput,
    RunStatus,
    Tribunal,
    Verdict,
)


LABELS = {"LABEL_0": NLIClass.CONTRADICTION, "LABEL_1": NLIClass.NEUTRAL, "LABEL_2": NLIClass.ENTAILMENT}


def config(**changes):
    values = {
        "model_id": MINILM_CANDIDATE,
        "version": "synthetic-revision-1",
        "label_mapping": LABELS,
        "timeout_seconds": 0.2,
        "runtime_config": {"device": "cpu", "batch_size": 3},
    }
    values.update(changes)
    return NLIModelConfig(**values)


def inputs(texts=("El campo formativo es Lenguajes.",)):
    claim = AtomicClaim(
        claim_id="claim-1", claim_type=CLAIM_TYPE_FIELD, subject="document",
        predicate="campo_formativo", object_value="Lenguajes", state=CLAIM_STATE_CANDIDATE,
    )
    candidates = [
        EvidenceCandidate(
            candidate_id=f"candidate-{index}",
            fragment=AtlasDocumentFragment(
                fragment_id=f"fragment-{index}", source_id="synthetic", page_number=index + 1, text=text,
            ),
            retrieval_score=100.0 - index, rank=index + 1,
        )
        for index, text in enumerate(texts)
    ]
    receipt = RetrievalReceipt(
        receipt_id="atlas-1", query="Lenguajes", claim_id=claim.claim_id,
        index_version="synthetic-1", top_k=3, candidates=candidates,
        total_candidates_found=len(candidates), is_empty=not candidates,
        retriever_name="fake", reranker_name=None, execution_time_ms=0.0,
    )
    return claim, receipt


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def infer_batch(self, pairs):
        self.calls.append(pairs)
        if isinstance(self.outputs, Exception):
            raise self.outputs
        return self.outputs


def score(contradiction=0.0, neutral=0.0, entailment=0.0):
    return RawNLIOutput({"LABEL_0": contradiction, "LABEL_1": neutral, "LABEL_2": entailment})


@pytest.mark.parametrize(
    ("output", "verdict", "reason"),
    [
        (score(entailment=4.0), Verdict.SUPPORT, "winning_label"),
        (score(contradiction=4.0), Verdict.CONTRADICTION, "winning_label"),
        (score(neutral=4.0), Verdict.INSUFFICIENT_EVIDENCE, "neutral"),
        (score(contradiction=4.0, entailment=4.0), Verdict.INSUFFICIENT_EVIDENCE, "tie"),
    ],
)
def test_one_pair_preserves_raw_logits_and_claim(output, verdict, reason):
    claim, retrieval = inputs()
    fake = FakeAdapter([output])

    result = Tribunal(config(), fake).evaluate(claim, retrieval, "El campo formativo del documento es Lenguajes.")

    assert result.status == RunStatus.COMPLETED
    assert result.transitions == (RunStatus.PENDING, RunStatus.RUNNING, RunStatus.COMPLETED)
    assert result.verdict == verdict
    assert result.decisions[0].reason == reason
    assert result.decisions[0].logits == output.logits  # crudos; sin softmax
    assert result.decisions[0].pair.fragment_id == "fragment-0"
    assert result.decisions[0].pair.premise == retrieval.candidates[0].fragment.text
    assert result.decisions[0].pair.hypothesis == "El campo formativo del documento es Lenguajes."
    assert result.model_id == MINILM_CANDIDATE
    assert result.model_version == "synthetic-revision-1"
    assert result.label_mapping == {key: value.value for key, value in LABELS.items()}
    assert result.runtime_config == {"device": "cpu", "batch_size": 3}
    assert result.latency_ms >= 0
    assert result.shadow_mode is True
    assert claim.state == CLAIM_STATE_CANDIDATE
    assert fake.calls[0][0].claim_id == claim.claim_id
    assert fake.calls[0][0].receipt_id == retrieval.receipt_id
    serialized = json.loads(json.dumps(result.to_dict()))
    assert serialized["status"] == "completed"
    assert serialized["decisions"][0]["score_kind"] == "raw_logits"
    assert serialized["decisions"][0]["logits"] == output.logits


def test_vertical_slice_from_atlas_receipt_to_shadow_tribunal():
    manifest, fragments = create_synthetic_sep_fixture()
    atlas = AtlasIndex(index_version="synthetic-1")
    atlas.register_manifest(manifest)
    atlas.add_fragments(fragments)
    atlas.build_index()
    claim = AtomicClaim(
        claim_id="claim-nombrario", claim_type=CLAIM_TYPE_FIELD,
        subject="document", predicate="proyecto", object_value="El nombrario del grupo",
        state=CLAIM_STATE_CANDIDATE,
    )
    retrieval = atlas.retrieve_for_claim(claim, top_k=1)
    assert len(retrieval.candidates) == 1
    fake = FakeAdapter([score(entailment=7)])

    result = Tribunal(config(), fake).evaluate(claim, retrieval, "El proyecto se llama El nombrario del grupo.")

    assert result.retrieval_receipt_id == retrieval.receipt_id
    assert result.decisions[0].pair.fragment_id == retrieval.candidates[0].fragment.fragment_id
    assert result.verdict == Verdict.SUPPORT
    assert claim.state == CLAIM_STATE_CANDIDATE


def test_batch_preserves_disagreement_and_retrieval_order():
    claim, retrieval = inputs(("Dice Lenguajes", "Dice Matemáticas", "No menciona campo"))
    fake = FakeAdapter([score(entailment=8), score(contradiction=3), score(neutral=2)])

    result = Tribunal(config(model_id=MDEBERTA_CANDIDATE), fake).evaluate(claim, retrieval, "El campo es Lenguajes")

    assert len(fake.calls) == 1
    assert [pair.fragment_id for pair in fake.calls[0]] == ["fragment-0", "fragment-1", "fragment-2"]
    assert [decision.verdict for decision in result.decisions] == [
        Verdict.SUPPORT, Verdict.CONTRADICTION, Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert result.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.reason == "disagreement"
    assert claim.state == CLAIM_STATE_CANDIDATE


def test_no_candidates_is_explicit_and_does_not_call_adapter():
    claim, retrieval = inputs(())
    fake = FakeAdapter([])

    result = Tribunal(config(), fake).evaluate(claim, retrieval, "El campo es Lenguajes")

    assert result.status == RunStatus.COMPLETED
    assert result.transitions == (RunStatus.PENDING, RunStatus.COMPLETED)
    assert result.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.reason == "no_candidates"
    assert result.decisions == ()
    assert fake.calls == []


@pytest.mark.parametrize(
    ("adapter", "status", "reason", "error_type"),
    [
        (None, RunStatus.MODEL_UNAVAILABLE, "adapter_not_configured", None),
        (FakeAdapter(ModelUnavailableError()), RunStatus.MODEL_UNAVAILABLE, "model_unavailable", None),
        (FakeAdapter(RuntimeError("synthetic failure")), RunStatus.ERROR, "adapter_or_output_error", "RuntimeError"),
        (FakeAdapter(TimeoutError("adapter timeout")), RunStatus.ERROR, "adapter_or_output_error", "TimeoutError"),
        (FakeAdapter([]), RunStatus.ERROR, "adapter_or_output_error", "ValueError"),
        (FakeAdapter([RawNLIOutput({"unexpected": 1.0})]), RunStatus.ERROR, "adapter_or_output_error", "ValueError"),
        (FakeAdapter([score(entailment=float("nan"))]), RunStatus.ERROR, "adapter_or_output_error", "ValueError"),
    ],
)
def test_failed_runs_have_no_semantic_verdict(adapter, status, reason, error_type):
    claim, retrieval = inputs()

    result = Tribunal(config(), adapter).evaluate(claim, retrieval, "El campo es Lenguajes")

    assert result.status == status
    assert result.reason == reason
    assert result.error_type == error_type
    assert result.verdict is None
    assert result.decisions == ()
    assert claim.state == CLAIM_STATE_CANDIDATE


def test_timeout_limits_wait_but_does_not_claim_to_cancel_adapter():
    gate = threading.Event()

    class BlockingAdapter:
        def infer_batch(self, pairs):
            gate.wait(timeout=1)
            return [score(entailment=5)]

    claim, retrieval = inputs()
    try:
        result = Tribunal(config(timeout_seconds=0.01), BlockingAdapter()).evaluate(
            claim, retrieval, "El campo es Lenguajes"
        )
    finally:
        gate.set()

    assert result.status == RunStatus.TIMED_OUT
    assert result.reason == "deadline_exceeded"
    assert result.verdict is None
    assert result.decisions == ()
    assert claim.state == CLAIM_STATE_CANDIDATE


def test_label_mapping_is_explicit_and_checkpoint_specific():
    claim, retrieval = inputs()
    reversed_labels = {"entail": NLIClass.ENTAILMENT, "contra": NLIClass.CONTRADICTION, "other": NLIClass.NEUTRAL}
    fake = FakeAdapter([RawNLIOutput({"entail": 9, "contra": 1, "other": 0})])

    result = Tribunal(config(label_mapping=reversed_labels), fake).evaluate(claim, retrieval, "El campo es Lenguajes")

    assert result.verdict == Verdict.SUPPORT
    with pytest.raises(ValueError, match="label_mapping"):
        config(label_mapping={"LABEL_0": NLIClass.ENTAILMENT})
    with pytest.raises(ValueError, match="label_mapping"):
        config(label_mapping={"a": "entailment", "b": "contradiction", "c": "neutral"})


def test_configuration_snapshots_label_mapping_before_execution():
    labels = dict(LABELS)
    configured = config(label_mapping=labels)
    labels["LABEL_2"] = NLIClass.NEUTRAL
    assert configured.label_mapping["LABEL_2"] == NLIClass.ENTAILMENT
    with pytest.raises(TypeError):
        configured.label_mapping["LABEL_2"] = NLIClass.NEUTRAL


def test_mismatched_claim_or_missing_hypothesis_is_rejected_before_adapter():
    claim, retrieval = inputs()
    fake = FakeAdapter([score(entailment=1)])
    tribunal = Tribunal(config(), fake)

    with pytest.raises(ValueError, match="no corresponde"):
        tribunal.evaluate(claim, replace(retrieval, claim_id="other"), "El campo es Lenguajes")
    with pytest.raises(ValueError, match="hipótesis"):
        tribunal.evaluate(claim, retrieval, "   ")
    assert fake.calls == []
