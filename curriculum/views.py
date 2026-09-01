import csv
import hashlib
from collections import Counter
import io
import json
import threading
import time
import unicodedata
import uuid
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core import signing
from django.core.cache import cache
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, OperationalError
from django.db import transaction
from django.db.models import Q
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
        sessions = list(group.sessions.order_by("-started_at", "-id"))
        assignments = list(
            group.teacher_assignments.order_by("-created_at", "-id")
        )
        latest = sessions[0] if sessions else None
        result_batches = [session.result_batch_id for session in sessions]
        result_qs = PseudonymousResult.objects.filter(result_batch_id__in=result_batches)
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
                "worked_activity_count": result_qs.values("activity_id").distinct().count(),
                "participation_count": result_qs.values("participant_key").distinct().count(),
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
        },
    )


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
                **{key: _csv_safe_text(value) for key, value in row.items() if key != "assignments"},
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

    return render(
        request,
        "curriculum/tutor_curriculum.html",
        {
            "imports": CurriculumImportJob.objects.filter(
                created_by=request.user
            ).order_by("-updated_at", "-id")[:20],
            "package_cards": package_cards,
            "published_snapshots": PublishedPackageSnapshot.objects.filter(
                package__created_by=request.user
            ).select_related("package").order_by("-published_at", "-id")[:20],
        },
    )


@teacher_required
def tutor_package_detail(request, snapshot_id):
    """Show one immutable published activity in teacher language."""

    snapshot = get_object_or_404(
        PublishedPackageSnapshot.objects.select_related("package"),
        pk=snapshot_id,
        package__created_by=request.user,
    )
    payload = snapshot.payload or {}
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

            connection.close()


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
        updated_at=started_at,
    )
    if not claimed:
        # Compare-and-set closes the stale-request race: only one worker starts.
        return redirect("tutor-import-wait", job_id=job.pk)
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


@teacher_required
@require_http_methods(["GET"])
def tutor_import_wait(request, job_id):
    """Waiting shell updated by incremental polling while a stage runs."""

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    _release_stale_import_stage(job)
    if not job.progress_stage:
        return redirect("tutor-import-detail", job_id=job.pk)
    return render(
        request,
        "curriculum/tutor_import_wait.html",
        {
            "job": job,
            "progress_state": _import_progress_state(job),
            "wait_message": IMPORT_STAGE_WAIT_MESSAGES.get(
                job.progress_stage,
                "El asistente virtual está trabajando…",
            ),
        },
    )


def _import_progress_state(job):
    if job.progress_stage:
        if job.progress_done:
            return "partial"
        if job.progress_total:
            return "working"
        return "waiting"
    if job.error_message:
        return "error"
    return "finished"


IMPORT_PROGRESS_LABELS = {
    "waiting": "Esperando al asistente",
    "working": "El asistente está trabajando",
    "partial": "Hay un resultado parcial guardado",
    "finished": "Generación terminada",
    "error": "La generación se interrumpió",
}


@teacher_required
@require_http_methods(["GET"])
def tutor_import_status(request, job_id):
    """Small owner-scoped polling payload; never starts or repeats work."""

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
    _release_stale_import_stage(job)
    state = _import_progress_state(job)
    return JsonResponse(
        {
            "state": state,
            "label": IMPORT_PROGRESS_LABELS[state],
            "stage": job.progress_stage,
            "done": job.progress_done,
            "total": job.progress_total,
            "error": job.error_message,
            "started_at": (
                job.progress_started_at.isoformat()
                if job.progress_started_at is not None
                else None
            ),
            "finished_at": (
                job.progress_finished_at.isoformat()
                if job.progress_finished_at is not None
                else None
            ),
            "redirect_url": reverse("tutor-import-detail", args=[job.pk]),
        }
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
        pdf = request.FILES.get("pdf")
        if pdf is None:
            return render(
                request,
                "curriculum/tutor_import_form.html",
                {"error": "Selecciona el PDF de la currícula."},
                status=400,
            )
        job = CurriculumImportJob.objects.create(pdf=pdf, created_by=request.user)
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

    job = get_object_or_404(
        CurriculumImportJob,
        pk=job_id,
        created_by=request.user,
    )
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
        drafts = CurriculumPackage.objects.filter(
            ai_assisted=True,
            created_by=request.user,
        ).order_by("-id")[:20]
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
    job.progress_finished_at = timezone.now()
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
