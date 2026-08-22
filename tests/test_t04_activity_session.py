import hashlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import ClassroomSession, CurriculumPackage, PublishedPackageSnapshot


pytestmark = pytest.mark.django_db


def published_snapshot(
    version,
    *,
    title,
    micro_lesson,
    option_text,
    expected,
    package=None,
):
    package = package or CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": micro_lesson,
        "questions": [
            {
                "type": "reactivo",
                "value": {
                    "prompt": "¿Cuál opción corresponde?",
                    "options": [
                        {
                            "position": 1,
                            "text": option_text,
                            "expected": expected,
                            "feedback": "Retroalimentación fijada.",
                        },
                        {
                            "position": 2,
                            "text": "Otra opción",
                            "expected": not expected,
                            "feedback": "Otra retroalimentación fijada.",
                        },
                    ],
                    "hints": ["Pista fijada."],
                },
            }
        ],
        "final_explanation": "Explicación fijada.",
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=version,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{version}-{title}",
        ),
    )


def test_activity_stays_on_started_snapshot_when_a_correction_is_published():
    package = CurriculumPackage.objects.create(title="Versión uno")
    snapshot_one = published_snapshot(
        1,
        title="Versión uno",
        micro_lesson="Microlección uno.",
        option_text="Respuesta uno",
        expected=True,
        package=package,
    )
    client = Client()

    start_response = client.post(
        reverse("student-session-start", args=[snapshot_one.pk]),
    )
    assert start_response.status_code == 302
    first_session = ClassroomSession.objects.get()
    assert first_session.snapshot_id == snapshot_one.pk

    package.title = "Versión corregida"
    package.save()
    snapshot_two = published_snapshot(
        2,
        title="Versión corregida",
        micro_lesson="Microlección corregida.",
        option_text="Respuesta corregida",
        expected=False,
        package=package,
    )

    first_activity = client.get(start_response["Location"])

    assert first_activity.status_code == 200
    assert "Versión uno" in first_activity.text
    assert "Microlección uno." in first_activity.text
    assert "Respuesta uno" in first_activity.text
    assert "Versión corregida" not in first_activity.text
    assert "Microlección corregida." not in first_activity.text
    assert "Respuesta corregida" not in first_activity.text

    second_start = client.post(
        reverse("student-session-start", args=[snapshot_two.pk]),
    )
    second_activity = client.get(second_start["Location"])
    second_session = ClassroomSession.objects.exclude(pk=first_session.pk).get()

    assert second_activity.status_code == 200
    assert second_session.snapshot_id == snapshot_two.pk
    assert "Versión corregida" in second_activity.text
    assert "Microlección corregida." in second_activity.text
    assert "Respuesta corregida" in second_activity.text


def test_session_cannot_start_without_a_published_snapshot():
    response = Client().post(
        reverse("student-session-start", args=[999999]),
    )

    assert response.status_code == 404
    assert ClassroomSession.objects.count() == 0


def test_student_activity_does_not_expose_expected_answers_or_full_snapshot_payload():
    snapshot = published_snapshot(
        1,
        title="Actividad visible",
        micro_lesson="Microlección visible.",
        option_text="Opción visible",
        expected=True,
    )
    client = Client()
    start_response = client.post(
        reverse("student-session-start", args=[snapshot.pk]),
    )

    activity = client.get(start_response["Location"])

    assert activity.status_code == 200
    assert "Microlección visible." in activity.text
    assert "Opción visible" in activity.text
    assert "respuesta esperada" not in activity.text
    assert '"expected"' not in activity.text
    assert "fixed-snapshot-payload" not in activity.text


def test_session_snapshot_cannot_be_reassigned_by_save_bulk_update_or_sql():
    snapshot_one = published_snapshot(
        1,
        title="Snapshot uno",
        micro_lesson="Microlección uno.",
        option_text="Opción uno",
        expected=True,
    )
    snapshot_two = published_snapshot(
        1,
        title="Snapshot dos",
        micro_lesson="Microlección dos.",
        option_text="Opción dos",
        expected=True,
    )
    session = ClassroomSession.start_from_snapshot(snapshot_one)

    session.snapshot = snapshot_two
    with pytest.raises(ValidationError, match="fijado"):
        session.save()
    session.refresh_from_db()
    assert session.snapshot_id == snapshot_one.pk

    session.snapshot_id = snapshot_two.pk
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.bulk_update([session], ["snapshot"])
    session.refresh_from_db()
    assert session.snapshot_id == snapshot_one.pk

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_classroomsession SET snapshot_id = %s WHERE id = %s",
                    [snapshot_two.pk, session.pk],
                )
    session.refresh_from_db()
    assert session.snapshot_id == snapshot_one.pk


def test_stopped_session_remains_stopped_in_activity_view():
    snapshot = published_snapshot(
        1,
        title="Sesión detenida",
        micro_lesson="Contenido detenido.",
        option_text="Opción detenida",
        expected=True,
    )
    client = Client()
    start_response = client.post(
        reverse("student-session-start", args=[snapshot.pk]),
    )
    session = ClassroomSession.objects.get()
    session.stop()

    activity = client.get(start_response["Location"])

    assert activity.status_code == 200
    assert "Detenida" in activity.text
    assert "Completada" not in activity.text
