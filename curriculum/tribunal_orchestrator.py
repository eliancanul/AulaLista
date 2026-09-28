"""Orquestación selectiva local del tribunal (#127).

Las decisiones son señales experimentales en shadow mode. Ninguna ruta escribe
AtomicClaim, ImportDossier, modelos editoriales ni progreso curricular.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

from curriculum.atlas.models import RetrievalReceipt
from curriculum.atlas.constants import PRIVACY_GUARANTEE_OFFLINE
from curriculum.claims import AtomicClaim, compile_dossier_to_atomic_claims
from curriculum.source_interpreter import ImportDossier
from curriculum.tribunal import RunStatus, TribunalReceipt, Verdict


class Disposition(str, Enum):
    ACCEPT = "accept"
    CONTRADICTION = "contradiction"
    ABSTAIN = "abstain"


class RouteState(str, Enum):
    PENDING = "pending"
    RETRIEVED = "retrieved"
    PRIMARY = "primary"
    ESCALATED = "escalated"
    SECONDARY = "secondary"
    ACCEPT = "accept"
    CONTRADICTION = "contradiction"
    ABSTAIN = "abstain"


class DecisionGate(Protocol):
    """Regla externa versionada; sus umbrales se calibran fuera del runner."""

    gate_id: str
    version: str

    def allows(self, receipts: tuple[TribunalReceipt, ...]) -> bool: ...


class Retriever(Protocol):
    index_version: str

    def get_metrics(self) -> object | None: ...

    def retrieve_for_claim(self, claim: AtomicClaim, top_k: int = 3) -> RetrievalReceipt: ...


class Judge(Protocol):
    config: object

    def evaluate(self, claim: AtomicClaim, retrieval: RetrievalReceipt, hypothesis: str) -> TribunalReceipt: ...


class AppealAdapter(Protocol):
    """Extensión local futura. El runner de #127 no ejecuta apelaciones."""

    def appeal(self, claim: AtomicClaim, retrieval: RetrievalReceipt, receipts: tuple[TribunalReceipt, ...]) -> object: ...


@dataclass(frozen=True)
class SelectivePolicy:
    policy_id: str
    version: str
    top_k: int
    primary_gate: DecisionGate | None = None
    agreement_gate: DecisionGate | None = None

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("La política requiere identificador y versión")
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int) or self.top_k < 1:
            raise ValueError("top_k debe ser un entero positivo")
        for gate in (self.primary_gate, self.agreement_gate):
            if gate is not None and (not gate.gate_id.strip() or not gate.version.strip()):
                raise ValueError("Cada regla debe declarar identificador y versión")

    def identity(self) -> dict[str, object]:
        def gate_ref(gate: DecisionGate | None) -> dict[str, str] | None:
            return {"id": gate.gate_id, "version": gate.version} if gate is not None else None

        return {
            "id": self.policy_id,
            "version": self.version,
            "top_k": self.top_k,
            "primary_gate": gate_ref(self.primary_gate),
            "agreement_gate": gate_ref(self.agreement_gate),
        }


@dataclass(frozen=True)
class StageReceipt:
    stage: str
    status: str
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"stage": self.stage, "status": self.status, "details": self.details}


@dataclass(frozen=True)
class OrchestrationReceipt:
    run_id: str
    request_id: str
    attempt: int
    previous_run_id: str | None
    claim_id: str
    source_doc_sha256: str
    hypothesis_sha256: str
    index_version: str | None
    index_hash: str | None
    policy: dict[str, object] | None
    disposition: Disposition
    reason: str
    transitions: tuple[RouteState, ...]
    stages: tuple[StageReceipt, ...]
    telemetry: dict[str, float | int]
    agreement: str  # support | contradiction | disagreement | not_observed
    shadow_mode: bool = True
    human_review_required: bool = True
    semantic_quality: str = "not_evaluable"

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "attempt": self.attempt,
            "previous_run_id": self.previous_run_id,
            "claim_id": self.claim_id,
            "source_doc_sha256": self.source_doc_sha256,
            "hypothesis_sha256": self.hypothesis_sha256,
            "index_version": self.index_version,
            "index_hash": self.index_hash,
            "policy": self.policy,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "transitions": [state.value for state in self.transitions],
            "stages": [stage.to_dict() for stage in self.stages],
            "telemetry": self.telemetry,
            "agreement": self.agreement,
            "shadow_mode": self.shadow_mode,
            "human_review_required": self.human_review_required,
            "semantic_quality": self.semantic_quality,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OrchestrationReceipt:
        return cls(
            run_id=str(data["run_id"]),
            request_id=str(data["request_id"]),
            attempt=int(data["attempt"]),
            previous_run_id=data["previous_run_id"],  # type: ignore[arg-type]
            claim_id=str(data["claim_id"]),
            source_doc_sha256=str(data["source_doc_sha256"]),
            hypothesis_sha256=str(data["hypothesis_sha256"]),
            index_version=data["index_version"],  # type: ignore[arg-type]
            index_hash=data["index_hash"],  # type: ignore[arg-type]
            policy=data["policy"],  # type: ignore[arg-type]
            disposition=Disposition(data["disposition"]),
            reason=str(data["reason"]),
            transitions=tuple(RouteState(item) for item in data["transitions"]),  # type: ignore[union-attr]
            stages=tuple(StageReceipt(**item) for item in data["stages"]),  # type: ignore[union-attr]
            telemetry=data["telemetry"],  # type: ignore[arg-type]
            agreement=str(data["agreement"]),
            shadow_mode=bool(data["shadow_mode"]),
            human_review_required=bool(data["human_review_required"]),
            semantic_quality=str(data["semantic_quality"]),
        )


class ReceiptStore(Protocol):
    def get(self, run_id: str) -> OrchestrationReceipt | None: ...

    def save(self, receipt: OrchestrationReceipt) -> OrchestrationReceipt: ...


class InMemoryReceiptStore:
    def __init__(self) -> None:
        self._runs: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> OrchestrationReceipt | None:
        with self._lock:
            payload = self._runs.get(run_id)
        return OrchestrationReceipt.from_dict(json.loads(payload)) if payload is not None else None

    def save(self, receipt: OrchestrationReceipt) -> OrchestrationReceipt:
        payload = json.dumps(receipt.to_dict(), sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self._lock:
            stored = self._runs.setdefault(receipt.run_id, payload)
        return OrchestrationReceipt.from_dict(json.loads(stored))


class SQLiteReceiptStore:
    """Registro local durable. Se persisten referencias y logits, nunca textos."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS tribunal_runs (run_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")

    def get(self, run_id: str) -> OrchestrationReceipt | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload_json FROM tribunal_runs WHERE run_id = ?", (run_id,)).fetchone()
        return OrchestrationReceipt.from_dict(json.loads(row[0])) if row else None

    def save(self, receipt: OrchestrationReceipt) -> OrchestrationReceipt:
        payload = json.dumps(receipt.to_dict(), sort_keys=True, ensure_ascii=False, allow_nan=False)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR IGNORE INTO tribunal_runs VALUES (?, ?)", (receipt.run_id, payload))
            row = db.execute("SELECT payload_json FROM tribunal_runs WHERE run_id = ?", (receipt.run_id,)).fetchone()
        return OrchestrationReceipt.from_dict(json.loads(row[0]))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _judge_ref(judge: Judge | None) -> dict[str, str] | None:
    if judge is None:
        return None
    try:
        config = judge.config
        if not config.model_id or not config.version:
            return None
        return {"model_id": str(config.model_id), "version": str(config.version)}
    except AttributeError:
        return None


def _retrieval_stage(receipt: RetrievalReceipt) -> StageReceipt:
    return StageReceipt("retrieval", "completed", {
        "receipt_id": receipt.receipt_id,
        "index_version": receipt.index_version,
        "top_k": receipt.top_k,
        "total_candidates_found": receipt.total_candidates_found,
        "retriever": receipt.retriever_name,
        "reranker": receipt.reranker_name,
        "latency_ms": receipt.execution_time_ms,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "fragment_id": candidate.fragment.fragment_id,
                "source_id": candidate.fragment.source_id,
                "page_number": candidate.fragment.page_number,
                "rank": candidate.rank,
                "retrieval_score": candidate.retrieval_score,
                "rerank_score": candidate.rerank_score,
                "final_score": candidate.final_score,
            }
            for candidate in receipt.candidates
        ],
    })


def _judge_stage(name: str, receipt: TribunalReceipt) -> StageReceipt:
    # La configuración arbitraria puede contener rutas o secretos. Sólo se
    # registran parámetros operativos conocidos para reproducir la corrida.
    safe_runtime = {
        key: receipt.runtime_config[key]
        for key in ("backend", "device", "batch_size", "max_length", "local_files_only")
        if key in receipt.runtime_config
    }
    return StageReceipt(name, receipt.status.value, {
        "run_id": receipt.run_id,
        "retrieval_receipt_id": receipt.retrieval_receipt_id,
        "model_id": receipt.model_id,
        "model_version": receipt.model_version,
        "label_mapping": receipt.label_mapping,
        "runtime_config": safe_runtime,
        "timeout_seconds": receipt.timeout_seconds,
        "latency_ms": receipt.latency_ms,
        "verdict": receipt.verdict.value if receipt.verdict is not None else None,
        "reason": receipt.reason,
        "error_type": receipt.error_type,
        "transitions": [state.value for state in receipt.transitions],
        "decisions": [
            {
                "candidate_id": decision.pair.candidate_id,
                "fragment_id": decision.pair.fragment_id,
                "logits": decision.logits,
                "score_kind": "raw_logits",
                "verdict": decision.verdict.value,
                "reason": decision.reason,
            }
            for decision in receipt.decisions
        ],
    })


class SelectiveRunner:
    """Ruta optativa de investigación; la ausencia de configuración cierra en abstención."""

    def __init__(
        self,
        store: ReceiptStore,
        *,
        retriever: Retriever | None = None,
        primary: Judge | None = None,
        secondary: Judge | None = None,
        policy: SelectivePolicy | None = None,
        enabled: bool = False,
        on_receipt: Callable[[OrchestrationReceipt], None] | None = None,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.primary = primary
        self.secondary = secondary
        self.policy = policy
        self.enabled = enabled
        self.on_receipt = on_receipt

    def run(self, claim: AtomicClaim, hypothesis: str, *, attempt: int = 1) -> OrchestrationReceipt:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("attempt debe ser un entero positivo")
        started = time.perf_counter()
        try:
            metrics = self.retriever.get_metrics() if self.enabled and self.retriever is not None else None
            index_version = self.retriever.index_version if self.enabled and self.retriever is not None else None
            index_hash = str(metrics.index_hash) if metrics is not None else None
        except Exception:
            metrics = None
            index_version = None
            index_hash = None
        policy_ref = self.policy.identity() if self.policy is not None else None
        hypothesis_sha = _sha(hypothesis)
        # Incluye contenido, política, índice y versiones: una edición nunca
        # reutiliza un recibo de una entrada anterior con el mismo claim_id.
        identity = {
            "claim_sha256": _sha(json.dumps(claim.to_dict(), sort_keys=True, ensure_ascii=False, default=str)),
            "hypothesis_sha256": hypothesis_sha,
            "index_version": index_version,
            "index_hash": index_hash,
            "policy": policy_ref,
            "primary": _judge_ref(self.primary),
            "secondary": _judge_ref(self.secondary),
            "enabled": self.enabled,
        }
        request_id = _sha(json.dumps(identity, sort_keys=True, ensure_ascii=False))
        run_id = _sha(f"{request_id}:{attempt}")
        existing = self.store.get(run_id)
        if existing is not None:
            return existing
        previous_run_id = None
        if attempt > 1:
            previous_run_id = _sha(f"{request_id}:{attempt - 1}")
            if self.store.get(previous_run_id) is None:
                raise ValueError("El intento anterior debe existir para preservar la trazabilidad")

        transitions = [RouteState.PENDING]
        stages: list[StageReceipt] = []
        model_calls = 0
        pair_count = 0
        agreement = "not_observed"

        def finish(disposition: Disposition, reason: str) -> OrchestrationReceipt:
            transitions.append(RouteState(disposition.value))
            receipt = OrchestrationReceipt(
                run_id=run_id,
                request_id=request_id,
                attempt=attempt,
                previous_run_id=previous_run_id,
                claim_id=claim.claim_id,
                source_doc_sha256=claim.source_doc_sha256,
                hypothesis_sha256=hypothesis_sha,
                index_version=index_version,
                index_hash=index_hash,
                policy=policy_ref,
                disposition=disposition,
                reason=reason,
                transitions=tuple(transitions),
                stages=tuple(stages),
                telemetry={
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "model_calls": model_calls,
                    "pair_count": pair_count,
                },
                agreement=agreement,
            )
            saved = self.store.save(receipt)
            if self.on_receipt is not None and saved.run_id == receipt.run_id:
                try:
                    self.on_receipt(saved)
                except Exception:
                    # Telemetría externa no cambia una decisión ya persistida.
                    pass
            return saved

        if not self.enabled:
            return finish(Disposition.ABSTAIN, "runner_disabled")
        if not hypothesis.strip():
            return finish(Disposition.ABSTAIN, "hypothesis_missing")
        if self.policy is None:
            return finish(Disposition.ABSTAIN, "policy_unconfigured")
        if self.retriever is None or metrics is None:
            return finish(Disposition.ABSTAIN, "atlas_unavailable")
        if self.primary is None:
            return finish(Disposition.ABSTAIN, "primary_unavailable")

        try:
            retrieval = self.retriever.retrieve_for_claim(copy.deepcopy(claim), top_k=self.policy.top_k)
            current_metrics = self.retriever.get_metrics()
            if (
                retrieval.claim_id != claim.claim_id
                or retrieval.index_version != index_version
                or retrieval.privacy_guarantee != PRIVACY_GUARANTEE_OFFLINE
                or current_metrics is None
                or current_metrics.index_hash != index_hash
            ):
                raise ValueError("El recibo de Atlas no corresponde a la entrada")
            stages.append(_retrieval_stage(retrieval))
            transitions.append(RouteState.RETRIEVED)
        except Exception as exc:
            stages.append(StageReceipt("retrieval", "error", {"error_type": type(exc).__name__}))
            return finish(Disposition.ABSTAIN, "retrieval_failed")
        if not retrieval.candidates:
            return finish(Disposition.ABSTAIN, "no_candidates")

        def judge(name: str, adapter: Judge) -> TribunalReceipt | None:
            nonlocal model_calls, pair_count
            model_calls += 1
            pair_count += len(retrieval.candidates)
            try:
                result = adapter.evaluate(copy.deepcopy(claim), copy.deepcopy(retrieval), hypothesis)
                if (
                    result.claim_id != claim.claim_id
                    or result.retrieval_receipt_id != retrieval.receipt_id
                    or not result.shadow_mode
                    or result.model_id != adapter.config.model_id
                    or result.model_version != adapter.config.version
                ):
                    raise ValueError("El recibo NLI no corresponde a la entrada")
                if result.status == RunStatus.COMPLETED and (
                    len(result.decisions) != len(retrieval.candidates)
                    or any(
                        decision.pair.claim_id != claim.claim_id
                        or decision.pair.receipt_id != retrieval.receipt_id
                        or decision.pair.candidate_id != candidate.candidate_id
                        or decision.pair.fragment_id != candidate.fragment.fragment_id
                        for decision, candidate in zip(result.decisions, retrieval.candidates)
                    )
                ):
                    raise ValueError("El batch NLI no conserva la evidencia recuperada")
                stages.append(_judge_stage(name, result))
                return result
            except Exception as exc:
                stages.append(StageReceipt(name, "error", {"error_type": type(exc).__name__}))
                return None

        first = judge("primary", self.primary)
        transitions.append(RouteState.PRIMARY)
        if first is None or first.status != RunStatus.COMPLETED or first.verdict is None:
            return finish(Disposition.ABSTAIN, "primary_failed")

        def gate_allows(gate: DecisionGate | None, receipts: tuple[TribunalReceipt, ...]) -> bool | None:
            if gate is None:
                return False
            try:
                result = gate.allows(receipts)
                if not isinstance(result, bool):
                    raise ValueError("La regla debe devolver bool")
                return result
            except Exception as exc:
                stages.append(StageReceipt("policy", "error", {"error_type": type(exc).__name__}))
                return None

        if first.verdict in (Verdict.SUPPORT, Verdict.CONTRADICTION):
            allowed = gate_allows(self.policy.primary_gate, (first,))
            if allowed is None:
                return finish(Disposition.ABSTAIN, "policy_failed")
            if allowed:
                disposition = Disposition.ACCEPT if first.verdict == Verdict.SUPPORT else Disposition.CONTRADICTION
                stages.append(StageReceipt("policy", "selected", {"gate": "primary", "agreement_is_truth": False}))
                return finish(disposition, "primary_gate")

        transitions.append(RouteState.ESCALATED)
        stages.append(StageReceipt("escalation", "requested", {"reason": first.reason}))
        if self.secondary is None:
            return finish(Disposition.ABSTAIN, "secondary_unavailable")
        if _judge_ref(self.secondary) == _judge_ref(self.primary):
            return finish(Disposition.ABSTAIN, "secondary_not_distinct")
        second = judge("secondary", self.secondary)
        transitions.append(RouteState.SECONDARY)
        if second is None or second.status != RunStatus.COMPLETED or second.verdict is None:
            return finish(Disposition.ABSTAIN, "secondary_failed")
        if first.verdict != second.verdict:
            agreement = "disagreement"
            return finish(Disposition.ABSTAIN, "judge_disagreement")
        if first.verdict == Verdict.INSUFFICIENT_EVIDENCE:
            return finish(Disposition.ABSTAIN, "insufficient_evidence")

        agreement = first.verdict.value
        allowed = gate_allows(self.policy.agreement_gate, (first, second))
        if allowed is None:
            return finish(Disposition.ABSTAIN, "policy_failed")
        if not allowed:
            return finish(Disposition.ABSTAIN, "agreement_not_authorized")
        stages.append(StageReceipt("policy", "selected", {"gate": "agreement", "agreement_is_truth": False}))
        disposition = Disposition.ACCEPT if first.verdict == Verdict.SUPPORT else Disposition.CONTRADICTION
        return finish(disposition, "agreement_gate")

    def run_dossier(
        self, dossier: ImportDossier, hypotheses: Mapping[str, str], *, attempt: int = 1
    ) -> tuple[OrchestrationReceipt, ...]:
        """Compila sin inventar hipótesis; faltantes se abstienen explícitamente."""
        return tuple(
            self.run(claim, hypotheses.get(claim.claim_id, ""), attempt=attempt)
            for claim in compile_dossier_to_atomic_claims(dossier)
        )


def summarize_runs(receipts: Iterable[OrchestrationReceipt]) -> dict[str, float | int]:
    """Cobertura y costo operativo; nunca precisión o calidad semántica."""
    unique_attempts = {receipt.run_id: receipt for receipt in receipts}
    attempts = tuple(unique_attempts.values())
    latest: dict[str, OrchestrationReceipt] = {}
    for receipt in attempts:
        prior = latest.get(receipt.request_id)
        if prior is None or receipt.attempt > prior.attempt:
            latest[receipt.request_id] = receipt
    resolved = sum(item.disposition != Disposition.ABSTAIN for item in latest.values())
    return {
        "runs": len(attempts),
        "requests": len(latest),
        "resolved": resolved,
        "abstained": len(latest) - resolved,
        "coverage": resolved / len(latest) if latest else 0.0,
        "latency_ms_total": sum(item.telemetry["latency_ms"] for item in attempts),
        "model_calls": sum(item.telemetry["model_calls"] for item in attempts),
        "pair_count": sum(item.telemetry["pair_count"] for item in attempts),
    }
