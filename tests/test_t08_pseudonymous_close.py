import hashlib
import json
import os
from unittest.mock import patch

import django
import pytest
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
    ClassroomSessionClosure,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
    PseudonymousResult,
    StudentTurn,
)
from curriculum.ephemeral import ephemeral_session_summary_key  # noqa: E402
from curriculum.views import (  # noqa: E402
    HINT_PROGRESS_KEY_PREFIX,
)


from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db


def published_snapshot(title="Paquete T08"):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": "Una idea principal organiza el sentido.",
        "questions": [
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
        ],
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


def active_question_session():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 1, 1)
    session.confirm()
    return session


def hidden_capability(response, name):
    marker = f'name="{name}" value="'
    start = response.text.index(marker) + len(marker)
    return response.text[start:].split('"', 1)[0]


def test_answers_and_help_are_ephemeral_until_explicit_close():
    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()

    started = client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    turn = StudentTurn.objects.get()
    activity = client.get(reverse("student-activity", args=[session.pk]))
    answer = client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    )
    help_response = client.post(
        reverse("student-question-assistance", args=[session.pk, 0]),
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": hidden_capability(activity, "hint_capability"),
        },
    )

    assert started.status_code == answer.status_code == help_response.status_code == 200 or (
        started.status_code == 302
        and answer.status_code == help_response.status_code == 200
    )
    assert not PseudonymousResult.objects.exists()
    summary = cache.get(ephemeral_session_summary_key(session.pk))
    assert summary["turns"][str(turn.pk)]["responses"] == [
        {"question_index": 0, "selected_position": 1, "is_correct": True}
    ]
    assert summary["turns"][str(turn.pk)]["help_requests"] == [
        {"kind": "hint", "question_index": 0, "hint_index": 0}
    ]
    assert "Luna" not in json.dumps(summary, ensure_ascii=False)


def test_close_materializes_metrics_and_erases_temporal_relations():
    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    activity = client.get(reverse("student-activity", args=[session.pk]))
    client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    )
    client.post(
        reverse("student-question-assistance", args=[session.pk, 0]),
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": hidden_capability(activity, "hint_capability"),
        },
    )
    client.post(reverse("student-turn-ready", args=[session.pk]))

    closed = session.close()
    result = PseudonymousResult.objects.get()

    assert closed.status == ClassroomSession.STATUS_CLOSED
    assert closed.closed_at is not None
    assert not StudentTurn.objects.exists()
    assert not DeviceAssignment.objects.exists()
    assert cache.get(ephemeral_session_summary_key(session.pk)) is None
    assert result.id is not None
    assert result.snapshot_id == session.snapshot_id
    assert result.snapshot_version == session.snapshot.version
    assert result.snapshot_sha256 == session.snapshot.sha256
    assert result.state == PseudonymousResult.STATE_COMPLETED
    assert result.duration_seconds is not None
    assert result.responses == [
        {"question_index": 0, "selected_position": 1, "is_correct": True}
    ]
    assert result.score == 1
    assert result.help_requests == [
        {"kind": "hint", "question_index": 0, "hint_index": 0}
    ]
    assert result.technical_errors == []
    assert result.state == PseudonymousResult.STATE_COMPLETED
    receipt = ClassroomSessionClosure.objects.get(session=session)
    assert receipt.closed_at == closed.closed_at
    assert receipt.nonce is not None
    temporal_names = {"session", "turn", "assignment", "display_name", "cookie"}
    assert not temporal_names.intersection(
        field.name for field in PseudonymousResult._meta.fields
    )
    assert all(
        field.remote_field is None for field in PseudonymousResult._meta.fields
    )


def test_close_is_idempotent_and_rejects_stopped_without_partial_deletion():
    session = active_question_session()
    assignment = session.device_assignments.get()
    turn = assignment.reserve_turn("Luna")
    first_close = session.close()
    first_closed_at = first_close.closed_at
    first_receipt = ClassroomSessionClosure.objects.get(session=session)
    second_close = session.close()
    second_receipt = ClassroomSessionClosure.objects.get(session=session)

    assert second_close.status == ClassroomSession.STATUS_CLOSED
    assert second_close.closed_at == first_closed_at
    assert second_receipt.nonce == first_receipt.nonce
    assert PseudonymousResult.objects.count() == 1

    stopped = active_question_session()
    stopped_assignment = stopped.device_assignments.get()
    stopped_assignment.reserve_turn("Sol")
    stopped.stop()
    with pytest.raises(ValidationError):
        stopped.close()
    assert StudentTurn.objects.filter(assignment__session=stopped).exists()
    assert DeviceAssignment.objects.filter(session=stopped).exists()


def test_close_materializes_unknown_or_active_summary_as_abandoned():
    session = active_question_session()
    assignment = session.device_assignments.get()
    turn = assignment.reserve_turn("Luna")
    cache.set(
        ephemeral_session_summary_key(session.pk),
        {
            "turns": {
                str(turn.pk): {
                    "state": "active",
                    "started_at": turn.started_at.isoformat(),
                    "completed_at": None,
                    "responses": [],
                    "help_requests": [],
                    "technical_errors": [],
                }
            }
        },
    )

    session.close()

    assert PseudonymousResult.objects.get().state == PseudonymousResult.STATE_ABANDONED


def test_closed_status_requires_a_closure_receipt_at_the_database_boundary():
    session = active_question_session()
    session.status = ClassroomSession.STATUS_CLOSED
    session.closed_at = timezone.now()
    with pytest.raises(ValidationError):
        session.save(update_fields=["status", "closed_at"])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.filter(pk=session.pk).update(
                status=ClassroomSession.STATUS_CLOSED,
                closed_at=timezone.now(),
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_classroomsession SET status = 'closed', closed_at = %s WHERE id = %s",
                    [timezone.now(), session.pk],
                )
    assert not ClassroomSessionClosure.objects.filter(session=session).exists()


def test_closed_session_rejects_device_assignment_reassignment_by_bulk_and_sql():
    source = active_question_session()
    target = active_question_session()
    assignment = source.device_assignments.get()
    target.close()

    assignment.session_id = target.pk
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeviceAssignment.objects.bulk_update([assignment], ["session"])
    assignment.refresh_from_db()
    assert assignment.session_id == source.pk

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_deviceassignment SET session_id = %s WHERE id = %s",
                    [target.pk, assignment.pk],
                )
    assignment.refresh_from_db()
    assert assignment.session_id == source.pk


def test_result_batch_is_required_and_unique():
    session = active_question_session()
    snapshot = session.snapshot

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PseudonymousResult.objects.create(
                snapshot_id=snapshot.pk,
                snapshot_version=snapshot.version,
                snapshot_sha256=snapshot.sha256,
                state=PseudonymousResult.STATE_ABANDONED,
                responses=[],
                score=0,
                help_requests=[],
                technical_errors=[],
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.create(
                snapshot=snapshot,
                result_batch_id=session.result_batch_id,
            )


def test_close_rolls_back_temporal_deletion_when_result_materialization_fails():
    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    turn = StudentTurn.objects.get()
    client.get(reverse("student-activity", args=[session.pk]))
    summary_before = cache.get(ephemeral_session_summary_key(session.pk))
    hint_key = f"{HINT_PROGRESS_KEY_PREFIX}:{turn.pk}:0"
    assert summary_before is not None
    assert cache.get(hint_key) is not None

    with patch.object(
        PseudonymousResult.objects,
        "create",
        side_effect=RuntimeError("fallo de prueba"),
    ):
        with pytest.raises(RuntimeError, match="fallo de prueba"):
            session.close()

    session.refresh_from_db()
    assert session.status == ClassroomSession.STATUS_ACTIVE
    assert StudentTurn.objects.filter(assignment__session=session).exists()
    assert DeviceAssignment.objects.filter(session=session).exists()
    assert not PseudonymousResult.objects.exists()
    assert cache.get(ephemeral_session_summary_key(session.pk)) == summary_before
    assert cache.get(hint_key) is not None


def test_close_clears_summary_and_all_hint_cache_after_final_save():
    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    turn = StudentTurn.objects.get()
    client.get(reverse("student-activity", args=[session.pk]))
    hint_key = f"{HINT_PROGRESS_KEY_PREFIX}:{turn.pk}:0"
    assert cache.get(hint_key) is not None

    session.close()

    assert cache.get(ephemeral_session_summary_key(session.pk)) is None
    assert cache.get(hint_key) is None
    assert cache.get(f"{HINT_PROGRESS_KEY_PREFIX}:consumed-index:{turn.pk}:0") is None


def test_prepared_session_can_close_without_creating_a_result():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)

    session.close()

    session.refresh_from_db()
    assert session.status == ClassroomSession.STATUS_CLOSED
    assert session.closed_at is not None
    assert not PseudonymousResult.objects.exists()
    assert not DeviceAssignment.objects.filter(session=session).exists()


def test_closed_session_blocks_student_activity_and_turn_routes():
    session = active_question_session()
    assignment = session.device_assignments.get()
    client = Client()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    session.close()

    assert client.get(reverse("student-activity", args=[session.pk])).status_code == 403
    assert client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    ).status_code == 403
    assert client.post(
        reverse("student-question-assistance", args=[session.pk, 0]),
        {"kind": "hint", "hint_index": 0},
    ).status_code == 403
    assert client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Sol"},
    ).status_code == 403
    assert client.post(
        reverse("student-turn-recover", args=[session.pk, assignment.local_identifier]),
    ).status_code == 403
    assert client.post(reverse("student-turn-ready", args=[session.pk])).status_code == 403


def test_closed_session_is_terminal_in_sqlite_and_rejects_new_assignments():
    session = active_question_session()
    session.close()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.filter(pk=session.pk).update(
                status=ClassroomSession.STATUS_ACTIVE,
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_classroomsession SET status = %s WHERE id = %s",
                    [ClassroomSession.STATUS_ACTIVE, session.pk],
                )
    with pytest.raises(IntegrityError):
        DeviceAssignment.objects.create(
            session=session,
            assigned_capacity=1,
            remaining_capacity=1,
        )


def test_duplicate_names_produce_independent_nameless_results_and_exports():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 2)
    session.confirm()
    assignments = list(session.device_assignments.order_by("id"))
    for assignment in assignments:
        client = Client()
        client.post(
            reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
            {"display_name": "Luna"},
        )
        client.post(reverse("student-turn-ready", args=[session.pk]))
    session.close()

    results = list(
        PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id)
    )
    review = tutor_client().get(reverse("tutor-session-review", args=[session.pk]))
    get_export = tutor_client().get(reverse("tutor-session-export", args=[session.pk]))
    export = tutor_client().post(reverse("tutor-session-export", args=[session.pk]),
        {"format": "json"},
    )
    csv_export = tutor_client().post(reverse("tutor-session-export", args=[session.pk]),
        {"format": "csv"},
    )

    assert len(results) == 2
    assert len({result.id for result in results}) == 2
    assert all(result.result_batch_id == session.result_batch_id for result in results)
    assert "Luna" not in review.text
    assert get_export.status_code == 405
    assert export.status_code == 200
    assert "Luna" not in export.text
    assert "participant_label" in export.text
    for result in results:
        assert str(result.id) not in export.text
        assert str(result.participant_key) not in export.text
    assert csv_export.status_code == 200
    assert "Luna" not in csv_export.text
    for result in results:
        assert str(result.id) not in csv_export.text
        assert str(result.participant_key) not in csv_export.text


def test_delete_requires_explicit_post_and_can_delete_selected_or_all_results():
    session = active_question_session()
    assignment = session.device_assignments.get()
    assignment.reserve_turn("Luna")
    session.close()
    result = PseudonymousResult.objects.get()

    other = active_question_session()
    other.device_assignments.get().reserve_turn("Sol")
    other.close()
    other_result = PseudonymousResult.objects.get(
        result_batch_id=other.result_batch_id,
    )
    scoped_client = tutor_client()
    wrong_session_delete = scoped_client.post(
        reverse("tutor-result-delete", args=[session.pk, other_result.pk]),
    )
    get_delete = scoped_client.get(
        reverse("tutor-result-delete", args=[session.pk, result.pk])
    )
    delete_one = scoped_client.post(
        reverse("tutor-result-delete", args=[session.pk, result.pk])
    )

    assert wrong_session_delete.status_code == 404
    assert get_delete.status_code == 405
    assert delete_one.status_code == 200
    assert list(PseudonymousResult.objects.values_list("pk", flat=True)) == [
        other_result.pk
    ]
    bulk_delete = tutor_client().post(reverse("tutor-session-results-delete", args=[other.pk]),
    )
    assert bulk_delete.status_code == 200
    # Borrar todos los resultados también elimina las respuestas de encuesta del lote.
    assert bulk_delete.json() == {"deleted": 1, "surveys_deleted": 0}
    assert not PseudonymousResult.objects.exists()
