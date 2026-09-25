"""Ruta selectiva de #127 con Atlas y jueces sintéticos, sin red ni pesos."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import dataclass, replace

import pytest

from curriculum.atlas import AtlasIndex, create_synthetic_sep_fixture
from curriculum.claims import AtomicClaim, CLAIM_STATE_CANDIDATE, CLAIM_TYPE_FIELD
from curriculum.source_interpreter import (
    ImportDossier, InterpretedField, ORIGIN_EXTRACTED, STATUS_SUPPORTED, SourceReference,
)
from curriculum.tribunal import (
    NLIClass, NLIModelConfig, RawNLIOutput, Tribunal, Verdict,
)
from curriculum.tribunal_orchestrator import (
    Disposition, InMemoryReceiptStore, RouteState, SQLiteReceiptStore,
    SelectivePolicy, SelectiveRunner, summarize_runs,
)


LABELS = {"entailment": NLIClass.ENTAILMENT, "neutral": NLIClass.NEUTRAL, "contradiction": NLIClass.CONTRADICTION}


class FakeAdapter:
    def __init__(self, output: RawNLIOutput | Exception):
        self.output = output
        self.calls = 0

    def infer_batch(self, pairs):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return [self.output for _ in pairs]


@dataclass
class Gate:
    gate_id: str
    version: str
    allowed: bool
    calls: int = 0

    def allows(self, receipts):
        self.calls += 1
        return self.allowed


def judge(model_id: str, output: RawNLIOutput | Exception):
    adapter = FakeAdapter(output)
    tribunal = Tribunal(NLIModelConfig(model_id, "fake-v1", LABELS, 1.0), adapter)
    return tribunal, adapter


def score(*, entailment=0.0, neutral=0.0, contradiction=0.0):
    return RawNLIOutput({"entailment": entailment, "neutral": neutral, "contradiction": contradiction})


@pytest.fixture
def atlas_and_claim():
    manifest, fragments = create_synthetic_sep_fixture()
    atlas = AtlasIndex(index_version="synthetic-127")
    atlas.register_manifest(manifest)
    atlas.add_fragments(fragments)
    atlas.build_index()
    claim = AtomicClaim(
        claim_id="claim-127", claim_type=CLAIM_TYPE_FIELD, subject="document",
        predicate="proyecto", object_value="El Nombrario", state=CLAIM_STATE_CANDIDATE,
        source_doc_sha256="source-sha-127", excerpt="El Nombrario",
    )
    return atlas, claim


def policy(primary=True, agreement=True):
    return SelectivePolicy(
        "policy-127", "v1", 2,
        primary_gate=Gate("primary-rule", "v1", primary) if primary is not None else None,
        agreement_gate=Gate("agreement-rule", "v1", agreement) if agreement is not None else None,
    )


def test_disabled_and_unconfigured_runner_fail_closed_without_model_calls(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, adapter = judge("fast", score(entailment=4))
    store = InMemoryReceiptStore()
    disabled = SelectiveRunner(store, retriever=atlas, primary=first, policy=policy())
    before = copy.deepcopy(claim.to_dict())

    receipt = disabled.run(claim, "El proyecto se llama El Nombrario.")
    assert receipt.disposition == Disposition.ABSTAIN
    assert receipt.reason == "runner_disabled"
    assert receipt.transitions == (RouteState.PENDING, RouteState.ABSTAIN)
    assert adapter.calls == 0
    assert claim.to_dict() == before

    unconfigured = SelectiveRunner(store, retriever=atlas, primary=first, enabled=True)
    assert unconfigured.run(claim, "El proyecto se llama El Nombrario.").reason == "policy_unconfigured"
    assert adapter.calls == 0
    assert SelectiveRunner(store, policy=policy(), enabled=True).run(claim, "algo").reason == "atlas_unavailable"
    assert SelectiveRunner(store, retriever=atlas, policy=policy(), enabled=True).run(claim, "algo").reason == "primary_unavailable"


def test_easy_claim_stops_at_first_judge_and_never_changes_claim(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, fast = judge("fast", score(entailment=4))
    second, slow = judge("slow", score(contradiction=4))
    events = []
    runner = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first, secondary=second,
        policy=policy(), enabled=True, on_receipt=events.append,
    )
    before = copy.deepcopy(claim.to_dict())

    receipt = runner.run(claim, "El proyecto se llama El Nombrario.")

    assert receipt.disposition == Disposition.ACCEPT
    assert receipt.reason == "primary_gate"
    assert receipt.transitions == (RouteState.PENDING, RouteState.RETRIEVED, RouteState.PRIMARY, RouteState.ACCEPT)
    assert [stage.stage for stage in receipt.stages] == ["retrieval", "primary", "policy"]
    assert receipt.stages[1].details["decisions"][0]["score_kind"] == "raw_logits"
    assert receipt.shadow_mode and receipt.human_review_required
    assert receipt.semantic_quality == "not_evaluable"
    assert fast.calls == 1 and slow.calls == 0
    assert claim.to_dict() == before
    assert len(events) == 1
    assert summarize_runs([receipt, receipt])["coverage"] == 1.0
    assert summarize_runs([receipt, receipt])["model_calls"] == 1


def test_uncertainty_escalates_agreement_requires_separate_gate(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, fast = judge("fast", score(entailment=3))
    second, slow = judge("slow", score(entailment=5))
    runner = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first, secondary=second,
        policy=policy(primary=False, agreement=False), enabled=True,
    )

    receipt = runner.run(claim, "El proyecto se llama El Nombrario.")

    assert receipt.disposition == Disposition.ABSTAIN
    assert receipt.reason == "agreement_not_authorized"
    assert receipt.agreement == Verdict.SUPPORT.value
    assert RouteState.ESCALATED in receipt.transitions
    assert receipt.telemetry["model_calls"] == 2
    assert fast.calls == slow.calls == 1

    approved = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first, secondary=second,
        policy=policy(primary=False, agreement=True), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert approved.disposition == Disposition.ACCEPT
    assert approved.reason == "agreement_gate"
    assert approved.stages[-1].details["agreement_is_truth"] is False


def test_disagreement_and_neutral_abstain_even_with_permissive_gates(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, _ = judge("fast", score(entailment=4))
    second, _ = judge("slow", score(contradiction=4))
    receipt = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first, secondary=second,
        policy=policy(primary=False), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert receipt.disposition == Disposition.ABSTAIN
    assert receipt.reason == "judge_disagreement"
    assert receipt.agreement == "disagreement"

    neutral_first, _ = judge("fast-neutral", score(neutral=4))
    neutral_second, _ = judge("slow-neutral", score(neutral=4))
    neutral = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=neutral_first, secondary=neutral_second,
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert neutral.reason == "insufficient_evidence"
    assert neutral.disposition == Disposition.ABSTAIN


def test_missing_secondary_model_and_duplicate_judge_fail_closed(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, _ = judge("fast", score(entailment=4))
    missing = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first,
        policy=policy(primary=False), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert missing.reason == "secondary_unavailable"
    assert missing.disposition == Disposition.ABSTAIN

    duplicate, duplicate_adapter = judge("fast", score(entailment=4))
    repeated = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first, secondary=duplicate,
        policy=policy(primary=False), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert repeated.reason == "secondary_not_distinct"
    assert duplicate_adapter.calls == 0


def test_no_candidates_model_unavailable_and_gate_error(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, adapter = judge("fast", score(entailment=4))
    absent = copy.deepcopy(claim)
    absent.claim_id = "absent"
    absent.object_value = "zzzxxyyqq"
    absent.excerpt = ""
    no_candidates = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first,
        policy=policy(), enabled=True,
    ).run(absent, "zzzxxyyqq")
    assert no_candidates.reason == "no_candidates"
    assert adapter.calls == 0

    unavailable = Tribunal(NLIModelConfig("missing", "fake-v1", LABELS, 1.0), None)
    failed = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=unavailable,
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert failed.reason == "primary_failed"
    assert failed.stages[1].status == "model_unavailable"

    class BrokenGate:
        gate_id = "broken"
        version = "v1"

        def allows(self, receipts):
            raise RuntimeError("secret detail")

    broken_policy = SelectivePolicy("policy-127", "v1", 2, primary_gate=BrokenGate())
    broken = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first,
        policy=broken_policy, enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert broken.reason == "policy_failed"
    assert broken.stages[-1].details == {"error_type": "RuntimeError"}
    assert "secret detail" not in json.dumps(broken.to_dict())


def test_contradiction_and_failure_paths(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, _ = judge("fast", score(contradiction=4))
    selected = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first,
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama otro.")
    assert selected.disposition == Disposition.CONTRADICTION
    assert claim.state == CLAIM_STATE_CANDIDATE

    broken, _ = judge("broken", RuntimeError("private document text must not persist"))
    receipt = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=broken,
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama otro.")
    assert receipt.disposition == Disposition.ABSTAIN
    assert receipt.reason == "primary_failed"
    assert receipt.stages[1].status == "error"
    assert receipt.stages[1].details["error_type"] == "RuntimeError"
    assert "private document text" not in json.dumps(receipt.to_dict())


def test_sqlite_retry_is_idempotent_and_saves_no_document_text(tmp_path, atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, adapter = judge("fast", score(entailment=4))
    path = tmp_path / "shadow" / "receipts.sqlite3"
    hypothesis = "Texto privado de la planeación: El proyecto se llama El Nombrario."
    runner = SelectiveRunner(
        SQLiteReceiptStore(path), retriever=atlas, primary=first,
        policy=policy(), enabled=True,
    )
    original = runner.run(claim, hypothesis)
    replay = SelectiveRunner(
        SQLiteReceiptStore(path), retriever=atlas, primary=first,
        policy=policy(), enabled=True,
    ).run(claim, hypothesis)
    assert replay.to_dict() == original.to_dict()
    assert adapter.calls == 1
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT payload_json FROM tribunal_runs").fetchall()
    assert len(rows) == 1
    assert "Texto privado" not in rows[0][0]
    assert "El Nombrario" not in rows[0][0]
    assert "premise" not in rows[0][0]
    assert "hypothesis" not in rows[0][0].replace("hypothesis_sha256", "")

    changed = runner.run(claim, hypothesis + " Cambio explícito.")
    assert changed.run_id != original.run_id
    assert adapter.calls == 2
    assert path.stat().st_mode & 0o777 == 0o600


def test_explicit_retry_preserves_previous_failure_and_trace(tmp_path, atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, adapter = judge("fast", RuntimeError("temporary failure"))
    store = SQLiteReceiptStore(tmp_path / "receipts.sqlite3")
    runner = SelectiveRunner(store, retriever=atlas, primary=first, policy=policy(), enabled=True)

    failed = runner.run(claim, "El proyecto se llama El Nombrario.")
    assert failed.disposition == Disposition.ABSTAIN
    assert runner.run(claim, "El proyecto se llama El Nombrario.").run_id == failed.run_id
    assert adapter.calls == 1

    adapter.output = score(entailment=4)
    retried = runner.run(claim, "El proyecto se llama El Nombrario.", attempt=2)
    assert retried.disposition == Disposition.ACCEPT
    assert retried.request_id == failed.request_id
    assert retried.previous_run_id == failed.run_id
    assert retried.attempt == 2
    assert store.get(failed.run_id).reason == "primary_failed"
    assert adapter.calls == 2
    summary = summarize_runs([failed, failed, retried])
    assert summary["runs"] == 2
    assert summary["requests"] == 1
    assert summary["coverage"] == 1.0
    assert summary["model_calls"] == 2
    with pytest.raises(ValueError, match="intento anterior"):
        runner.run(claim, "El proyecto se llama El Nombrario.", attempt=4)


def test_mutating_plugins_cannot_change_source_claim(atlas_and_claim):
    atlas, claim = atlas_and_claim
    before = copy.deepcopy(claim.to_dict())
    first, _ = judge("fast", score(entailment=4))

    class MutatingRetriever:
        index_version = atlas.index_version

        def get_metrics(self):
            return atlas.get_metrics()

        def retrieve_for_claim(self, received, top_k):
            received.state = "forged"
            return atlas.retrieve_for_claim(received, top_k=top_k)

    class MutatingJudge:
        config = first.config

        def evaluate(self, received, retrieval, hypothesis):
            result = first.evaluate(received, retrieval, hypothesis)
            received.state = "forged"
            retrieval.candidates.clear()
            return result

    receipt = SelectiveRunner(
        InMemoryReceiptStore(), retriever=MutatingRetriever(), primary=MutatingJudge(),
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert receipt.disposition == Disposition.ACCEPT
    assert claim.to_dict() == before


def test_malformed_judge_receipt_cannot_select_without_candidate_links(atlas_and_claim):
    atlas, claim = atlas_and_claim
    first, _ = judge("fast", score(entailment=4))

    class BrokenJudge:
        config = first.config

        def evaluate(self, received, retrieval, hypothesis):
            return replace(first.evaluate(received, retrieval, hypothesis), decisions=())

    receipt = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=BrokenJudge(),
        policy=policy(), enabled=True,
    ).run(claim, "El proyecto se llama El Nombrario.")
    assert receipt.disposition == Disposition.ABSTAIN
    assert receipt.reason == "primary_failed"
    assert receipt.stages[1].details == {"error_type": "ValueError"}


def test_compiler_to_runner_requires_explicit_hypotheses(atlas_and_claim):
    atlas, _ = atlas_and_claim
    first, adapter = judge("fast", score(entailment=4))
    dossier = ImportDossier(
        source_sha256="doc-127", source_name="synthetic.pdf", page_count=1,
        general_fields={
            "proyecto": InterpretedField(
                name="proyecto", value="El Nombrario", origin=ORIGIN_EXTRACTED,
                status=STATUS_SUPPORTED,
                evidence=[SourceReference(document_sha256="doc-127", page_number=1, excerpt="El Nombrario")],
            ),
            "metodologia": InterpretedField(name="metodologia", value="", origin=ORIGIN_EXTRACTED, status=STATUS_SUPPORTED),
        },
    )
    from curriculum.claims import compile_dossier_to_atomic_claims

    claims = compile_dossier_to_atomic_claims(dossier)
    hypotheses = {claims[0].claim_id: "El proyecto se llama El Nombrario."}
    receipts = SelectiveRunner(
        InMemoryReceiptStore(), retriever=atlas, primary=first,
        policy=policy(), enabled=True,
    ).run_dossier(dossier, hypotheses)
    assert len(receipts) == 2
    assert receipts[0].disposition == Disposition.ACCEPT
    assert receipts[1].disposition == Disposition.ABSTAIN
    assert receipts[1].reason == "hypothesis_missing"
    assert adapter.calls == 1
