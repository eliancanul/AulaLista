import hashlib

from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError
from django.db import transaction
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from curriculum.models import (
    ClassroomSession,
    DeviceAssignment,
    PublishedPackageSnapshot,
    StudentTurn,
)
from curriculum.practice import (
    PracticeContractError,
    evaluate_response,
    issue_capability,
    request_assistance,
    verify_capability,
)

# Ephemeral anti-replay/progression guard only; never score/evidence. Expires in 3600s.
HINT_PROGRESS_TTL = 3600
HINT_PROGRESS_KEY_PREFIX = "aulalista.practice.hint-progress"
TURN_CAPABILITY_COOKIE = "aulalista.student-turn"
TURN_CAPABILITY_SALT = "aulalista.student-turn.capability.v1"
LOCAL_SESSION_TTL = 12 * 60 * 60
TURN_CAPABILITY_MAX_AGE = LOCAL_SESSION_TTL


def student_packages(request):
    return render(request, "curriculum/student_packages.html", {"packages": []})


def _turn_capability(turn):
    return signing.dumps(
        {
            "session_id": turn.assignment.session_id,
            "assignment_id": turn.assignment_id,
            "local_identifier": str(turn.assignment.local_identifier),
            "turn_id": str(turn.pk),
        },
        salt=TURN_CAPABILITY_SALT,
        compress=True,
    )


def _read_turn_capability(request):
    token = request.COOKIES.get(TURN_CAPABILITY_COOKIE)
    if not token:
        return None
    try:
        payload = signing.loads(
            token,
            salt=TURN_CAPABILITY_SALT,
            max_age=TURN_CAPABILITY_MAX_AGE,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _set_turn_cookie(response, turn):
    response.set_cookie(
        TURN_CAPABILITY_COOKIE,
        _turn_capability(turn),
        max_age=TURN_CAPABILITY_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )


def _clear_turn_cookie(response):
    response.delete_cookie(TURN_CAPABILITY_COOKIE, samesite="Lax")


@transaction.atomic
def _assignment_for_turn_capability(request, session_id):
    payload = _read_turn_capability(request)
    if not payload:
        return None, None
    if payload.get("session_id") != session_id:
        return None, payload
    try:
        session = ClassroomSession.objects.select_for_update().get(pk=session_id)
        if session.status != ClassroomSession.STATUS_ACTIVE:
            return None, payload
        assignment = DeviceAssignment.objects.select_for_update().get(
            pk=payload.get("assignment_id"),
            session_id=session_id,
            local_identifier=payload.get("local_identifier"),
        )
        turn = StudentTurn.objects.select_for_update().select_related(
            "assignment", "assignment__session", "assignment__session__snapshot"
        ).get(
            pk=payload.get("turn_id"),
            assignment=assignment,
            status=StudentTurn.STATUS_ACTIVE,
        )
    except (
        ClassroomSession.DoesNotExist,
        DeviceAssignment.DoesNotExist,
        StudentTurn.DoesNotExist,
        ValueError,
        TypeError,
    ):
        return None, payload
    return turn, payload


@never_cache
@transaction.atomic
@require_http_methods(["GET", "POST"])
def student_turn_start(request, session_id, local_identifier):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update(),
        pk=session_id,
    )
    assignment = get_object_or_404(
        DeviceAssignment.objects.select_for_update(),
        session=session,
        local_identifier=local_identifier,
    )
    if assignment.session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La sesión no está disponible para iniciar un turno."
        )

    capability = _read_turn_capability(request)
    if capability and (
        capability.get("session_id") != session_id
        or capability.get("assignment_id") != assignment.pk
        or capability.get("local_identifier") != str(assignment.local_identifier)
    ):
        return HttpResponseForbidden("La capacidad no corresponde a este dispositivo.")

    context = {"session": assignment.session, "assignment": assignment}
    active_turn = StudentTurn.objects.filter(
        assignment=assignment,
        status=StudentTurn.STATUS_ACTIVE,
    ).first()
    if active_turn:
        if capability and capability.get("turn_id") == str(active_turn.pk):
            return redirect("student-activity", session_id=session_id)
        if request.method == "GET":
            context["recovery_available"] = True
            return render(
                request,
                "curriculum/student_turn_start.html",
                context,
                status=409,
            )
        return HttpResponse(
            "Este dispositivo ya tiene un turno activo; continúa con su capacidad.",
            status=409,
        )

    if request.method == "POST":
        try:
            turn = assignment.reserve_turn(request.POST.get("display_name"))
        except ValidationError as error:
            context["error"] = str(error)
            return render(
                request,
                "curriculum/student_turn_start.html",
                context,
                status=400,
            )
        except IntegrityError:
            if StudentTurn.objects.filter(
                assignment=assignment,
                status=StudentTurn.STATUS_ACTIVE,
            ).exists():
                return HttpResponse(
                    "Este dispositivo ya tiene un turno activo; continúa con su capacidad.",
                    status=409,
                )
            context["error"] = "La capacidad restante de este dispositivo se agotó."
            return render(
                request,
                "curriculum/student_turn_start.html",
                context,
                status=400,
            )
        response = redirect("student-activity", session_id=session_id)
        _set_turn_cookie(response, turn)
        return response
    return render(request, "curriculum/student_turn_start.html", context)


@never_cache
@transaction.atomic
@require_POST
def student_turn_recover(request, session_id, local_identifier):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update(),
        pk=session_id,
    )
    assignment = get_object_or_404(
        DeviceAssignment.objects.select_for_update(),
        session=session,
        local_identifier=local_identifier,
    )
    if assignment.session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La sesión no está disponible para recuperar un turno."
        )

    capability = _read_turn_capability(request)
    if capability and (
        capability.get("session_id") != session_id
        or capability.get("assignment_id") != assignment.pk
        or capability.get("local_identifier") != str(assignment.local_identifier)
    ):
        return HttpResponseForbidden("La capacidad no corresponde a este dispositivo.")

    turn = StudentTurn.objects.select_for_update().filter(
        assignment=assignment,
        status=StudentTurn.STATUS_ACTIVE,
    ).first()
    if turn is None:
        return HttpResponse("No hay un turno activo para recuperar.", status=409)
    response = redirect("student-activity", session_id=session_id)
    _set_turn_cookie(response, turn)
    return response


@never_cache
@transaction.atomic
@require_POST
def student_turn_ready(request, session_id):
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is not None:
        question_count = len(turn.assignment.session.snapshot.payload.get("questions", []) or [])
        completed = turn.finish()
        clear_practice_cache(completed.pk, range(question_count))
        response = redirect(
            "student-turn-start",
            session_id=session_id,
            local_identifier=completed.assignment.local_identifier,
        )
        _clear_turn_cookie(response)
        return response

    response = redirect("student-packages")
    _clear_turn_cookie(response)
    return response


@require_http_methods(["GET", "POST"])
def tutor_session_prepare(request, snapshot_id):
    snapshot = get_object_or_404(PublishedPackageSnapshot, pk=snapshot_id)
    context = {"snapshot": snapshot}
    if request.method == "POST":
        try:
            session = ClassroomSession.prepare_from_snapshot(
                snapshot,
                request.POST.get("student_count"),
                request.POST.get("device_count"),
            )
        except ValidationError as error:
            # This local-only form has no teacher account yet; show the contract
            # error without inventing an authentication or identity layer.
            context["error"] = str(error)
            return render(
                request,
                "curriculum/tutor_session_prepare.html",
                context,
                status=400,
            )
        return redirect("tutor-session-review", session_id=session.pk)
    return render(request, "curriculum/tutor_session_prepare.html", context)


def tutor_session_review(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot").prefetch_related(
            "device_assignments"
        ),
        pk=session_id,
    )
    return render(
        request,
        "curriculum/tutor_session_review.html",
        {"session": session, "assignments": session.device_assignments.all()},
    )


@require_POST
def tutor_session_confirm(request, session_id):
    session = get_object_or_404(ClassroomSession, pk=session_id)
    try:
        session.confirm()
    except ValidationError as error:
        return render(
            request,
            "curriculum/tutor_session_review.html",
            {
                "session": session,
                "assignments": session.device_assignments.all(),
                "error": str(error),
            },
            status=400,
        )
    return redirect("tutor-session-review", session_id=session.pk)


def _unconfirmed_session_response(session):
    if session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La actividad sólo está disponible para una sesión activa."
        )
    return None


@never_cache
@transaction.atomic
def student_activity(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is None:
        return HttpResponseForbidden(
            "La actividad requiere el turno activo y la capacidad de este dispositivo."
        )
    return render(
        request,
        "curriculum/student_activity.html",
        _activity_context(session, turn=turn),
    )


def _activity_context(session, **extra):
    turn = extra.get("turn")
    context = {
        "session": session,
        "snapshot_payload": session.snapshot.payload,
        "turn": turn,
        "activity_questions": _activity_questions(session, turn),
    }
    context.update(extra)
    return context


def _activity_questions(session, turn):
    questions = session.snapshot.payload.get("questions", []) or []
    activity_questions = []
    turn_id = turn.pk if turn is not None else session.pk
    for question_index, question in enumerate(questions):
        value = question.get("value", {}) if isinstance(question, dict) else {}
        hint_state = _current_hint_state(
            turn_id,
            question_index,
            session_id=session.pk,
        )
        next_hint_index = hint_state["next_hint_index"]
        hints = list(value.get("hints", []) or [])
        activity_questions.append(
            {
                "index": question_index,
                "value": value,
                "hint_index": next_hint_index,
                "hint_capability": (
                    hint_state["capability"]
                    if next_hint_index < len(hints)
                    else None
                ),
            }
        )
    return activity_questions


def _hint_progress_key(turn_id, question_index):
    return f"{HINT_PROGRESS_KEY_PREFIX}:{turn_id}:{question_index}"


def _consumed_hint_key(turn_id, question_index, capability):
    digest = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed:{turn_id}:{question_index}:{digest}"


def _consumed_hint_index_key(turn_id, question_index):
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn_id}:{question_index}"


def clear_practice_cache(turn_id, question_indices):
    """Explicitly remove ephemeral T05 state for one completed turn."""

    for question_index in question_indices:
        progress_key = _hint_progress_key(turn_id, question_index)
        consumed_index_key = _consumed_hint_index_key(turn_id, question_index)
        consumed_keys = cache.get(consumed_index_key, []) or []
        cache.delete_many([progress_key, consumed_index_key, *consumed_keys])


def _current_hint_state(turn_id, question_index, *, session_id=None):
    """Read the ephemeral anti-replay/progression state, never learning evidence."""

    key = _hint_progress_key(turn_id, question_index)
    state = cache.get(key)
    if isinstance(state, dict) and {"next_hint_index", "capability"} <= state.keys():
        return state

    candidate = {
        "next_hint_index": 0,
        "capability": issue_capability(
            "hint",
            session_id=session_id if session_id is not None else turn_id,
            question_index=question_index,
            turn_id=turn_id,
            next_hint_index=0,
        ),
    }
    if cache.add(key, candidate, timeout=HINT_PROGRESS_TTL):
        return candidate
    return cache.get(key)


def _consume_hint_capability(
    turn_id,
    question_index,
    hint_index,
    capability,
    *,
    session_id=None,
):
    """Atomically consume one nonce, then advance temporal hint authorization."""

    state = _current_hint_state(
        turn_id,
        question_index,
        session_id=session_id,
    )
    if (
        state["next_hint_index"] != hint_index
        or state["capability"] != capability
    ):
        return False
    if not cache.add(
        _consumed_hint_key(turn_id, question_index, capability),
        True,
        timeout=HINT_PROGRESS_TTL,
    ):
        return False
    consumed_key = _consumed_hint_key(turn_id, question_index, capability)
    consumed_index_key = _consumed_hint_index_key(turn_id, question_index)
    consumed_keys = cache.get(consumed_index_key, []) or []
    cache.set(consumed_index_key, [*consumed_keys, consumed_key], timeout=HINT_PROGRESS_TTL)
    cache.set(
        _hint_progress_key(turn_id, question_index),
        {
            "next_hint_index": hint_index + 1,
            "capability": issue_capability(
                "hint",
                session_id=session_id if session_id is not None else turn_id,
                question_index=question_index,
                turn_id=turn_id,
                next_hint_index=hint_index + 1,
            ),
        },
        timeout=HINT_PROGRESS_TTL,
    )
    return True


@never_cache
@transaction.atomic
@require_POST
def student_question_answer(request, session_id, question_index):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is None:
        return HttpResponseForbidden(
            "La respuesta requiere el turno activo y la capacidad de este dispositivo."
        )
    try:
        result = evaluate_response(
            session.snapshot.payload,
            question_index,
            request.POST.get("option_position"),
        )
    except PracticeContractError as error:
        return HttpResponseBadRequest(str(error))

    return render(
        request,
        "curriculum/student_activity.html",
        _activity_context(
            session,
            turn=turn,
            practice_result=result,
            answered_question_index=question_index,
            explanation_capability=issue_capability(
                "explanation",
                session_id=session_id,
                question_index=question_index,
                turn_id=turn.pk,
            ),
        ),
    )


@never_cache
@transaction.atomic
@require_POST
def student_question_assistance(request, session_id, question_index):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is None:
        return HttpResponseForbidden(
            "La ayuda requiere el turno activo y la capacidad de este dispositivo."
        )
    kind = request.POST.get("kind", "hint")
    hint_index = None
    if kind == "hint":
        try:
            hint_index = int(request.POST.get("hint_index"))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("La pista requiere una capacidad válida.")
        if (
            verify_capability(
                request.POST.get("hint_capability"),
                kind="hint",
                session_id=session_id,
                question_index=question_index,
                turn_id=turn.pk,
                next_hint_index=hint_index,
            )
            is None
        ):
            return HttpResponseBadRequest("La pista requiere una capacidad válida y secuencial.")
    elif kind == "explanation":
        if (
            verify_capability(
                request.POST.get("explanation_capability"),
                kind="explanation",
                session_id=session_id,
                question_index=question_index,
                turn_id=turn.pk,
            )
            is None
        ):
            return HttpResponseBadRequest(
                "La explicación final requiere una capacidad emitida después de responder."
            )

    try:
        assistance = request_assistance(
            session.snapshot.payload,
            question_index,
            kind=kind,
            hint_index=hint_index if hint_index is not None else 0,
        )
    except PracticeContractError as error:
        return HttpResponseBadRequest(str(error))

    if kind == "hint" and not _consume_hint_capability(
        turn.pk,
        question_index,
        hint_index,
        request.POST.get("hint_capability"),
        session_id=session_id,
    ):
        return HttpResponseBadRequest("La capacidad de pista ya fue consumida o quedó fuera de orden.")

    next_hint_capability = None
    if assistance.next_hint_index is not None:
        next_hint_capability = _current_hint_state(
            turn.pk,
            question_index,
            session_id=session_id,
        )["capability"]

    return render(
        request,
        "curriculum/student_activity.html",
        _activity_context(
            session,
            turn=turn,
            assistance=assistance,
            assistance_question_index=question_index,
            next_hint_capability=next_hint_capability,
        ),
    )
