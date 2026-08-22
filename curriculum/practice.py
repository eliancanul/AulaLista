from dataclasses import dataclass

from django.core import signing
from django.core.signing import BadSignature, SignatureExpired


PRACTICE_CAPABILITY_SALT = "aulalista.practice.capability.v1"
PRACTICE_CAPABILITY_MAX_AGE = 3600


class PracticeContractError(ValueError):
    """The published snapshot cannot answer the requested practice action."""


@dataclass(frozen=True)
class DeterministicPracticeResult:
    question_index: int
    selected_position: int
    is_correct: bool
    score: int
    feedback: str


@dataclass(frozen=True)
class RegulatedAssistance:
    kind: str
    text: str
    hint_index: int | None = None
    next_hint_index: int | None = None
    score_impact: int = 0


def issue_capability(
    kind,
    *,
    session_id,
    question_index,
    turn_id=None,
    next_hint_index=None,
):
    if kind not in {"explanation", "hint"}:
        raise ValueError("La capacidad de práctica no tiene un tipo autorizado.")

    payload = {
        "kind": kind,
        "session_id": str(session_id),
        "question_index": int(question_index),
    }
    if turn_id is not None:
        payload["turn_id"] = str(turn_id)
    if kind == "hint":
        if next_hint_index is None:
            raise ValueError("Una capacidad de pista requiere su siguiente índice.")
        payload["next_hint_index"] = int(next_hint_index)
    return signing.dumps(
        payload,
        salt=PRACTICE_CAPABILITY_SALT,
        compress=True,
    )


def verify_capability(
    token,
    *,
    kind,
    session_id,
    question_index,
    turn_id=None,
    next_hint_index=None,
):
    if not token:
        return None
    try:
        payload = signing.loads(
            token,
            salt=PRACTICE_CAPABILITY_SALT,
            max_age=PRACTICE_CAPABILITY_MAX_AGE,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    if (
        payload.get("kind") != kind
        or payload.get("session_id") != str(session_id)
        or payload.get("question_index") != int(question_index)
    ):
        return None
    if turn_id is not None and payload.get("turn_id") != str(turn_id):
        return None
    if kind == "hint" and payload.get("next_hint_index") != int(next_hint_index):
        return None
    return payload


def evaluate_response(snapshot_payload, question_index, selected_position):
    question = _question_from(snapshot_payload, question_index)
    try:
        selected_position = int(selected_position)
    except (TypeError, ValueError) as error:
        raise PracticeContractError("La respuesta debe elegir una opción ordenada.") from error

    selected_option = next(
        (
            option
            for option in _options_from(question)
            if option.get("position") == selected_position
        ),
        None,
    )
    if selected_option is None:
        raise PracticeContractError("La respuesta debe elegir una opción disponible.")

    is_correct = selected_option.get("expected") is True
    return DeterministicPracticeResult(
        question_index=question_index,
        selected_position=selected_position,
        is_correct=is_correct,
        score=int(is_correct),
        feedback=str(selected_option.get("feedback", "")),
    )


def request_assistance(
    snapshot_payload,
    question_index,
    *,
    kind,
    hint_index=0,
):
    question = _question_from(snapshot_payload, question_index)

    if kind == "hint":
        hints = list(question.get("hints", []) or [])
        try:
            hint_index = int(hint_index)
        except (TypeError, ValueError) as error:
            raise PracticeContractError("La pista debe solicitarse en orden.") from error
        if hint_index < 0 or hint_index >= len(hints):
            raise PracticeContractError("No hay una pista autorizada en ese orden.")
        next_hint_index = hint_index + 1 if hint_index + 1 < len(hints) else None
        return RegulatedAssistance(
            kind="hint",
            text=str(hints[hint_index]),
            hint_index=hint_index,
            next_hint_index=next_hint_index,
        )

    if kind == "explanation":
        return RegulatedAssistance(
            kind="explanation",
            text=str(snapshot_payload.get("final_explanation", "")),
        )

    raise PracticeContractError("El tipo de ayuda no está autorizado.")


def _question_from(snapshot_payload, question_index):
    try:
        question = snapshot_payload["questions"][question_index]
    except (KeyError, IndexError, TypeError) as error:
        raise PracticeContractError("El reactivo solicitado no existe en el snapshot.") from error

    if isinstance(question, dict) and "value" in question:
        question = question["value"]
    if not isinstance(question, dict):
        raise PracticeContractError("El reactivo publicado no tiene una estructura válida.")
    return question


def _options_from(question):
    options = list(question.get("options", []) or [])
    if not options:
        raise PracticeContractError("El reactivo publicado no tiene opciones.")
    return options
