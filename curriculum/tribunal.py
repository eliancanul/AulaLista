"""Tribunal NLI local en shadow mode (#126).

Flujo: AtomicClaim + RetrievalReceipt -> pares -> adaptador -> TribunalReceipt.
El recibo no escribe estados curriculares ni concede autoridad editorial.

FSM de una corrida (evento, guarda, transición):
  start, hay candidatos y adaptador, pending -> running
  no_candidates, ninguno, pending -> completed
  unavailable, falta adaptador o éste lo informa, pending/running -> model_unavailable
  returned, batch completo y válido, running -> completed
  deadline, excede el plazo, running -> timed_out
  raised/invalid_output, excepción o contrato roto, running -> error
Sólo completed tiene veredicto. Un batch fallido no conserva resultados parciales.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from curriculum.atlas.models import RetrievalReceipt
from curriculum.claims import AtomicClaim


MINILM_CANDIDATE = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
MDEBERTA_CANDIDATE = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"


class NLIClass(str, Enum):
    ENTAILMENT = "entailment"
    CONTRADICTION = "contradiction"
    NEUTRAL = "neutral"


class Verdict(str, Enum):
    SUPPORT = "support"
    CONTRADICTION = "contradiction"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    MODEL_UNAVAILABLE = "model_unavailable"
    ERROR = "error"


class ModelUnavailableError(Exception):
    """El adaptador local no puede cargar o ejecutar el checkpoint solicitado."""


class InferenceDeadlineExceeded(TimeoutError):
    """El tribunal dejó de esperar al adaptador tras el plazo configurado."""


@dataclass(frozen=True)
class NLIModelConfig:
    model_id: str
    version: str
    label_mapping: Mapping[str, NLIClass]
    timeout_seconds: float
    runtime_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.version.strip():
            raise ValueError("model_id y version son obligatorios")
        mapping = dict(self.label_mapping)
        if len(mapping) != 3 or any(not isinstance(value, NLIClass) for value in mapping.values()) or set(mapping.values()) != set(NLIClass) or any(
            not isinstance(label, str) or not label.strip() for label in mapping
        ):
            raise ValueError("label_mapping debe asociar tres labels distintos a entailment, contradiction y neutral")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo y finito")
        object.__setattr__(self, "label_mapping", MappingProxyType(mapping))
        object.__setattr__(self, "runtime_config", MappingProxyType(dict(self.runtime_config)))


@dataclass(frozen=True)
class NLIPair:
    claim_id: str
    receipt_id: str
    candidate_id: str
    fragment_id: str
    premise: str
    hypothesis: str


@dataclass(frozen=True)
class RawNLIOutput:
    """Logits sin softmax ni interpretación probabilística."""

    logits: Mapping[str, float]


class NLIAdapter(Protocol):
    def infer_batch(self, pairs: tuple[NLIPair, ...]) -> Sequence[RawNLIOutput]: ...


@dataclass(frozen=True)
class PairDecision:
    pair: NLIPair
    logits: dict[str, float]
    verdict: Verdict
    reason: str  # winning_label | neutral | tie


@dataclass(frozen=True)
class TribunalReceipt:
    run_id: str
    claim_id: str
    retrieval_receipt_id: str
    model_id: str
    model_version: str
    label_mapping: dict[str, str]
    runtime_config: dict[str, Any]
    timeout_seconds: float
    latency_ms: float
    status: RunStatus
    verdict: Verdict | None
    reason: str
    decisions: tuple[PairDecision, ...]
    transitions: tuple[RunStatus, ...]
    error_type: str | None = None
    shadow_mode: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa el recibo sin presentar logits como probabilidades."""
        return {
            "run_id": self.run_id,
            "claim_id": self.claim_id,
            "retrieval_receipt_id": self.retrieval_receipt_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "label_mapping": dict(self.label_mapping),
            "runtime_config": dict(self.runtime_config),
            "timeout_seconds": self.timeout_seconds,
            "latency_ms": self.latency_ms,
            "status": self.status.value,
            "verdict": self.verdict.value if self.verdict is not None else None,
            "reason": self.reason,
            "decisions": [
                {
                    "pair": asdict(decision.pair),
                    "logits": dict(decision.logits),
                    "score_kind": "raw_logits",
                    "verdict": decision.verdict.value,
                    "reason": decision.reason,
                }
                for decision in self.decisions
            ],
            "transitions": [status.value for status in self.transitions],
            "error_type": self.error_type,
            "shadow_mode": self.shadow_mode,
        }


_ALLOWED = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.MODEL_UNAVAILABLE},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.TIMED_OUT, RunStatus.MODEL_UNAVAILABLE, RunStatus.ERROR},
}


def _advance(history: list[RunStatus], next_status: RunStatus) -> None:
    if next_status not in _ALLOWED.get(history[-1], set()):
        raise RuntimeError(f"Transición NLI inválida: {history[-1]} -> {next_status}")
    history.append(next_status)


def _interpret(pair: NLIPair, output: RawNLIOutput, mapping: Mapping[str, NLIClass]) -> PairDecision:
    if not isinstance(output, RawNLIOutput) or set(output.logits) != set(mapping):
        raise ValueError("Labels de logits incompatibles con el checkpoint configurado")
    logits = dict(output.logits)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in logits.values()):
        raise ValueError("Los logits deben ser números finitos")
    maximum = max(logits.values())
    winners = [mapping[label] for label, value in logits.items() if value == maximum]
    if len(winners) != 1:
        return PairDecision(pair, logits, Verdict.INSUFFICIENT_EVIDENCE, "tie")
    winner = winners[0]
    if winner == NLIClass.NEUTRAL:
        return PairDecision(pair, logits, Verdict.INSUFFICIENT_EVIDENCE, "neutral")
    verdict = Verdict.SUPPORT if winner == NLIClass.ENTAILMENT else Verdict.CONTRADICTION
    return PairDecision(pair, logits, verdict, "winning_label")


def _combine(decisions: tuple[PairDecision, ...]) -> tuple[Verdict, str]:
    """Conserva desacuerdos; ningún score de Atlas decide el veredicto."""
    verdicts = {decision.verdict for decision in decisions}
    if Verdict.SUPPORT in verdicts and Verdict.CONTRADICTION in verdicts:
        return Verdict.INSUFFICIENT_EVIDENCE, "disagreement"
    if Verdict.CONTRADICTION in verdicts:
        return Verdict.CONTRADICTION, "contradicting_candidate"
    if Verdict.SUPPORT in verdicts:
        return Verdict.SUPPORT, "supporting_candidate"
    return Verdict.INSUFFICIENT_EVIDENCE, "neutral_or_tie"


def _infer_with_deadline(
    adapter: NLIAdapter, pairs: tuple[NLIPair, ...], timeout_seconds: float
) -> Sequence[RawNLIOutput]:
    result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((True, adapter.infer_batch(pairs)))
        except Exception as exc:
            result_queue.put((False, exc))

    # El hilo es daemon: el plazo limita la espera del tribunal, NO cancela la
    # inferencia bloqueante. Un runtime real deberá proporcionar cancelación propia.
    threading.Thread(target=worker, daemon=True).start()
    try:
        ok, value = result_queue.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        raise InferenceDeadlineExceeded("Se agotó el plazo de espera NLI") from exc
    if not ok:
        raise value  # type: ignore[misc]
    return value  # type: ignore[return-value]


class Tribunal:
    """Orquesta una corrida local sin mutar AtomicClaim ni RetrievalReceipt."""

    def __init__(self, config: NLIModelConfig, adapter: NLIAdapter | None = None) -> None:
        adapter_labels = getattr(adapter, "label_mapping", None)
        if adapter_labels is not None and dict(adapter_labels) != dict(config.label_mapping):
            raise ValueError("El mapeo de labels del adaptador no coincide con la configuración NLI")
        self.config = config
        self.adapter = adapter

    def evaluate(
        self,
        claim: AtomicClaim,
        retrieval: RetrievalReceipt,
        hypothesis: str | None = None,
    ) -> TribunalReceipt:
        if retrieval.claim_id != claim.claim_id:
            raise ValueError("El recibo de Atlas no corresponde a la afirmación")
        if hypothesis is None:
            hypothesis = build_claim_hypothesis(claim)
        if not isinstance(hypothesis, str) or not hypothesis.strip():
            raise ValueError("La hipótesis explícita es obligatoria")

        start = time.perf_counter()
        history = [RunStatus.PENDING]
        verdict: Verdict | None = None
        reason = ""
        error_type: str | None = None
        decisions: tuple[PairDecision, ...] = ()

        if not retrieval.candidates:
            _advance(history, RunStatus.COMPLETED)
            verdict, reason = Verdict.INSUFFICIENT_EVIDENCE, "no_candidates"
        elif self.adapter is None:
            _advance(history, RunStatus.MODEL_UNAVAILABLE)
            reason = "adapter_not_configured"
        else:
            pairs = tuple(
                NLIPair(
                    claim_id=claim.claim_id,
                    receipt_id=retrieval.receipt_id,
                    candidate_id=candidate.candidate_id,
                    fragment_id=candidate.fragment.fragment_id,
                    premise=candidate.fragment.text,
                    hypothesis=hypothesis,
                )
                for candidate in retrieval.candidates
            )
            _advance(history, RunStatus.RUNNING)
            try:
                outputs = _infer_with_deadline(self.adapter, pairs, self.config.timeout_seconds)
                if not isinstance(outputs, Sequence) or len(outputs) != len(pairs):
                    raise ValueError("El batch NLI debe devolver un resultado por candidato")
                decisions = tuple(
                    _interpret(pair, output, self.config.label_mapping)
                    for pair, output in zip(pairs, outputs)
                )
                verdict, reason = _combine(decisions)
                _advance(history, RunStatus.COMPLETED)
            except ModelUnavailableError:
                _advance(history, RunStatus.MODEL_UNAVAILABLE)
                reason = "model_unavailable"
            except InferenceDeadlineExceeded:
                _advance(history, RunStatus.TIMED_OUT)
                reason = "deadline_exceeded"
            except Exception as exc:
                _advance(history, RunStatus.ERROR)
                reason = "adapter_or_output_error"
                error_type = type(exc).__name__
            if history[-1] != RunStatus.COMPLETED:
                decisions = ()
                verdict = None

        status = history[-1]
        return TribunalReceipt(
            run_id=uuid4().hex,
            claim_id=claim.claim_id,
            retrieval_receipt_id=retrieval.receipt_id,
            model_id=self.config.model_id,
            model_version=self.config.version,
            label_mapping={label: meaning.value for label, meaning in self.config.label_mapping.items()},
            runtime_config=dict(self.config.runtime_config),
            timeout_seconds=self.config.timeout_seconds,
            latency_ms=(time.perf_counter() - start) * 1000,
            status=status,
            verdict=verdict,
            reason=reason,
            decisions=decisions,
            transitions=tuple(history),
            error_type=error_type,
        )


def build_claim_hypothesis(claim: AtomicClaim) -> str:
    """Construye una hipótesis NLI tipada y explícita para una afirmación atómica (#126).

    Invariantes arquitectónicas:
    - La hipótesis hace explícita la afirmación a contrastar con evidencia documental,
      sin presuponer veredicto semántico ni sustituir la autoridad docente.
    - Separa estrictamente la presencia/identidad literal de una actividad (lo que el documento
      propone textualmente) de la hipótesis de asignación a un rol, fase o momento pedagógico
      (que permanece como inferencia sujeta a revisión docente).
    """
    pred = claim.predicate
    val = str(claim.object_value).strip()

    if pred == "objetivo":
        return f"El documento plantea como objetivo o finalidad: {val}."
    elif pred in ("duracion_proyecto", "temporalidad"):
        return f"El proyecto sugiere una duración global de: {val}."
    elif pred in ("primera_actividad", "actividad_inicial"):
        return f"El documento propone como primera actividad: {val}."
    elif pred in ("actividad", "texto_actividad", "descripcion_actividad"):
        return f"El documento propone la actividad: {val}."
    elif pred in ("inicio", "desarrollo", "cierre"):
        return f"La asignación de la actividad al momento de {pred} es una propuesta pedagógica sujeta a revisión docente: {val}."
    elif pred in ("rol_pedagogico", "rol", "fase", "fase_actividad", "momento"):
        return f"La asignación de la actividad a la fase o rol pedagógico '{val}' es una inferencia sujeta a revisión docente."
    elif pred == "pertenece_a_unidad_revision":
        return f"La relación de la actividad con la unidad de revisión {val} es una propuesta pedagógica sujeta a validación docente."
    elif pred == "pertenece_a_sesion":
        return f"La actividad pertenece a la sesión {val}."
    elif pred == "campo_formativo":
        return f"El campo formativo del proyecto es {val}."
    elif pred == "metodologia":
        return f"La metodología del proyecto es {val}."
    elif pred == "proyecto":
        return f"El proyecto se titula {val}."
    elif pred == "escenario":
        return f"El escenario del proyecto es {val}."
    else:
        return f"El valor correspondiente a {pred} es {val}."
