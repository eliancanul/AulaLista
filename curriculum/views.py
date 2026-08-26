import csv
import hashlib
import io
import json
import threading
import uuid
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError
from django.db import transaction

from django.utils import timezone
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from health.qr import qr_svg

from curriculum.ephemeral import (
    clear_practice_cache,
    ensure_ephemeral_turn_summary,
    record_ephemeral_help,
    record_ephemeral_response,
    read_ephemeral_session_summary,
    update_ephemeral_turn_summary,
)
from curriculum.models import (
    ClassroomSession,
    CurriculumImportJob,
    CurriculumPackage,
    CurriculumProgress,
    DeviceAssignment,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
    PseudonymousSurveyResponse,
    StudentRoadmapProgress,
    StudentTurn,
)
from curriculum.practice import (
    PracticeContractError,
    evaluate_response,
    issue_capability,
    request_assistance,
    verify_capability,
)
from curriculum.survey import (
    STUDENT_SURVEY_QUESTIONS,
    SurveyContractError,
    survey_aggregate,
    validate_survey_answers,
)

# Ephemeral anti-replay/progression guard only; never score/evidence. Expires in 3600s.
HINT_PROGRESS_TTL = 3600
HINT_PROGRESS_KEY_PREFIX = "aulalista.practice.hint-progress"
SURVEY_SUBMITTED_KEY_PREFIX = "aulalista.survey.submitted"
TURN_CAPABILITY_COOKIE = "aulalista.student-turn"
TURN_CAPABILITY_SALT = "aulalista.student-turn.capability.v1"
DEVICE_ASSIGNMENT_COOKIE = "aulalista.device-assignment"
DEVICE_ASSIGNMENT_SALT = "aulalista.device-assignment.capability.v1"
LOCAL_SESSION_TTL = 12 * 60 * 60
TURN_CAPABILITY_MAX_AGE = LOCAL_SESSION_TTL
DEVICE_ASSIGNMENT_MAX_AGE = LOCAL_SESSION_TTL
SURVEY_SUBMITTED_TTL = LOCAL_SESSION_TTL


def _safe_teacher_next(request):
    """Return only a local path for Wagtail's login ``next`` parameter.

    The protected request is normally already a relative path, but explicitly
    validating it keeps this boundary safe if a deployment or middleware ever
    supplies an unusual request path. Wagtail remains responsible for the
    actual login and its final redirect validation.
    """

    next_url = request.get_full_path()
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts=set(),
        require_https=request.is_secure(),
    ):
        return next_url
    return "/"


def teacher_required(view_func):
    """Require Wagtail's existing staff account for teacher operations."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(_safe_teacher_next(request))
        if not request.user.is_staff:
            return HttpResponseForbidden(
                "La sección del maestro requiere una cuenta de personal."
            )
        if not request.user.is_active:
            return HttpResponseForbidden(
                "La sección del maestro requiere una cuenta de personal."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def student_packages(request):
    active_sessions = (
        ClassroomSession.objects.filter(status=ClassroomSession.STATUS_ACTIVE)
        .select_related("snapshot")
        .order_by("-started_at", "-id")
    )
    return render(
        request,
        "curriculum/student_packages.html",
        {"active_sessions": active_sessions},
    )


def _device_binding(assignment):
    return signing.dumps(
        {
            "session_id": assignment.session_id,
            "assignment_id": assignment.pk,
            "local_identifier": str(assignment.local_identifier),
        },
        salt=DEVICE_ASSIGNMENT_SALT,
        compress=True,
    )


def _read_device_binding(request):
    token = request.COOKIES.get(DEVICE_ASSIGNMENT_COOKIE)
    if not token:
        return None
    try:
        payload = signing.loads(
            token,
            salt=DEVICE_ASSIGNMENT_SALT,
            max_age=DEVICE_ASSIGNMENT_MAX_AGE,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _bound_assignment(request, session):
    """Return this browser's own assignment for the session, if it still exists."""

    payload = _read_device_binding(request)
    if not payload or payload.get("session_id") != session.pk:
        return None
    try:
        return DeviceAssignment.objects.get(
            pk=payload.get("assignment_id"),
            session=session,
            local_identifier=payload.get("local_identifier"),
        )
    except (DeviceAssignment.DoesNotExist, ValueError, TypeError):
        return None


def _set_device_cookie(response, assignment):
    response.set_cookie(
        DEVICE_ASSIGNMENT_COOKIE,
        _device_binding(assignment),
        max_age=DEVICE_ASSIGNMENT_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )


@never_cache
@transaction.atomic
@require_http_methods(["GET", "POST"])
def student_session_join(request, session_id):
    """Common entry point: one link or QR serves every device in the session."""

    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related("snapshot"),
        pk=session_id,
    )
    if session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La sesión no está disponible para incorporarse."
        )

    bound = _bound_assignment(request, session)
    if bound is not None:
        # This browser already owns one assignment; it never claims another.
        return redirect(
            "student-turn-start",
            session_id=session.pk,
            local_identifier=bound.local_identifier,
        )

    context = {"session": session}
    if request.method == "GET":
        return render(request, "curriculum/student_join.html", context)

    try:
        candidates = list(
            DeviceAssignment.objects.filter(
                session=session,
                remaining_capacity__gt=0,
                claimed_at__isnull=True,
            )
            .exclude(student_turns__status=StudentTurn.STATUS_ACTIVE)
            .order_by("id")
            .values_list("pk", flat=True)
        )
        assignment = (
            DeviceAssignment.objects.select_for_update()
            .filter(pk__in=candidates)
            .order_by("id")
            .first()
        )
    except IntegrityError:
        assignment = None
    if assignment is None:
        context["error"] = (
            "No hay dispositivos disponibles en este momento; espera a que se libere un turno."
        )
        return render(request, "curriculum/student_join.html", context, status=409)
    assignment.claimed_at = timezone.now()
    assignment.save(update_fields=["claimed_at"])

    response = redirect(
        "student-turn-start",
        session_id=session.pk,
        local_identifier=assignment.local_identifier,
    )
    _set_device_cookie(response, assignment)
    return response


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
    if session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La sesión no está disponible para iniciar un turno."
        )
    assignment = get_object_or_404(
        DeviceAssignment.objects.select_for_update(),
        session=session,
        local_identifier=local_identifier,
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
        ensure_ephemeral_turn_summary(session_id, turn)
        StudentRoadmapProgress.for_turn(turn)
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
    if session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La sesión no está disponible para recuperar un turno."
        )
    assignment = get_object_or_404(
        DeviceAssignment.objects.select_for_update(),
        session=session,
        local_identifier=local_identifier,
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
    StudentRoadmapProgress.for_turn(turn)
    response = redirect("student-activity", session_id=session_id)
    _set_turn_cookie(response, turn)
    return response


@never_cache
@transaction.atomic
@require_POST
def student_turn_ready(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update(),
        pk=session_id,
    )
    if session.status != ClassroomSession.STATUS_ACTIVE:
        response = HttpResponseForbidden(
            "La sesión no está disponible para cerrar un turno."
        )
        _clear_turn_cookie(response)
        return response
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is not None:
        question_count = len(turn.assignment.session.snapshot.payload.get("questions", []) or [])
        completed = turn.finish()
        update_ephemeral_turn_summary(
            session_id,
            completed,
            state="completed",
            completed_at=completed.completed_at.isoformat(),
        )
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


@teacher_required
@require_http_methods(["GET"])
def tutor_roadmaps(request):
    """Authenticated teacher surface for manual curriculum confirmation."""

    from curriculum.roadmap import ordered_nodes

    snapshots = list(PublishedRoadmapSnapshot.objects.all()[:20])
    cards = []
    for snapshot in snapshots:
        progress = {
            item.node_id: item
            for item in snapshot.curriculum_progress.select_related("confirmed_by")
        }
        cards.append(
            {
                "snapshot": snapshot,
                "nodes": [
                    {**node, "progress": progress.get(node["id"])}
                    for node in ordered_nodes(snapshot.payload)
                ],
                "progress_count": len(progress),
            }
        )
    return render(request, "curriculum/tutor_roadmaps.html", {"roadmap_cards": cards})


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_roadmap_progress(request, snapshot_id):
    """Record only an explicit teacher decision; students have no route here."""

    from curriculum.roadmap import ordered_nodes

    snapshot = get_object_or_404(PublishedRoadmapSnapshot, pk=snapshot_id)
    nodes = ordered_nodes(snapshot.payload)
    if request.method == "POST":
        node_id = str(request.POST.get("node_id", "")).strip()
        allowed = {node["id"] for node in nodes}
        if node_id not in allowed:
            return render(
                request,
                "curriculum/tutor_roadmap_progress.html",
                {"snapshot": snapshot, "nodes": nodes, "error": "Selecciona un tema publicado."},
                status=400,
            )
        try:
            CurriculumProgress.confirm(
                roadmap_snapshot=snapshot,
                node_id=node_id,
                status=request.POST.get("status", CurriculumProgress.STATUS_WORKED),
                teacher=request.user,
            )
        except ValidationError as error:
            return render(
                request,
                "curriculum/tutor_roadmap_progress.html",
                {"snapshot": snapshot, "nodes": nodes, "error": str(error)},
                status=400,
            )
        return redirect("tutor-roadmap-progress", snapshot_id=snapshot.pk)

    progress = {
        item.node_id: item
        for item in snapshot.curriculum_progress.select_related("confirmed_by")
    }
    return render(
        request,
        "curriculum/tutor_roadmap_progress.html",
        {
            "snapshot": snapshot,
            "nodes": [{**node, "progress": progress.get(node["id"])} for node in nodes],
        },
    )


@teacher_required
def tutor_sessions(request):
    """Operational teacher landing for the existing session workflow.

    Counts are derived at read time; the landing does not create or persist
    any additional classroom state.
    """
    sessions = (
        ClassroomSession.objects.select_related("snapshot", "snapshot__package")
        .order_by("-started_at", "-id")[:20]
    )
    session_cards = []
    for session in sessions:
        participant_count = (
            StudentTurn.objects.filter(
                assignment__session=session,
                status=StudentTurn.STATUS_ACTIVE,
            ).count()
            if session.status == ClassroomSession.STATUS_ACTIVE
            else 0
        )
        if session.status == ClassroomSession.STATUS_PREPARED:
            action_label = "Revisar y activar"
        elif session.status == ClassroomSession.STATUS_ACTIVE:
            action_label = (
                "Esperando participantes · abrir control autenticado"
                if participant_count == 0
                else "Actividad en progreso · abrir control autenticado"
            )
        elif session.status == ClassroomSession.STATUS_CLOSED:
            action_label = "Revisar resultados y exportar"
        else:
            action_label = "Revisar"
        title = session.snapshot.payload.get("title") or session.snapshot.package.title
        session_cards.append(
            {
                "session": session,
                "title": title,
                "state": session.get_status_display(),
                "participant_count": participant_count,
                "participant_label": (
                    "participante" if participant_count == 1 else "participantes"
                ),
                "action_label": action_label,
                "action_url": reverse(
                    (
                        "tutor-session-active"
                        if session.status == ClassroomSession.STATUS_ACTIVE
                        else "tutor-session-review"
                    ),
                    args=[session.pk],
                ),
                "review_url": reverse(
                    "tutor-session-review", args=[session.pk]
                ),
                "projection_url": reverse(
                    "session-projection", args=[session.pk]
                ),
            }
        )
    snapshots = (
        PublishedPackageSnapshot.objects.select_related("package")
        .order_by("-published_at", "-id")[:12]
    )
    return render(
        request,
        "curriculum/tutor_sessions.html",
        {"session_cards": session_cards, "snapshots": snapshots},
    )


@teacher_required

@require_http_methods(["GET", "POST"])
def tutor_session_prepare(request, snapshot_id):
    snapshot = get_object_or_404(PublishedPackageSnapshot, pk=snapshot_id)
    context = {
        "snapshot": snapshot,
        "roadmaps": PublishedRoadmapSnapshot.objects.all()[:20],
    }
    if request.method == "POST":
        try:
            roadmap_snapshot = None
            roadmap_id = request.POST.get("roadmap_snapshot_id")
            if roadmap_id:
                roadmap_snapshot = get_object_or_404(
                    PublishedRoadmapSnapshot,
                    pk=roadmap_id,
                )
            session = ClassroomSession.prepare_from_snapshot(
                snapshot,
                request.POST.get("student_count"),
                request.POST.get("device_count"),
                roadmap_snapshot=roadmap_snapshot,
            )
        except ValidationError as error:
            # Keep contract errors explicit; authentication is handled by the
            # Wagtail-backed teacher boundary above.
            context["error"] = str(error)
            return render(
                request,
                "curriculum/tutor_session_prepare.html",
                context,
                status=400,
            )
        return redirect("tutor-session-review", session_id=session.pk)
    return render(request, "curriculum/tutor_session_prepare.html", context)


@teacher_required

def tutor_session_review(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot").prefetch_related(
            "device_assignments"
        ),
        pk=session_id,
    )
    results = list(
        PseudonymousResult.objects.filter(
            result_batch_id=session.result_batch_id,
        )
    )
    survey_responses = _session_survey_responses(session)
    join_url = ""
    join_qr_svg = ""
    if session.status == ClassroomSession.STATUS_ACTIVE:
        join_url = request.build_absolute_uri(
            reverse("student-session-join", args=[session.pk])
        )
        join_qr_svg = qr_svg(join_url)
    labeled_assignments = [
        {
            "label": f"Dispositivo {position}",
            "assigned_capacity": assignment.assigned_capacity,
            "remaining_capacity": assignment.remaining_capacity,
        }
        for position, assignment in enumerate(session.device_assignments.all(), start=1)
    ]
    return render(
        request,
        "curriculum/tutor_session_review.html",
        {
            "session": session,
            "assignments": labeled_assignments,
            "snapshot_label": (
                f"versión {session.snapshot.version} · "
                f"{session.snapshot.sha256[:8]}"
            ),
            "result_aggregate": _result_aggregate(results),
            "survey_aggregate": survey_aggregate(survey_responses),
            "survey_response_count": survey_responses.count(),
            "join_url": join_url,
            "join_qr_svg": join_qr_svg,
        },
    )


@never_cache
@teacher_required
def tutor_session_active(request, session_id):
    """Authenticated operational view; aliases exist only in active state."""
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot"), pk=session_id
    )
    active_turns = StudentTurn.objects.none()
    if session.status == ClassroomSession.STATUS_ACTIVE:
        active_turns = StudentTurn.objects.filter(
            assignment__session_id=session.pk,
            status=StudentTurn.STATUS_ACTIVE,
        ).exclude(display_name="").order_by("started_at", "pk")
    join_url = ""
    join_qr_svg = ""
    if session.status == ClassroomSession.STATUS_ACTIVE:
        join_url = request.build_absolute_uri(
            reverse("student-session-join", args=[session.pk])
        )
        join_qr_svg = qr_svg(join_url)
    return render(
        request,
        "curriculum/tutor_session_active.html",
        {
            "session": session,
            "active_turns": active_turns,
            "participant_count": active_turns.count(),
            "join_url": join_url,
            "join_qr_svg": join_qr_svg,
            "snapshot_label": (
                f"versión {session.snapshot.version} · {session.snapshot.sha256[:8]}"
            ),
        },
    )


@never_cache
def tutor_session_projection(request, session_id):
    """Public projection: status, count, and active join material only."""
    # Intentionally public: this is a classroom projection, not a teacher action.
    session = get_object_or_404(ClassroomSession, pk=session_id)
    participant_count = 0
    join_url = ""
    join_qr_svg = ""
    if session.status == ClassroomSession.STATUS_ACTIVE:
        participant_count = StudentTurn.objects.filter(
            assignment__session_id=session.pk,
            status=StudentTurn.STATUS_ACTIVE,
        ).count()
        join_url = request.build_absolute_uri(
            reverse("student-session-join", args=[session.pk])
        )
        join_qr_svg = qr_svg(join_url)
    return render(
        request,
        "curriculum/tutor_session_projection.html",
        {
            "session": session,
            "participant_count": participant_count,
            "join_url": join_url,
            "join_qr_svg": join_qr_svg,
        },
    )


@teacher_required

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


@teacher_required

@require_POST
def tutor_session_close(request, session_id):
    session = get_object_or_404(ClassroomSession, pk=session_id)
    try:
        session.close()
    except ValidationError as error:
        return render(
            request,
            "curriculum/tutor_session_review.html",
            {
                "session": session,
                "assignments": session.device_assignments.all(),
                "result_aggregate": _result_aggregate(
                    PseudonymousResult.objects.filter(
                        result_batch_id=session.result_batch_id,
                    )
                ),
                "error": str(error),
            },
            status=400,
        )
    return redirect("tutor-session-review", session_id=session.pk)


def _result_aggregate(results):
    results = list(results)
    return {
        "count": len(results),
        "completed_count": sum(
            result.state == PseudonymousResult.STATE_COMPLETED for result in results
        ),
        "score_total": sum(result.score for result in results),
        "score_average": (
            sum(result.score for result in results) / len(results) if results else 0
        ),
        "help_count": sum(len(result.help_requests or []) for result in results),
        "technical_error_count": sum(
            len(result.technical_errors or []) for result in results
        ),
    }


def _session_survey_responses(session):
    return PseudonymousSurveyResponse.objects.filter(
        result_batch_id=session.result_batch_id,
    )


def _result_export_payload(result):
    return {
        "id": str(result.id),
        "snapshot_id": result.snapshot_id,
        "snapshot_version": result.snapshot_version,
        "snapshot_sha256": result.snapshot_sha256,
        "state": result.state,
        "duration_seconds": result.duration_seconds,
        "responses": result.responses,
        "score": result.score,
        "help_requests": result.help_requests,
        "technical_errors": result.technical_errors,
    }


@teacher_required

@require_POST
def tutor_session_export(request, session_id):
    session = get_object_or_404(ClassroomSession, pk=session_id)
    if session.status != ClassroomSession.STATUS_CLOSED:
        return HttpResponseBadRequest("Sólo se pueden exportar sesiones cerradas.")
    results = PseudonymousResult.objects.filter(
        result_batch_id=session.result_batch_id,
    )
    payload = [_result_export_payload(result) for result in results]
    export_format = request.POST.get("format", "json").lower()
    if export_format == "json":
        # JSON incluye también el resumen agregado de la encuesta seudonimizada.
        response = JsonResponse(
            {
                "results": payload,
                "survey": survey_aggregate(_session_survey_responses(session)),
            }
        )
        response["Content-Disposition"] = (
            f'attachment; filename="aulalista-session-{session.pk}.json"'
        )
        return response
    if export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "snapshot_id",
                "snapshot_version",
                "snapshot_sha256",
                "state",
                "duration_seconds",
                "responses",
                "score",
                "help_requests",
                "technical_errors",
            ],
        )
        writer.writeheader()
        for result in payload:
            writer.writerow(
                {
                    **result,
                    "responses": json.dumps(result["responses"], ensure_ascii=False),
                    "help_requests": json.dumps(
                        result["help_requests"], ensure_ascii=False
                    ),
                    "technical_errors": json.dumps(
                        result["technical_errors"], ensure_ascii=False
                    ),
                }
            )
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="aulalista-session-{session.pk}.csv"'
        )
        return response
    return HttpResponseBadRequest("El formato de exportación no está disponible.")


@teacher_required

@require_POST
def tutor_session_results_delete(request, session_id):
    session = get_object_or_404(ClassroomSession, pk=session_id)
    if session.status != ClassroomSession.STATUS_CLOSED:
        return HttpResponseBadRequest("Sólo se pueden eliminar resultados de una sesión cerrada.")
    result_ids = request.POST.getlist("result_id")
    queryset = PseudonymousResult.objects.filter(
        result_batch_id=session.result_batch_id,
    )
    deleted_surveys = 0
    if result_ids:
        # Sin llave resultado↔encuesta por diseño: borrar resultados
        # individuales conserva las respuestas de encuesta del lote.
        queryset = queryset.filter(id__in=result_ids)
    else:
        deleted_surveys, _ = PseudonymousSurveyResponse.objects.filter(
            result_batch_id=session.result_batch_id,
        ).delete()
    deleted, _ = queryset.delete()
    return JsonResponse({"deleted": deleted, "surveys_deleted": deleted_surveys})


@teacher_required

@require_POST
def tutor_result_delete(request, session_id, result_id):
    session = get_object_or_404(ClassroomSession, pk=session_id)
    if session.status != ClassroomSession.STATUS_CLOSED:
        return HttpResponseBadRequest("Sólo se pueden eliminar resultados de una sesión cerrada.")
    result = get_object_or_404(
        PseudonymousResult,
        pk=result_id,
        result_batch_id=session.result_batch_id,
    )
    result.delete()
    return JsonResponse({"deleted": 1})


@never_cache
@require_http_methods(["GET", "POST"])
def student_session_survey(request, session_id):
    """Pseudonymous end-of-activity survey gated by this device's assignment.

    Access uses the signed device-binding cookie, but nothing that identifies
    the turn or device is ever stored: the response row carries only the opaque
    batch and snapshot references plus the validated answers.
    """

    session = get_object_or_404(ClassroomSession, pk=session_id)
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    assignment = _bound_assignment(request, session)
    if assignment is None:
        return HttpResponseForbidden(
            "La encuesta requiere la capacidad del dispositivo asignado."
        )

    submitted_key = f"{SURVEY_SUBMITTED_KEY_PREFIX}:{assignment.pk}"
    already_submitted = cache.get(submitted_key) is True
    context = {
        "session": session,
        "survey_questions": STUDENT_SURVEY_QUESTIONS,
        "already_submitted": already_submitted,
    }
    if request.method == "GET":
        return render(request, "curriculum/student_survey.html", context)
    if already_submitted:
        return HttpResponseBadRequest(
            "Este dispositivo ya envió su encuesta para esta sesión."
        )

    try:
        answers = validate_survey_answers(request.POST)
    except SurveyContractError as error:
        context["error"] = str(error)
        return render(request, "curriculum/student_survey.html", context, status=400)

    PseudonymousSurveyResponse.objects.create(
        result_batch_id=session.result_batch_id,
        snapshot_id=session.snapshot_id,
        snapshot_version=session.snapshot.version,
        answers=answers,
    )
    cache.set(submitted_key, True, timeout=SURVEY_SUBMITTED_TTL)
    context["already_submitted"] = True
    return render(request, "curriculum/student_survey.html", context)


def _import_stage_runner():
    """Return the callable used to run a slow import stage.

    Stages run in a daemon thread so the teacher immediately gets a waiting
    page (issues #32/#36). The test suite can disable this with
    AULALISTA_IMPORT_ASYNC=False to keep everything deterministic inline.
    """

    if getattr(settings, "AULALISTA_IMPORT_ASYNC", True):

        def spawn(target, *args):
            threading.Thread(target=target, args=args, daemon=True).start()

        return spawn

    return lambda target, *args: target(*args)


def _run_import_job_stage(job_id, stage, payload=None):
    """Worker entry point: execute one LLM stage and persist its outcome.

    Interruptions never discard the proposals already generated: partial
    results stay reviewable under the corresponding proposed status (#36).
    """

    fallback_status = {
        "extract": CurriculumImportJob.STATUS_FAILED,
        "subtopics": CurriculumImportJob.STATUS_SUBTOPICS_PROPOSED,
        "activities": CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        "add_missing": CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
    }
    pipeline_module = None
    failure_traceback = ""
    try:
        job = CurriculumImportJob.objects.get(pk=job_id)
        from curriculum import curriculum_import as pipeline

        pipeline_module = pipeline
        pipeline.start_llm_trace()
        if stage == "extract":
            _import_action_extract(job, pipeline)
        elif stage == "subtopics":
            _import_action_confirm_topics(job, pipeline, payload["topics"])
        elif stage == "activities":
            _import_action_generate_activities(job, pipeline)
        elif stage == "add_missing":
            _import_action_add_missing_activities(job, pipeline)
        else:
            raise ValueError(f"Etapa desconocida: {stage}")
    except Exception as error:  # noqa: BLE001 - the worker must never die silently
        import traceback

        failure_traceback = traceback.format_exc()
        job = CurriculumImportJob.objects.filter(pk=job_id).first()
        if job:
            job.status = fallback_status[stage]
            job.error_message = str(error)[:500]
            job.progress_stage = ""
            job.save(
                update_fields=[
                    "status",
                    "error_message",
                    "progress_stage",
                    "updated_at",
                ]
            )
    finally:
        entries = (
            pipeline_module.stop_llm_trace() if pipeline_module else []
        )
        if pipeline_module and failure_traceback:
            # Structured failure record so debugging never depends on a
            # buried one-line message (#34/#47 lessons).
            entries.append(
                {
                    "stage": stage,
                    "model": "",
                    "system": "",
                    "prompt": "",
                    "response_raw": "",
                    "duration_ms": 0,
                    "attempts": 0,
                    "errors": [failure_traceback],
                    "ok": False,
                }
            )
        try:
            if entries:
                job = CurriculumImportJob.objects.filter(pk=job_id).first()
                if job:
                    # Persist every LLM exchange for the technical log (#34).
                    job.llm_trace = list(job.llm_trace) + entries
                    job.save(update_fields=["llm_trace", "updated_at"])
        finally:
            from django.db import connection

            connection.close()


def _start_import_stage(request, job, stage, payload=None):
    """Mark the stage as running and hand it to the background runner."""

    if job.progress_stage:
        # A stage is already running; just watch it instead of starting twice.
        return redirect("tutor-import-wait", job_id=job.pk)
    job.progress_stage = stage
    job.progress_done = 0
    job.progress_total = 0
    job.progress_started_at = timezone.now()
    job.error_message = ""
    job.save(
        update_fields=[
            "progress_stage",
            "progress_done",
            "progress_total",
            "progress_started_at",
            "error_message",
            "updated_at",
        ]
    )
    _import_stage_runner()(_run_import_job_stage, job.pk, stage, payload)
    return redirect("tutor-import-wait", job_id=job.pk)


IMPORT_STAGE_WAIT_MESSAGES = {
    "extract": "El asistente virtual está leyendo los temas…",
    "subtopics": "El asistente virtual está organizando los subtemas…",
    "activities": "El asistente virtual está creando las actividades…",
    "add_missing": "El asistente virtual está agregando las actividades que faltan…",
}

# Safety valve: if the worker died with the server (or hangs), stop waiting.
IMPORT_STAGE_TIMEOUT = timedelta(minutes=90)


@teacher_required
@require_http_methods(["GET"])
def tutor_import_wait(request, job_id):
    """Waiting page that polls the job while an LLM stage runs (#32/#36).

    The page refreshes itself every few seconds; once the stage clears, the
    teacher lands back on the review panel automatically.
    """

    job = get_object_or_404(CurriculumImportJob, pk=job_id)
    stale = bool(
        job.progress_started_at
        and timezone.now() - job.progress_started_at > IMPORT_STAGE_TIMEOUT
    )
    if stale:
        job.progress_stage = ""
        job.error_message = (
            "El asistente virtual tardó demasiado y el proceso se detuvo. "
            "Puedes reintentarlo."
        )
        job.save(update_fields=["progress_stage", "error_message", "updated_at"])
    if not job.progress_stage:
        return redirect("tutor-import-detail", job_id=job.pk)
    return render(
        request,
        "curriculum/tutor_import_wait.html",
        {
            "job": job,
            "wait_message": IMPORT_STAGE_WAIT_MESSAGES.get(
                job.progress_stage,
                "El asistente virtual está trabajando…",
            ),
        },
    )


def _render_technical_log_markdown(job):
    """Human-readable technical log of every LLM exchange (#34)."""

    from curriculum import curriculum_import as pipeline

    lines = [
        f"# Bitácora técnica · Importación #{job.pk}",
        "",
        f"- Modelo: `{pipeline.llm_model()}` · Ollama: `{pipeline.ollama_url()}`",
        f"- Estado del job: {job.get_status_display}",
        f"- Páginas: {job.page_count or '—'} · Intercambios: {len(job.llm_trace)}",
        f"- Generado: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for number, entry in enumerate(job.llm_trace, start=1):
        status = "ok" if entry.get("ok") else "FALLÓ"
        lines += [
            f"## {number}. {entry.get('stage') or 'sin etapa'} — "
            f"{entry.get('duration_ms', 0)} ms · {entry.get('attempts', 1)} "
            f"intento(s) · {status}",
            "",
            "**Prompt (system)**",
            "",
            "```",
            entry.get("system", ""),
            "```",
            "",
            "**Prompt (user)**",
            "",
            "```",
            entry.get("prompt", ""),
            "```",
            "",
            "**Respuesta cruda**",
            "",
            "```json",
            entry.get("response_raw", ""),
            "```",
            "",
        ]
        if entry.get("errors"):
            lines += ["**Errores durante los intentos**", ""]
            lines += [f"- {error}" for error in entry["errors"]]
            lines.append("")
    return "\n".join(lines)


@teacher_required
@require_http_methods(["GET"])
def tutor_import_log_md(request, job_id):
    """Download the full technical log as Markdown (#34)."""

    job = get_object_or_404(CurriculumImportJob, pk=job_id)
    content = _render_technical_log_markdown(job)
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="bitacora-import-{job.pk}.md"'
    )
    return response


@teacher_required
@require_http_methods(["GET"])
def tutor_import_log_json(request, job_id):
    """Download the full technical log as JSON (#34)."""

    job = get_object_or_404(CurriculumImportJob, pk=job_id)
    response = JsonResponse(list(job.llm_trace), safe=False, json_dumps_params={
        "ensure_ascii": False,
        "indent": 2,
    })
    response["Content-Disposition"] = (
        f'attachment; filename="bitacora-import-{job.pk}.json"'
    )
    return response


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_import_upload(request):
    """Stage A entry: the teacher uploads the curriculum PDF."""

    if request.method == "POST":
        pdf = request.FILES.get("pdf")
        if pdf is None:
            return render(
                request,
                "curriculum/tutor_import_form.html",
                {"error": "Selecciona el PDF de la currícula."},
                status=400,
            )
        job = CurriculumImportJob.objects.create(pdf=pdf)
        return redirect("tutor-import-detail", job_id=job.pk)
    return render(request, "curriculum/tutor_import_form.html", {})


@teacher_required

@require_http_methods(["GET", "POST"])
def tutor_import_detail(request, job_id):
    """Staging review: extraction, topic/subtopic proposals and checkpoints.

    Every LLM stage runs only on explicit teacher action, and every proposal
    stays editable until confirmed. No CurriculumPackage is ever created here.
    """

    from curriculum import curriculum_import as pipeline

    job = get_object_or_404(CurriculumImportJob, pk=job_id)
    if job.progress_stage:
        # A stage is running in the background; watch it on the waiting page.
        return redirect("tutor-import-wait", job_id=job.pk)
    context = {"job": job}
    if job.status == CurriculumImportJob.STATUS_COMPLETED:
        context["subtemas_totales"] = sum(
            len(topic.get("subtemas", [])) for topic in job.topics
        )
        context["actividades_estimadas"] = sum(
            (sub.get("actividades_sugeridas") or 1)
            for topic in job.topics
            for sub in topic.get("subtemas", [])
        )

    action = request.POST.get("action") if request.method == "POST" else None
    try:
        if action == "extract":
            return _start_import_stage(request, job, "extract")
        elif action == "confirm_topics":
            kept_topics = _topics_from_post(request.POST)
            if not kept_topics:
                raise ValueError("Confirma al menos un tema antes de continuar.")
            return _start_import_stage(
                request,
                job,
                "subtopics",
                payload={"topics": kept_topics},
            )
        elif action == "save_topics":
            job.topics = _topics_from_post(request.POST)
            job.save(update_fields=["topics", "updated_at"])
        elif action == "save_subtopics":
            job.topics = _subtopics_from_post(request.POST)
            job.save(update_fields=["topics", "updated_at"])
        elif action == "confirm_subtopics":
            job.topics = _subtopics_from_post(request.POST)
            job.status = CurriculumImportJob.STATUS_COMPLETED
            job.error_message = ""
            job.save()
        elif action == "generate_activities":
            return _start_import_stage(request, job, "activities")
        elif action == "add_missing_activities":
            return _start_import_stage(request, job, "add_missing")
        elif action == "remove_activity":
            _import_action_remove_activity(job, request.POST)
        elif action == "convert_selected":
            _import_action_convert(job, request.POST)
    except (pipeline.ImportPipelineError, ValueError) as error:
        job.status = CurriculumImportJob.STATUS_FAILED
        job.error_message = str(error)
        job.progress_stage = ""
        job.save(
            update_fields=[
                "status",
                "error_message",
                "progress_stage",
                "updated_at",
            ]
        )
    job.refresh_from_db()
    context["error"] = job.error_message
    if job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED:
        grouped = _grouped_activities(job)
        context["grouped_activities"] = grouped
        context["any_missing"] = any(
            sub["faltantes"] for group in grouped for sub in group["subs"]
        )
    if job.status == CurriculumImportJob.STATUS_CONVERTED:
        drafts = CurriculumPackage.objects.filter(ai_assisted=True).order_by("-id")[:20]
        context["drafts"] = drafts
        context["drafts_count"] = drafts.count()
    return render(request, "curriculum/tutor_import_detail.html", context)


def _import_action_extract(job, pipeline):
    """Extraction + Stage B topic identification over all chunks."""

    chunks = job.extract_text()
    job.progress_total = len(chunks)
    job.progress_done = 0
    job.save(update_fields=["progress_total", "progress_done", "updated_at"])
    proposals_per_chunk = []
    log = []
    for index, chunk in enumerate(chunks):
        topics = pipeline.identify_topics(chunk)
        proposals_per_chunk.append(topics)
        log.append(
            {
                "stage": "identify_topics",
                "pages": [chunk["first_page"], chunk["last_page"]],
                "proposed_count": len(topics),
            }
        )
        job.progress_done = index + 1
        job.save(update_fields=["progress_done", "updated_at"])
    consolidated = pipeline.consolidate_topics(proposals_per_chunk)
    # Pasada semántica final: agrupa fragmentos del mismo tema curricular
    # en una sola llamada LLM barata (#47); degrada a los candidatos
    # heurísticos si el modelo no responde.
    topics = pipeline.consolidate_topics_semantic(consolidated)
    log.append(
        {
            "stage": "consolidate_topics",
            "candidates": len(consolidated),
            "proposed_count": len(topics),
        }
    )
    job.topics = [
        {**topic, "subtemas": []}
        for topic in topics
    ]
    job.llm_log = log
    job.status = CurriculumImportJob.STATUS_TOPICS_PROPOSED
    job.error_message = ""
    job.progress_stage = ""
    job.save()
    return job


def _import_action_confirm_topics(job, pipeline, topics):
    """Human checkpoint 1 → Stage C subtopic proposals for each kept topic."""

    if not topics:
        raise ValueError("Confirma al menos un tema antes de continuar.")
    context_text = job.source_text
    log = list(job.llm_log)
    job.progress_total = len(topics)
    job.progress_done = 0
    job.save(update_fields=["progress_total", "progress_done", "updated_at"])
    for index, topic in enumerate(topics):
        window = pipeline.context_for_pages(
            context_text,
            topic.get("pagina_inicio", 1),
            topic.get("pagina_fin", 1),
        )
        proposal = pipeline.propose_subtopics(topic["titulo"], window)
        topic["subtemas"] = [
            {"titulo": title, "actividades_sugeridas": proposal["actividades_sugeridas"]}
            for title in proposal["subtemas"]
        ]
        log.append(
            {
                "stage": "propose_subtopics",
                "topic": topic["titulo"],
                "proposed_count": len(proposal["subtemas"]),
            }
        )
        # Persist after every topic so an interruption keeps the partial work.
        job.progress_done = index + 1
        job.topics = topics
        job.llm_log = log
        job.save(
            update_fields=[
                "topics",
                "llm_log",
                "progress_done",
                "updated_at",
            ]
        )
    job.status = CurriculumImportJob.STATUS_SUBTOPICS_PROPOSED
    job.error_message = ""
    job.progress_stage = ""
    job.save()
    return job


def _topics_from_post(post_data):
    import re

    topics = []
    indices = sorted(
        int(match.group(1))
        for key in post_data
        if (match := re.fullmatch(r"topic_(\d+)", key))
    )
    for index in indices:
        title = str(post_data.get(f"topic_{index}", "") or "").strip()[:200]
        # Unchecked checkboxes never reach the server; presence = keep (#44).
        keep = f"keep_{index}" in post_data
        if keep and title:
            topics.append(
                {
                    "titulo": title,
                    "pagina_inicio": int(post_data.get(f"start_{index}") or 1),
                    "pagina_fin": int(post_data.get(f"end_{index}") or 1),
                    "subtemas": [],
                }
            )
    return topics


def _subtopics_from_post(post_data):
    """Rebuild the confirmed hierarchy from the subtopic review form."""

    import re

    topics = []
    heading_indices = sorted(
        int(match.group(1))
        for key in post_data
        if (match := re.fullmatch(r"heading_(\d+)", key))
    )
    for topic_index in heading_indices:
        title = str(post_data.get(f"heading_{topic_index}", "") or "").strip()[:200]
        if not title or f"keep_topic_{topic_index}" not in post_data:
            continue  # absent checkbox = dropped by the teacher (#44)
        sub_indices = sorted(
            int(match.group(1))
            for key in post_data
            if (match := re.fullmatch(rf"topic_{topic_index}_sub_(\d+)", key))
        )
        subtopics = []
        for sub_index in sub_indices:
            if f"keep_{topic_index}_{sub_index}" not in post_data:
                continue  # absent checkbox = dropped by the teacher (#44)
            sub_title = str(
                post_data.get(f"topic_{topic_index}_sub_{sub_index}", "") or ""
            ).strip()[:200]
            if not sub_title:
                continue
            try:
                suggested = int(post_data.get(f"acts_{topic_index}_{sub_index}") or 1)
            except ValueError:
                suggested = 1
            subtopics.append(
                {"titulo": sub_title, "actividades_sugeridas": max(1, suggested)}
            )
        topics.append(
            {
                "titulo": title,
                "pagina_inicio": int(post_data.get(f"start_{topic_index}") or 1),
                "pagina_fin": int(post_data.get(f"end_{topic_index}") or 1),
                "subtemas": subtopics,
            }
        )
    return topics


def _import_action_generate_activities(job, pipeline):
    """Stage D: draft activities for every confirmed subtopic."""

    if not job.topics:
        raise ValueError("No hay jerarquía confirmada para generar actividades.")
    context_text = job.source_text
    log = list(job.llm_log)
    expected = sum(
        len(topic.get("subtemas", [])) for topic in job.topics
    )
    job.progress_total = expected
    job.progress_done = 0
    job.save(update_fields=["progress_total", "progress_done", "updated_at"])
    proposals = []
    done = 0
    for topic in job.topics:
        for sub in topic.get("subtemas", []):
            count = sub.get("actividades_sugeridas") or 1

            def make_proposal(feedback_issues, _sub=sub, _count=count):
                return pipeline.propose_activities(
                    _sub["titulo"],
                    context_text,
                    _count,
                    feedback_issues=feedback_issues or None,
                )

            proposal, validity, attempts = _propose_validated(make_proposal)
            proposals.append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "topic_title": topic["titulo"],
                    "subtopic_title": sub["titulo"],
                    "is_valid": validity["is_valid"],
                    "issues": validity["missing"],
                    "proposal": proposal,
                    "selected": validity["is_valid"],
                }
            )
            log.append(
                {
                    "stage": "propose_activities",
                    "subtema": sub["titulo"],
                    "reactivos": len(proposal["questions"]),
                    "is_valid": validity["is_valid"],
                    "intentos_validacion": attempts,
                }
            )
            # Persist after each proposal so an interruption never loses the
            # activities already generated (#36).
            done += 1
            job.progress_done = done
            job.activities = proposals
            job.llm_log = log
            job.save(
                update_fields=[
                    "activities",
                    "llm_log",
                    "progress_done",
                    "updated_at",
                ]
            )
    job.status = CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    job.error_message = ""
    job.progress_stage = ""
    job.save()
    return job


MAX_VALIDATION_ATTEMPTS = 3


def _propose_validated(make_proposal):
    """Draft an activity and regenerate with feedback until valid (#49).

    ``make_proposal(feedback_issues)`` must return a raw proposal; the loop
    feeds the exact structural issues back to the model. Bounded: after
    MAX_VALIDATION_ATTEMPTS the last proposal returns with its issues so the
    teacher still sees it flagged invalid (never convertible).
    """

    feedback_issues = []
    proposal = validity = None
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        proposal = make_proposal(feedback_issues)
        validity = _validate_proposal(proposal)
        if validity["is_valid"]:
            return proposal, validity, attempt + 1
        feedback_issues = validity["missing"]
    return proposal, validity, MAX_VALIDATION_ATTEMPTS


def _validate_proposal(proposal):
    """Run the canonical structural validation on a staging proposal."""

    from curriculum.models import CurriculumPackage as Package

    draft = Package(
        title=proposal["title"],
        objective=proposal["objective"],
        micro_lesson=proposal["micro_lesson"],
        final_explanation=proposal["final_explanation"],
        questions=[
            (question["block_type"], question["value"])
            for question in proposal["questions"]
        ],
    )
    return draft.structural_validation()


def _activity_id(entry, fallback_index):
    """Stable identifier for a staging proposal (older jobs may lack one)."""

    return entry.get("id") or f"idx-{fallback_index}"


def _import_action_remove_activity(job, post_data):
    """Human checkpoint: drop one staging proposal with the X button (#35).

    Removal never calls the model and never touches surviving proposals.
    """

    target = str(post_data.get("activity_id") or "")
    kept = []
    removed = False
    for index, entry in enumerate(job.activities):
        if not removed and _activity_id(entry, index) == target:
            removed = True
            continue
        kept.append(entry)
    if not removed:
        raise ValueError("La actividad ya no está en la lista.")
    job.activities = kept
    job.save(update_fields=["activities", "updated_at"])
    return removed


def _import_action_add_missing_activities(job, pipeline):
    """Stage D+: top-up only the missing activities per subtopic (#35).

    Existing proposals are immutable context; the model drafts just what is
    missing to reach the teacher-requested count. Append-only: whatever was
    already on screen stays exactly as approved.
    """

    if not job.topics:
        raise ValueError("No hay jerarquía confirmada para completar actividades.")
    context_text = job.source_text
    log = list(job.llm_log)

    # Compute how many new proposals each subtopic needs before calling the
    # model so progress_total reflects real work.
    pending = []
    for topic in job.topics:
        for sub in topic.get("subtemas", []):
            requested = max(1, int(sub.get("actividades_sugeridas") or 1))
            existing = [
                entry
                for entry in job.activities
                if entry.get("topic_title") == topic["titulo"]
                and entry.get("subtopic_title") == sub["titulo"]
            ]
            missing = requested - len(existing)
            if missing > 0:
                pending.append(
                    (
                        topic,
                        sub,
                        min(missing, 5),
                        [
                            f"{entry['proposal'].get('title', '')}: "
                            f"{entry['proposal'].get('objective', '')}"
                            for entry in existing
                        ],
                    )
                )
    job.progress_total = sum(item[2] for item in pending)
    job.progress_done = 0
    job.save(update_fields=["progress_total", "progress_done", "updated_at"])

    added = 0
    proposals = list(job.activities)
    for topic, sub, missing, summaries in pending:
        def make_topup(feedback_issues, _sub=sub, _missing=missing, _sum=summaries):
            return pipeline.propose_activities_incremental(
                _sub["titulo"],
                context_text,
                _missing,
                _sum,
                feedback_issues=feedback_issues or None,
            )

        proposal, validity, _attempts = _propose_validated(make_topup)
        proposals.append(
            {
                "id": uuid.uuid4().hex[:8],
                "topic_title": topic["titulo"],
                "subtopic_title": sub["titulo"],
                "is_valid": validity["is_valid"],
                "issues": validity["missing"],
                "proposal": proposal,
                "selected": validity["is_valid"],
                "added_by_topup": True,
            }
        )
        log.append(
            {
                "stage": "add_missing_activities",
                "subtema": sub["titulo"],
                "reactivos": len(proposal["questions"]),
                "is_valid": validity["is_valid"],
                "intentos_validacion": _attempts,
            }
        )
        added += 1
        job.progress_done = added
        job.activities = proposals
        job.llm_log = log
        job.save(
            update_fields=[
                "activities",
                "llm_log",
                "progress_done",
                "updated_at",
            ]
        )
    job.error_message = ""
    job.progress_stage = ""
    job.save()
    return added


def _grouped_activities(job):
    """Hierarchy view of staging proposals: topic → subtopic → activity (#35)."""

    grouped = []
    for topic in job.topics:
        subs = []
        for sub in topic.get("subtemas", []):
            entries = []
            for index, entry in enumerate(job.activities):
                if (
                    entry.get("topic_title") != topic["titulo"]
                    or entry.get("subtopic_title") != sub["titulo"]
                ):
                    continue
                entries.append(
                    {
                        "id": _activity_id(entry, index),
                        "index": index,
                        "entry": entry,
                    }
                )
            subs.append(
                {
                    "titulo": sub["titulo"],
                    "sugeridas": max(1, int(sub.get("actividades_sugeridas") or 1)),
                    "entries": entries,
                    "faltantes": max(
                        0,
                        max(1, int(sub.get("actividades_sugeridas") or 1))
                        - len(entries),
                    ),
                }
            )
        grouped.append({"titulo": topic["titulo"], "subs": subs})
    return grouped


def _import_action_convert(job, post_data):
    """Human checkpoint 3: convert selected valid proposals into drafts."""

    from curriculum.models import CurriculumPackage

    created = 0
    indices = post_data.getlist("select")
    if not indices:
        raise ValueError("Selecciona al menos una actividad válida para convertir.")
    for index in indices:
        entry = job.activities[int(index)]
        if not entry.get("is_valid"):
            continue  # un reactivo inválido nunca se convierte, ni marcándolo
        package = CurriculumPackage.objects.create(
            title=entry["proposal"]["title"][:160],
            objective=entry["proposal"]["objective"],
            micro_lesson=entry["proposal"]["micro_lesson"],
            final_explanation=entry["proposal"]["final_explanation"],
            questions=[
                (question["block_type"], question["value"])
                for question in entry["proposal"]["questions"]
            ],
            ai_assisted=True,
        )
        created += 1
    job.status = CurriculumImportJob.STATUS_CONVERTED
    job.save(update_fields=["status", "updated_at"])
    return created


def _unconfirmed_session_response(session):
    if session.status != ClassroomSession.STATUS_ACTIVE:
        return HttpResponseForbidden(
            "La actividad sólo está disponible para una sesión activa."
        )
    return None


def _roadmap_context(session, turn):
    progress = StudentRoadmapProgress.for_turn(turn) if turn is not None else None
    return {
        "roadmap_progress": progress,
        "roadmap_states": progress.roadmap_states() if progress else [],
        "roadmap_snapshot": session.roadmap_snapshot,
    }


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


@never_cache
@transaction.atomic
def student_roadmap(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related(
            "snapshot", "roadmap_snapshot"
        ),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is None:
        return HttpResponseForbidden(
            "El camino requiere el turno activo y la capacidad de este dispositivo."
        )
    return render(
        request,
        "curriculum/student_roadmap.html",
        {"session": session, **_roadmap_context(session, turn)},
    )


def _activity_context(session, **extra):
    turn = extra.get("turn")
    context = {
        "session": session,
        "snapshot_payload": session.snapshot.payload,
        "turn": turn,
        "activity_questions": _activity_questions(session, turn),
        **_roadmap_context(session, turn),
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


def _complete_activity_after_response(session, turn):
    """Advance only the turn's roadmap after every snapshot rule is satisfied."""

    progress = StudentRoadmapProgress.for_turn(turn)
    if progress is None:
        return False
    questions = session.snapshot.payload.get("questions", []) or []
    summary = read_ephemeral_session_summary(session.pk)
    responses = {
        item.get("question_index"): item
        for item in summary.get("turns", {}).get(str(turn.pk), {}).get("responses", [])
    }
    if questions and not all(
        responses.get(index, {}).get("is_correct") is True
        for index in range(len(questions))
    ):
        return False
    activity_id = progress.current_activity_id()
    if activity_id is None:
        return False
    progress.complete_activity(activity_id, package_snapshot=session.snapshot)
    return True


def _hint_progress_key(turn_id, question_index):
    return f"{HINT_PROGRESS_KEY_PREFIX}:{turn_id}:{question_index}"


def _consumed_hint_key(turn_id, question_index, capability):
    digest = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed:{turn_id}:{question_index}:{digest}"


def _consumed_hint_index_key(turn_id, question_index):
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn_id}:{question_index}"


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
def student_roadmap_complete(request, session_id, activity_id):
    """Complete a no-question activity after its local deterministic rules."""

    session = get_object_or_404(
        ClassroomSession.objects.select_for_update().select_related(
            "snapshot", "roadmap_snapshot"
        ),
        pk=session_id,
    )
    blocked = _unconfirmed_session_response(session)
    if blocked:
        return blocked
    turn, _ = _assignment_for_turn_capability(request, session_id)
    if turn is None:
        return HttpResponseForbidden(
            "Completar la actividad requiere el turno activo y su capacidad."
        )
    if session.snapshot.payload.get("questions"):
        summary = read_ephemeral_session_summary(session.pk)
        responses = summary.get("turns", {}).get(str(turn.pk), {}).get("responses", [])
        response_by_question = {
            item.get("question_index"): item for item in responses
        }
        if not all(
            response_by_question.get(index, {}).get("is_correct") is True
            for index in range(len(session.snapshot.payload.get("questions", []) or []))
        ):
            return HttpResponseBadRequest(
                "La actividad requiere completar correctamente sus reactivos."
            )
    progress = StudentRoadmapProgress.for_turn(turn)
    if progress is None:
        return HttpResponseBadRequest("La sesión no tiene un roadmap publicado.")
    try:
        progress.complete_activity(activity_id, package_snapshot=session.snapshot)
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    return redirect("student-roadmap", session_id=session_id)


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
    record_ephemeral_response(session_id, turn, result)
    activity_completed = result.is_correct and _complete_activity_after_response(
        session,
        turn,
    )

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
            activity_completed=activity_completed,
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
    record_ephemeral_help(session_id, turn, question_index, assistance)

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
