import hashlib
import json
import os
import re
import uuid

import django
import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
    StudentTurn,
)
from curriculum.views import HINT_PROGRESS_KEY_PREFIX  # noqa: E402
import curriculum.views as curriculum_views  # noqa: E402


pytestmark = pytest.mark.django_db


def published_snapshot(title="Paquete T07", *, with_question=False):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": "Una idea principal organiza el sentido.",
        "questions": (
            [
                {
                    "type": "reactivo",
                    "value": {
                        "prompt": "¿Cuál opción corresponde?",
                        "options": [
                            {
                                "position": 1,
                                "text": "La idea principal",
                                "expected": True,
                                "feedback": "Elegiste la idea principal.",
                            },
                            {
                                "position": 2,
                                "text": "Un detalle",
                                "expected": False,
                                "feedback": "Elegiste un detalle.",
                            },
                        ],
                        "hints": [
                            "Busca la afirmación que organiza el sentido.",
                            "Después distingue los detalles.",
                        ],
                    },
                }
            ]
            if with_question
            else []
        ),
        "final_explanation": "La idea principal organiza el sentido.",
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{title}-{package.pk}",
        ),
    )


def active_session(*, student_count=2, device_count=1):
    snapshot = published_snapshot()
    session = ClassroomSession.prepare_from_snapshot(
        snapshot,
        student_count,
        device_count,
    )
    session.confirm()
    return session


def active_question_session(*, student_count=2, device_count=1):
    snapshot = published_snapshot(with_question=True)
    session = ClassroomSession.prepare_from_snapshot(
        snapshot,
        student_count,
        device_count,
    )
    session.confirm()
    return session


def hidden_capability(response, name):
    matches = re.findall(rf'name="{name}" value="([^"]+)"', response.text)
    assert matches, f"No se emitió la capacidad {name}."
    return matches[-1]


def test_device_captures_a_non_empty_reasonable_apodo_and_keeps_it_out_of_tutor_review():
    session = active_session()
    assignment = session.device_assignments.get()
    client = Client()

    response = client.post(
        reverse(
            "student-turn-start",
            args=[session.pk, assignment.local_identifier],
        ),
        {"display_name": "  Luna  "},
    )

    assert response.status_code == 302
    turn = StudentTurn.objects.get()
    assert turn.display_name == "Luna"
    assert "Luna" not in client.get(
        reverse("tutor-session-review", args=[session.pk])
    ).text


@pytest.mark.parametrize(
    "display_name",
    ["", "   ", "\t\n\r\v\f", "x" * 81],
)
def test_device_rejects_an_empty_or_unreasonably_long_apodo(display_name):
    session = active_session()
    assignment = session.device_assignments.get()

    response = Client().post(
        reverse(
            "student-turn-start",
            args=[session.pk, assignment.local_identifier],
        ),
        {"display_name": display_name},
    )

    assert response.status_code == 400
    assert not StudentTurn.objects.exists()


def test_equal_names_get_independent_uuid_turns_and_progress_capacity_on_each_assignment():
    session = active_session(student_count=2, device_count=2)
    assignments = list(session.device_assignments.order_by("id"))
    first_client = Client()
    second_client = Client()

    first_response = first_client.post(
        reverse("student-turn-start", args=[session.pk, assignments[0].local_identifier]),
        {"display_name": "Luna"},
    )
    second_response = second_client.post(
        reverse("student-turn-start", args=[session.pk, assignments[1].local_identifier]),
        {"display_name": "Luna"},
    )

    turns = list(StudentTurn.objects.order_by("started_at", "id"))
    assert first_response.status_code == second_response.status_code == 302
    assert len(turns) == 2
    assert turns[0].display_name == turns[1].display_name == "Luna"
    assert turns[0].pk != turns[1].pk
    assert turns[0].assignment_id != turns[1].assignment_id
    assert all(
        DeviceAssignment.objects.get(pk=assignment.pk).remaining_capacity == 0
        for assignment in assignments
    )


def test_turn_cookie_is_httponly_and_cannot_continue_another_assignment_or_without_it():
    session = active_session(student_count=2, device_count=2)
    assignments = list(session.device_assignments.order_by("id"))
    client = Client()

    started = client.post(
        reverse("student-turn-start", args=[session.pk, assignments[0].local_identifier]),
        {"display_name": "Luna"},
    )
    cookie = started.cookies.get("aulalista.student-turn")

    assert cookie is not None
    assert cookie["httponly"] is True
    assert client.get(
        reverse("student-turn-start", args=[session.pk, assignments[1].local_identifier])
    ).status_code == 403

    other_device = Client()
    assert other_device.get(
        reverse("student-activity", args=[session.pk])
    ).status_code == 403


def test_session_activity_url_cannot_bypass_a_turn():
    session = active_session()

    response = Client().get(reverse("student-activity", args=[session.pk]))

    assert response.status_code == 403


def test_t05_answer_and_help_require_the_active_turn_and_do_not_write_answer_data():
    session = active_question_session()
    assignment = session.device_assignments.get()
    answer_url = reverse("student-question-answer", args=[session.pk, 0])
    assistance_url = reverse("student-question-assistance", args=[session.pk, 0])

    blocked_answer = Client().post(answer_url, {"option_position": 1})
    blocked_help = Client().post(assistance_url, {"kind": "hint", "hint_index": 0})
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    activity = client.get(reverse("student-activity", args=[session.pk]))
    hint_capability = hidden_capability(activity, "hint_capability")
    answer = client.post(answer_url, {"option_position": 1})
    help_response = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": hint_capability,
        },
    )

    assert blocked_answer.status_code == blocked_help.status_code == 403
    assert answer.status_code == help_response.status_code == 200
    assert "Respuesta correcta" in answer.text
    assert "Busca la afirmación que organiza el sentido." in help_response.text
    assert not any(field in {field.name for field in StudentTurn._meta.fields} for field in ["answer", "score"])


def test_ready_is_idempotent_clears_ephemeral_context_and_allows_a_fresh_turn():
    session = active_question_session(student_count=2, device_count=1)
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    activity = client.get(reverse("student-activity", args=[session.pk]))
    first_hint = client.post(
        reverse("student-question-assistance", args=[session.pk, 0]),
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": hidden_capability(activity, "hint_capability"),
        },
    )
    old_turn = StudentTurn.objects.get(status=StudentTurn.STATUS_ACTIVE)
    ready = client.post(reverse("student-turn-ready", args=[session.pk]))
    old_turn.refresh_from_db()
    repeated_ready = client.post(reverse("student-turn-ready", args=[session.pk]))

    assert first_hint.status_code == 200
    assert ready.status_code == 302
    assert repeated_ready.status_code == 302
    assert old_turn.status == StudentTurn.STATUS_COMPLETED
    assert old_turn.display_name == ""
    assert old_turn.completed_at is not None
    assert cache.get(f"{HINT_PROGRESS_KEY_PREFIX}:{old_turn.pk}:0") is None
    assert client.get(reverse("student-activity", args=[session.pk])).status_code == 403

    fresh_start = client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Sol"},
    )
    fresh_turn = StudentTurn.objects.exclude(pk=old_turn.pk).get()
    fresh_activity = client.get(reverse("student-activity", args=[session.pk]))

    assert fresh_start.status_code == 302
    assert fresh_turn.pk != old_turn.pk
    assert fresh_turn.status == StudentTurn.STATUS_ACTIVE
    assert fresh_turn.display_name == "Sol"
    assert 'name="hint_index" value="0"' in fresh_activity.text


def test_capacity_is_consumed_once_per_turn_and_never_overflows():
    session = active_session(student_count=2, device_count=1)
    assignment = session.device_assignments.get()
    client = Client()
    start_url = reverse(
        "student-turn-start",
        args=[session.pk, assignment.local_identifier],
    )

    first = client.post(start_url, {"display_name": "Uno"})
    client.post(reverse("student-turn-ready", args=[session.pk]))
    second = client.post(start_url, {"display_name": "Dos"})
    client.post(reverse("student-turn-ready", args=[session.pk]))
    third = Client().post(start_url, {"display_name": "Tres"})

    assignment.refresh_from_db()
    assert first.status_code == second.status_code == 302
    assert third.status_code == 400
    assert assignment.remaining_capacity == 0
    with pytest.raises(IntegrityError):
        StudentTurn.objects.create(assignment=assignment, display_name="SQL bypass")


def test_turn_assignment_and_completed_status_are_immutable_and_snapshot_remains_pinned():
    session = active_session(student_count=2, device_count=2)
    assignments = list(session.device_assignments.order_by("id"))
    turn = assignments[0].reserve_turn("Luna")
    assert turn.assignment.session.snapshot_id == session.snapshot_id

    turn.assignment = assignments[1]
    with pytest.raises(ValidationError, match="asignación"):
        turn.save()
    turn.refresh_from_db()
    turn.finish()
    turn.display_name = "Reapertura"
    with pytest.raises(ValidationError, match="reabrirse"):
        turn.save()

    with pytest.raises(IntegrityError):
        StudentTurn.objects.filter(pk=turn.pk).update(status=StudentTurn.STATUS_ACTIVE)


def test_t07_does_not_introduce_result_or_classroom_close_entities():
    model_names = {model.__name__ for model in apps.get_models()}

    assert "PseudonymousResult" not in model_names
    assert "ClassroomSessionClose" not in model_names


def test_only_active_classrooms_allow_activity_answer_and_assistance():
    prepared = ClassroomSession.prepare_from_snapshot(
        published_snapshot(with_question=True),
        1,
        1,
    )
    prepared_assignment = prepared.device_assignments.get()
    prepared_urls = [
        reverse("student-activity", args=[prepared.pk]),
        reverse("student-question-answer", args=[prepared.pk, 0]),
        reverse("student-question-assistance", args=[prepared.pk, 0]),
    ]
    prepared_client = Client()

    stopped = active_question_session()
    stopped_assignment = stopped.device_assignments.get()
    stopped_client = Client()
    stopped_client.post(
        reverse("student-turn-start", args=[stopped.pk, stopped_assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    stopped.stop()
    stopped_urls = [
        reverse("student-activity", args=[stopped.pk]),
        reverse("student-question-answer", args=[stopped.pk, 0]),
        reverse("student-question-assistance", args=[stopped.pk, 0]),
    ]

    assert prepared_assignment.session.status == ClassroomSession.STATUS_PREPARED
    assert all(
        prepared_client.post(url, {"option_position": 1}).status_code == 403
        if url.endswith("/answer/") or url.endswith("/assistance/")
        else prepared_client.get(url).status_code == 403
        for url in prepared_urls
    )
    assert all(
        stopped_client.post(url, {"option_position": 1}).status_code == 403
        if url.endswith("/answer/") or url.endswith("/assistance/")
        else stopped_client.get(url).status_code == 403
        for url in stopped_urls
    )


def test_queryset_and_sql_cannot_restore_capacity_or_start_another_turn():
    session = active_session(student_count=1, device_count=1)
    assignment = session.device_assignments.get()
    client = Client()
    start_url = reverse(
        "student-turn-start",
        args=[session.pk, assignment.local_identifier],
    )
    client.post(start_url, {"display_name": "Luna"})
    assignment.refresh_from_db()
    assert assignment.remaining_capacity == 0

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeviceAssignment.objects.filter(pk=assignment.pk).update(
                remaining_capacity=1,
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_deviceassignment SET remaining_capacity = %s WHERE id = %s",
                    [1, assignment.pk],
                )

    assignment.refresh_from_db()
    assert assignment.remaining_capacity == 0
    client.post(reverse("student-turn-ready", args=[session.pk]))
    assert Client().post(start_url, {"display_name": "Sol"}).status_code == 400


def test_database_rejects_incomplete_completion_and_non_active_session_inserts():
    session = active_session(student_count=2, device_count=1)
    assignment = session.device_assignments.get()
    turn = assignment.reserve_turn("Luna")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentTurn.objects.filter(pk=turn.pk).update(
                status=StudentTurn.STATUS_COMPLETED,
            )
    turn.refresh_from_db()
    assert turn.status == StudentTurn.STATUS_ACTIVE
    finished = turn.finish()
    assert finished.status == StudentTurn.STATUS_COMPLETED
    assert finished.display_name == ""
    assert finished.completed_at is not None

    prepared = ClassroomSession.prepare_from_snapshot(
        published_snapshot("Preparada T07"),
        1,
        1,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentTurn.objects.create(
                assignment=prepared.device_assignments.get(),
                display_name="Preparada",
            )

    stopped = active_session(student_count=2, device_count=1)
    stopped.stop()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentTurn.objects.create(
                assignment=stopped.device_assignments.get(),
                display_name="Detenida",
            )


def test_direct_completed_inserts_and_completed_update_after_stop_are_rejected():
    prepared = ClassroomSession.prepare_from_snapshot(
        published_snapshot("Completed preparada"),
        1,
        1,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentTurn.objects.create(
                assignment=prepared.device_assignments.get(),
                status=StudentTurn.STATUS_COMPLETED,
                display_name="No debe entrar",
                completed_at=timezone.now(),
            )

    active = active_session(student_count=2, device_count=1)
    turn = active.device_assignments.get().reserve_turn("Luna")
    active.stop()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE curriculum_studentturn
                    SET status = 'completed', display_name = '', completed_at = %s
                    WHERE id = %s
                    """,
                    [timezone.now(), turn.pk.hex],
                )
    turn.refresh_from_db()
    assert turn.status == StudentTurn.STATUS_ACTIVE

    stopped = active_session(student_count=2, device_count=1)
    stopped.stop()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentTurn.objects.create(
                assignment=stopped.device_assignments.get(),
                status=StudentTurn.STATUS_COMPLETED,
                display_name="No debe entrar",
                completed_at=timezone.now(),
            )


def test_ready_and_finish_do_not_complete_a_turn_after_session_stop():
    session = active_session(student_count=2, device_count=1)
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    turn = StudentTurn.objects.get()
    session.stop()

    ready = client.post(reverse("student-turn-ready", args=[session.pk]))
    turn.refresh_from_db()
    assert ready.status_code == 302
    assert turn.status == StudentTurn.STATUS_ACTIVE
    with pytest.raises(ValidationError, match="activa"):
        turn.finish()
    turn.refresh_from_db()
    assert turn.status == StudentTurn.STATUS_ACTIVE


def test_expired_or_missing_cookie_can_recover_only_the_assignment_turn(monkeypatch):
    session = active_session(student_count=2, device_count=2)
    assignments = list(session.device_assignments.order_by("id"))
    client = Client()
    start_url = reverse(
        "student-turn-start",
        args=[session.pk, assignments[0].local_identifier],
    )
    client.post(start_url, {"display_name": "Luna"})

    monkeypatch.setattr(curriculum_views, "TURN_CAPABILITY_MAX_AGE", 0)
    assert client.get(reverse("student-activity", args=[session.pk])).status_code == 403
    recovery_url = reverse(
        "student-turn-recover",
        args=[session.pk, assignments[0].local_identifier],
    )
    recovered = client.post(recovery_url)
    assert recovered.status_code == 302
    assert recovered.cookies.get("aulalista.student-turn") is not None

    monkeypatch.setattr(curriculum_views, "TURN_CAPABILITY_MAX_AGE", 12 * 60 * 60)
    assert client.get(reverse("student-activity", args=[session.pk])).status_code == 200
    assert client.post(
        reverse("student-turn-recover", args=[session.pk, assignments[1].local_identifier])
    ).status_code == 403

    fresh_client = Client()
    fresh_recovery = fresh_client.post(recovery_url)
    assert fresh_recovery.status_code == 302
    assert fresh_client.get(reverse("student-activity", args=[session.pk])).status_code == 200


def test_student_turn_start_and_activity_are_not_cacheable():
    session = active_session()
    assignment = session.device_assignments.get()
    client = Client()
    start_url = reverse(
        "student-turn-start",
        args=[session.pk, assignment.local_identifier],
    )

    start = client.get(start_url)
    client.post(start_url, {"display_name": "Luna"})
    activity = client.get(reverse("student-activity", args=[session.pk]))

    assert "no-store" in start["Cache-Control"]
    assert "no-store" in activity["Cache-Control"]


def test_sql_and_bulk_active_turns_reject_blank_or_overlong_names():
    session = active_session(student_count=4, device_count=1)
    assignment = session.device_assignments.get()

    for invalid_name in ("   ", "\t\t", "x" * 81):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                StudentTurn.objects.bulk_create(
                    [
                        StudentTurn(
                            id=uuid.uuid4(),
                            assignment=assignment,
                            display_name=invalid_name,
                            status=StudentTurn.STATUS_ACTIVE,
                        )
                    ]
                )

    for invalid_name in ("   ", "\n\n", "y" * 81):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO curriculum_studentturn
                            (id, assignment_id, display_name, status, started_at, completed_at)
                        VALUES (%s, %s, %s, 'active', %s, NULL)
                        """,
                        [
                            uuid.uuid4().hex,
                            assignment.pk,
                            invalid_name,
                            timezone.now(),
                        ],
                    )

    valid_name = "z" * 80 + "\t\n\r\v\f "
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO curriculum_studentturn
                    (id, assignment_id, display_name, status, started_at, completed_at)
                VALUES (%s, %s, %s, 'active', %s, NULL)
                """,
                [uuid.uuid4().hex, assignment.pk, valid_name, timezone.now()],
            )

    assert StudentTurn.objects.get().display_name == valid_name
