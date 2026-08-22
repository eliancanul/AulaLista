import hashlib

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from curriculum.models import ClassroomSession, PublishedPackageSnapshot
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


def student_packages(request):
    return render(request, "curriculum/student_packages.html", {"packages": []})


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
    if session.status == ClassroomSession.STATUS_PREPARED:
        return HttpResponseForbidden(
            "La sesión requiere confirmación explícita antes de iniciar la actividad."
        )
    return None


def student_activity(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    return render(
        request,
        "curriculum/student_activity.html",
        _activity_context(session),
    )


def _activity_context(session, **extra):
    context = {
        "session": session,
        "snapshot_payload": session.snapshot.payload,
        "activity_questions": _activity_questions(session),
    }
    context.update(extra)
    return context


def _activity_questions(session):
    questions = session.snapshot.payload.get("questions", []) or []
    activity_questions = []
    for question_index, question in enumerate(questions):
        value = question.get("value", {}) if isinstance(question, dict) else {}
        hint_state = _current_hint_state(session.pk, question_index)
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


def _hint_progress_key(session_id, question_index):
    return f"{HINT_PROGRESS_KEY_PREFIX}:{session_id}:{question_index}"


def _consumed_hint_key(session_id, question_index, capability):
    digest = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed:{session_id}:{question_index}:{digest}"


def _current_hint_state(session_id, question_index):
    """Read the ephemeral anti-replay/progression state, never learning evidence."""

    key = _hint_progress_key(session_id, question_index)
    state = cache.get(key)
    if isinstance(state, dict) and {"next_hint_index", "capability"} <= state.keys():
        return state

    candidate = {
        "next_hint_index": 0,
        "capability": issue_capability(
            "hint",
            session_id=session_id,
            question_index=question_index,
            next_hint_index=0,
        ),
    }
    if cache.add(key, candidate, timeout=HINT_PROGRESS_TTL):
        return candidate
    return cache.get(key)


def _consume_hint_capability(session_id, question_index, hint_index, capability):
    """Atomically consume one nonce, then advance temporal hint authorization."""

    state = _current_hint_state(session_id, question_index)
    if (
        state["next_hint_index"] != hint_index
        or state["capability"] != capability
    ):
        return False
    if not cache.add(
        _consumed_hint_key(session_id, question_index, capability),
        True,
        timeout=HINT_PROGRESS_TTL,
    ):
        return False
    cache.set(
        _hint_progress_key(session_id, question_index),
        {
            "next_hint_index": hint_index + 1,
            "capability": issue_capability(
                "hint",
                session_id=session_id,
                question_index=question_index,
                next_hint_index=hint_index + 1,
            ),
        },
        timeout=HINT_PROGRESS_TTL,
    )
    return True


@require_POST
def student_question_answer(request, session_id, question_index):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
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
            practice_result=result,
            answered_question_index=question_index,
            explanation_capability=issue_capability(
                "explanation",
                session_id=session_id,
                question_index=question_index,
            ),
        ),
    )


@require_POST
def student_question_assistance(request, session_id, question_index):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot"),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
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
        session_id,
        question_index,
        hint_index,
        request.POST.get("hint_capability"),
    ):
        return HttpResponseBadRequest("La capacidad de pista ya fue consumida o quedó fuera de orden.")

    next_hint_capability = None
    if assistance.next_hint_index is not None:
        next_hint_capability = _current_hint_state(
            session_id,
            question_index,
        )["capability"]

    return render(
        request,
        "curriculum/student_activity.html",
        _activity_context(
            session,
            assistance=assistance,
            assistance_question_index=question_index,
            next_hint_capability=next_hint_capability,
        ),
    )
