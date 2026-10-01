import csv
import hashlib
import logging
from collections import Counter
import io
import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core import signing
from django.core.cache import cache
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, OperationalError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.http import (
    FileResponse,
    Http404,
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

from health.lan import lan_url_notice, session_join_url
from health.qr import qr_svg

from curriculum.ephemeral import (
    clear_practice_cache,
    ensure_ephemeral_turn_summary,
    record_ephemeral_help,
    record_ephemeral_response,
    update_ephemeral_turn_summary,
)
from curriculum.models import (
    InstitutionalAuditEvent,
    ClassroomGroup,
    ClassroomSession,
    GroupRoadmapProgress,
    CurriculumImportJob,
    CurriculumPackage,
    CurriculumProgress,
    DeviceAssignment,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
    PseudonymousSurveyResponse,
    School,
    SupportRequest,
    StudentRoadmapProgress,
    StudentTurn,
    TeacherAssignment,
    _is_platform_administrator,
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

logger = logging.getLogger(__name__)

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
DIRECTOR_TEACHER_TOKEN_SALT = "aulalista.director.teacher-choice.v1"
DIRECTOR_IMPORT_TOKEN_SALT = "aulalista.director.import-preview.v1"
DIRECTOR_IMPORT_CACHE_PREFIX = "aulalista.director.import-preview"


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
        if _is_director(request.user):
            return HttpResponseForbidden(
                "La cuenta de Director no tiene autoridad docente ni editorial."
            )
        if _is_platform_administrator(request.user):
            return HttpResponseForbidden(
                "La cuenta de Administrador de Plataforma no tiene autoridad docente ni editorial."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def _director_school(user):
    """Resolve the explicitly configured School for a Director, if any."""

    return (
        School.objects.filter(
            director=user,
            is_configured=True,
            archived=False,
        )
        .order_by("id")
        .first()
    )


def _is_director(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and _director_school(user) is not None
    )


def director_required(view_func):
    """Require the active institutional Director, never a technical admin."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(_safe_teacher_next(request))
        if not _is_director(request.user):
            return HttpResponseForbidden(
                "La vista institucional requiere una cuenta de Director."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def platform_administrator_required(view_func):
    """Allow technical account administration without institutional authority."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(_safe_teacher_next(request))
        if not _is_platform_administrator(request.user):
            return HttpResponseForbidden(
                "La operación técnica requiere un PlatformAdministrator."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def _assignable_teachers(school):
    """Active local teachers that are not bound to another School.

    A local installation has one configured School, so an otherwise unbound
    staff account is eligible for its first assignment.  Historical or active
    assignment to another School fails closed in isolation fixtures.
    """

    if school is None:
        return get_user_model().objects.none()
    foreign_teacher_ids = TeacherAssignment.objects.exclude(school=school).values(
        "teacher_id"
    )
    return (
        get_user_model()
        .objects.filter(is_active=True, is_staff=True, is_superuser=False)
        .exclude(pk__in=foreign_teacher_ids)
        .exclude(directed_schools__isnull=False)
        .distinct()
        .order_by("first_name", "last_name", "id")
    )


def _director_groups(user):
    school = _director_school(user)
    if school is None:
        return ClassroomGroup.objects.none(), None
    return ClassroomGroup.objects.filter(school=school), school


def _presentation_name(user):
    return (user.get_full_name() or "Docente asignada").strip()


def _teacher_choice_token(user):
    return signing.dumps({"teacher_id": user.pk}, salt=DIRECTOR_TEACHER_TOKEN_SALT, compress=True)


def _teacher_from_choice_token(value, school):
    try:
        payload = signing.loads(value, salt=DIRECTOR_TEACHER_TOKEN_SALT, max_age=LOCAL_SESSION_TTL)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    teacher_id = payload.get("teacher_id") if isinstance(payload, dict) else None
    return _assignable_teachers(school).filter(pk=teacher_id).first()


def _director_scope(user):
    groups, school = _director_groups(user)
    return groups.filter(archived__in=(False, True)), school


def _director_export_rows(user, *, include_actions=False):
    groups, school = _director_scope(user)
    rows = []
    for group in groups.select_related("school").prefetch_related(
        "sessions", "teacher_assignments__teacher"
    ).order_by("archived", "name", "id"):
        sessions = list(
            group.sessions.filter(status=ClassroomSession.STATUS_CLOSED).order_by("-closed_at", "-id")
        )
        assignments = list(
            group.teacher_assignments.order_by("-created_at", "-id")
        )
        latest = sessions[0] if sessions else None
        result_batches = [session.result_batch_id for session in sessions]
        result_qs = PseudonymousResult.objects.filter(result_batch_id__in=result_batches)
        aggregate = _result_aggregate(result_qs)
        latest_aggregate = (
            _result_aggregate(
                PseudonymousResult.objects.filter(result_batch_id=latest.result_batch_id),
                session=latest,
            )
            if latest else None
        )
        period = "No disponible"
        if sessions:
            dates = [session.closed_at.date() for session in sessions if session.closed_at]
            period = f"{min(dates)} a {max(dates)}" if dates else "No disponible"
        roadmap_position = "No disponible"
        if latest and latest.roadmap_snapshot_id:
            from curriculum.roadmap import ordered_activity_ids
            activity_ids = ordered_activity_ids(latest.roadmap_snapshot.payload)
            progress = GroupRoadmapProgress.objects.filter(session=latest).first()
            if activity_ids and progress and progress.current_activity_id in activity_ids:
                roadmap_position = f"Actividad {activity_ids.index(progress.current_activity_id) + 1} de {len(activity_ids)}"
        row = {
                "school": school.name if school else "School legacy no atribuida",
                "group": group.name,
                "group_status": "archived" if group.archived else "active",
                "academic_year": group.academic_year,
                "modality": group.modality,
                "grade": group.grade,
                "group_key": group.group_key,
                "shift": group.shift,
                "session_count": len(sessions),
                "latest_session_status": latest.get_status_display() if latest else "Sin sesiones",
                "roadmap_title": latest.roadmap_snapshot.title if latest and latest.roadmap_snapshot_id else "Sin roadmap",
                "worked_activity_count": aggregate["activities_worked"],
                "participation_count": latest_aggregate["participant_count"] if latest_aggregate else 0,
                "metrics": [
                    {"label": "Actividades trabajadas", "value": aggregate["activities_worked"] if sessions else "No disponible", "source": "Sesiones cerradas", "period": period, "updated_at": latest.closed_at if latest else None},
                    {"label": "Participantes únicos en la última sesión cerrada", "value": latest_aggregate["participant_count"] if latest_aggregate else "No disponible", "source": "Última sesión cerrada", "period": str(latest.closed_at.date()) if latest and latest.closed_at else "No disponible", "updated_at": latest.closed_at if latest else None},
                    {"label": "Posición del roadmap", "value": roadmap_position, "source": "Snapshot fijado a la sesión", "period": period, "updated_at": latest.closed_at if latest else None},
                    {"label": "Sesiones cerradas", "value": len(sessions), "source": "Sesiones cerradas", "period": period, "updated_at": latest.closed_at if latest else None},
                ],
                "assignments": [
                    {
                        "teacher": _presentation_name(assignment.teacher),
                        "function": assignment.function,
                        "subject": assignment.subject,
                        "status": assignment.get_status_display(),
                        "valid_from": assignment.valid_from.isoformat() if assignment.valid_from else "",
                        "valid_until": assignment.valid_until.isoformat() if assignment.valid_until else "",
                    }
                    for assignment in assignments
                ],
            }
        if include_actions:
            row["assignment_url"] = reverse("director-group-assign", args=[group.pk])
        rows.append(row)
    return rows, school


@director_required
@require_http_methods(["GET"])
def director_dashboard(request):
    """Show only Director-scoped institutional and aggregate projections."""

    rows, school = _director_export_rows(request.user, include_actions=True)
    audits = InstitutionalAuditEvent.objects.filter(school=school) if school else InstitutionalAuditEvent.objects.none()
    return render(
        request,
        "curriculum/director_dashboard.html",
        {
            "school": school,
            "classroom_cards": rows,
            "audit_events": audits.order_by("-occurred_at", "-id")[:20],
            "teachers": [
                {"label": _presentation_name(teacher), "token": _teacher_choice_token(teacher)}
                for teacher in _assignable_teachers(school)
            ],
            "support_requests": SupportRequest.objects.filter(school=school).select_related(
                "classroom_group", "created_by", "responsible"
            )[:20],
            "support_responsibles": get_user_model().objects.filter(
                is_active=True, is_staff=True
            ).order_by("first_name", "last_name", "id"),
        },
    )


@director_required
@require_POST
def director_support_request_update(request, request_id):
    """Direction alone changes the institutional status of a support request."""

    support_request = get_object_or_404(
        SupportRequest.objects.select_related("school"),
        pk=request_id,
        school=_director_school(request.user),
    )
    status = request.POST.get("status", "")
    if status not in dict(SupportRequest.STATUS_CHOICES):
        return HttpResponseBadRequest("El estado de la solicitud no es válido.")
    if support_request.closed_at:
        return HttpResponseBadRequest("La solicitud ya está cerrada y no puede editarse.")
    responsible_id = request.POST.get("responsible_id", "").strip()
    if responsible_id:
        responsible = get_user_model().objects.filter(
            pk=responsible_id, is_active=True, is_staff=True
        ).first()
        if responsible is None:
            return HttpResponseBadRequest("La persona responsable no está disponible.")
        if _is_platform_administrator(responsible) and support_request.category != SupportRequest.CATEGORY_TECHNICAL:
            return HttpResponseBadRequest("Administración técnica sólo atiende solicitudes técnicas.")
        support_request.responsible = responsible
    support_request.status = status
    if status in (SupportRequest.STATUS_RESOLVED, SupportRequest.STATUS_DISMISSED):
        support_request.closed_at = timezone.now()
    support_request.save(update_fields=["status", "responsible", "closed_at", "updated_at"])
    InstitutionalAuditEvent.record(
        school=support_request.school,
        actor=request.user,
        action="support_request_updated",
        object_type="SupportRequest",
        object_id=support_request.pk,
        classroom_group=support_request.classroom_group,
        new_state={"category": support_request.category, "status": support_request.status, "responsible": _presentation_name(support_request.responsible) if support_request.responsible else ""},
        source="manual",
    )
    return redirect("director-dashboard")


@director_required
@require_POST
def director_group_assign(request, group_id):
    """Create an append-only TeacherAssignment within the Director's School."""

    groups, school = _director_groups(request.user)
    group = get_object_or_404(groups, pk=group_id)
    teacher_value = str(
        request.POST.get("teacher_token")
        or request.POST.get("teacher_id")
        or request.POST.get("teacher")
        or ""
    ).strip()
    teacher = _teacher_from_choice_token(teacher_value, school)
    if teacher is None:
        teachers = _assignable_teachers(school)
        teacher = teachers.filter(pk=teacher_value).first() if teacher_value.isdigit() else teachers.filter(username=teacher_value).first()
    if teacher is None:
        return HttpResponseBadRequest("Selecciona una cuenta docente existente y activa.")
    if teacher.pk == request.user.pk:
        return HttpResponseBadRequest("Dirección no puede adscribirse a sí misma.")
    function = str(request.POST.get("function", "")).strip()
    subject = str(request.POST.get("subject", "")).strip()
    try:
        with transaction.atomic():
            duplicate = TeacherAssignment.objects.select_for_update().filter(
                classroom_group=group,
                teacher=teacher,
                status=TeacherAssignment.STATUS_ACTIVE,
                function=function,
                subject=subject,
            ).exists()
            if not duplicate:
                TeacherAssignment.create_assignment(
                    teacher=teacher,
                    classroom_group=group,
                    actor=request.user,
                    function=function,
                    subject=subject,
                    source="manual",
                )
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    return redirect("director-dashboard")


@director_required
@require_POST
def director_export(request):
    """Export institutional metadata and aggregates, never student detail."""

    rows, school = _director_export_rows(request.user)
    audits = InstitutionalAuditEvent.objects.filter(school=school).order_by("-occurred_at", "-id") if school else []
    def audit_state(state):
        state = state or {}
        pairs = []
        if "status" in state:
            pairs.append(f"Estado: {state['status']}")
        teacher = _audit_state_teacher(state)
        if teacher:
            pairs.append(f"docente: {teacher}")
        return "; ".join(pairs) or "Sin cambio visible"

    audit_rows = [
        {
            "actor": event.actor_display_name,
            "role": event.actor_role,
            "action": event.action,
            "object": event.object_type,
            "previous": audit_state(event.previous_state),
            "new": audit_state(event.new_state),
            "source": event.source,
            "occurred_at": event.occurred_at.isoformat(),
        }
        for event in audits
    ]
    payload = {
        "school": school.name if school else "School legacy no atribuida",
        "groups": rows,
        "audit": audit_rows,
    }
    export_format = request.POST.get("format", request.GET.get("format", "json")).lower()
    if export_format == "json":
        response = JsonResponse(payload)
        response["Content-Disposition"] = 'attachment; filename="aulalista-institucional.json"'
        return response
    if export_format == "csv":
        output = io.StringIO()
        fieldnames = [
            "school", "group", "group_status", "academic_year", "modality", "grade",
            "group_key", "shift", "session_count", "latest_session_status", "roadmap_title",
            "worked_activity_count", "participation_count", "assignments",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **{key: _csv_safe_text(value) for key, value in row.items() if key not in {"assignments", "metrics"}},
                "assignments": _csv_safe_text("; ".join(
                    f"{assignment['teacher']} ({assignment['status']})"
                    for assignment in row["assignments"]
                )),
            })
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="aulalista-institucional.csv"'
        return response
    return HttpResponseBadRequest("El formato de exportación no está disponible.")


def _audit_state_teacher(state):
    """Project an audit teacher reference without exporting an account ID."""

    teacher_id = (state or {}).get("teacher_id")
    if teacher_id is None:
        return ""
    teacher = get_user_model().objects.filter(pk=teacher_id).first()
    return _presentation_name(teacher) if teacher is not None else "Cuenta histórica"


@platform_administrator_required
@require_POST
def platform_director_handoff(request):
    """Perform the explicitly authorized, atomic institutional handoff."""

    if request.POST.get("confirm") != "CAMBIAR":
        return HttpResponseBadRequest("Confirma el cambio de Dirección antes de aplicarlo.")
    school = School.configured()
    if school is None:
        return HttpResponseBadRequest("No hay una School institucional configurada.")
    director_id = str(request.POST.get("director", "")).strip()
    new_director = get_user_model().objects.filter(pk=director_id).first()
    if new_director is None:
        return HttpResponseBadRequest("Selecciona una cuenta existente para Dirección.")
    try:
        school.handoff_director(new_director, actor=request.user, source="manual")
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    return redirect("director-dashboard")


@director_required
@require_http_methods(["GET", "POST"])
def director_import_preview(request):
    """Analyze an .xlsx workbook; this operation never writes institutional data."""

    if request.method == "GET":
        return render(request, "curriculum/director_import_form.html")
    upload = request.FILES.get("workbook")
    if upload is None or not upload.name.lower().endswith(".xlsx"):
        return render(request, "curriculum/director_import_form.html", {"error": "Selecciona un archivo .xlsx."}, status=400)
    from curriculum.institutional_import import workbook_preview
    school = _director_school(request.user)
    try:
        preview = workbook_preview(upload, school, _assignable_teachers(school))
    except ValidationError as error:
        return render(request, "curriculum/director_import_form.html", {"error": str(error)}, status=400)
    nonce = uuid.uuid4().hex
    cache.set(f"{DIRECTOR_IMPORT_CACHE_PREFIX}:{nonce}", {"school_id": school.pk, "preview": preview}, timeout=LOCAL_SESSION_TTL)
    token = signing.dumps({"nonce": nonce, "school_id": school.pk}, salt=DIRECTOR_IMPORT_TOKEN_SALT, compress=True)
    return render(request, "curriculum/director_import_preview.html", {"preview": preview, "preview_token": token})


@director_required
@require_POST
def director_import_apply(request):
    """Apply a reviewed preview atomically; ambiguous rows require an explicit choice."""

    try:
        token = signing.loads(request.POST.get("preview_token", ""), salt=DIRECTOR_IMPORT_TOKEN_SALT, max_age=LOCAL_SESSION_TTL)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return HttpResponseBadRequest("La vista previa expiró; vuelve a analizar el archivo.")
    school = _director_school(request.user)
    cached = cache.get(f"{DIRECTOR_IMPORT_CACHE_PREFIX}:{token.get('nonce')}")
    if not cached or cached.get("school_id") != school.pk or token.get("school_id") != school.pk:
        return HttpResponseBadRequest("La vista previa no corresponde a tu School o ya expiró.")
    selections = {}
    for row in cached["preview"]["rows"]:
        value = request.POST.get(f"teacher_{row['row_number']}", "")
        if value.isdigit():
            selections[str(row["row_number"])] = int(value)
    from curriculum.institutional_import import apply_preview
    try:
        with transaction.atomic():
            result = apply_preview(cached["preview"], school, request.user, selections)
            InstitutionalAuditEvent.record(
                school=school, actor=request.user, action="institutional_import_applied",
                object_type="InstitutionalImport", source="excel",
                new_state={"groups_created": result["created_groups"], "groups_changed": result["changed_groups"], "assignments_created": result["created_assignments"]},
            )
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    cache.delete(f"{DIRECTOR_IMPORT_CACHE_PREFIX}:{token['nonce']}")
    messages.success(request, "Importación confirmada: se aplicaron sólo las altas y cambios revisados.")
    return redirect("director-dashboard")


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
            "assignment",
            "assignment__session",
            "assignment__session__snapshot",
            "assignment__session__roadmap_snapshot",
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
        clear_practice_cache(
            completed.pk,
            range(question_count),
            activity_ids=_roadmap_activity_ids(completed.assignment.session) or None,
        )
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
@require_http_methods(["GET", "POST"])
def tutor_roadmaps(request):
    """Publish a teacher-selected roadmap and confirm its curriculum position."""

    from curriculum.roadmap import ordered_activities, ordered_nodes

    package_snapshots = list(
        PublishedPackageSnapshot.objects.filter(
            package__created_by=request.user
        ).select_related("package").order_by(
            "-published_at", "-id"
        )
    )
    publication_error = None
    if request.method == "POST":
        selected_ids = request.POST.getlist("package")
        if not selected_ids:
            # Compatibility with previously rendered teacher forms.
            selected_ids = request.POST.getlist("package_snapshot_ids")
        if not selected_ids:
            selected_ids = request.POST.getlist("package_snapshot_id")
        snapshots_by_id = {str(snapshot.pk): snapshot for snapshot in package_snapshots}
        selected_snapshots = [snapshots_by_id[item] for item in selected_ids if item in snapshots_by_id]
        try:
            PublishedRoadmapSnapshot.publish(
                title=request.POST.get("title", "Roadmap"),
                package_snapshots=selected_snapshots,
                teacher=request.user,
            )
        except ValidationError as error:
            publication_error = str(error)
        else:
            return redirect("tutor-roadmaps")

    snapshots = list(
        PublishedRoadmapSnapshot.objects.filter(published_by=request.user)[:20]
    )
    cards = []
    for snapshot in snapshots:
        progress = {
            item.node_id: item
            for item in snapshot.curriculum_progress.select_related("confirmed_by")
        }
        snapshot_by_id = {
            str(item.pk): item for item in package_snapshots
        }
        activity_by_id = {
            activity["id"]: activity
            for activity in ordered_activities(snapshot.payload)
        }
        nodes = []
        for node in ordered_nodes(snapshot.payload):
            activity = activity_by_id.get(node["id"], {})
            activity_snapshot = snapshot_by_id.get(
                str(activity.get("package_snapshot_id"))
            )
            nodes.append(
                {
                    **node,
                    "progress": progress.get(node["id"]),
                    "activity_snapshot": activity_snapshot,
                }
            )
        cards.append(
            {
                "snapshot": snapshot,
                "nodes": nodes,
                "progress_count": len(progress),
            }
        )
    return render(
        request,
        "curriculum/tutor_roadmaps.html",
        {
            "roadmap_cards": cards,
            "package_snapshots": package_snapshots,
            "publication_error": publication_error,
        },
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_roadmap_progress(request, snapshot_id):
    """Record only an explicit teacher decision; students have no route here."""

    from curriculum.roadmap import ordered_activities, ordered_nodes

    snapshot = get_object_or_404(
        PublishedRoadmapSnapshot,
        pk=snapshot_id,
        published_by=request.user,
    )
    nodes = ordered_nodes(snapshot.payload)
    activity_by_id = {
        activity["id"]: activity
        for activity in ordered_activities(snapshot.payload)
    }
    package_snapshot_ids = {
        str(activity.get("package_snapshot_id"))
        for activity in activity_by_id.values()
        if activity.get("package_snapshot_id") is not None
    }
    activity_snapshots = {
        str(item.pk): item
        for item in PublishedPackageSnapshot.objects.filter(
            pk__in=package_snapshot_ids,
            package__created_by=request.user,
        )
    }
    progress = {
        item.node_id: item
        for item in snapshot.curriculum_progress.select_related("confirmed_by")
    }
    nodes = [
        {
            **node,
            "activity_snapshot": activity_snapshots.get(
                str(activity_by_id.get(node["id"], {}).get("package_snapshot_id"))
            ),
            "progress": progress.get(node["id"]),
        }
        for node in nodes
    ]
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

    return render(
        request,
        "curriculum/tutor_roadmap_progress.html",
        {"snapshot": snapshot, "nodes": nodes},
    )


@teacher_required
def tutor_home(request):
    """Canonical teacher entry point, backed by the existing session console.

    ``/tutor/`` is deliberately not a second dashboard: it renders the same
    operational landing as the sessions route so a teacher can enter the
    workflow after login and continue through the existing paths.
    """

    return tutor_sessions(request)


@teacher_required
def tutor_curriculum(request):
    """Teacher-facing index for imported proposals, drafts, and publications."""

    packages = list(
        CurriculumPackage.objects.filter(created_by=request.user).order_by(
            "-updated_at", "-id"
        )[:30]
    )
    published_snapshots_by_package = {}
    for snapshot in PublishedPackageSnapshot.objects.filter(
        package__created_by=request.user
    ).order_by(
        "-published_at", "-id"
    ):
        published_snapshots_by_package.setdefault(snapshot.package_id, snapshot)
    published_package_ids = set(published_snapshots_by_package)
    package_cards = []
    for package in packages:
        workflow_state = package.current_workflow_state
        if package.pk in published_package_ids:
            editorial_state = "Publicado"
        elif package.import_approvals.filter(is_active=True).exists():
            editorial_state = "Aprobada para preparar"
        elif workflow_state is not None:
            editorial_state = workflow_state.get_status_display()
        else:
            editorial_state = "Borrador editable"
        package_cards.append(
            {
                "package": package,
                "editorial_state": editorial_state,
                "editor_url": reverse(
                    package.snippet_viewset.get_url_name("edit"),
                    args=[package.pk],
                ),
                "is_published": package.pk in published_package_ids,
                "published_snapshot": published_snapshots_by_package.get(package.pk),
            }
        )

    raw_jobs = list(
        CurriculumImportJob.objects.filter(created_by=request.user).order_by(
            "-updated_at", "-id"
        )[:20]
    )
    import_cards = []
    for job in raw_jobs:
        pres = _get_derived_import_presentation(job)
        interp_state = getattr(job, "interpretation_state", CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED)
        has_valid_dossier = pres.get("has_valid_dossier", False)

        active_approval = (
            job.get_active_approval(has_valid_ready_dossier=True)
            if (has_valid_dossier and hasattr(job, "get_active_approval"))
            else None
        )
        # 1. APPROVED + valid dossier -> tutor-import-interpretation, CTA Ver planeación aprobada
        if active_approval and has_valid_dossier:
            canonical_state = "approved"
            action_url = reverse("tutor-import-interpretation", args=[job.pk])
            action_text = "Ver planeación aprobada"
            status_label = "Aprobada"
        # 2. READY + valid dossier -> tutor-import-interpretation, CTA Revisar planeación
        elif interp_state == CurriculumImportJob.INTERPRETATION_STATE_READY and has_valid_dossier:
            canonical_state = "ready"
            action_url = reverse("tutor-import-interpretation", args=[job.pk])
            action_text = "Revisar planeación"
            status_label = "Requiere revisión"
        # 2. FAILED or error -> tutor-import-wait, CTA Resolver e intentar de nuevo
        elif pres["state"] == "error" or interp_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED:
            canonical_state = "failed"
            action_url = reverse("tutor-import-wait", args=[job.pk])
            action_text = "Resolver e intentar de nuevo"
            status_label = "Requiere atención"
        # 3. delayed -> tutor-import-wait, CTA Ver progreso
        elif pres["state"] == "delayed":
            canonical_state = "delayed"
            action_url = reverse("tutor-import-wait", args=[job.pk])
            action_text = "Ver progreso"
            status_label = "Demora en progreso"
        # 4. ORGANIZING / active claim / active progress stage -> tutor-import-wait, CTA Ver progreso
        elif (
            interp_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
            or job.progress_stage
            or job.interpretation_claim_token
        ):
            canonical_state = "organizing"
            action_url = reverse("tutor-import-wait", args=[job.pk])
            action_text = "Ver progreso"
            status_label = "En organización"
        # 5. NOT_STARTED / legacy sin lifecycle -> tutor-import-upload, CTA Importar planeación
        else:
            canonical_state = "not_started"
            action_url = reverse("tutor-import-upload")
            action_text = "Importar planeación"
            status_label = "Sin iniciar"

        import_cards.append(
            {
                "job": job,
                "canonical_state": canonical_state,
                "action_url": action_url,
                "action_text": action_text,
                "status_label": status_label,
            }
        )

    return render(
        request,
        "curriculum/tutor_curriculum.html",
        {
            "imports": raw_jobs,
            "import_cards": import_cards,
            "package_cards": package_cards,
            "published_snapshots": PublishedPackageSnapshot.objects.filter(
                package__created_by=request.user
            ).select_related("package").order_by("-published_at", "-id")[:20],
        },
    )


def _normalize_legacy_source_references(references, fallback_sha=""):
    if not references:
        return []
    normalized = []
    for ref in references:
        if not isinstance(ref, dict):
            continue
        item = dict(ref)
        if "source_pages" not in item and "pages" in item:
            item["source_pages"] = item["pages"]
        if not item.get("source_pdf_sha256") and fallback_sha:
            item["source_pdf_sha256"] = fallback_sha
        normalized.append(item)
    return normalized


@teacher_required
def tutor_package_detail(request, snapshot_id):
    """Show one immutable published activity in teacher language."""

    snapshot = get_object_or_404(
        PublishedPackageSnapshot.objects.select_related("package"),
        pk=snapshot_id,
        package__created_by=request.user,
    )
    payload = dict(snapshot.payload or {})
    if "source_references" in payload:
        fallback_sha = getattr(snapshot, "source_pdf_sha256", "") or getattr(snapshot, "sha256", "")
        payload["source_references"] = _normalize_legacy_source_references(
            payload["source_references"], fallback_sha
        )
    questions = []
    for question in payload.get("questions", []) or []:
        value = question.get("value", question) if isinstance(question, dict) else {}
        value = value if isinstance(value, dict) else {}
        questions.append(
            {
                "prompt": value.get("prompt", ""),
                "options": value.get("options", []) or [],
                "hints": value.get("hints", []) or [],
            }
        )
    return render(
        request,
        "curriculum/tutor_package_detail.html",
        {
            "snapshot": snapshot,
            "payload": payload,
            "questions": questions,
        },
    )


@teacher_required
def tutor_sessions(request):
    """Operational teacher landing for the existing session workflow.

    Counts are derived at read time; the landing does not create or persist
    any additional classroom state.
    """
    sessions = (
        _teacher_sessions(request).select_related(
            "snapshot", "snapshot__package", "classroom_group"
        )
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
                "group_name": session.classroom_group.name if session.classroom_group else "Sin salón",
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
                "results_url": reverse(
                    "tutor-session-results", args=[session.pk]
                ),
            }
        )
    classroom_groups = list(
        ClassroomGroup.objects.filter(created_by=request.user)
        .prefetch_related("classroom_sessions")
        .order_by("name", "id")
    )
    classroom_cards = []
    for group in classroom_groups:
        group_sessions = list(group.classroom_sessions.all())
        active_sessions = [
            session
            for session in group_sessions
            if session.status == ClassroomSession.STATUS_ACTIVE
        ]
        classroom_cards.append(
            {
                "group": group,
                "active_sessions": active_sessions,
                "active_count": len(active_sessions),
                "session_count": len(group_sessions),
            }
        )
    snapshots = (
        PublishedPackageSnapshot.objects.filter(package__created_by=request.user)
        .select_related("package")
        .order_by("-published_at", "-id")[:12]
    )
    return render(
        request,
        "curriculum/tutor_sessions.html",
        {
            "session_cards": session_cards,
            "snapshots": snapshots,
            "classroom_groups": classroom_groups,
            "classroom_cards": classroom_cards,
        },
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_groups(request):
    """Create and list classroom labels; this view never contains a roster."""

    if request.method == "POST":
        group = ClassroomGroup(
            name=request.POST.get("name", ""),
            created_by=request.user,
        )
        try:
            group.full_clean()
            group.save()
        except (ValidationError, IntegrityError) as error:
            return render(
                request,
                "curriculum/tutor_groups.html",
                {
                    "classroom_groups": ClassroomGroup.objects.filter(created_by=request.user),
                    "error": str(error),
                },
                status=400,
            )
        return redirect("tutor-groups")
    return render(
        request,
        "curriculum/tutor_groups.html",
        {"classroom_groups": ClassroomGroup.objects.filter(created_by=request.user)},
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_session_prepare(request, snapshot_id):
    snapshot = get_object_or_404(
        PublishedPackageSnapshot,
        pk=snapshot_id,
        package__created_by=request.user,
    )
    context = {
        "snapshot": snapshot,
        "roadmaps": PublishedRoadmapSnapshot.objects.filter(
            published_by=request.user
        )[:20],
        "classroom_groups": ClassroomGroup.objects.filter(created_by=request.user),
    }
    if request.method == "POST":
        try:
            roadmap_snapshot = None
            roadmap_id = request.POST.get("roadmap") or request.POST.get(
                "roadmap_snapshot_id"
            )
            if roadmap_id:
                roadmap_snapshot = get_object_or_404(
                    PublishedRoadmapSnapshot,
                    pk=roadmap_id,
                    published_by=request.user,
                )
            classroom_group = None
            group_id = request.POST.get("classroom_group")
            if group_id:
                classroom_group = get_object_or_404(
                    ClassroomGroup,
                    pk=group_id,
                    created_by=request.user,
                )
            session = ClassroomSession.prepare_from_snapshot(
                snapshot,
                request.POST.get("student_count"),
                request.POST.get("device_count"),
                roadmap_snapshot=roadmap_snapshot,
                classroom_group=classroom_group,
                teacher=request.user,
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


def _session_join_context(request, session):
    """Return one explicit LAN join URL and its safe degraded state."""

    join_url, configured = session_join_url(request, session.pk)
    return {
        "join_url": join_url,
        "join_qr_svg": qr_svg(join_url) if configured else "",
        "join_url_is_configured": configured,
        "join_url_notice": lan_url_notice(configured),
    }


def _teacher_sessions(request):
    """Return active-assignment sessions and explicitly marked legacy rows."""

    assigned_groups = TeacherAssignment.objects.filter(
        teacher=request.user,
        status=TeacherAssignment.STATUS_ACTIVE,
    ).values("classroom_group_id")
    return ClassroomSession.objects.filter(
        Q(classroom_group_id__in=assigned_groups)
        | Q(legacy_owner_unresolved=True)
        | Q(school__isnull=True, created_by=request.user)
    )


def _teacher_session_or_404(request, session_id, queryset=None):
    queryset = queryset if queryset is not None else ClassroomSession.objects
    return get_object_or_404(
        queryset.filter(
            Q(
                classroom_group_id__in=TeacherAssignment.objects.filter(
                    teacher=request.user,
                    status=TeacherAssignment.STATUS_ACTIVE,
                ).values("classroom_group_id")
            )
            | Q(legacy_owner_unresolved=True)
            | Q(school__isnull=True, created_by=request.user)
        ),
        pk=session_id,
    )


def _teacher_group_or_404(request, group_id):
    """Resolve only a group covered by an active assignment or a legacy owner."""

    return get_object_or_404(
        ClassroomGroup.objects.filter(
            Q(
                teacher_assignments__teacher=request.user,
                teacher_assignments__status=TeacherAssignment.STATUS_ACTIVE,
            )
            | Q(school__isnull=True, created_by=request.user)
        ).distinct(),
        pk=group_id,
    )


@teacher_required
@require_POST
def tutor_group_support_request(request, group_id):
    """Let an assigned teacher request bounded institutional support."""

    group = _teacher_group_or_404(request, group_id)
    try:
        target_date = datetime.strptime(request.POST.get("target_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest("Indica una fecha objetivo válida.")
    support_request = SupportRequest(
        school=group.school,
        classroom_group=group,
        created_by=request.user,
        category=request.POST.get("category", ""),
        description=request.POST.get("description", ""),
        target_date=target_date,
    )
    try:
        support_request.full_clean()
        support_request.save()
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    InstitutionalAuditEvent.record(
        school=group.school,
        actor=request.user,
        action="support_request_created",
        object_type="SupportRequest",
        object_id=support_request.pk,
        classroom_group=group,
        new_state={"category": support_request.category, "status": support_request.status},
        source="manual",
    )
    return redirect("tutor-groups")


@teacher_required
def tutor_session_review(request, session_id):
    session = _teacher_session_or_404(
        request,
        session_id,
        ClassroomSession.objects.select_related(
            "snapshot", "roadmap_snapshot", "classroom_group"
        ).prefetch_related("device_assignments"),
    )
    results = list(
        PseudonymousResult.objects.filter(
            result_batch_id=session.result_batch_id,
        )
    )
    survey_responses = _session_survey_responses(session)
    join_context = (
        _session_join_context(request, session)
        if session.status == ClassroomSession.STATUS_ACTIVE
        else {"join_url": "", "join_qr_svg": ""}
    )
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
            "result_aggregate": _result_aggregate(results, session=session),
            "survey_aggregate": survey_aggregate(survey_responses),
            "survey_response_count": survey_responses.count(),
            "individual_register": _individual_result_register(results, session)
            if session.status == ClassroomSession.STATUS_CLOSED
            else [],
            **join_context,
        },
    )


@never_cache
@teacher_required
def tutor_session_active(request, session_id):
    """Authenticated operational view; aliases exist only in active state."""
    session = _teacher_session_or_404(
        request,
        session_id,
        ClassroomSession.objects.select_related("snapshot"),
    )
    active_turns = StudentTurn.objects.none()
    if session.status == ClassroomSession.STATUS_ACTIVE:
        active_turns = StudentTurn.objects.filter(
            assignment__session_id=session.pk,
            status=StudentTurn.STATUS_ACTIVE,
        ).exclude(display_name="").order_by("started_at", "pk")
    join_context = (
        _session_join_context(request, session)
        if session.status == ClassroomSession.STATUS_ACTIVE
        else {"join_url": "", "join_qr_svg": ""}
    )
    group_progress = GroupRoadmapProgress.for_session(session)
    roadmap_lessons = []
    if group_progress:
        from curriculum.roadmap import ordered_activities
        current_id = group_progress.current_activity_id
        activities = ordered_activities(session.roadmap_snapshot.payload)
        current_position = next(
            (index for index, row in enumerate(activities) if row["id"] == current_id),
            len(activities),
        )
        seen = set()
        for position, row in enumerate(activities):
            if row["lesson_id"] not in seen:
                seen.add(row["lesson_id"])
                if position > current_position:
                    roadmap_lessons.append(row)
    return render(
        request,
        "curriculum/tutor_session_active.html",
        {
            "session": session,
            "active_turns": active_turns,
            "participant_count": active_turns.count(),
            "group_roadmap_progress": group_progress,
            "roadmap_lessons": roadmap_lessons,
            **join_context,
            "snapshot_label": (
                f"versión {session.snapshot.version} · {session.snapshot.sha256[:8]}"
            ),
        },
    )


@never_cache
@teacher_required
@require_POST
def tutor_session_roadmap_advance(request, session_id):
    """Move this session's shared roadmap cursor forward by teacher action."""
    session = _teacher_session_or_404(
        request,
        session_id,
        ClassroomSession.objects.select_for_update().select_related(
            "roadmap_snapshot"
        ),
    )
    if session.status != ClassroomSession.STATUS_ACTIVE or not session.roadmap_snapshot_id:
        return HttpResponseForbidden("La sesión no tiene un roadmap activo.")
    from curriculum.roadmap import ordered_activities
    requested = str(request.POST.get("lesson_id", "")).strip()
    activities = ordered_activities(session.roadmap_snapshot.payload)
    target = next((item["id"] for item in activities if item["lesson_id"] == requested), None)
    if target is None:
        return HttpResponseBadRequest("Selecciona una actividad del roadmap publicado.")
    try:
        GroupRoadmapProgress.for_session(session).advance_to(target)
    except ValidationError as error:
        return HttpResponseBadRequest(str(error))
    return redirect("tutor-session-active", session_id=session.pk)


@never_cache
def tutor_session_projection(request, session_id):
    """Public projection: status, count, and active join material only."""
    # Intentionally public: this is a classroom projection, not a teacher action.
    session = get_object_or_404(ClassroomSession, pk=session_id)
    participant_count = 0
    join_context = {"join_url": "", "join_qr_svg": ""}
    if session.status == ClassroomSession.STATUS_ACTIVE:
        participant_count = StudentTurn.objects.filter(
            assignment__session_id=session.pk,
            status=StudentTurn.STATUS_ACTIVE,
        ).count()
        join_context = _session_join_context(request, session)
    return render(
        request,
        "curriculum/tutor_session_projection.html",
        {
            "session": session,
            "participant_count": participant_count,
            **join_context,
        },
    )


@teacher_required

@require_POST
def tutor_session_confirm(request, session_id):
    session = _teacher_session_or_404(request, session_id)
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
    session = _teacher_session_or_404(request, session_id)
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
                    ),
                    session=session,
                ),
                "error": str(error),
            },
            status=400,
        )
    return redirect("tutor-session-review", session_id=session.pk)


_RESULT_RESPONSE_REQUIRED_FIELDS = {
    "question_index",
    "selected_position",
    "is_correct",
}
_RESULT_RESPONSE_OPTIONAL_FIELDS = {"activity_id"}
# Sessions created before roadmap support execute one package directly.  The
# close path records that package under this stable sentinel because there is
# no published activity ID to resolve.
_LEGACY_RESULT_ACTIVITY_ID = "actividad-0"


def _is_valid_result_response(response):
    """Validate the exact persisted shape emitted by ``record_ephemeral_response``.

    A non-empty mapping is not evidence: old rows and hand-written demo data
    may contain arbitrary JSON.  Only a deterministic practice result with
    the three required primitive fields (and the optional activity scope) can
    make an activity count as worked.
    """

    if not isinstance(response, dict):
        return False
    keys = set(response)
    if not _RESULT_RESPONSE_REQUIRED_FIELDS <= keys:
        return False
    if keys - _RESULT_RESPONSE_REQUIRED_FIELDS - _RESULT_RESPONSE_OPTIONAL_FIELDS:
        return False
    question_index = response.get("question_index")
    selected_position = response.get("selected_position")
    if (
        isinstance(question_index, bool)
        or not isinstance(question_index, int)
        or question_index < 0
        or isinstance(selected_position, bool)
        or not isinstance(selected_position, int)
        or selected_position < 0
        or not isinstance(response.get("is_correct"), bool)
    ):
        return False
    if "activity_id" in response and (
        not isinstance(response["activity_id"], str)
        or not response["activity_id"].strip()
    ):
        return False
    return True


def _valid_result_responses(result):
    responses = result.responses if isinstance(result.responses, list) else []
    result_activity_id = getattr(result, "activity_id", None)
    has_result_activity_id = hasattr(result, "activity_id")
    return [
        response
        for response in responses
        if _is_valid_result_response(response)
        and (
            "activity_id" not in response
            or not has_result_activity_id
            or (
                result_activity_id not in (None, "")
                and str(response["activity_id"]) == str(result_activity_id)
            )
        )
    ]


def _has_valid_result_response(result):
    """Return whether a persisted result contains at least one valid response."""

    return bool(_valid_result_responses(result))


def _result_activity_catalog(session):
    """Index only activities available in the session's frozen roadmap."""

    if session is None or not session.roadmap_snapshot_id:
        return None
    from curriculum.roadmap import ordered_activities

    activities = ordered_activities(session.roadmap_snapshot.payload)
    catalog = {}
    for activity in activities:
        activity_id = activity["id"]
        # A legacy malformed snapshot may predate the publication guard.  It
        # is unsafe to choose one duplicate occurrence, so make every result
        # row fail closed instead of mixing its statistics or title.
        if activity_id in catalog:
            return {}
        catalog[activity_id] = activity
    return catalog


def _presented_roadmap_activity_ids(session, catalog):
    """Return roadmap activities that could have been opened in this session."""

    progress = GroupRoadmapProgress.objects.filter(session_id=session.pk).first()
    if progress is not None:
        if progress.roadmap_snapshot_id != session.roadmap_snapshot_id:
            # A cursor from another frozen roadmap cannot establish launch
            # history for this session.  Keep every result projection closed.
            return set()
        presented = {str(value) for value in (progress.completed_activity_ids or [])}
        if progress.current_activity_id:
            presented.add(str(progress.current_activity_id))
        # Corrupt/legacy progress may contain IDs outside the frozen catalog;
        # those IDs must not influence result navigation or pending flags.
        return presented & set(catalog)
    # Legacy/demo rows may predate the shared cursor.  A package snapshot is
    # not launch evidence: several later roadmap activities may reuse it.
    # Return no unworked activities; a valid persisted result is handled as
    # direct evidence by _result_row_activity_context instead.
    return set()


def _result_row_activity_context(result, session):
    """Return safe human context for a result row, or ``None`` when invalid."""

    if session is None:
        return None
    if str(result.result_batch_id) != str(session.result_batch_id):
        return None
    activity_id = str(result.activity_id or _LEGACY_RESULT_ACTIVITY_ID)
    catalog = _result_activity_catalog(session)
    if catalog is not None:
        activity = catalog.get(activity_id)
        if activity is None:
            return None
        # A valid persisted response is direct evidence that this activity
        # was opened, even for legacy sessions that predate the shared
        # cursor.  Empty/abandoned rows are not evidence: without a cursor,
        # their activity may still be a future roadmap step.
        progress = GroupRoadmapProgress.objects.filter(session_id=session.pk).first()
        presented_activity_ids = _presented_roadmap_activity_ids(session, catalog)
        if activity_id not in presented_activity_ids:
            # A present-but-mismatched cursor is tampered/invalid state, not
            # the legacy absence case.  Do not let a valid-looking result
            # bypass the fail-closed roadmap boundary.
            if progress is not None:
                return None
            if not _has_valid_result_response(result):
                return None
            # A legacy session has no cursor proving that a later activity
            # backed by another package was launched.  Keep the conservative
            # boundary used by its persisted base snapshot; a valid result
            # from that snapshot is still direct evidence for the worked row.
            expected_activity_snapshot_id = (
                activity.get("package_snapshot_id") or session.snapshot_id
            )
            if str(expected_activity_snapshot_id) != str(session.snapshot_id):
                return None
        expected_snapshot_id = activity.get("package_snapshot_id") or session.snapshot_id
        expected_snapshot = PublishedPackageSnapshot.objects.filter(
            pk=expected_snapshot_id
        ).only("pk", "version", "sha256").first()
        if expected_snapshot is None or not _result_matches_snapshot(
            result, expected_snapshot
        ):
            return None
    else:
        if activity_id != _LEGACY_RESULT_ACTIVITY_ID:
            # A session without a roadmap can only have emitted the close-time
            # sentinel.  Never let an arbitrary/future ID inherit the package
            # title through this legacy fallback.
            return None
        expected_snapshot = getattr(session, "snapshot", None)
        if expected_snapshot is None or not _result_matches_snapshot(
            result, expected_snapshot
        ):
            return None
    activity = catalog.get(activity_id) if catalog is not None else None
    if activity is None:
        payload = getattr(getattr(session, "snapshot", None), "payload", {}) or {}
        return {
            "unit_title": "Unidad",
            "lesson_title": "Lección",
            "activity_title": payload.get("title") or "Actividad",
        }
    return {
        "unit_title": activity.get("unit_title") or "Unidad",
        "lesson_title": activity.get("lesson_title") or "Lección",
        "activity_title": activity.get("title") or "Actividad",
    }


def _result_matches_snapshot(result, snapshot):
    """Require the complete immutable package snapshot identity on a result."""

    return (
        str(getattr(result, "snapshot_id", "")) == str(snapshot.pk)
        and getattr(result, "snapshot_version", None) == snapshot.version
        and getattr(result, "snapshot_sha256", None) == snapshot.sha256
    )


def _result_aggregate(results, session=None):
    """Build group-only metrics from activities that received a response.

    Closing a session deliberately retains an abandoned row for every
    participant/activity so the teacher can understand what happened.  Those
    rows are not evidence that the activity was worked.  The results surface
    therefore first removes rows without response payloads, then collapses
    duplicate participant/activity observations before counting activities or
    participants.  This also makes old rows and hand-created demo data obey
    the same contract as newly closed sessions.
    """

    result_list = list(results)
    sessions_by_batch = {}
    if session is None:
        batch_ids = {str(result.result_batch_id) for result in result_list}
        sessions_by_batch = {
            str(item.result_batch_id): item
            for item in ClassroomSession.objects.filter(
                result_batch_id__in=batch_ids
            ).select_related("snapshot", "snapshot__package", "roadmap_snapshot")
        }
    rows = []
    for result in result_list:
        result_session = session or sessions_by_batch.get(str(result.result_batch_id))
        activity_context = _result_row_activity_context(result, result_session)
        if activity_context is None:
            continue
        valid_responses = _valid_result_responses(result)
        if not valid_responses:
            continue
        activity_id = str(result.activity_id or _LEGACY_RESULT_ACTIVITY_ID)
        participant_key = str(result.participant_key)
        batch_id = str(result.result_batch_id)
        rows.append(
            (batch_id, activity_id, participant_key, result, valid_responses, activity_context)
        )

    # Keep one observation per participant/activity.  Prefer a completed row,
    # then the row with the richest response payload, and finally the newest
    # row (the queryset's normal ordering is newest first).
    observations = {}
    for (
        batch_id,
        activity_id,
        participant_key,
        result,
        valid_responses,
        activity_context,
    ) in rows:
        key = (batch_id, activity_id, participant_key)
        current = observations.get(key)
        candidate = (result, valid_responses, activity_context)
        if current is None:
            observations[key] = candidate
            continue
        current_result, current_responses, _current_context = current
        candidate_rank = (
            result.state == PseudonymousResult.STATE_COMPLETED,
            len(valid_responses),
        )
        current_rank = (
            current_result.state == PseudonymousResult.STATE_COMPLETED,
            len(current_responses),
        )
        if candidate_rank > current_rank:
            observations[key] = candidate

    observed = list(observations.values())
    by_activity = {}
    for result, valid_responses, activity_context in observed:
        activity_id = str(result.activity_id or _LEGACY_RESULT_ACTIVITY_ID)
        activity_key = (str(result.result_batch_id), activity_id)
        by_activity.setdefault(activity_key, []).append(
            (result, valid_responses, activity_context)
        )

    worked_activities = []
    for (_, activity_id), activity_rows in by_activity.items():
        # An activity is completed for the group when at least one valid
        # participant observation completed it; otherwise it was participated
        # in but interrupted.  Scores and support signals are summed across
        # unique participant observations, never duplicate result rows.
        completed = any(
            result.state == PseudonymousResult.STATE_COMPLETED
            for result, _, _ in activity_rows
        )
        durations = [
            result.duration_seconds
            for result, _, _ in activity_rows
            if result.duration_seconds is not None
        ]
        responses = [
            response
            for _, activity_responses, _ in activity_rows
            for response in activity_responses
        ]
        worked_activities.append(
            {
                "activity_id": activity_id,
                "state": (
                    PseudonymousResult.STATE_COMPLETED
                    if completed
                    else PseudonymousResult.STATE_ABANDONED
                ),
                "participants": len(activity_rows),
                "score_total": sum(
                    sum(1 for response in valid_responses if response["is_correct"])
                    for _, valid_responses, _ in activity_rows
                ),
                "help_count": sum(
                    len(result.help_requests or [])
                    for result, _, _ in activity_rows
                ),
                "technical_error_count": sum(
                    len(result.technical_errors or [])
                    for result, _, _ in activity_rows
                ),
                "duration_total_seconds": sum(durations),
                "response_count": len(responses),
                "results": [result for result, _, _ in activity_rows],
                **activity_rows[0][2],
            }
        )

    if session is not None and session.roadmap_snapshot_id:
        # QuerySets are intentionally newest-first for the register, but an
        # export is a roadmap report: its rows follow the frozen curriculum
        # order and remain deterministic across result creation timing.
        from curriculum.roadmap import ordered_activities

        activity_order = {
            activity["id"]: index
            for index, activity in enumerate(
                ordered_activities(session.roadmap_snapshot.payload)
            )
        }
        worked_activities.sort(
            key=lambda activity: (
                activity_order.get(activity["activity_id"], len(activity_order)),
                activity["activity_id"],
            )
        )

    completed_count = sum(
        activity["state"] == PseudonymousResult.STATE_COMPLETED
        for activity in worked_activities
    )
    abandoned_count = sum(
        activity["state"] == PseudonymousResult.STATE_ABANDONED
        for activity in worked_activities
    )
    participant_count = len(
        {
            (batch_id, participant_key)
            for batch_id, _, participant_key, _, _, _ in rows
        }
    )
    durations = [
        result.duration_seconds
        for result, _, _ in observed
        if result.duration_seconds is not None
    ]
    score_total = sum(activity["score_total"] for activity in worked_activities)
    response_count = sum(activity["response_count"] for activity in worked_activities)
    activity_results = [
        result for activity in worked_activities for result in activity["results"]
    ]
    snapshot_labels = sorted(
        {
            f"versión {result.snapshot_version} · {result.snapshot_sha256[:8]}"
            for result in activity_results
            if result.snapshot_sha256
        }
    )
    distribution = {
        "Completadas": completed_count,
        "Interrumpidas": abandoned_count,
    }
    return {
        # Compatibility keys remain available to the review surface; rendered
        # results and exports choose only the aggregate-safe projections.
        "count": len(worked_activities),
        "response_count": response_count,
        "participation_count": len(observed),
        "activities_worked": len(worked_activities),
        "worked_activities": worked_activities,
        "completed_count": completed_count,
        "score_total": score_total,
        "score_average": score_total / len(observed) if observed else 0,
        "help_count": sum(activity["help_count"] for activity in worked_activities),
        "technical_error_count": sum(
            activity["technical_error_count"] for activity in worked_activities
        ),
        # Teacher-facing group vocabulary.
        "participants": participant_count,
        "participant_count": participant_count,
        "activities_completed": completed_count,
        "activities_participated": len(worked_activities),
        "is_demo": bool(
            getattr(getattr(session, "snapshot", None), "package", None)
            and getattr(session.snapshot.package, "is_demo", False)
        ),
        "distribution": distribution,
        "result_distribution": distribution,
        "duration_total_seconds": sum(durations),
        "duration_average_seconds": (
            sum(durations) / len(durations) if durations else 0
        ),
        "snapshot_labels": snapshot_labels,
        "snapshot_versions": sorted({result.snapshot_version for result in activity_results}),
        "snapshot_hashes": sorted(
            {result.snapshot_sha256[:8] for result in activity_results if result.snapshot_sha256}
        ),
    }


def _individual_result_register(results, session):
    """Prepare the opt-in teacher register with short opaque labels only."""

    # The opt-in register is the existing #86 observation surface.  It may
    # retain an interrupted turn with no response, while the aggregate above
    # deliberately excludes that row from worked statistics.
    results = list(results)

    grouped = {}
    for result in results:
        activity_context = _result_row_activity_context(result, session)
        if activity_context is None:
            continue
        participant_key = str(result.participant_key)
        participant = grouped.setdefault(
            participant_key,
            {
                "label": participant_key[:8],
                "activities": [],
            },
        )
        participant["activities"].append(
            {
                "title": activity_context["activity_title"],
                "state": result.get_state_display(),
            }
        )
    return sorted(grouped.values(), key=lambda item: item["label"])


def _roadmap_results_navigation(session, aggregate, *, include_unworked=False):
    """Return a presentation-only roadmap tree for the results screen.

    The published roadmap remains the source of order and titles.  Result rows
    only annotate activities that were actually worked; activities without a
    response are omitted from the default view and can be explicitly shown as
    "Sin participación" without being described as pending or deficient.
    """

    if not session.roadmap_snapshot_id:
        return []
    from curriculum.roadmap import ordered_activities

    roadmap_activities = ordered_activities(session.roadmap_snapshot.payload)
    catalog = _result_activity_catalog(session)
    if catalog is None or len(catalog) != len(roadmap_activities):
        # A legacy snapshot with duplicate activity IDs cannot be rendered
        # safely because its title/state join is ambiguous.
        return []
    presented_activity_ids = _presented_roadmap_activity_ids(session, catalog)
    worked = {
        item["activity_id"]: item for item in aggregate.get("worked_activities", [])
    }
    units = []
    unit_by_id = {}
    lesson_by_key = {}
    for activity in roadmap_activities:
        result = worked.get(activity["id"])
        if activity["id"] not in presented_activity_ids and result is None:
            continue
        if include_unworked and result is not None:
            continue
        if result is None and not include_unworked:
            continue
        unit = unit_by_id.get(activity["unit_id"])
        if unit is None:
            unit = {"title": activity["unit_title"], "lessons": []}
            unit_by_id[activity["unit_id"]] = unit
            units.append(unit)
        lesson_key = (activity["unit_id"], activity["lesson_id"])
        lesson = lesson_by_key.get(lesson_key)
        if lesson is None:
            lesson = {"title": activity["lesson_title"], "activities": []}
            lesson_by_key[lesson_key] = lesson
            unit["lessons"].append(lesson)
        lesson["activities"].append(
            {
                "title": activity["title"],
                "state": (
                    "Completada"
                    if result and result["state"] == PseudonymousResult.STATE_COMPLETED
                    else "Participación registrada"
                    if result
                    else "Sin participación"
                ),
                "participants": result["participants"] if result else 0,
            }
        )
    return units


def _result_card_context(session, aggregate, *, include_unworked=False):
    """Add the stable roadmap/session navigation data consumed by both UIs."""

    from curriculum.roadmap import ordered_activities

    roadmap_activities = (
        ordered_activities(session.roadmap_snapshot.payload)
        if session.roadmap_snapshot_id
        else []
    )
    catalog = _result_activity_catalog(session)
    roadmap_activity_ids = (
        _presented_roadmap_activity_ids(session, catalog)
        if catalog is not None and len(catalog) == len(roadmap_activities)
        else set()
    )
    worked_activity_ids = {
        item["activity_id"] for item in aggregate.get("worked_activities", [])
    }
    return {
        "roadmap_navigation": _roadmap_results_navigation(
            session, aggregate, include_unworked=include_unworked
        ),
        "has_unworked_activities": bool(
            roadmap_activity_ids - worked_activity_ids
        ),
    }


@teacher_required
def tutor_results(request):
    """List worked activities by default, with an explicit no-participation view."""

    show_unworked = request.GET.get("vista") == "sin-participacion"

    sessions = _teacher_sessions(request).filter(
        status=ClassroomSession.STATUS_CLOSED
    ).select_related(
        "snapshot", "snapshot__package", "roadmap_snapshot", "classroom_group"
    )[:30]
    result_cards = []
    has_unworked_sessions = False
    for session in sessions:
        aggregate = _result_aggregate(
            PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id),
            session=session,
        )
        card = {"session": session, "aggregate": aggregate}
        card.update(
            _result_card_context(
                session, aggregate, include_unworked=show_unworked
            )
        )
        if card["has_unworked_activities"]:
            has_unworked_sessions = True
        if show_unworked or aggregate["count"]:
            result_cards.append(card)
    groups = ClassroomGroup.objects.filter(created_by=request.user)
    group_cards = []
    for group in groups:
        group_sessions = list(
            ClassroomSession.objects.filter(
                classroom_group=group,
                status=ClassroomSession.STATUS_CLOSED,
            )
        )
        if not group_sessions:
            continue
        batch_ids = [session.result_batch_id for session in group_sessions]
        group_cards.append(
            {
                "group": group,
                "aggregate": _result_aggregate(
                    PseudonymousResult.objects.filter(result_batch_id__in=batch_ids)
                ),
                "survey": survey_aggregate(
                    PseudonymousSurveyResponse.objects.filter(
                        result_batch_id__in=batch_ids
                    )
                ),
            }
        )
    return render(
        request,
        "curriculum/tutor_results.html",
        {
            "result_cards": result_cards,
            "group_cards": group_cards,
            "show_unworked": show_unworked,
            "has_unworked_sessions": has_unworked_sessions,
        },
    )


@teacher_required
def tutor_group_results(request, group_id):
    group = _teacher_group_or_404(request, group_id)
    sessions = ClassroomSession.objects.filter(
        classroom_group=group,
        status=ClassroomSession.STATUS_CLOSED,
    )
    batch_ids = sessions.values_list("result_batch_id", flat=True)
    return render(
        request,
        "curriculum/tutor_group_results.html",
        {
            "group": group,
            "sessions": sessions,
            "aggregate": _result_aggregate(
                PseudonymousResult.objects.filter(result_batch_id__in=batch_ids)
            ),
            "survey_aggregate": survey_aggregate(
                PseudonymousSurveyResponse.objects.filter(
                    result_batch_id__in=batch_ids
                )
            ),
        },
    )


@teacher_required
def tutor_session_results(request, session_id):
    """Show one session's group summary, never an individual dossier."""

    session = _teacher_session_or_404(
        request,
        session_id,
        ClassroomSession.objects.select_related(
            "snapshot", "snapshot__package", "roadmap_snapshot"
        ),
    )
    aggregate = _result_aggregate(
        PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id),
        session=session,
    )
    show_unworked = request.GET.get("vista") == "sin-participacion"
    return render(
        request,
        "curriculum/tutor_session_results.html",
        {
            "session": session,
            "aggregate": aggregate,
            "survey_aggregate": survey_aggregate(_session_survey_responses(session)),
            "show_unworked": show_unworked,
            **_result_card_context(
                session, aggregate, include_unworked=show_unworked
            ),
        },
    )


@teacher_required
@require_POST
def tutor_group_close_year(request, group_id):
    """Explicitly erase only a group's results and star ratings."""

    group = _teacher_group_or_404(request, group_id)
    if request.POST.get("confirm") != "CERRAR":
        return HttpResponseBadRequest(
            "Confirma el cierre de año antes de borrar. No se borró ningún dato."
        )
    with transaction.atomic():
        batch_ids = list(
            ClassroomSession.objects.filter(classroom_group=group).values_list(
                "result_batch_id", flat=True
            )
        )
        deleted_results, _ = PseudonymousResult.objects.filter(
            result_batch_id__in=batch_ids
        ).delete()
        deleted_surveys, _ = PseudonymousSurveyResponse.objects.filter(
            result_batch_id__in=batch_ids
        ).delete()
    return redirect("tutor-groups")


def _session_survey_responses(session):
    return PseudonymousSurveyResponse.objects.filter(
        result_batch_id=session.result_batch_id,
    )


def _result_export_payload(activity):
    """Return one aggregate-safe activity row without technical identifiers."""

    return {
        "unit_title": activity["unit_title"],
        "lesson_title": activity["lesson_title"],
        "activity_title": activity["activity_title"],
        "state": (
            "completed"
            if activity["state"] == PseudonymousResult.STATE_COMPLETED
            else "abandoned"
        ),
        "participants": activity["participants"],
        "duration_seconds": activity["duration_total_seconds"],
        "response_count": activity["response_count"],
        "score": activity["score_total"],
        "help_count": activity["help_count"],
        "technical_error_count": activity["technical_error_count"],
    }


def _csv_safe_text(value):
    """Neutralize spreadsheet formulas without changing JSON/UI titles.

    Spreadsheet applications may interpret a cell as a formula when a value
    starts with ``=``, ``+``, ``-`` or ``@``.  Some importers also ignore
    leading spaces, tabs and control characters, so inspect past that prefix
    before deciding whether to add the literal-text apostrophe.  csv.DictWriter
    still owns quoting and newline escaping after this narrow transformation.
    """

    if not isinstance(value, str) or not value:
        return value
    index = 0
    while index < len(value):
        character = value[index]
        if (
            character.isspace()
            or unicodedata.category(character) in {"Cc", "Cf"}
        ):
            index += 1
            continue
        break
    if index < len(value) and value[index] in "=+-@":
        return "'" + value
    return value


@teacher_required

@require_POST
def tutor_session_export(request, session_id):
    session = _teacher_session_or_404(request, session_id)
    if session.status != ClassroomSession.STATUS_CLOSED:
        return HttpResponseBadRequest("Sólo se pueden exportar sesiones cerradas.")
    results = PseudonymousResult.objects.filter(
        result_batch_id=session.result_batch_id,
    )
    # The export is deliberately aggregate-only.  Participant labels,
    # activity IDs, snapshot IDs/hashes and raw response payloads are all
    # pseudonymous or technical identifiers and are not part of #100's
    # /resultados/ projection surface.
    aggregate = _result_aggregate(results, session=session)
    payload = [_result_export_payload(activity) for activity in aggregate["worked_activities"]]
    export_format = request.POST.get("format", "json").lower()
    if export_format == "json":
        # JSON incluye también el resumen agregado de la encuesta seudonimizada.
        response = JsonResponse(
            {"results": payload, "survey": survey_aggregate(_session_survey_responses(session))}
        )
        response["Content-Disposition"] = (
            'attachment; filename="aulalista-resultados.json"'
        )
        return response
    if export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "unit_title",
                "lesson_title",
                "activity_title",
                "state",
                "participants",
                "duration_seconds",
                "response_count",
                "score",
                "help_count",
                "technical_error_count",
            ],
        )
        writer.writeheader()
        for result in payload:
            writer.writerow(
                {
                    **result,
                    "unit_title": _csv_safe_text(result["unit_title"]),
                    "lesson_title": _csv_safe_text(result["lesson_title"]),
                    "activity_title": _csv_safe_text(result["activity_title"]),
                }
            )
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="aulalista-resultados.csv"'
        )
        return response
    return HttpResponseBadRequest("El formato de exportación no está disponible.")


@teacher_required

@require_POST
def tutor_session_results_delete(request, session_id):
    session = _teacher_session_or_404(request, session_id)
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
    detail = f"{deleted} resultado"
    if deleted != 1:
        detail += "s"
    if deleted_surveys:
        detail += f" y {deleted_surveys} encuesta"
        if deleted_surveys != 1:
            detail += "s"
    messages.success(request, f"Se borraron {detail} de la sesión.")
    return redirect("tutor-home")


@teacher_required

@require_POST
def tutor_result_delete(request, session_id, result_id):
    session = _teacher_session_or_404(request, session_id)
    if session.status != ClassroomSession.STATUS_CLOSED:
        return HttpResponseBadRequest("Sólo se pueden eliminar resultados de una sesión cerrada.")
    result = get_object_or_404(
        PseudonymousResult,
        pk=result_id,
        result_batch_id=session.result_batch_id,
    )
    result.delete()
    messages.success(request, "Se borró el resultado de la sesión.")
    return redirect("tutor-home")


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
        rating=answers,
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


def _run_import_job_stage_once(job_id, stage, payload=None):
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
        if job.cancel_requested:
            _finish_cancelled_import_stage(job)
            return
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
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            _finish_cancelled_import_stage(job)
    except Exception as error:  # noqa: BLE001 - the worker must never die silently
        import traceback

        if isinstance(error, OperationalError) and "locked" in str(error).lower():
            # SQLite lock contention is transient while the waiting page polls;
            # let the bounded wrapper retry the stage instead of recording a
            # false pipeline failure.
            raise

        failure_traceback = traceback.format_exc()
        job = CurriculumImportJob.objects.filter(pk=job_id).first()
        if job:
            job.status = fallback_status[stage]
            job.error_message = str(error)[:500]
            job.progress_stage = ""
            job.progress_finished_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "error_message",
                    "progress_stage",
                    "progress_finished_at",
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

            if not getattr(connection, "in_atomic_block", False):
                try:
                    connection.close()
                except Exception:
                    pass


def _run_import_job_stage(job_id, stage, payload=None):
    """Run a stage with bounded retries for transient SQLite lock contention."""

    for attempt in range(8):
        try:
            return _run_import_job_stage_once(job_id, stage, payload)
        except OperationalError as error:
            if "locked" not in str(error).lower():
                raise
            if attempt == 7:
                fallback_status = {
                    "extract": CurriculumImportJob.STATUS_FAILED,
                    "subtopics": CurriculumImportJob.STATUS_SUBTOPICS_PROPOSED,
                    "activities": CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
                    "add_missing": CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
                }
                # The worker may be a daemon: never leave the waiting page in
                # an unobservable running state after exhausting lock retries.
                CurriculumImportJob.objects.filter(pk=job_id).update(
                    status=fallback_status[stage],
                    error_message=(
                        "La etapa se detuvo después de varios bloqueos de la base local. "
                        "Puedes reintentarlo."
                    ),
                    progress_stage="",
                    progress_finished_at=timezone.now(),
                    updated_at=timezone.now(),
                )
                return None
            time.sleep(0.05 * (attempt + 1))


def _start_import_stage(request, job, stage, payload=None):
    """Mark the stage as running and hand it to the background runner."""

    started_at = timezone.now()
    claimed = CurriculumImportJob.objects.filter(
        pk=job.pk,
        progress_stage="",
    ).update(
        progress_stage=stage,
        progress_done=0,
        progress_total=0,
        progress_started_at=started_at,
        progress_finished_at=None,
        error_message="",
        cancel_requested=False,
        cancelled_at=None,
        updated_at=started_at,
    )
    if not claimed:
        # Compare-and-set closes the stale-request race: only one worker starts.
        return redirect("tutor-import-wait", job_id=job.pk)
    if hasattr(request, "session"):
        request.session[f"legacy_stage_{job.pk}"] = stage
    _import_stage_runner()(_run_import_job_stage, job.pk, stage, payload)
    return redirect("tutor-import-wait", job_id=job.pk)


def _finish_cancelled_import_stage(job, expected_claim_token=None):
    from curriculum.interpretation_commands import finish_cancelled_stage

    token = expected_claim_token or getattr(job, "interpretation_claim_token", None)
    return finish_cancelled_stage(job, expected_claim_token=token)


IMPORT_STAGE_WAIT_MESSAGES = {
    "extract": "El asistente virtual está leyendo los temas…",
    "subtopics": "El asistente virtual está organizando los subtemas…",
    "activities": "El asistente virtual está creando las actividades…",
    "add_missing": "El asistente virtual está agregando las actividades que faltan…",
}

# Safety valve: if the worker died with the server (or hangs), stop waiting.
IMPORT_STAGE_TIMEOUT = timedelta(minutes=90)


def _release_stale_import_stage(job):
    stale = bool(
        job.progress_stage
        and job.progress_started_at
        and timezone.now() - job.progress_started_at > IMPORT_STAGE_TIMEOUT
    )
    if not stale:
        return False
    job.progress_stage = ""
    job.progress_finished_at = timezone.now()
    job.error_message = (
        "El asistente virtual tardó demasiado y el proceso se detuvo. "
        "Puedes reintentarlo."
    )
    job.save(
        update_fields=[
            "progress_stage",
            "progress_finished_at",
            "error_message",
            "updated_at",
        ]
    )
    return True


CLAIM_STAGE_INTERPRETING = "reading_pdf"
ACTIVE_INTERPRETATION_STAGES = {CLAIM_STAGE_INTERPRETING}
DEFAULT_WAIT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 0.05


def _sync_job_from_model(target, source):
    """Synchronize relevant operational fields into caller's in-memory job instance."""
    target.interpretation_dossier = source.interpretation_dossier
    target.interpretation_claim_token = source.interpretation_claim_token
    target.interpretation_claimed_at = source.interpretation_claimed_at
    target.interpretation_state = source.interpretation_state
    target.progress_stage = source.progress_stage
    target.progress_started_at = source.progress_started_at
    target.progress_finished_at = source.progress_finished_at
    target.progress_done = source.progress_done
    target.progress_total = source.progress_total
    target.page_count = source.page_count
    target.interpretation_error_message = getattr(source, "interpretation_error_message", "")
    target.error_message = source.error_message


def _execute_with_db_lock_retry(func, max_attempts=40, base_delay=0.01, max_delay=0.1, using=None):
    """Execute a callable, retrying on transient SQLite OperationalError (table/database locked).

    Safe cleanup policy:
    - If called outside an active transaction (in_atomic_block is False), closes the connection
      between retries to reset transient lock states on SQLite.
    - If called inside an active transaction (in_atomic_block is True), DOES NOT close the
      connection or alter the caller's transaction ownership, avoiding ProgrammingError
      ('Cannot operate on a closed database') and preserving caller transaction integrity.
    - Permanent locks are never hidden: if max_attempts is exhausted, the original exception is raised.
    """
    import random
    from django.db import connection, connections
    from django.db.utils import OperationalError

    target_conn = connections[using] if using else connection
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return func()
        except OperationalError as exc:
            msg = str(exc).lower()
            if "locked" in msg or "busy" in msg:
                last_exc = exc
                if not getattr(target_conn, "in_atomic_block", False):
                    try:
                        target_conn.close()
                    except Exception:
                        pass
                sleep_time = min(max_delay, base_delay * (1.3 ** attempt)) + random.uniform(0.001, 0.01)
                time.sleep(sleep_time)
                continue
            raise
    if last_exc:
        raise last_exc


DEFAULT_INTERPRETATION_CLAIM_TIMEOUT = timedelta(minutes=10)


def trigger_job_interpretation(
    job,
    wait_timeout=DEFAULT_WAIT_TIMEOUT,
    poll_interval=DEFAULT_POLL_INTERVAL,
    stale_threshold=DEFAULT_INTERPRETATION_CLAIM_TIMEOUT,
):
    """Trigger V0 source interpretation once, saving the dossier on the job.

    Concurrency and idempotency contract with durable claim token:
    - Exactly one caller claims the interpretation via CAS: interpretation_claim_token IS NULL
      (or stale beyond stale_threshold) and interpretation_dossier is empty, generating an owner UUID.
    - progress_stage remains purely for UX reporting; prepare() can set or clear it
      without affecting claim ownership.
    - Owner runs CurriculumSourceInterpreter.prepare outside any open database transaction.
    - Success: Atomic conditional UPDATE (pk + owner token + empty dossier) persists dossier,
      sets progress_stage='', and clears claim_token/claimed_at in a single operation.
    - Error: Atomic conditional UPDATE (pk + owner token) records error and clears claim.
      Never overwrites foreign state/error.
    - If final UPDATE rows=0: Ownership was lost. Re-reads DB: if a valid dossier was persisted
      by another owner, returns it; if an error was recorded, raises it; otherwise raises
      CurriculumInterpretationError('Se perdió el reclamo...'). Never returns unpersisted local dossier.
    - Waiters detect active claim via interpretation_claim_token (not progress_stage) and poll
      boundedly without DB locks, returning the persisted dossier or propagating owner domain error.
    """
    from django.db import connection
    from django.db.utils import OperationalError
    from curriculum.source_interpreter import (
        CurriculumInterpretationError,
        CurriculumSourceInterpreter,
    )

    if isinstance(stale_threshold, (int, float)):
        stale_threshold = timedelta(seconds=stale_threshold)

    # 1. Check in database before attempting claim
    def _read_fresh():
        return CurriculumImportJob.objects.filter(pk=job.pk).first()

    fresh = _execute_with_db_lock_retry(_read_fresh)
    if fresh is None:
        raise CurriculumInterpretationError(f"El trabajo de importación #{job.pk} no existe.")
    if fresh.has_valid_ready_dossier():
        # Fast reconciliation of existing valid dossier:
        # Only reconcile to READY if claim_token is NULL.
        # If there is an active foreign claim, DO NOT clear or overwrite the claim token!
        if fresh.interpretation_claim_token is None:
            if getattr(fresh, "interpretation_state", None) != CurriculumImportJob.INTERPRETATION_STATE_READY:
                from curriculum.interpretation_commands import reconcile_existing_ready_dossier

                reconcile_existing_ready_dossier(fresh)
                fresh.interpretation_state = CurriculumImportJob.INTERPRETATION_STATE_READY
                fresh.interpretation_error_message = ""
        _sync_job_from_model(job, fresh)
        return fresh.get_interpretation_dossier()

    # 3. Compare-and-set atomic claim using dedicated interpretation_claim_token:
    # Claim if interpretation_claim_token IS NULL or if claimed_at <= now - stale_threshold.
    owner_token = uuid.uuid4()
    now = timezone.now()

    from curriculum.interpretation_commands import (
        claim_interpretation_worker,
        finish_worker_failure,
        finish_worker_success,
    )
    from curriculum.source_interpreter import InterpretationCancelledError

    def _attempt_claim():
        return claim_interpretation_worker(
            job,
            owner_token=owner_token,
            stale_threshold=stale_threshold,
            now=now,
        )

    rows_claimed = _execute_with_db_lock_retry(_attempt_claim)

    if rows_claimed == 1:
        # OWNER PATH: compute outside any open database transaction
        job.interpretation_claim_token = owner_token
        job.interpretation_claimed_at = now
        job.interpretation_state = CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        try:
            dossier = CurriculumSourceInterpreter.prepare(
                job,
                timeout_seconds=wait_timeout,
                is_cancelled=lambda: _execute_with_db_lock_retry(
                    lambda: CurriculumImportJob.objects.filter(
                        pk=job.pk, cancel_requested=True
                    ).exists()
                ),
            )
        except Exception as exc:
            logger.warning(
                "Fallo durante la interpretación del trabajo %s: %s", job.pk, exc
            )
            now_dt = timezone.now()

            def _save_failure():
                return finish_worker_failure(
                    job,
                    owner_token=owner_token,
                    error_message=str(exc),
                    is_cancelled=isinstance(exc, InterpretationCancelledError),
                    now=now_dt,
                )

            try:
                rows_failed = _execute_with_db_lock_retry(_save_failure)
                fresh_failed = _execute_with_db_lock_retry(_read_fresh)
                if fresh_failed:
                    _sync_job_from_model(job, fresh_failed)
            except Exception as clear_exc:
                logger.error("No se pudo limpiar claim tras fallo en job %s: %s", job.pk, clear_exc)

            if isinstance(exc, OperationalError):
                raise CurriculumInterpretationError(
                    f"Fallo por bloqueo de base de datos durante la interpretación: {exc}"
                ) from exc
            raise

        # Prepare succeeded: atomically persist dossier and release claim
        now_dt = timezone.now()

        def _save_success():
            return finish_worker_success(
                job,
                owner_token=owner_token,
                dossier=dossier,
                now=now_dt,
            )

        rows_persisted = _execute_with_db_lock_retry(_save_success)
        if rows_persisted == 1:
            fresh_saved = _execute_with_db_lock_retry(_read_fresh)
            if fresh_saved:
                _sync_job_from_model(job, fresh_saved)
                return fresh_saved.get_interpretation_dossier()
            job.refresh_from_db()
            return job.get_interpretation_dossier()

        # rows_persisted == 0: Ownership was lost!
        # NUNCA retornar dossier local ni declarar éxito.
        # Refresca DB y retorna sólo dossier persistido por dueño vigente o error honesto/acotado.
        fresh_lost = _execute_with_db_lock_retry(_read_fresh)
        if fresh_lost:
            _sync_job_from_model(job, fresh_lost)
            foreign_dossier = fresh_lost.get_interpretation_dossier()
            if foreign_dossier is not None:
                return foreign_dossier
            foreign_err = getattr(fresh_lost, "interpretation_error_message", "").strip()
            if foreign_err:
                raise CurriculumInterpretationError(foreign_err)

        raise CurriculumInterpretationError(
            f"Se perdió el reclamo de interpretación del trabajo #{job.pk} antes de persistir."
        )

    # WAITER PATH: Caller did not win claim; bounded polling without DB locks
    # Detects claim via interpretation_claim_token, not progress_stage
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            current = CurriculumImportJob.objects.filter(pk=job.pk).first()
        except OperationalError as exc:
            msg = str(exc).lower()
            if "locked" in msg or "busy" in msg:
                continue
            raise CurriculumInterpretationError(
                f"Error de base de datos para trabajo #{job.pk}: {exc}"
            ) from exc

        if current is None:
            raise CurriculumInterpretationError(f"El trabajo de importación #{job.pk} no existe.")

        dossier = current.get_interpretation_dossier()
        if dossier is not None:
            _sync_job_from_model(job, current)
            return dossier

        current_err = getattr(current, "interpretation_error_message", "").strip()
        if current_err:
            _sync_job_from_model(job, current)
            raise CurriculumInterpretationError(current_err)

        # Waiter checks interpretation_claim_token, not progress_stage
        if current.interpretation_claim_token is None:
            time.sleep(0.02)
            try:
                refreshed = CurriculumImportJob.objects.filter(pk=job.pk).first()
            except OperationalError:
                refreshed = None
            if refreshed:
                dossier = refreshed.get_interpretation_dossier()
                if dossier is not None:
                    _sync_job_from_model(job, refreshed)
                    return dossier
                refreshed_err = getattr(refreshed, "interpretation_error_message", "").strip()
                if refreshed_err:
                    _sync_job_from_model(job, refreshed)
                    raise CurriculumInterpretationError(refreshed_err)
            raise CurriculumInterpretationError(
                f"El proceso de interpretación del trabajo #{job.pk} finalizó sin generar dossier ni error."
            )

    raise CurriculumInterpretationError(
        f"Tiempo de espera agotado ({wait_timeout}s) aguardando la interpretación del trabajo #{job.pk}."
    )


STALE_STAGE_ERROR_MESSAGE = (
    "El asistente virtual tardó demasiado y el proceso se detuvo. "
    "Puedes reintentarlo."
)
STALE_STAGE_DELAYED_MESSAGE = "Está tardando más de lo esperado; aún puede terminar"


def _normalize_datetime(dt):
    """Safely convert naive or aware datetimes to the active timezone, handling None robustly."""
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _is_import_stage_stale(job, now=None):
    """Pure query checking whether the current job progress_stage or active claim has exceeded timeout."""
    if now is None:
        now = timezone.now()
    else:
        now = _normalize_datetime(now)

    # Check progress_stage staleness
    if job.progress_stage and job.progress_started_at:
        started_at = _normalize_datetime(job.progress_started_at)
        if started_at and (now - started_at) > IMPORT_STAGE_TIMEOUT:
            return True

    # Check interpretation claim staleness
    if job.interpretation_claim_token and job.interpretation_claimed_at:
        claimed_at = _normalize_datetime(job.interpretation_claimed_at)
        if claimed_at and (now - claimed_at) > IMPORT_STAGE_TIMEOUT:
            return True

    return False


def _is_valid_ready_interpretation_dossier(job, pdf_bytes: bytes | None = None):
    """Pure query checking if the job possesses a valid, ready, deserializable ImportDossier.
    Never mutates persistence. Delegates to model method has_valid_ready_dossier().
    """
    raw = getattr(job, "interpretation_dossier", None)
    if not raw or not isinstance(raw, dict):
        return False
    # Strict explicit raw key verification prior to deserialization
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return False
    if raw.get("status") != "active":
        return False
    source_sha = raw.get("source_sha256")
    if not isinstance(source_sha, str) or not bool(re.fullmatch(r"^[0-9a-fA-F]{64}$", source_sha.strip())):
        return False

    if hasattr(job, "has_valid_ready_dossier"):
        return job.has_valid_ready_dossier(pdf_bytes=pdf_bytes)
    dossier = job.get_interpretation_dossier()
    if dossier is None or getattr(dossier, "version", 0) < 1:
        return False
    if getattr(dossier, "status", "") != "active":
        return False
    if pdf_bytes is None:
        if not getattr(job, "pdf", None):
            return False
        try:
            with job.pdf.open("rb") as stream:
                pdf_bytes = stream.read()
        except (FileNotFoundError, OSError, IOError, ValueError):
            return False
    current_sha = hashlib.sha256(pdf_bytes).hexdigest()
    return current_sha.lower() == source_sha.strip().lower()


def _import_progress_state(job, has_valid_dossier=None):
    legacy_active = job.progress_stage in IMPORT_STAGE_WAIT_MESSAGES
    interp_state = getattr(job, "interpretation_state", None)
    if interp_state == CurriculumImportJob.INTERPRETATION_STATE_READY and not legacy_active:
        if has_valid_dossier is None:
            has_valid_dossier = _is_valid_ready_interpretation_dossier(job)
        if has_valid_dossier:
            return "finished"
    if job.cancel_requested or job.cancelled_at:
        return "error"
    interp_error = getattr(job, "interpretation_error_message", "").strip()
    if (interp_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED or interp_error) and not legacy_active:
        return "error"
    if job.progress_stage or (job.interpretation_claim_token and not job.interpretation_dossier):
        if job.progress_done:
            return "partial"
        if job.progress_total:
            return "working"
        return "waiting"
    if job.interpretation_dossier:
        if interp_state == CurriculumImportJob.INTERPRETATION_STATE_READY:
            if has_valid_dossier is None:
                has_valid_dossier = _is_valid_ready_interpretation_dossier(job)
            if not has_valid_dossier:
                return "error"
    if job.status in (CurriculumImportJob.STATUS_COMPLETED, CurriculumImportJob.STATUS_CONVERTED):
        return "finished"
    if not job.progress_stage and job.progress_done and job.progress_done == job.progress_total:
        return "finished"
    return "waiting"


IMPORT_PROGRESS_LABELS = {
    "waiting": "Esperando al asistente",
    "working": "El asistente está trabajando",
    "partial": "Hay un resultado parcial guardado",
    "finished": "Planeación organizada/lista para revisar",
    "error": "La generación se interrumpió",
    "delayed": STALE_STAGE_DELAYED_MESSAGE,
}


SAFE_ERROR_GENERIC = "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo."
SAFE_ERROR_INTERRUPTED = "La generación se interrumpió."
SAFE_ERROR_CANCELLED = "Interpretación cancelada a petición."
SAFE_ERROR_CANCELLED_TEACHER = "Cancelado por el docente."
SAFE_ERROR_INTERPRETATION = "Error durante la interpretación del PDF."
SAFE_ERROR_STREAM_READ = "No pudimos leer el archivo PDF de la planeación. Puedes volver a intentarlo."
SAFE_ERROR_INTEGRITY_MISMATCH = "Alerta de integridad: El archivo PDF de la planeación no coincide con la evidencia registrada. Se requiere reextracción explícita."
SAFE_ERROR_INTEGRITY_ALTERED_DURING = "Alerta de integridad: El archivo PDF de la planeación fue alterado durante el procesamiento. Se requiere reextracción explícita."
SAFE_ERROR_INTEGRITY_DISK = "Alerta de integridad: El archivo PDF en disco fue alterado. Dossier invalidado."
SAFE_ERROR_INTEGRITY_SERVER = "Conflicto de integridad: El archivo PDF en el servidor fue alterado."
SAFE_ERROR_PDF_UNAVAILABLE = "El archivo PDF de la currícula no está disponible o no se puede leer."
SAFE_ERROR_TIMEOUT = "Tiempo de espera excedido al organizar la planeación. Puedes volver a intentarlo."

_SQL_KEYWORD_PATTERN = re.compile(
    r"\b(select\b|insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|where\b)",
    re.IGNORECASE,
)
_FILE_PATH_PATTERN = re.compile(r"(?:/|[a-zA-Z]:\\)[\w.-]+", re.IGNORECASE)


def _sanitize_teacher_error_message(err_msg: str) -> str:
    """Return a brief, safe, teacher-facing explanation. Fail-closed against any secret or trace.
    Completely removes stack traces, internal exceptions, model/prompt jargon, paths, URLs, SQL,
    and credentials. Never returns input or concatenates input: returns exclusively fixed teacher constants."""
    if not err_msg or not isinstance(err_msg, str):
        return SAFE_ERROR_INTERRUPTED

    clean = err_msg.strip()
    if not clean:
        return SAFE_ERROR_INTERRUPTED

    # Any multiline string is immediately rejected to prevent stack trace leaks
    if "\n" in clean or "\r" in clean:
        return SAFE_ERROR_GENERIC

    lower = clean.lower()

    # Secret / token / sensitive credentials / emails / tokens
    if any(s in lower for s in ("sk-", "api_key", "secret", "token=", "password", "bearer ", "@", "eyj")):
        return SAFE_ERROR_GENERIC

    # URLs or local file paths (Unix / Windows)
    if "http://" in lower or "https://" in lower or lower.startswith("file ") or _FILE_PATH_PATTERN.search(clean):
        return SAFE_ERROR_GENERIC

    # SQL patterns
    if _SQL_KEYWORD_PATTERN.search(clean):
        return SAFE_ERROR_GENERIC

    # Fixed domain categories -> ONLY return fixed teacher constants
    if "cancelad" in lower or "petición" in lower:
        if "docente" in lower:
            return SAFE_ERROR_CANCELLED_TEACHER
        return SAFE_ERROR_CANCELLED

    if "interrumpió" in lower:
        return SAFE_ERROR_INTERRUPTED

    if "error durante la interpretación" in lower or ("interpretación" in lower and "pdf" in lower):
        return SAFE_ERROR_INTERPRETATION

    if "alterado durante el procesamiento" in lower:
        return SAFE_ERROR_INTEGRITY_ALTERED_DURING

    if "no coincide con la evidencia registrada" in lower or "reextracción explícita" in lower:
        return SAFE_ERROR_INTEGRITY_MISMATCH

    if "disco fue alterado" in lower or "dossier invalidado" in lower:
        return SAFE_ERROR_INTEGRITY_DISK

    if "servidor fue alterado" in lower:
        return SAFE_ERROR_INTEGRITY_SERVER

    if "stream corrupto" in lower or "reextracción" in lower or "no se pudo leer el archivo pdf" in lower or "no pudimos leer" in lower:
        return SAFE_ERROR_STREAM_READ

    if "tiempo" in lower and ("excedido" in lower or "timeout" in lower or "espera" in lower):
        return SAFE_ERROR_TIMEOUT

    if "no está disponible" in lower or "no se puede leer" in lower:
        return SAFE_ERROR_PDF_UNAVAILABLE

    # Technical markers & pipeline jargon
    tech_markers = (
        "traceback",
        "runtimeerror",
        "operationalerror",
        "syntaxerror",
        "zerodivisionerror",
        "valueerror",
        "typeerror",
        "nameerror",
        "attributeerror",
        "pipeline_v1",
        "pipeline legado",
        "database locked",
        "table is locked",
        "llm_model",
        "prompt_tokens",
        "exception",
        "error:",
        "line ",
    )
    if any(marker in lower for marker in tech_markers):
        return SAFE_ERROR_GENERIC

    if ("pipeline" in lower or "model" in lower or "prompt" in lower) and not ("planeación" in lower or "plan" in lower):
        return SAFE_ERROR_GENERIC

    return SAFE_ERROR_GENERIC


def _get_derived_import_presentation(job, now=None):
    """Pure query deriving presentation state from model attributes without modifying DB."""
    if now is None:
        now = timezone.now()
    else:
        now = _normalize_datetime(now)

    interp_state = getattr(job, "interpretation_state", CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED)

    # 1. Real cancellation only if persistent cancellation signals exist
    if job.cancel_requested or job.cancelled_at:
        raw_msg = (
            getattr(job, "interpretation_error_message", "").strip()
            or "Interpretación cancelada a petición."
        )
        safe_msg = _sanitize_teacher_error_message(raw_msg)
        return {
            "is_stale": False,
            "state": "error",
            "label": IMPORT_PROGRESS_LABELS["error"],
            "description": safe_msg,
            "stage": job.progress_stage,
            "error": safe_msg,
            "finished_at": _normalize_datetime(job.cancelled_at or job.progress_finished_at),
            "needs_reextract": False,
            "has_valid_dossier": False,
        }

    raw_dossier = getattr(job, "interpretation_dossier", None)
    has_raw_dossier = isinstance(raw_dossier, dict) and bool(raw_dossier)
    tamper_flagged = has_raw_dossier and raw_dossier.get("status") == "invalidated_source_tampered"

    # B2 Gate: ONLY perform physical file integrity hash check if READY candidate!
    # "Instrumentación exige máximo 1 FieldFile.open por card READY y 0 para estados no-READY."
    has_valid_dossier = False
    is_ready_candidate = bool(interp_state == CurriculumImportJob.INTERPRETATION_STATE_READY)
    if is_ready_candidate:
        has_valid_dossier = _is_valid_ready_interpretation_dossier(job)

    # 2. Ready state: requires BOTH ready candidate AND valid dossier/integrity
    legacy_active = job.progress_stage in IMPORT_STAGE_WAIT_MESSAGES
    if is_ready_candidate and has_valid_dossier and not legacy_active:
        return {
            "is_stale": False,
            "state": "finished",
            "label": IMPORT_PROGRESS_LABELS["finished"],
            "description": "",
            "stage": job.progress_stage,
            "error": "",
            "finished_at": _normalize_datetime(job.progress_finished_at),
            "needs_reextract": False,
            "has_valid_dossier": True,
        }

    # B1/B3: If READY was asserted in DB but dossier/PDF is NOT valid, fail-closed as integrity error requiring reextract
    if is_ready_candidate and not has_valid_dossier:
        diag_error = "Conflicto de integridad: El archivo PDF en el servidor fue alterado."
        if tamper_flagged:
            diag_error = "Alerta de integridad: El archivo PDF en disco fue alterado. Dossier invalidado."
        safe_diag = _sanitize_teacher_error_message(diag_error)
        return {
            "is_stale": False,
            "state": "error",
            "label": IMPORT_PROGRESS_LABELS["error"],
            "description": safe_diag,
            "stage": job.progress_stage,
            "error": safe_diag,
            "finished_at": _normalize_datetime(job.progress_finished_at),
            "needs_reextract": True,
            "has_valid_dossier": False,
        }

    # If raw dossier is explicitly flagged as invalidated_source_tampered:
    if tamper_flagged and interp_state != CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED:
        diag_error = "Alerta de integridad: El archivo PDF en disco fue alterado. Dossier invalidado."
        safe_diag = _sanitize_teacher_error_message(diag_error)
        return {
            "is_stale": False,
            "state": "error",
            "label": IMPORT_PROGRESS_LABELS["error"],
            "description": safe_diag,
            "stage": job.progress_stage,
            "error": safe_diag,
            "finished_at": _normalize_datetime(job.progress_finished_at),
            "needs_reextract": True,
            "has_valid_dossier": False,
        }

    # B3 PRECEDENCE:
    # "interpretation_state==FAILED prevalece sobre stale/claim/progress legacy en derived presentation:
    #  state error + retry/reextract adecuado. Staleness sólo deriva delayed para ORGANIZING/no estado terminal. No mutar claim por GET."
    interp_error = getattr(job, "interpretation_error_message", "").strip()
    if not legacy_active and (
        interp_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        or (interp_error and interp_state != CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED)
    ):
        raw_msg = interp_error or "La generación se interrumpió."
        safe_msg = _sanitize_teacher_error_message(raw_msg)
        is_integrity_err = any(w in raw_msg.lower() for w in ("alterado", "integridad", "corrupto", "tamper"))
        return {
            "is_stale": False,
            "state": "error",
            "label": IMPORT_PROGRESS_LABELS["error"],
            "description": safe_msg,
            "stage": job.progress_stage,
            "error": safe_msg,
            "finished_at": _normalize_datetime(job.progress_finished_at),
            "needs_reextract": bool(is_integrity_err),
            "has_valid_dossier": False,
        }

    # 3. Staleness check: Staleness applies for non-terminal active states (FAILED and READY handled above)
    is_stale = _is_import_stage_stale(job, now=now)
    if is_stale:
        ref_dt = _normalize_datetime(job.progress_started_at or job.interpretation_claimed_at)
        derived_finished_at = _normalize_datetime(job.progress_finished_at) or (
            ref_dt + IMPORT_STAGE_TIMEOUT if ref_dt else None
        )
        return {
            "is_stale": True,
            "state": "delayed",
            "label": IMPORT_PROGRESS_LABELS["delayed"],
            "description": "",
            "stage": job.progress_stage,
            "error": "",
            "finished_at": derived_finished_at,
            "needs_reextract": False,
            "has_valid_dossier": False,
        }

    # 4. Active stage or claim (ORGANIZING):
    if (
        interp_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        or job.progress_stage
        or job.interpretation_claim_token
    ):
        state = _import_progress_state(job, has_valid_dossier=has_valid_dossier)
        stage_desc = IMPORT_STAGE_WAIT_MESSAGES.get(job.progress_stage, "")
        return {
            "is_stale": False,
            "state": state,
            "label": IMPORT_PROGRESS_LABELS.get(state, "Esperando al asistente"),
            "description": stage_desc,
            "stage": job.progress_stage,
            "error": "",
            "finished_at": _normalize_datetime(job.progress_finished_at),
            "needs_reextract": False,
            "has_valid_dossier": False,
        }

    # 5. Default idle / Not started:
    state = _import_progress_state(job, has_valid_dossier=has_valid_dossier)
    return {
        "is_stale": False,
        "state": state,
        "label": IMPORT_PROGRESS_LABELS.get(state, "Esperando al asistente"),
        "description": "",
        "stage": job.progress_stage,
        "error": "",
        "finished_at": _normalize_datetime(job.progress_finished_at),
        "needs_reextract": False,
        "has_valid_dossier": False,
    }


@teacher_required
@require_http_methods(["GET"])
def tutor_import_wait(request, job_id):
    """Waiting shell updated by incremental polling while a stage runs. Pure read view."""

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    # If the user session explicitly triggered a legacy pipeline stage that has now completed,
    # hand control back to the legacy review panel (session cleanup deferred to explicit POST handlers):
    legacy_stage = None
    if hasattr(request, "session"):
        legacy_stage = request.session.get(f"legacy_stage_{job.pk}")
    if legacy_stage and not job.progress_stage:
        return redirect("tutor-import-detail", job_id=job.pk)

    pres = _get_derived_import_presentation(job)
    needs_reextract = pres.get("needs_reextract", False)

    # 1. Delayed state:
    if pres["state"] == "delayed":
        return render(
            request,
            "curriculum/tutor_import_wait.html",
            {
                "job": job,
                "ready_for_review": False,
                "needs_reextract": False,
                "wait_heading": "Estamos organizando tu planeación",
                "progress_state": pres["state"],
                "label": pres["label"],
                "wait_message": pres["label"],
                "description": pres.get("description", ""),
                "error": pres.get("error") or None,
            },
        )

    # 2. Error state:
    if pres["state"] == "error":
        return render(
            request,
            "curriculum/tutor_import_wait.html",
            {
                "job": job,
                "ready_for_review": False,
                "needs_reextract": needs_reextract,
                "wait_heading": "Estamos organizando tu planeación",
                "progress_state": pres["state"],
                "label": pres["label"],
                "wait_message": pres["label"],
                "description": pres.get("description", ""),
                "error": pres["error"] or "La generación se interrumpió.",
            },
        )

    # 3. Active downstream stage running (legacy background worker):
    if job.progress_stage in IMPORT_STAGE_WAIT_MESSAGES and not pres.get("is_stale"):
        return render(
            request,
            "curriculum/tutor_import_wait.html",
            {
                "job": job,
                "ready_for_review": False,
                "needs_reextract": False,
                "wait_heading": "Estamos organizando tu planeación",
                "progress_state": pres["state"],
                "label": pres["label"],
                "wait_message": pres["label"],
                "description": pres.get("description", ""),
            },
        )

    # 5. Valid ready dossier has PRECEDENCE: render ready review view
    interp_state = getattr(job, "interpretation_state", None)
    has_valid_dossier = pres.get("has_valid_dossier", False)
    if (
        pres["state"] == "finished"
        and interp_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        and has_valid_dossier
    ):
        review_url = reverse("tutor-import-interpretation", args=[job.pk])
        return render(
            request,
            "curriculum/tutor_import_wait.html",
            {
                "job": job,
                "ready_for_review": True,
                "needs_reextract": False,
                "review_url": review_url,
                "wait_heading": "Estamos organizando tu planeación",
                "label": pres["label"],
                "wait_message": "Tu planeación está lista para ser revisada.",
                "description": pres.get("description", ""),
                "progress_state": pres["state"],
            },
        )

    # 6. Legacy background stage just finished with topics/subtopics (only when explicit legacy session marker):
    if job.progress_finished_at and not job.progress_stage and job.topics:
        if legacy_stage:
            return redirect("tutor-import-detail", job_id=job.pk)
        return redirect("tutor-curriculum")

    # 7. Active claim token or active interpretation stage without dossier:
    if job.progress_stage or (job.interpretation_claim_token and not job.interpretation_dossier):
        return render(
            request,
            "curriculum/tutor_import_wait.html",
            {
                "job": job,
                "ready_for_review": False,
                "needs_reextract": False,
                "wait_heading": "Estamos organizando tu planeación",
                "progress_state": pres["state"],
                "label": pres["label"],
                "wait_message": pres["label"],
                "description": pres.get("description", ""),
            },
        )

    if legacy_stage:
        return redirect("tutor-import-detail", job_id=job.pk)
    return redirect("tutor-curriculum")


@teacher_required
@require_POST
def tutor_import_cancel(request, job_id):
    job = get_object_or_404(CurriculumImportJob, pk=job_id, created_by=request.user)
    if job.progress_stage or job.interpretation_claim_token:
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            cancel_requested=True, updated_at=timezone.now()
        )
    return redirect("tutor-curriculum")


@teacher_required
@require_POST
def tutor_import_retry(request, job_id):
    """POST endpoint to idempotently retry curriculum interpretation on a failed or stale job.
    Reuses the existing job and PDF without creating new jobs or published snapshots."""
    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )

    # 1. If already READY with valid dossier: fast redirect to review
    if job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY and job.has_valid_ready_dossier():
        return redirect("tutor-import-interpretation", job_id=job.pk)

    # 2. If actively organizing with non-stale claim: redirect to wait without duplicate worker
    if job.interpretation_claim_token and not job.is_stage_stale():
        return redirect("tutor-import-wait", job_id=job.pk)

    # 3. Initiate retry via command seam
    from curriculum.interpretation_commands import retry_job_interpretation, ReextractRequired
    try:
        retry_job_interpretation(job)
    except ReextractRequired as exc:
        return HttpResponse(
            str(exc) or "Se requiere una reextracción explícita.",
            status=409,
            content_type="text/plain; charset=utf-8",
        )
    except Exception as exc:
        logger.warning("Fallo al reintentar interpretación para trabajo %s: %s", job.pk, exc)

    job.refresh_from_db()
    if job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY and job.has_valid_ready_dossier():
        return redirect("tutor-import-interpretation", job_id=job.pk)
    return redirect("tutor-import-wait", job_id=job.pk)


@teacher_required
@require_http_methods(["GET"])
def tutor_import_status(request, job_id):
    """Small owner-scoped polling payload; pure read view, never mutates persistence."""

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    pres = _get_derived_import_presentation(job)
    started_at_aware = _normalize_datetime(job.progress_started_at or job.interpretation_claimed_at)
    needs_reextract = pres.get("needs_reextract", False)
    can_retry = (
        not needs_reextract
        and (
            pres["state"] == "error"
            or getattr(job, "interpretation_state", None) == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        )
    )
    return JsonResponse(
        {
            "state": pres["state"],
            "interpretation_state": getattr(job, "interpretation_state", CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED),
            "label": pres["label"],
            "description": pres.get("description", ""),
            "stage": pres["stage"],
            "done": job.progress_done,
            "total": job.progress_total,
            "error": pres["error"],
            "can_retry": can_retry,
            "retry_url": reverse("tutor-import-retry", args=[job.pk]) if can_retry else None,
            "needs_reextract": needs_reextract,
            "reextract_url": reverse("tutor-import-interpretation", args=[job.pk]) if needs_reextract else None,
            "started_at": (
                started_at_aware.isoformat()
                if started_at_aware is not None
                else None
            ),
            "finished_at": (
                pres["finished_at"].isoformat()
                if pres["finished_at"] is not None
                else None
            ),
            "redirect_url": (
                reverse("tutor-import-interpretation", args=[job.pk])
                if (
                    pres["state"] == "finished"
                    and getattr(job, "interpretation_state", None) == CurriculumImportJob.INTERPRETATION_STATE_READY
                    and pres.get("has_valid_dossier", False)
                )
                else reverse("tutor-import-wait", args=[job.pk])
            ),
        }
    )


@teacher_required
@require_http_methods(["GET"])
def tutor_import_source_page(request, job_id, page_number):
    """Serve an import PDF inline only to its owning teacher.

    Authoritative source: uses active/current approval blob if approved;
    otherwise falls back to job.pdf (with integrity check against dossier).
    Supports single HTTP Range requests (206 Partial Content, Content-Range, Accept-Ranges,
    Content-Length), returning 416 for unsatisfiable ranges.
    """

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    try:
        page_number = int(page_number)
    except (TypeError, ValueError):
        raise Http404("Número de página no válido.")
    if page_number < 1:
        raise Http404("El número de página debe ser mayor o igual a 1.")

    pdf_bytes = None
    pdf_sha = None

    # Check approval blob first (serves immutable blob when approved, even if job.pdf is deleted)
    dossier = job.get_interpretation_dossier()
    v = getattr(dossier, "version", None) if dossier else None
    sha = getattr(dossier, "source_sha256", None) if dossier else None
    approval = None
    if v and sha:
        approval = job.approvals.filter(dossier_version=v, source_sha256=sha).first()
    if approval and approval.source_blob and approval.source_blob.is_valid_blob():
        blob = approval.source_blob
        if (blob.sha256 or "").lower() == (approval.source_sha256 or "").lower():
            pdf_bytes = bytes(blob.content)
            pdf_sha = blob.sha256.lower()

    # Fallback to job.pdf if not approved or no valid blob
    if pdf_bytes is None:
        if not job.pdf:
            raise Http404("El documento PDF fuente no está disponible.")
        try:
            with job.pdf.open("rb") as stream:
                pdf_bytes = stream.read()
        except Exception:
            raise Http404("No se pudo leer el archivo PDF fuente.")

        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest().lower()
        dossier = job.get_interpretation_dossier()
        if dossier and (dossier.source_sha256 or "").lower() != pdf_sha:
            return HttpResponse(
                "Conflicto de integridad: El archivo PDF en el servidor fue alterado "
                "(SHA-256 no coincide con el dossier original). El visor de láminas fuente está bloqueado "
                "hasta que se realice una reextracción segura.",
                status=409,
            )

    # Page count validation
    effective_page_count = job.page_count
    if not effective_page_count:
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            effective_page_count = len(reader.pages)
        except Exception as exc:
            logger.warning("No se pudo calcular el total de páginas para el trabajo %s: %s", job.pk, exc)
    if effective_page_count and page_number > int(effective_page_count):
        raise Http404("Página fuera de rango.")

    total_length = len(pdf_bytes)

    # Range header handling
    range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
    if range_header:
        range_header = range_header.strip()
        if not range_header.startswith("bytes="):
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{total_length}"
            return response

        range_val = range_header[6:].strip()
        if "," in range_val:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{total_length}"
            return response

        parts = range_val.split("-", 1)
        if len(parts) != 2:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{total_length}"
            return response
        start_str, end_str = parts[0].strip(), parts[1].strip()

        try:
            if start_str and end_str:
                start = int(start_str)
                end = int(end_str)
                if start > end or start >= total_length or start < 0:
                    response = HttpResponse(status=416)
                    response["Content-Range"] = f"bytes */{total_length}"
                    return response
                end = min(end, total_length - 1)
            elif start_str and not end_str:
                start = int(start_str)
                if start >= total_length or start < 0:
                    response = HttpResponse(status=416)
                    response["Content-Range"] = f"bytes */{total_length}"
                    return response
                end = total_length - 1
            elif not start_str and end_str:
                suffix = int(end_str)
                if suffix <= 0:
                    response = HttpResponse(status=416)
                    response["Content-Range"] = f"bytes */{total_length}"
                    return response
                start = max(0, total_length - suffix)
                end = total_length - 1
            else:
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{total_length}"
                return response
        except ValueError:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{total_length}"
            return response

        slice_bytes = pdf_bytes[start : end + 1]
        response = HttpResponse(slice_bytes, status=206, content_type="application/pdf")
        response["Content-Range"] = f"bytes {start}-{end}/{total_length}"
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(len(slice_bytes))
        response["Content-Disposition"] = "inline; filename=source.pdf"
        return response

    response = HttpResponse(pdf_bytes, status=200, content_type="application/pdf")
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(total_length)
    response["Content-Disposition"] = "inline; filename=source.pdf"
    return response



@teacher_required
@require_http_methods(["GET"])
def tutor_package_source_page(request, snapshot_id, page_number):
    """Serve only the immutable PDF copy captured by the published snapshot."""

    snapshot = get_object_or_404(
        PublishedPackageSnapshot,
        pk=snapshot_id,
        package__created_by=request.user,
    )
    raw_references = snapshot.payload.get("source_references", []) if snapshot.payload else []
    fallback_sha = getattr(snapshot, "source_pdf_sha256", "") or getattr(snapshot, "sha256", "")
    references = _normalize_legacy_source_references(raw_references, fallback_sha)
    try:
        page_number = int(page_number)
    except (TypeError, ValueError):
        raise Http404
    page_references = [
        reference
        for reference in references
        if isinstance(reference, dict)
        and page_number in {
            int(page)
            for page in reference.get("source_pages", [])
            if str(page).isdigit()
        }
    ]
    expected_hashes = {
        str(reference.get("source_pdf_sha256", ""))
        for reference in page_references
        if reference.get("source_pdf_sha256")
    }
    if (
        not page_references
        or not snapshot.source_pdf
        or not snapshot.source_pdf_sha256
        or expected_hashes != {snapshot.source_pdf_sha256}
    ):
        raise Http404
    with snapshot.source_pdf.open("rb") as source:
        content = source.read()
    if hashlib.sha256(content).hexdigest() != snapshot.source_pdf_sha256:
        raise Http404
    response = FileResponse(ContentFile(content, name="source.pdf"), content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=source.pdf"
    return response


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

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
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

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
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
        pdf_list = request.FILES.getlist("pdf")
        def _reject(error_msg):
            for key in request.FILES:
                for item in request.FILES.getlist(key):
                    try:
                        item.close()
                    except Exception:
                        pass
            return render(
                request,
                "curriculum/tutor_import_form.html",
                {"error": error_msg},
                status=400,
            )

        if len(pdf_list) != 1 or len(request.FILES) > 1:
            if len(pdf_list) == 0:
                error_msg = "Selecciona el PDF de la currícula."
            else:
                error_msg = "Elige un solo archivo PDF para continuar."
            return _reject(error_msg)

        pdf = pdf_list[0]
        filename = (getattr(pdf, "name", "") or "").strip()
        if not filename.lower().endswith(".pdf"):
            return _reject("El archivo debe ser un documento en formato PDF (.pdf).")

        if getattr(pdf, "size", 0) == 0:
            return _reject("El archivo seleccionado está vacío. Por favor elige un PDF válido.")

        max_upload_size = getattr(settings, "CURRICULUM_MAX_UPLOAD_SIZE_BYTES", 25 * 1024 * 1024)
        if getattr(pdf, "size", 0) > max_upload_size:
            max_mb = max_upload_size // (1024 * 1024)
            return _reject(f"El archivo supera el tamaño máximo permitido de {max_mb} MB.")

        try:
            from pypdf import PdfReader
            if hasattr(pdf, "seek"):
                pdf.seek(0)
            reader = PdfReader(pdf)
            if len(reader.pages) < 1:
                return _reject("El documento PDF no contiene páginas válidas.")
            if hasattr(pdf, "seek"):
                pdf.seek(0)
        except Exception:
            return _reject("El archivo no es un documento PDF válido o está dañado. Por favor elige otro archivo.")

        job = CurriculumImportJob.objects.create(pdf=pdf, created_by=request.user)
        try:
            trigger_job_interpretation(job)
        except Exception as exc:
            logger.warning("Fallo al iniciar interpretación para trabajo %s: %s", job.pk, exc)
            from curriculum.interpretation_commands import record_upload_outer_failure

            record_upload_outer_failure(job, error_message=str(exc))
            job.refresh_from_db()
        return redirect("tutor-import-wait", job_id=job.pk)
    return render(request, "curriculum/tutor_import_form.html", {})


@teacher_required
@require_http_methods(["GET", "POST"])
def tutor_import_interpretation(request, job_id):
    """V0: Session interpretation, provenance, teacher corrections, save and reopen."""
    import copy
    import re
    from curriculum.source_interpreter import (
        CANONICAL_CAMPOS,
        CurriculumInterpretationError,
        CurriculumSourceInterpreter,
        ImportDossier,
        InterpretationCancelledError,
        InterpretationTimeoutError,
        SelectionError,
        SourcePdfReadError,
        _find_single_annex_ref,
        _utc_iso_now,
        compute_reextract_diff,
        preserve_reextract_decisions,
        derive_campos_formativos_options,
        derive_operational_queue,
        normalize_campos_formativos,
        parse_canonical_positive_int,
        resolve,
        PRIORITY_REQUIRES_RESOLUTION,
        PRIORITY_PENDING_REVIEW,
        PRIORITY_POSTPONED,
        PRIORITY_NOT_SPECIFIED,
        PRIORITY_REVIEWED,
        GENERAL_FIELD_DISPLAY_ORDER,
        SESSION_FIELD_DISPLAY_ORDER,
    )


    SCALAR_FORM_FIELDS = {
        "action",
        "expected_version",
        "confirm_approval",
        "confirm_pending_items",
        "item_id",
        "scope",
        "session_filter",
        "value",
        "field",
        "reference_id",
        "session_id",
        "session_number",
        "confirm_field",
        "campos_formativos_present",
        "proyecto",
        "proposito",
        "finalidad",
        "metodologia",
        "escenario_proyecto",
        "inicio",
        "desarrollo",
        "cierre",
        "materiales",
        "evaluacion",
        "contexto_ejecucion",
    }

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    if not job.pdf:
        raise Http404("El trabajo no tiene un archivo PDF asociado.")

    with job.pdf.open("rb") as stream:
        current_bytes = stream.read()
    current_pdf_sha256 = hashlib.sha256(current_bytes).hexdigest()

    parsed_post_session_number: int | None = None
    if request.method == "POST":
        # B1 & F6: Reject duplicate scalar inputs with HTTP 400 before mutation/versioning
        for k in request.POST.keys():
            if (
                k in SCALAR_FORM_FIELDS
                or k.startswith("annex_confirm_")
                or k.startswith("annex_manual_page_")
                or k.startswith("annex_manual_confirm_")
                or k.startswith("annex_disassociate_")
            ):
                if len(request.POST.getlist(k)) > 1:
                    return HttpResponseBadRequest(
                        f"Múltiples valores no permitidos para el campo escalar '{k}'."
                    )

        # B4: Canonical validation for session_number on ANY POST action before branch dispatch
        if "session_number" in request.POST:
            try:
                parsed_post_session_number = parse_canonical_positive_int(request.POST["session_number"])
            except ValueError:
                return HttpResponseBadRequest("Número de sesión inválido en 'session_number'.")

        action = request.POST.get("action")
    else:
        action = None

    success_message = ""
    error_message = ""
    post_status_code = 200
    invalid_field = None
    inline_errors = {}
    request_selected_session = None
    request_selected_item_key = None

    dossier = job.get_interpretation_dossier()
    source_tampered = bool(
        dossier is not None and dossier.source_sha256 != current_pdf_sha256
    )

    # Check for unrecoverable identity conflicts / duplicate tokens across sessions and annexes
    if dossier is not None:
        try:
            derive_operational_queue(dossier)
        except SelectionError as exc:
            if any(w in str(exc).lower() for w in ("ambiguo", "múltiples", "duplicado", "conflicto")):
                return HttpResponseBadRequest(str(exc))
            raise

    report = getattr(dossier, "verification_report", None) if dossier else None
    if not isinstance(report, dict) and isinstance(getattr(job, "interpretation_dossier", None), dict):
        report = job.interpretation_dossier.get("verification_report")

    # Strict canonical validation of verification report against physical PDF
    from curriculum.verification import validate_canonical_verification_report

    report_valid = bool(
        report is not None
        and dossier is not None
        and validate_canonical_verification_report(dossier, current_bytes, report)
    )

    is_valid_ready = bool(
        job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        and dossier is not None
        and getattr(dossier, "version", 0) >= 1
        and getattr(dossier, "status", "") == "active"
        and not source_tampered
        and _is_valid_ready_interpretation_dossier(job, pdf_bytes=current_bytes)
        and report_valid
    )

    if request.method == "GET":
        if not is_valid_ready:
            return redirect("tutor-import-wait", job_id=job.pk)

    if request.method == "POST" and action != "reextract":
        if not is_valid_ready:
            return HttpResponse(
                "Conflicto de integridad: El archivo PDF fue modificado o la planeación contiene bloqueos "
                "de comprobación automática. "
                "Las correcciones y confirmaciones están bloqueadas para evitar desalineación de láminas y datos. "
                "Debe realizar una reextracción explícita.",
                status=409,
            )

    if request.method == "POST":
        if hasattr(request, "session"):
            request.session.pop(f"legacy_stage_{job.pk}", None)

        if action == "approve":
            from curriculum.approval_commands import execute_teacher_approval

            result = execute_teacher_approval(
                job_id=job.pk,
                user=request.user,
                post_data=request.POST,
                is_dedicated_route=False,
            )
            if not result.is_success:
                if result.http_status == 404:
                    raise Http404(result.message)
                return HttpResponse(result.message, status=result.http_status)

            success_message = result.message
            job.refresh_from_db()
            dossier = job.get_interpretation_dossier()
            active_approval = result.approval
            is_approved = True

        # Sol Advanced Audit: atomic mutation with select_for_update for mutating actions
        QUEUE_ACTIONS = ("confirm_queue_item", "save_queue_item", "leave_queue_item_pending", "postpone_queue_item")
        MUTATING_ACTIONS = ("save_corrections", "confirm_all", "reextract", *QUEUE_ACTIONS)

        if action in MUTATING_ACTIONS:
            with transaction.atomic():
                job = (
                    CurriculumImportJob.objects.select_for_update()
                    .filter(pk=job_id, created_by=request.user)
                    .first()
                )
                if not job:
                    raise Http404("El trabajo de importación no existe.")
                dossier = job.get_interpretation_dossier()

                # Requirement 1: expected_version validation
                if dossier is not None and action in MUTATING_ACTIONS:
                    req_expected_version = request.POST.get("expected_version")
                    if req_expected_version is None or str(req_expected_version).strip() == "":
                        if action not in ("confirm_all",):
                            return HttpResponse(
                                "El campo 'expected_version' es requerido para validar la concurrencia del dossier.",
                                status=400,
                            )
                    else:
                        try:
                            exp_ver = parse_canonical_positive_int(req_expected_version)
                        except ValueError:
                            return HttpResponse(
                                "El campo 'expected_version' debe ser un número entero válido.",
                                status=400,
                            )
                        if action != "reextract" and exp_ver != dossier.version:
                            conflict_msg = (
                                f"Conflicto de concurrencia (409): El formulario fue cargado con la versión {exp_ver}, "
                                f"pero el documento ya se encuentra en la versión {dossier.version} por modificaciones concurrentes. "
                                "Recargue la página para ver las correcciones más recientes."
                            )
                            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                                return HttpResponse(conflict_msg, status=409)
                            context = {
                                "job": job,
                                "dossier": dossier,
                                "selected_session": dossier.get_session(dossier.selection.get("session_id")) if dossier and dossier.sessions else None,
                                "active_session_id": dossier.selection.get("session_id", "") if dossier else "",
                                "active_session_number": dossier.selection.get("session_number", 1) if dossier else 1,
                                "current_pdf_sha256": current_pdf_sha256,
                                "source_tampered": source_tampered,
                                "success_message": "",
                                "error_message": conflict_msg,
                            }
                            return render(request, "curriculum/tutor_import_interpretation.html", context, status=409)

                # P0-1: Block mutation operations on tampered source with 409 Conflict
                if source_tampered and action in ("save_corrections", "confirm_all", "approve"):
                    return HttpResponse(
                        "Conflicto de integridad: El archivo PDF fue modificado o reemplazado en el servidor "
                        "(SHA-256 no coincide con el dossier de interpretación). Las correcciones y confirmaciones "
                        "están bloqueadas para evitar desalineación de páginas. Debe realizar una reextracción explícita.",
                        status=409,
                    )

                if action == "reextract":
                    # Check active foreign claim first: return 409 Conflict without mutating persistence
                    job.refresh_from_db()
                    if job.interpretation_claim_token:
                        return HttpResponse(
                            "No se puede reextraer: la organización de interpretación está en progreso por otro proceso.",
                            status=409,
                        )

                    # Requirement 3: Explicit retry/re-extract clears cancel_requested before starting
                    had_cancel_request = bool(job.cancel_requested)
                    if job.cancel_requested:
                        job.cancel_requested = False
                        job.save(update_fields=["cancel_requested", "updated_at"])

                    old_history = copy.deepcopy(dossier.history) if dossier else []
                    old_version = dossier.version if dossier else 0
                    old_selection = copy.deepcopy(dossier.selection) if dossier else {}
                    old_dossier_snapshot = copy.deepcopy(dossier) if dossier else None

                    selection_reset = False
                    try:
                        dossier = CurriculumSourceInterpreter.prepare(
                            job, selection=old_selection if old_selection else None, job=job, timeout_seconds=30.0
                        )
                    except SelectionError:
                        # Requirement 2: Only retry without old_selection when the error is strictly a selection error
                        dossier = CurriculumSourceInterpreter.prepare(
                            job, selection=None, job=job, timeout_seconds=30.0
                        )
                        selection_reset = True
                    except InterpretationCancelledError as exc:
                        from curriculum.interpretation_commands import finish_cancelled_stage

                        finish_cancelled_stage(job)
                        err_msg = f"Reextracción cancelada: {exc}"
                        return HttpResponse(err_msg, status=409)
                    except (TimeoutError, InterpretationTimeoutError) as exc:
                        from curriculum.interpretation_commands import record_reextract_failure

                        err_msg = f"Tiempo de extracción excedido durante reextracción: {exc}"
                        record_reextract_failure(job, err_msg, current_pdf_sha256, dossier)
                        return HttpResponse(err_msg, status=504)
                    except (SourcePdfReadError, Exception) as exc:
                        # Requirement 2: PDF inválido => 400/422 controlado, último dossier preservado (marcado invalidated si hash cambió), progress_stage limpio y mensaje útil sin traceback al usuario.
                        from curriculum.interpretation_commands import record_reextract_failure

                        err_msg = f"No se pudo leer el archivo PDF fuente: {exc}."
                        record_reextract_failure(job, err_msg, current_pdf_sha256, dossier)
                        if request.headers.get("x-requested-with") == "XMLHttpRequest":
                            return HttpResponse(err_msg, status=422)
                        context = {
                            "job": job,
                            "dossier": dossier,
                            "selected_session": dossier.get_session(dossier.selection.get("session_id")) if dossier and dossier.sessions else None,
                            "active_session_id": dossier.selection.get("session_id", "") if dossier else "",
                            "active_session_number": dossier.selection.get("session_number", 1) if dossier else 1,
                            "current_pdf_sha256": current_pdf_sha256,
                            "source_tampered": bool(dossier and current_pdf_sha256 != getattr(dossier, "source_sha256", "")),
                            "success_message": "",
                            "error_message": err_msg,
                        }
                        return render(request, "curriculum/tutor_import_interpretation.html", context, status=422)

                    dossier.version = old_version + 1
                    actor_name = request.user.get_full_name().strip() or request.user.username
                    now_str = _utc_iso_now()

                    extraction_deltas = compute_reextract_diff(old_dossier_snapshot, dossier)
                    decision_deltas = preserve_reextract_decisions(old_dossier_snapshot, dossier, current_bytes)
                    reextract_entry = {
                        "version": dossier.version,
                        "action": "reextract",
                        "actor": actor_name,
                        "timestamp": now_str,
                        "selection_reset": selection_reset,
                        "retry_after_cancel": had_cancel_request,
                        "deltas": extraction_deltas + decision_deltas,
                        "summary": (
                            f"Reextracción segura ejecutada desde el documento actual "
                            f"(SHA-256: {current_pdf_sha256[:12]}...). "
                            + ("Reintento exitoso tras cancelación previa. " if had_cancel_request else "")
                            + f"Versión {dossier.version} registrada."
                        ),
                    }
                    entries_to_add = [reextract_entry]
                    if selection_reset:
                        entries_to_add.append({
                            "version": dossier.version,
                            "action": "selection_reset",
                            "actor": actor_name,
                            "timestamp": now_str,
                            "summary": (
                                f"Selección restablecida: la sesión previa {old_selection.get('session_id')} no existe en el nuevo documento. "
                                f"Se seleccionó por defecto la sesión '{dossier.selection.get('session_id')}'."
                            ),
                        })
                    dossier.history = old_history + entries_to_add
                    job.save_interpretation_dossier(dossier)
                    job.invalidate_approvals(reason="Reextracción ejecutada por el docente")
                    source_tampered = False
                    success_message = "Interpretación reiniciada de forma segura desde el documento fuente."

                    # Requirement 3: Clear obsolete progress_stage, keep cancel_requested False, keep cancelled_at intact
                    job.progress_stage = ""
                    job.cancel_requested = False
                    job.save(
                        update_fields=[
                            "progress_stage",
                            "cancel_requested",
                            "updated_at",
                        ]
                    )

                elif action in QUEUE_ACTIONS:
                    req_item_id = request.POST.get("item_id")
                    if not req_item_id or not isinstance(req_item_id, str) or not req_item_id.strip():
                        return HttpResponseBadRequest(
                            "El campo 'item_id' es requerido para acciones de la cola de revisión."
                        )
                    req_item_id = req_item_id.strip()

                    post_scope = request.POST.get("scope") or request.POST.get("session_filter")
                    get_scope = request.GET.get("scope") or request.GET.get("session_filter")
                    effective_scope = (post_scope or get_scope or "").strip() or None

                    try:
                        authorized_queue = derive_operational_queue(dossier, session_filter=effective_scope)
                    except SelectionError as exc:
                        return HttpResponseBadRequest(f"Alcance de cola no válido o ambiguo: {exc}")
                    except Exception as exc:
                        return HttpResponseBadRequest(f"Error al verificar la cola operativa: {exc}")

                    matching_items = [it for it in authorized_queue.items if it.item_id == req_item_id]
                    if len(matching_items) == 0:
                        return HttpResponseBadRequest(
                            f"El elemento '{req_item_id}' no existe o no pertenece al alcance visible autorizado."
                        )
                    elif len(matching_items) > 1:
                        return HttpResponseBadRequest(
                            f"Conflicto de unicidad: múltiples elementos coinciden con '{req_item_id}'."
                        )
                    target_item = matching_items[0]

                    # Scope binding enforcement:
                    if target_item.scope in ("session", "annex"):
                        if effective_scope in ("all", "document", "general"):
                            return HttpResponseBadRequest(
                                "Un elemento de sesión no puede mutarse bajo el alcance de documento o general."
                            )
                        if effective_scope and effective_scope not in (target_item.session_id, str(target_item.session_number)):
                            return HttpResponseBadRequest(
                                "El alcance especificado no coincide con la sesión del elemento."
                            )
                    elif target_item.scope == "general":
                        if effective_scope is not None and effective_scope not in ("", "all", "document", "general"):
                            return HttpResponseBadRequest(
                                "Un elemento de datos generales no puede mutarse bajo el alcance de una sesión."
                            )

                    # Per-action allowlist validation:
                    base_allowed = {"csrfmiddlewaretoken", "action", "expected_version", "item_id", "scope", "session_filter"}

                    if target_item.scope in ("general", "session"):
                        if target_item.field_name == "campos_formativos":
                            item_control_keys = {"campos_formativos", "campos_formativos_present"}
                        else:
                            item_control_keys = {target_item.field_name}
                    elif target_item.scope == "annex":
                        ref_id = target_item.reference_id or f"annex_{target_item.annex_number}"
                        item_control_keys = {
                            "annex_page",
                            "page",
                            f"annex_confirm_{ref_id}",
                            f"annex_manual_page_{ref_id}",
                            "manual_page",
                            f"annex_manual_confirm_{ref_id}",
                            "manual_confirm",
                            f"annex_disassociate_{ref_id}",
                            "disassociate",
                        }
                    else:
                        item_control_keys = set()

                    if action == "confirm_queue_item":
                        if "value" in request.POST:
                            return HttpResponseBadRequest("La acción 'confirm_queue_item' no acepta el parámetro 'value'.")
                        allowed_keys = base_allowed | item_control_keys
                        extra_keys = [k for k in request.POST.keys() if k not in allowed_keys]
                        if extra_keys:
                            return HttpResponseBadRequest(
                                f"Claves no autorizadas en 'confirm_queue_item' para '{target_item.human_label}': {extra_keys}."
                            )

                    elif action == "save_queue_item":
                        has_value = "value" in request.POST
                        has_control = any(k in request.POST for k in item_control_keys)
                        if not has_value and not has_control:
                            return HttpResponseBadRequest(
                                "La acción 'save_queue_item' exige exactamente su control o el parámetro 'value'."
                            )
                        if has_value and has_control:
                            return HttpResponseBadRequest(
                                "La acción 'save_queue_item' no permite enviar 'value' conjuntamente con el control específico."
                            )
                        allowed_keys = base_allowed | item_control_keys | ({"value"} if has_value else set())
                        extra_keys = [k for k in request.POST.keys() if k not in allowed_keys]
                        if extra_keys:
                            return HttpResponseBadRequest(
                                f"Claves no autorizadas en 'save_queue_item' para '{target_item.human_label}': {extra_keys}."
                            )

                    elif action == "leave_queue_item_pending":
                        if "value" in request.POST:
                            return HttpResponseBadRequest("La acción 'leave_queue_item_pending' no acepta valor.")
                        allowed_keys = base_allowed | item_control_keys
                        extra_keys = [k for k in request.POST.keys() if k not in allowed_keys]
                        if extra_keys:
                            return HttpResponseBadRequest(
                                f"Claves no autorizadas en 'leave_queue_item_pending' para '{target_item.human_label}': {extra_keys}."
                            )

                    elif action == "postpone_queue_item":
                        if "value" in request.POST:
                            return HttpResponseBadRequest("La acción 'postpone_queue_item' no acepta valor.")
                        allowed_keys = base_allowed | item_control_keys
                        extra_keys = [k for k in request.POST.keys() if k not in allowed_keys]
                        if extra_keys:
                            return HttpResponseBadRequest(
                                f"Claves no autorizadas en 'postpone_queue_item' para '{target_item.human_label}': {extra_keys}."
                            )

                    actor_name = request.user.get_full_name().strip() or request.user.username

                    if action == "leave_queue_item_pending":
                        success_message = f"Elemento '{target_item.human_label}' omitido por ahora."
                        curr_idx = authorized_queue.items.index(target_item)
                        if curr_idx + 1 < len(authorized_queue.items):
                            request_selected_item_key = authorized_queue.items[curr_idx + 1].stable_key
                        else:
                            request_selected_item_key = authorized_queue.items[0].stable_key if authorized_queue.items else None
                        if target_item.session_id:
                            request_selected_session = dossier.get_session(target_item.session_id)
                        if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
                            return JsonResponse({
                                "status": "ok",
                                "message": success_message,
                                "next_item_key": request_selected_item_key,
                            })
                    else:
                        corrections_payload = {}
                        if action == "postpone_queue_item":
                            if target_item.scope == "general":
                                corrections_payload = {"reviews": {target_item.field_name: "postponed"}}
                            elif target_item.scope == "session":
                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "reviews": {target_item.field_name: "postponed"},
                                }
                            elif target_item.scope == "annex":
                                ref_id = target_item.reference_id or f"annex_{target_item.annex_number}"
                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "reviews": {ref_id: "postponed"},
                                }
                        elif action == "confirm_queue_item":
                            if target_item.scope == "general":
                                corrections_payload = {"reviews": {target_item.field_name: "confirmed"}}
                            elif target_item.scope == "session":
                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "reviews": {target_item.field_name: "confirmed"},
                                }

                            elif target_item.scope == "annex":
                                ref_id = target_item.reference_id
                                page_val = (
                                    request.POST.get(f"annex_confirm_{ref_id}")
                                    or request.POST.get("annex_page")
                                    or request.POST.get("page")
                                )
                                manual_val = (
                                    request.POST.get(f"annex_manual_page_{ref_id}")
                                    or request.POST.get("manual_page")
                                )
                                manual_conf = (
                                    request.POST.get(f"annex_manual_confirm_{ref_id}") in ("1", "on", "true", "True")
                                    or request.POST.get("manual_confirm") in ("1", "on", "true", "True")
                                )
                                disassoc = (
                                    request.POST.get(f"annex_disassociate_{ref_id}") in ("1", "on", "true", "True")
                                    or request.POST.get("disassociate") in ("1", "on", "true", "True")
                                )

                                annex_conf = {}
                                manual_annex_conf = {}
                                if disassoc:
                                    annex_conf[ref_id] = None
                                elif manual_conf and manual_val:
                                    try:
                                        p_int = parse_canonical_positive_int(manual_val)
                                    except ValueError:
                                        error_message = f"Número de página manual inválido '{manual_val}'."
                                        invalid_field = f"annex_manual_page_{ref_id}"
                                        inline_errors[invalid_field] = error_message
                                        post_status_code = 400
                                    else:
                                        if p_int < 1 or p_int > dossier.page_count:
                                            error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                            invalid_field = f"annex_manual_page_{ref_id}"
                                            inline_errors[invalid_field] = error_message
                                            post_status_code = 400
                                        else:
                                            annex_conf[ref_id] = p_int
                                            manual_annex_conf[ref_id] = {"page": p_int, "confirmed": True}
                                elif page_val is not None and str(page_val).strip() != "":
                                    try:
                                        p_int = parse_canonical_positive_int(page_val)
                                    except ValueError:
                                        error_message = f"Número de página inválido '{page_val}'."
                                        invalid_field = f"annex_confirm_{ref_id}"
                                        inline_errors[invalid_field] = error_message
                                        post_status_code = 400
                                    else:
                                        if p_int < 1 or p_int > dossier.page_count:
                                            error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                            invalid_field = f"annex_confirm_{ref_id}"
                                            inline_errors[invalid_field] = error_message
                                            post_status_code = 400
                                        else:
                                            annex_conf[ref_id] = p_int
                                elif target_item.current_value is not None:
                                    annex_conf[ref_id] = target_item.current_value
                                elif target_item.original_value is not None:
                                    annex_conf[ref_id] = target_item.original_value
                                else:
                                    error_message = f"Debe seleccionar o especificar una página para confirmar el anexo '{target_item.human_label}'."
                                    invalid_field = f"annex_confirm_{ref_id}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400

                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "annex_confirmations": annex_conf,
                                }
                                if manual_annex_conf:
                                    corrections_payload["manual_annex_confirmations"] = manual_annex_conf

                        elif action == "save_queue_item":
                            if target_item.scope == "general":
                                if target_item.field_name == "campos_formativos":
                                    raw_vals = request.POST.getlist("campos_formativos")
                                    val = normalize_campos_formativos(raw_vals)
                                else:
                                    val = request.POST.get("value") if "value" in request.POST else request.POST.get(target_item.field_name, "")
                                corrections_payload = {"general_fields": {target_item.field_name: val}}
                            elif target_item.scope == "session":
                                val = request.POST.get("value") if "value" in request.POST else request.POST.get(target_item.field_name, "")
                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "session_fields": {target_item.field_name: val},
                                }
                            elif target_item.scope == "annex":
                                ref_id = target_item.reference_id
                                page_val = (
                                    request.POST.get(f"annex_confirm_{ref_id}")
                                    or request.POST.get("annex_page")
                                    or request.POST.get("page")
                                )
                                manual_val = (
                                    request.POST.get(f"annex_manual_page_{ref_id}")
                                    or request.POST.get("manual_page")
                                )
                                manual_conf = (
                                    request.POST.get(f"annex_manual_confirm_{ref_id}") in ("1", "on", "true", "True")
                                    or request.POST.get("manual_confirm") in ("1", "on", "true", "True")
                                )
                                disassoc = (
                                    request.POST.get(f"annex_disassociate_{ref_id}") in ("1", "on", "true", "True")
                                    or request.POST.get("disassociate") in ("1", "on", "true", "True")
                                )
                                annex_conf = {}
                                manual_annex_conf = {}
                                if disassoc:
                                    annex_conf[ref_id] = None
                                elif manual_conf and manual_val:
                                    try:
                                        p_int = parse_canonical_positive_int(manual_val)
                                    except ValueError:
                                        error_message = f"Número de página manual inválido '{manual_val}'."
                                        invalid_field = f"annex_manual_page_{ref_id}"
                                        inline_errors[invalid_field] = error_message
                                        post_status_code = 400
                                    else:
                                        if p_int < 1 or p_int > dossier.page_count:
                                            error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                            invalid_field = f"annex_manual_page_{ref_id}"
                                            inline_errors[invalid_field] = error_message
                                            post_status_code = 400
                                        else:
                                            annex_conf[ref_id] = p_int
                                            manual_annex_conf[ref_id] = {"page": p_int, "confirmed": True}
                                elif page_val is not None and str(page_val).strip() != "":
                                    try:
                                        p_int = parse_canonical_positive_int(page_val)
                                    except ValueError:
                                        error_message = f"Número de página inválido '{page_val}'."
                                        invalid_field = f"annex_confirm_{ref_id}"
                                        inline_errors[invalid_field] = error_message
                                        post_status_code = 400
                                    else:
                                        if p_int < 1 or p_int > dossier.page_count:
                                            error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                            invalid_field = f"annex_confirm_{ref_id}"
                                            inline_errors[invalid_field] = error_message
                                            post_status_code = 400
                                        else:
                                            annex_conf[ref_id] = p_int
                                else:
                                    annex_conf[ref_id] = None

                                corrections_payload = {
                                    "session_id": target_item.session_id,
                                    "annex_confirmations": annex_conf,
                                }
                                if manual_annex_conf:
                                    corrections_payload["manual_annex_confirmations"] = manual_annex_conf

                        if post_status_code != 400:
                            prev_ver = dossier.version
                            try:
                                dossier = resolve(dossier, corrections_payload, actor=actor_name, pdf_source=getattr(job, "pdf", None))
                            except ValueError as exc:
                                error_message = str(exc)
                                post_status_code = 400

                        if post_status_code != 400 and dossier.version != prev_ver:
                            job.save_interpretation_dossier(dossier)
                            job.invalidate_approvals(reason=f"Elemento de cola modificado por el docente (v{dossier.version})")
                            if action == "confirm_queue_item":
                                success_message = f"Elemento '{target_item.human_label}' confirmado por {actor_name}. Versión {dossier.version} registrada."
                            elif action == "postpone_queue_item":
                                success_message = f"Elemento '{target_item.human_label}' aplazado por {actor_name}. Versión {dossier.version} registrada."
                            else:
                                success_message = f"Elemento '{target_item.human_label}' guardado por {actor_name}. Versión {dossier.version} registrada."
                        elif post_status_code != 400:
                            success_message = f"Sin cambios para '{target_item.human_label}'. Versión sin modificaciones."

                        if post_status_code == 400:
                            request_selected_item_key = target_item.stable_key

                        if target_item.session_id:
                            request_selected_session = dossier.get_session(target_item.session_id)

                        if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
                            return JsonResponse({
                                "status": "ok" if post_status_code == 200 else "error",
                                "message": success_message or error_message,
                                "version": dossier.version if dossier else None,
                                "priority_state": "postponed" if action == "postpone_queue_item" else getattr(target_item, "priority_state", ""),
                            }, status=post_status_code)

                elif action in ("save_corrections", "confirm_all"):
                    if dossier is None:
                        try:
                            dossier = CurriculumSourceInterpreter.prepare(
                                job, job=job, timeout_seconds=30.0
                            )
                        except TimeoutError as exc:
                            from curriculum.interpretation_commands import record_direct_timeout

                            record_direct_timeout(job, error_message=str(exc))
                            return HttpResponse(f"Tiempo de extracción excedido: {exc}", status=504)
                        except ValueError as exc:
                            raise Http404(str(exc))

                    # P1-6: Partial POST support - only update fields present in request.POST
                    general_corrections = {}
                    for k in ("proyecto", "proposito", "finalidad", "metodologia", "escenario_proyecto"):
                        if k in request.POST:
                            general_corrections[k] = request.POST.get(k, "")
                    if "campos_formativos" in request.POST or "campos_formativos_present" in request.POST:
                        raw_list = request.POST.getlist("campos_formativos")
                        general_corrections["campos_formativos"] = normalize_campos_formativos(raw_list)

                    target_s_id = request.POST.get("session_id")
                    if target_s_id is not None:
                        target_s_id = target_s_id.strip() or None

                    target_s_num = parsed_post_session_number

                    if target_s_id is None and target_s_num is None:
                        target_s_id = dossier.selection.get("session_id")
                        target_s_num = dossier.selection.get("session_number")

                    target_session = None
                    if target_s_id:
                        target_session = dossier.get_session(target_s_id)
                    elif target_s_num is not None:
                        target_session = dossier.get_session_by_number(target_s_num)
                    elif dossier.selection.get("session_id"):
                        target_session = dossier.get_session(dossier.selection["session_id"])
                    elif len(dossier.sessions) == 1:
                        target_session = dossier.sessions[0]

                    session_corrections = {}
                    for k in ("inicio", "desarrollo", "cierre", "materiales", "evaluacion", "contexto_ejecucion"):
                        if k in request.POST:
                            session_corrections[k] = request.POST.get(k, "")

                    annex_confirmations = {}
                    manual_annex_confirmations = {}

                    # 1. Candidate radios
                    for key, val in request.POST.items():
                        if key.startswith("annex_confirm_"):
                            ref_key = key.removeprefix("annex_confirm_")
                            try:
                                ref = _find_single_annex_ref(target_session, ref_key)
                            except ValueError as exc:
                                error_message = str(exc)
                                invalid_field = f"annex_confirm_{ref_key}"
                                inline_errors[invalid_field] = error_message
                                post_status_code = 400
                                break
                            effective_key = ref.reference_id

                            if val is None or val == "":
                                annex_confirmations[effective_key] = None
                            else:
                                try:
                                    p_int = parse_canonical_positive_int(val)
                                except ValueError:
                                    error_message = f"Número de página inválido '{val}' para Anexo {ref_key}."
                                    invalid_field = f"annex_confirm_{ref_key}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400
                                    break
                                if p_int < 1 or p_int > dossier.page_count:
                                    error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                    invalid_field = f"annex_confirm_{ref_key}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400
                                    break
                                annex_confirmations[effective_key] = p_int

                    # 2. Manual annex confirmations and disassociations
                    for key in request.POST.keys():
                        if key.startswith("annex_manual_page_"):
                            ref_key = key.removeprefix("annex_manual_page_")
                            try:
                                ref = _find_single_annex_ref(target_session, ref_key)
                            except ValueError as exc:
                                error_message = str(exc)
                                invalid_field = f"annex_manual_page_{ref_key}"
                                inline_errors[invalid_field] = error_message
                                post_status_code = 400
                                break
                            effective_key = ref.reference_id

                            page_raw = request.POST.get(key, "")
                            is_confirmed = (
                                request.POST.get(f"annex_manual_confirm_{ref_key}") in ("1", "on", "true", "True")
                                or request.POST.get(f"annex_manual_confirm_{ref.reference_id}") in ("1", "on", "true", "True")
                                or request.POST.get(f"annex_manual_confirm_{ref.annex_number}") in ("1", "on", "true", "True")
                            )
                            is_disassoc = (
                                request.POST.get(f"annex_disassociate_{ref_key}") in ("1", "on", "true", "True")
                                or request.POST.get(f"annex_disassociate_{ref.reference_id}") in ("1", "on", "true", "True")
                                or request.POST.get(f"annex_disassociate_{ref.annex_number}") in ("1", "on", "true", "True")
                            )

                            if is_disassoc:
                                annex_confirmations[effective_key] = None
                            elif is_confirmed:
                                if page_raw is None or str(page_raw) == "":
                                    error_message = f"Debe ingresar un número de página válido para confirmar el anexo {ref_key}."
                                    invalid_field = f"annex_manual_page_{ref_key}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400
                                    break
                                try:
                                    p_int = parse_canonical_positive_int(page_raw)
                                except ValueError:
                                    error_message = f"Número de página inválido '{page_raw}' para anexo {ref_key}."
                                    invalid_field = f"annex_manual_page_{ref_key}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400
                                    break
                                if p_int < 1 or p_int > dossier.page_count:
                                    error_message = f"Página {p_int} fuera de rango. El documento tiene {dossier.page_count} páginas."
                                    invalid_field = f"annex_manual_page_{ref_key}"
                                    inline_errors[invalid_field] = error_message
                                    post_status_code = 400
                                    break
                                annex_confirmations[effective_key] = p_int
                                manual_annex_confirmations[effective_key] = {"page": p_int, "confirmed": True}
                        elif key.startswith("annex_disassociate_"):
                            ref_key = key.removeprefix("annex_disassociate_")
                            try:
                                ref = _find_single_annex_ref(target_session, ref_key)
                            except ValueError as exc:
                                error_message = str(exc)
                                invalid_field = f"annex_disassociate_{ref_key}"
                                inline_errors[invalid_field] = error_message
                                post_status_code = 400
                                break
                            effective_key = ref.reference_id
                            if request.POST.get(key) in ("1", "on", "true", "True"):
                                annex_confirmations[effective_key] = None

                    corrections_payload = {
                        "general_fields": general_corrections,
                        "session_id": target_s_id,
                        "session_fields": session_corrections,
                        "annex_confirmations": annex_confirmations,
                        "manual_annex_confirmations": manual_annex_confirmations,
                        "reviews": {"__all__": "confirmed"} if action == "confirm_all" else {},
                    }
                    if "confirm_field" in request.POST:
                        cf_val = request.POST.get("confirm_field", "").strip()
                        if not cf_val:
                            return HttpResponseBadRequest("El campo 'confirm_field' no puede ser vacío.")
                        if cf_val.startswith("general:"):
                            parts = cf_val.split(":")
                            if len(parts) != 2 or not parts[1] or parts[1] not in GENERAL_FIELD_DISPLAY_ORDER:
                                return HttpResponseBadRequest(f"Clave malformada o inválida en confirm_field: '{cf_val}'.")
                            f_key = parts[1]
                            if any(k != f_key for k in general_corrections.keys()) or session_corrections or annex_confirmations or manual_annex_confirmations:
                                return HttpResponseBadRequest("confirm_field sólo permite confirmar el elemento especificado sin modificar otros campos.")
                            corrections_payload["reviews"] = {f_key: "confirmed"}
                        elif cf_val.startswith("session:"):
                            parts = cf_val.split(":")
                            if len(parts) < 3:
                                return HttpResponseBadRequest(f"Clave malformada en confirm_field: '{cf_val}'.")
                            f_key = parts[-1]
                            cf_sess_id = ":".join(parts[1:-1])
                            cf_sess = dossier.get_session(cf_sess_id)
                            if not cf_sess or f_key not in SESSION_FIELD_DISPLAY_ORDER:
                                return HttpResponseBadRequest(f"Sesión o campo no válido en confirm_field: '{cf_val}'.")
                            if target_s_id and target_s_id != cf_sess_id:
                                return HttpResponseBadRequest("Discrepancia entre session_id y confirm_field.")
                            target_s_id = cf_sess_id
                            corrections_payload["session_id"] = cf_sess_id
                            if general_corrections or any(k != f_key for k in session_corrections.keys()) or annex_confirmations or manual_annex_confirmations:
                                return HttpResponseBadRequest("confirm_field sólo permite confirmar el elemento especificado sin modificar otros campos.")
                            corrections_payload["reviews"] = {f_key: "confirmed"}
                        elif cf_val.startswith("annex:"):
                            parts = cf_val.split(":")
                            if len(parts) < 3:
                                return HttpResponseBadRequest(f"Clave malformada en confirm_field: '{cf_val}'.")
                            ref_id = parts[-1]
                            cf_sess_id = ":".join(parts[1:-1])
                            cf_sess = dossier.get_session(cf_sess_id)
                            if not cf_sess:
                                return HttpResponseBadRequest(f"Sesión no válida en confirm_field: '{cf_val}'.")
                            if target_s_id and target_s_id != cf_sess_id:
                                return HttpResponseBadRequest("Discrepancia entre session_id y confirm_field.")
                            target_s_id = cf_sess_id
                            corrections_payload["session_id"] = cf_sess_id
                            try:
                                ref_obj = _find_single_annex_ref(cf_sess, ref_id)
                            except ValueError as exc:
                                return HttpResponseBadRequest(str(exc))
                            if ref_obj is None:
                                return HttpResponseBadRequest(f"Anexo '{ref_id}' no encontrado en la sesión.")
                            if general_corrections or session_corrections:
                                return HttpResponseBadRequest("confirm_field sólo permite confirmar el elemento especificado sin modificar otros campos.")
                            if ref_obj.reference_id not in corrections_payload.get("annex_confirmations", {}):
                                if ref_obj.candidate_pages:
                                    corrections_payload.setdefault("annex_confirmations", {})[ref_obj.reference_id] = ref_obj.candidate_pages[0]
                                elif ref_obj.confirmed_page:
                                    corrections_payload.setdefault("annex_confirmations", {})[ref_obj.reference_id] = ref_obj.confirmed_page
                                else:
                                    return HttpResponseBadRequest(f"No hay lámina candidata para confirmar el anexo '{ref_id}'.")
                        else:
                            return HttpResponseBadRequest(f"Formato desconocido en confirm_field: '{cf_val}'.")
                    if "session_number" in request.POST:
                        corrections_payload["session_number"] = target_s_num

                    actor_name = request.user.get_full_name().strip() or request.user.username
                    if post_status_code != 400:
                        prev_version = dossier.version
                        try:
                            # Sol Item 2: Invalid annex page or invalid payload rejects before partial mutation / version bump
                            dossier = resolve(dossier, corrections_payload, actor=actor_name, pdf_source=getattr(job, "pdf", None))
                        except ValueError as exc:
                            error_message = str(exc)
                            post_status_code = 400

                    if post_status_code != 400:
                        if dossier.version == prev_version:
                            success_message = "Sin cambios: los valores recibidos coinciden con el dossier actual. Versión sin modificaciones."
                        else:
                            job.save_interpretation_dossier(dossier)
                            job.invalidate_approvals(reason=f"Modificación editorial a versión {dossier.version} guardada por el docente")
                            if action == "confirm_all":
                                success_message = f"Campos fundamentados de la sesión confirmados por {actor_name}. Versión {dossier.version} guardada."
                            elif "confirm_field" in request.POST and request.POST.get("confirm_field"):
                                cf_name = request.POST.get("confirm_field").strip()
                                success_message = f"Campo '{cf_name}' confirmado por {actor_name}. Versión {dossier.version} registrada."
                            else:
                                success_message = f"Correcciones guardadas correctamente por {actor_name}. Versión {dossier.version} registrada."

                    if target_s_id:
                        request_selected_session = dossier.get_session(target_s_id)
                    elif target_s_num:
                        try:
                            request_selected_session = dossier.get_session(int(target_s_num))
                        except (ValueError, TypeError):
                            pass

        elif action == "switch_session":
            if source_tampered:
                return HttpResponse(
                    "Conflicto de integridad: El archivo PDF fue modificado o reemplazado en el servidor "
                    "(SHA-256 no coincide con el dossier de interpretación). Las correcciones y confirmaciones "
                    "están bloqueadas para evitar desalineación de páginas. Debe realizar una reextracción explícita.",
                    status=409,
                )
            req_s_id = request.POST.get("session_id")
            req_s_num = parsed_post_session_number
            target_s = None
            if req_s_id and dossier:
                target_s = dossier.get_session(req_s_id)
            elif req_s_num is not None and dossier:
                matching = [s for s in dossier.sessions if s.session_number == req_s_num]
                if len(matching) == 1:
                    target_s = matching[0]
                elif len(matching) > 1:
                    raise Http404(
                        f"Selección ambigua: existen {len(matching)} sesiones con número {req_s_num}. "
                        "Especifique session_id para desambiguar."
                    )
            if target_s is None:
                raise Http404("Sesión solicitada no existe en el documento.")
            request_selected_session = target_s
            success_message = f"Sesión '{target_s.title}' seleccionada."

    elif request.method == "GET":
        req_session_id = request.GET.get("session_id")
        req_session_num = request.GET.get("session")

        if dossier is None:
            init_selection = {}
            if req_session_id:
                init_selection["session_id"] = req_session_id
            elif req_session_num:
                try:
                    init_selection["session_number"] = parse_canonical_positive_int(req_session_num)
                except ValueError:
                    raise Http404(f"Número de sesión inválido: '{req_session_num}'.")
            # Sol Item 1: Strict validation on first visit / initial prepare
            try:
                dossier = CurriculumSourceInterpreter.prepare(
                    job, selection=init_selection, job=job, timeout_seconds=30.0
                )
                job.save_interpretation_dossier(dossier)
            except TimeoutError as exc:
                from curriculum.interpretation_commands import record_direct_timeout

                record_direct_timeout(job, error_message=str(exc))
                return HttpResponse(f"Tiempo de extracción excedido: {exc}", status=504)
            except ValueError as exc:
                raise Http404(str(exc))
        else:
            # P0-2: Explicit validation - 404 on nonexistent session or ambiguous session
            if req_session_id:
                target_s = dossier.get_session(req_session_id)
                if target_s is None:
                    raise Http404(f"Sesión con ID '{req_session_id}' no encontrada en el documento.")
                request_selected_session = target_s
            elif req_session_num:
                try:
                    s_num = parse_canonical_positive_int(req_session_num)
                except ValueError:
                    raise Http404(f"Número de sesión inválido: '{req_session_num}'.")
                matching = [s for s in dossier.sessions if s.session_number == s_num]
                if len(matching) == 0:
                    raise Http404(f"Sesión número {s_num} no encontrada en el documento.")
                elif len(matching) > 1:
                    raise Http404(
                        f"Selección ambigua: existen {len(matching)} sesiones con número {s_num}. "
                        "Especifique session_id para desambiguar."
                    )
                request_selected_session = matching[0]

    if job.progress_stage:
        job.progress_stage = ""

    if dossier and (not job.page_count or job.page_count != dossier.page_count):
        job.page_count = dossier.page_count

    # Resolve active session for rendering
    selected_session = None
    if request_selected_session is not None:
        selected_session = request_selected_session
    elif dossier and dossier.sessions:
        active_s_id = dossier.selection.get("session_id") if dossier.selection else None
        if active_s_id:
            selected_session = dossier.get_session(active_s_id)
        if selected_session is None:
            active_session_num = dossier.selection.get("session_number", 1) if dossier.selection else 1
            selected_session = dossier.get_session(active_session_num)
        if selected_session is None:
            selected_session = dossier.sessions[0]

    campos_field = dossier.general_fields.get("campos_formativos") if dossier else None
    raw_campos_val = campos_field.value if campos_field else None
    campos_formativos_options = derive_campos_formativos_options(raw_campos_val)
    available_campos = [opt["value"] for opt in campos_formativos_options]
    current_campos = normalize_campos_formativos(raw_campos_val)

    # F7: Derive operational review queue
    req_scope = (
        request.GET.get("scope")
        or request.GET.get("session_filter")
        or (request.POST.get("scope") if request.method == "POST" else None)
        or (request.POST.get("session_filter") if request.method == "POST" else None)
    )
    try:
        operational_queue = derive_operational_queue(dossier, session_filter=req_scope) if dossier else None
    except SelectionError as exc:
        if request.method == "POST" or any(w in str(exc).lower() for w in ("ambiguo", "múltiples", "duplicado", "conflicto")):
            return HttpResponseBadRequest(str(exc))
        raise Http404(str(exc))
    except CurriculumInterpretationError as exc:
        return HttpResponseBadRequest(str(exc))

    req_item_key = request_selected_item_key or request.GET.get("item")
    active_item = None
    if operational_queue and operational_queue.items:
        if req_item_key:
            active_item = next((it for it in operational_queue.items if it.stable_key == req_item_key or it.item_id == req_item_key), None)
        if active_item is None and operational_queue.first_pending_key:
            active_item = next(
                (it for it in operational_queue.items if it.stable_key == operational_queue.first_pending_key),
                None,
            )
        if active_item is None:
            active_item = operational_queue.items[0]

    if invalid_field and operational_queue and operational_queue.items:
        matched_item = None
        for it in operational_queue.items:
            if it.field_name == invalid_field:
                matched_item = it
                break
            if it.scope == "annex" and it.reference_id and (
                it.reference_id in invalid_field
                or f"annex_{it.annex_number}" in invalid_field
                or f"annex_{it.reference_id}" in invalid_field
            ):
                matched_item = it
                break
        if matched_item:
            active_item = matched_item

    if (active_item and active_item.session_id and request_selected_session is None
            and req_scope in (None, "", "all", "document")):
        selected_session = dossier.get_session(active_item.session_id) or selected_session

    active_item_index = operational_queue.items.index(active_item) if (operational_queue and active_item) else -1
    prev_item = operational_queue.items[active_item_index - 1] if (operational_queue and active_item_index > 0) else None
    next_item = (
        operational_queue.items[active_item_index + 1]
        if (operational_queue and 0 <= active_item_index < len(operational_queue.items) - 1)
        else None
    )

    pending_items = (
        [it for it in operational_queue.items if it.priority_state in (PRIORITY_REQUIRES_RESOLUTION, PRIORITY_PENDING_REVIEW)]
        if operational_queue
        else []
    )
    pending_progress_current = (
        pending_items.index(active_item) + 1 if (active_item and active_item in pending_items) else None
    )
    pending_progress_total = len(pending_items)

    active_item_current_value = active_item.current_value if active_item else ""
    if request.method == "POST" and active_item:
        if active_item.field_name in request.POST:
            active_item_current_value = request.POST.get(active_item.field_name, "")
        elif "value" in request.POST:
            active_item_current_value = request.POST.get("value", "")

    active_annex_manual_page = ""
    active_annex_manual_confirmed = False
    if active_item and active_item.scope == "annex":
        ref_id = active_item.reference_id
        if request.method == "POST":
            active_annex_manual_page = (
                request.POST.get(f"annex_manual_page_{ref_id}")
                or request.POST.get("annex_manual_page")
                or request.POST.get("manual_page", "")
            )
            active_annex_manual_confirmed = (
                request.POST.get(f"annex_manual_confirm_{ref_id}") in ("1", "on", "true", "True")
                or request.POST.get("manual_confirm") in ("1", "on", "true", "True")
            )
        if not active_annex_manual_page and active_item.confirmed_page and active_item.confirmed_page not in active_item.candidate_pages:
            active_annex_manual_page = str(active_item.confirmed_page)
            active_annex_manual_confirmed = True

    active_item_inline_error = inline_errors.get(invalid_field, "") if invalid_field else ""
    active_inline_errors = {}
    if invalid_field and active_item_inline_error:
        if "manual" in invalid_field:
            active_inline_errors["annex_manual_page"] = active_item_inline_error
        else:
            active_inline_errors[invalid_field] = active_item_inline_error

    submitted_post = {}
    if request.method == "POST":
        for k, v in request.POST.items():
            submitted_post[k] = v

    validated_report_context = None
    checked_items = []
    if report_valid and isinstance(report, dict):
        from curriculum.verification import compute_canonical_verification_report
        canonical_report = compute_canonical_verification_report(dossier, current_bytes)
        checked_cnt = sum(1 for i in canonical_report.get("items", []) if i.get("status") == "checked")
        review_cnt = sum(1 for i in canonical_report.get("items", []) if i.get("status") == "needs_teacher_review")
        checked_items = [i for i in canonical_report.get("items", []) if i.get("status") == "checked"]
        validated_report_context = dict(canonical_report)
        validated_report_context["checked_count"] = checked_cnt
        validated_report_context["needs_review_count"] = review_cnt
        validated_report_context["blocked_count"] = 0

    active_approval = job.get_active_approval(pdf_bytes=current_bytes)
    is_approved = active_approval is not None
    can_approve = bool(
        is_valid_ready
        and not source_tampered
        and report_valid
        and validated_report_context
        and validated_report_context.get("blocked_count", 0) == 0
        and operational_queue
        and operational_queue.requires_resolution_count == 0
    )

    context = {
        "job": job,
        "dossier": dossier,
        "selected_session": selected_session,
        "active_session_id": selected_session.session_id if selected_session else "",
        "active_session_number": selected_session.session_number if selected_session else 1,
        "current_pdf_sha256": current_pdf_sha256,
        "source_tampered": source_tampered,
        "success_message": success_message,
        "error_message": error_message,
        "invalid_field": invalid_field,
        "inline_errors": inline_errors,
        "active_inline_errors": active_inline_errors,
        "active_item_inline_error": active_item_inline_error,
        "active_item_current_value": active_item_current_value,
        "active_annex_manual_page": active_annex_manual_page,
        "active_annex_manual_confirmed": active_annex_manual_confirmed,
        "submitted_post": submitted_post,
        "post_status_code": post_status_code,
        "available_campos": available_campos,
        "current_campos": current_campos,
        "campos_formativos_options": campos_formativos_options,
        "queue": operational_queue,
        "active_item": active_item,
        "active_item_index": active_item_index,
        "prev_item": prev_item,
        "next_item": next_item,
        "pending_progress_current": pending_progress_current,
        "pending_progress_total": pending_progress_total,
        "verification_report": validated_report_context,
        "checked_items": checked_items,
        "active_approval": active_approval,
        "is_approved": is_approved,
        "can_approve": can_approve,
    }
    return render(request, "curriculum/tutor_import_interpretation.html", context, status=post_status_code)


@teacher_required
@require_http_methods(["POST"])
def tutor_import_approve(request, job_id):
    """Dedicated POST endpoint for explicit teacher approval of CurriculumImportJob."""
    from curriculum.approval_commands import execute_teacher_approval

    result = execute_teacher_approval(
        job_id=job_id,
        user=request.user,
        post_data=request.POST,
        is_dedicated_route=True,
    )
    if not result.is_success:
        if result.http_status == 404:
            raise Http404(result.message)
        return HttpResponse(result.message, status=result.http_status)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", "message": result.message})
    return redirect("tutor-import-interpretation", job_id=job_id)



@teacher_required

@require_http_methods(["GET", "POST"])
def tutor_import_detail(request, job_id):
    """Staging review: extraction, topic/subtopic proposals and checkpoints.

    Every LLM stage runs only on explicit teacher action, and every proposal
    stays editable until confirmed. No CurriculumPackage is ever created here.
    """

    from curriculum import curriculum_import as pipeline

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    if job.progress_stage and not _is_import_stage_stale(job):
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
    if request.method == "POST" and hasattr(request, "session"):
        request.session.pop(f"legacy_stage_{job.pk}", None)
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
        drafts = CurriculumPackage.objects.filter(
            ai_assisted=True,
            created_by=request.user,
        ).order_by("-id")[:20]
        context["drafts"] = drafts
        context["drafts_count"] = drafts.count()
    return render(request, "curriculum/tutor_import_detail.html", context)


def _import_action_extract(job, pipeline):
    """Extract source, using deterministic annex staging when safe.

    Unrecognised documents continue through Stage B topic identification and
    the existing human checkpoints unchanged.
    """

    chunks = job.extract_text()
    fast_path = pipeline.build_annex_fast_path(job.source_text)
    if fast_path is not None:
        return _import_action_annex_fast_path(job, fast_path)
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
    job.progress_finished_at = timezone.now()
    job.save()
    return job


def _import_action_annex_fast_path(job, fast_path):
    """Persist deterministic annex companions as reviewable staging data.

    This deliberately ends in ``ACTIVITIES_PROPOSED``: a teacher still reviews
    and selects the proposals before conversion, and no curriculum progress,
    publication, or approval state is touched.  Each item is saved separately
    so the existing waiting page can report partial work if the worker stops.
    """

    activities = list(fast_path.get("activities") or [])
    if not activities:
        raise ValueError("La vía rápida no produjo anexos revisables.")
    # Replays are expected after worker retries. Replace this stage's entries
    # while retaining diagnostics from earlier/fallback stages.
    now_log = [entry for entry in job.llm_log if entry.get("stage") != "annex_fast_path"]
    job.topics = list(fast_path.get("topics") or [])
    job.activities = []
    job.progress_total = len(activities)
    job.progress_done = 0
    job.error_message = ""
    job.save(
        update_fields=[
            "source_text",
            "page_count",
            "topics",
            "activities",
            "progress_total",
            "progress_done",
            "error_message",
            "updated_at",
        ]
    )
    for index, activity in enumerate(activities, start=1):
        job.activities = list(job.activities) + [activity]
        annex = activity.get("annex") or {}
        now_log.append(
            {
                "stage": "annex_fast_path",
                "subtema": activity.get("subtopic_title", ""),
                "pages": annex.get("source_pages", []),
                "kind": annex.get("kind", ""),
                "reactivos": len(activity.get("proposal", {}).get("questions", [])),
                "is_valid": bool(activity.get("is_valid")),
                "llm_calls": 0,
            }
        )
        job.progress_done = index
        job.llm_log = now_log
        job.save(
            update_fields=[
                "activities",
                "llm_log",
                "progress_done",
                "updated_at",
            ]
        )
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            _finish_cancelled_import_stage(job)
            return job
    job.status = CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    job.progress_stage = ""
    job.progress_finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "progress_stage",
            "progress_finished_at",
            "error_message",
            "updated_at",
        ]
    )
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
    job.progress_finished_at = timezone.now()
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
    job.progress_finished_at = timezone.now()
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
    job.progress_finished_at = timezone.now()
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
    """Human checkpoint 3: convert selected valid proposals into drafts.

    Selection resolves by stable activity identity (``_activity_id``), never
    by submitted list position: a stale/reordered positional index must fail
    closed instead of converting the wrong activity. A bare numeric index is
    honoured only as a legacy alias for entries that carry no explicit
    ``id`` (their stable identity is already the ``idx-<position>``
    fallback), preserving jobs staged before explicit ids existed.
    """

    from curriculum.models import CurriculumPackage

    targets = post_data.getlist("select")
    if not targets:
        raise ValueError("Selecciona al menos una actividad válida para convertir.")
    wanted = []
    seen_targets = set()
    for raw in targets:
        key = str(raw if raw is not None else "").strip()
        if not key or key in seen_targets:
            continue
        seen_targets.add(key)
        wanted.append(key)
    if not wanted:
        raise ValueError("Selecciona al menos una actividad válida para convertir.")
    activities = list(job.activities or [])
    matched_indices: list[int] = []
    for key in wanted:
        found = None
        for index, entry in enumerate(activities):
            if index in matched_indices:
                continue
            if not isinstance(entry, dict):
                continue
            if str(_activity_id(entry, index)) == key:
                found = index
                break
        if found is None:
            try:
                legacy_index = int(key, 10)
            except (TypeError, ValueError):
                continue
            if 0 <= legacy_index < len(activities):
                legacy_entry = activities[legacy_index]
                if (
                    isinstance(legacy_entry, dict)
                    and not legacy_entry.get("id")
                    and legacy_index not in matched_indices
                ):
                    # Legacy alias only: entries without an explicit id have
                    # no reorder-proof identity to resolve, so the submitted
                    # position is the only available reference.
                    found = legacy_index
        if found is None:
            raise ValueError(
                "Selecciona al menos una actividad válida para convertir. "
                f"La identidad '{key}' es inválida o está desactualizada."
            )
        matched_indices.append(found)

    stream_block = CurriculumPackage._meta.get_field("questions").stream_block
    valid_block_types = stream_block.child_blocks

    to_convert: list[tuple[int, dict[str, Any]]] = []
    for idx in matched_indices:
        entry = activities[idx]
        if not isinstance(entry, dict):
            raise ValueError(f"Formato inválido en la actividad {idx}.")
        if not entry.get("is_valid"):
            continue  # un reactivo inválido nunca se convierte, ni marcándolo

        proposal = entry.get("proposal")
        if not isinstance(proposal, dict):
            raise ValueError(f"Propuesta ausente o inválida en la actividad {idx}.")

        # Cuatro campos escalares requeridos y tipos estrictos (str no vacío)
        for field in ("title", "objective", "micro_lesson", "final_explanation"):
            if field not in proposal:
                raise ValueError(f"Campo requerido '{field}' ausente en la actividad {idx}.")
            val = proposal[field]
            if not isinstance(val, str) or isinstance(val, bool) or not val.strip():
                raise ValueError(f"Campo requerido '{field}' debe ser una cadena de texto no vacía en la actividad {idx}.")

        # Questions lista y cada pregunta dict con block_type y value válidos
        questions = proposal.get("questions")
        if not isinstance(questions, (list, tuple)) or isinstance(questions, (str, bytes)):
            raise ValueError(f"Lista de preguntas ausente o inválida en la actividad {idx}.")
        for q_idx, question in enumerate(questions):
            if not isinstance(question, dict):
                raise ValueError(f"Pregunta {q_idx} en actividad {idx} no es un diccionario válido.")
            if "block_type" not in question or "value" not in question:
                raise ValueError(f"Pregunta {q_idx} en actividad {idx} carece de block_type o value.")
            block_type = question["block_type"]
            if not isinstance(block_type, str) or block_type not in valid_block_types:
                raise ValueError(
                    f"Tipo de reactivo desconocido o inválido '{block_type}' en la actividad {idx}. "
                    f"Tipos permitidos: {list(valid_block_types.keys())}."
                )
            q_val = question["value"]
            if not isinstance(q_val, dict):
                raise ValueError(
                    f"El valor de la pregunta {q_idx} en la actividad {idx} debe ser un diccionario compatible con el bloque."
                )
            child_block = valid_block_types[block_type]
            try:
                child_block.clean(child_block.to_python(q_val))
            except Exception as err:
                raise ValueError(f"Estructura inválida en reactivo {q_idx} de la actividad {idx}: {err}")

        # Annex si se usa con tipos seguros
        annex = entry.get("annex")
        if annex is not None:
            if not isinstance(annex, dict):
                raise ValueError(f"Estructura de anexo inválida en la actividad {idx}.")
            for text_field in ("kind", "source_anchor", "source_url", "source_text"):
                if text_field in annex and annex[text_field] is not None:
                    if not isinstance(annex[text_field], str):
                        raise ValueError(f"Campo '{text_field}' del anexo en la actividad {idx} debe ser texto.")
            if "number" in annex and annex["number"] is not None:
                if not isinstance(annex["number"], (int, str)) or isinstance(annex["number"], bool):
                    raise ValueError(f"Número de anexo inválido en la actividad {idx}.")
            if "source_pages" in annex and annex["source_pages"] is not None:
                sp = annex["source_pages"]
                if not isinstance(sp, (list, tuple)) or isinstance(sp, (str, bytes)):
                    raise ValueError(f"Páginas de fuente de anexo inválidas en la actividad {idx}.")
                for p in sp:
                    if not isinstance(p, int) or isinstance(p, bool) or p < 1:
                        raise ValueError(f"Página de anexo inválida ({p}) en la actividad {idx}: debe ser entero >= 1.")
            if "source_urls" in annex and annex["source_urls"] is not None:
                su = annex["source_urls"]
                if not isinstance(su, (list, tuple)) or isinstance(su, (str, bytes)):
                    raise ValueError(f"URLs de fuente de anexo inválidas en la actividad {idx}.")
                for u in su:
                    if not isinstance(u, str):
                        raise ValueError(f"URL de anexo inválida en la actividad {idx}: debe ser cadena de texto.")

        to_convert.append((idx, entry))

    source_pdf_content = None
    source_pdf_sha256 = ""
    if job.pdf:
        with job.pdf.open("rb") as source_pdf:
            source_pdf_content = source_pdf.read()
        source_pdf_sha256 = hashlib.sha256(source_pdf_content).hexdigest()

    created = 0
    with transaction.atomic():
        for idx, entry in to_convert:
            annex = entry.get("annex") or {}
            source_references = []
            if annex:
                source_text = str(annex.get("source_text") or "")
                source_references = [
                    {
                        "import_job_id": job.pk,
                        "number": annex.get("number"),
                        "kind": annex.get("kind", ""),
                        "source_pages": list(annex.get("source_pages") or []),
                        "source_anchor": annex.get("source_anchor", ""),
                        "source_url": annex.get("source_url", ""),
                        "source_urls": list(annex.get("source_urls") or []),
                        "source_text": source_text,
                        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                        "source_pdf_sha256": source_pdf_sha256,
                    }
                ]
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
                source_references=source_references,
                source_pdf=(
                    ContentFile(source_pdf_content, name="source.pdf")
                    if source_pdf_content is not None and source_references
                    else None
                ),
                source_pdf_sha256=source_pdf_sha256 if source_references else "",
                created_by=job.created_by,
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


def _roadmap_context(session, turn, progress=None):
    progress = progress or (StudentRoadmapProgress.for_turn(turn) if turn is not None else None)
    group_progress = GroupRoadmapProgress.for_session(session)
    group_states = group_progress.states() if group_progress else []
    return {
        "roadmap_progress": progress,
        "group_roadmap_progress": group_progress,
        "roadmap_states": group_states,
        "roadmap_completed": bool(group_states and all(row["state"] == "COMPLETADA" for row in group_states)),
        "roadmap_is_shared": bool(group_progress),
        "roadmap_snapshot": session.roadmap_snapshot,
    }


def _activity_snapshot(session, progress=None):
    """Resolve the immutable package for the current roadmap activity."""

    if session.roadmap_snapshot_id is None:
        return session.snapshot
    group = GroupRoadmapProgress.for_session(session)
    activity_id = group.current_activity_id or next(
        (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
    )
    if activity_id is None:
        return session.snapshot
    from curriculum.roadmap import ordered_activities
    activity = next(row for row in ordered_activities(session.roadmap_snapshot.payload)
                    if row["id"] == activity_id)
    snapshot_id = activity.get("package_snapshot_id") or session.snapshot_id
    return PublishedPackageSnapshot.objects.get(pk=snapshot_id)


def _roadmap_activity_ids(session):
    if session.roadmap_snapshot_id is None:
        return []
    from curriculum.roadmap import ordered_activity_ids

    return ordered_activity_ids(session.roadmap_snapshot.payload)


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
    progress = StudentRoadmapProgress.for_turn(turn) if turn is not None else None
    group = GroupRoadmapProgress.for_session(session)
    roadmap_completed = bool(group and group.states() and all(
        row["state"] == "COMPLETADA" for row in group.states()
    ))
    activity_snapshot = session.snapshot if roadmap_completed else _activity_snapshot(session, progress)
    item_activity_id = None
    if group and not roadmap_completed:
        item_activity_id = group.current_activity_id or next(
            (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
        )
    context = {
        "session": session,
        "snapshot": activity_snapshot,
        "snapshot_payload": activity_snapshot.payload,
        "turn": turn,
        "activity_questions": [] if roadmap_completed else _activity_questions(session, turn, activity_snapshot),
        "roadmap_completed": roadmap_completed,
        "item_activity_id": item_activity_id,
        **_roadmap_context(session, turn, progress),
    }
    context.update(extra)
    return context


def _activity_questions(session, turn, activity_snapshot=None):
    activity_snapshot = activity_snapshot or session.snapshot
    questions = activity_snapshot.payload.get("questions", []) or []
    progress = StudentRoadmapProgress.for_turn(turn) if turn is not None else None
    group = GroupRoadmapProgress.for_session(session)
    activity_id = group.current_activity_id if group and group.current_activity_id else next(
        (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
    ) if group else None
    activity_questions = []
    turn_id = turn.pk if turn is not None else session.pk
    for question_index, question in enumerate(questions):
        value = question.get("value", {}) if isinstance(question, dict) else {}
        hint_state = _current_hint_state(
            turn_id,
            question_index,
            session_id=session.pk,
            activity_id=activity_id,
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


def _complete_activity_after_response(session, turn, question_index):
    """Persist correctness and advance the shared session route immediately."""

    progress = StudentRoadmapProgress.for_turn(turn)
    if progress is None:
        return False
    group = GroupRoadmapProgress.for_session(session)
    activity_id = group.current_activity_id or next(
        (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
    )
    if activity_id is None:
        return False
    activity_snapshot = _activity_snapshot(session, progress)
    questions = activity_snapshot.payload.get("questions", []) or []
    if not questions:
        return False
    completed = progress.record_correct_answer(
        activity_id,
        question_index,
        len(questions),
        enforce_current=False,
    )
    if completed:
        group.complete_activity(activity_id)
    return completed


def _hint_progress_key(turn_id, question_index, activity_id=None):
    if activity_id is None:
        return f"{HINT_PROGRESS_KEY_PREFIX}:{turn_id}:{question_index}"
    return f"{HINT_PROGRESS_KEY_PREFIX}:{turn_id}:{activity_id}:{question_index}"


def _consumed_hint_key(turn_id, question_index, capability, activity_id=None):
    digest = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    if activity_id is None:
        return f"{HINT_PROGRESS_KEY_PREFIX}:consumed:{turn_id}:{question_index}:{digest}"
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed:{turn_id}:{activity_id}:{question_index}:{digest}"


def _consumed_hint_index_key(turn_id, question_index, activity_id=None):
    if activity_id is None:
        return f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn_id}:{question_index}"
    return f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn_id}:{activity_id}:{question_index}"


def _current_hint_state(turn_id, question_index, *, session_id=None, activity_id=None):
    """Read the ephemeral anti-replay/progression state, never learning evidence."""

    key = _hint_progress_key(turn_id, question_index, activity_id)
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
            activity_id=activity_id,
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
    activity_id=None,
):
    """Atomically consume one nonce, then advance temporal hint authorization."""

    state = _current_hint_state(
        turn_id,
        question_index,
        session_id=session_id,
        activity_id=activity_id,
    )
    if (
        state["next_hint_index"] != hint_index
        or state["capability"] != capability
    ):
        return False
    if not cache.add(
        _consumed_hint_key(turn_id, question_index, capability, activity_id),
        True,
        timeout=HINT_PROGRESS_TTL,
    ):
        return False
    consumed_key = _consumed_hint_key(turn_id, question_index, capability, activity_id)
    consumed_index_key = _consumed_hint_index_key(turn_id, question_index, activity_id)
    consumed_keys = cache.get(consumed_index_key, []) or []
    cache.set(consumed_index_key, [*consumed_keys, consumed_key], timeout=HINT_PROGRESS_TTL)
    cache.set(
        _hint_progress_key(turn_id, question_index, activity_id),
        {
            "next_hint_index": hint_index + 1,
            "capability": issue_capability(
                "hint",
                session_id=session_id if session_id is not None else turn_id,
                question_index=question_index,
                turn_id=turn_id,
                next_hint_index=hint_index + 1,
                activity_id=activity_id,
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
    progress = StudentRoadmapProgress.for_turn(turn)
    if progress is None:
        return HttpResponseBadRequest("La sesión no tiene un roadmap publicado.")
    try:
        group = GroupRoadmapProgress.for_session(session)
        if activity_id != (group.current_activity_id or next(
            (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
        )):
            raise ValidationError("La actividad todavía no es el paso actual del grupo.")
        activity_snapshot = _activity_snapshot(session, progress)
        if activity_snapshot.payload.get("questions"):
            correct_indices = (progress.correct_question_indices or {}).get(str(activity_id), [])
            question_count = len(activity_snapshot.payload.get("questions", []) or [])
            if len(set(correct_indices)) < question_count:
                return HttpResponseBadRequest(
                    "La actividad requiere completar correctamente sus reactivos."
                )
        progress.complete_activity(activity_id, package_snapshot=activity_snapshot, enforce_current=False)
        group.complete_activity(activity_id)
    except (ValidationError, PublishedPackageSnapshot.DoesNotExist) as error:
        return HttpResponseBadRequest(str(error))
    return redirect("student-roadmap", session_id=session_id)


@never_cache
@transaction.atomic
@require_POST
def student_question_answer(request, session_id, question_index):
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
            "La respuesta requiere el turno activo y la capacidad de este dispositivo."
        )
    progress = StudentRoadmapProgress.for_turn(turn)
    group = GroupRoadmapProgress.for_session(session)
    activity_id = group.current_activity_id if group and group.current_activity_id else next(
        (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
    ) if group else None
    posted_activity_id = str(request.POST.get("activity_id", "")).strip()
    if group and posted_activity_id != activity_id:
        return HttpResponseBadRequest("La actividad ya cambió para el grupo.")
    try:
        result = evaluate_response(
            _activity_snapshot(session, progress).payload,
            question_index,
            request.POST.get("option_position"),
        )
    except PracticeContractError as error:
        return HttpResponseBadRequest(str(error))
    record_ephemeral_response(session_id, turn, result, activity_id=activity_id)
    activity_completed = result.is_correct and _complete_activity_after_response(
        session,
        turn,
        result.question_index,
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
                activity_id=activity_id,
            ),
            activity_completed=activity_completed,
        ),
    )


@never_cache
@transaction.atomic
@require_POST
def student_question_assistance(request, session_id, question_index):
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
            "La ayuda requiere el turno activo y la capacidad de este dispositivo."
        )
    progress = StudentRoadmapProgress.for_turn(turn)
    group = GroupRoadmapProgress.for_session(session)
    activity_id = group.current_activity_id if group and group.current_activity_id else next(
        (row["id"] for row in group.states() if row["state"] == "ACTUAL"), None
    ) if group else None
    activity_snapshot = _activity_snapshot(session, progress)
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
                activity_id=activity_id,
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
                activity_id=activity_id,
            )
            is None
        ):
            return HttpResponseBadRequest(
                "La explicación final requiere una capacidad emitida después de responder."
            )

    try:
        assistance = request_assistance(
            activity_snapshot.payload,
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
        activity_id=activity_id,
    ):
        return HttpResponseBadRequest("La capacidad de pista ya fue consumida o quedó fuera de orden.")
    record_ephemeral_help(
        session_id,
        turn,
        question_index,
        assistance,
        activity_id=activity_id,
    )

    next_hint_capability = None
    if assistance.next_hint_index is not None:
        next_hint_capability = _current_hint_state(
            turn.pk,
            question_index,
            session_id=session_id,
            activity_id=activity_id,
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
