import hashlib
import json
import os
import re
import uuid

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
    StudentTurn,
)


from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db

JOIN_ERROR_UNAVAILABLE = "No hay dispositivos disponibles"


def published_snapshot(title="Paquete T13"):
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
                    "hints": ["Busca la afirmación que organiza el sentido."],
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


def prepared_session(*, student_count=2, device_count=2):
    return ClassroomSession.prepare_from_snapshot(
        published_snapshot(),
        student_count,
        device_count,
    )


def active_session(*, student_count=2, device_count=2):
    session = prepared_session(student_count=student_count, device_count=device_count)
    session.confirm()
    return session


def join_path(session_id):
    return reverse("student-session-join", args=[session_id])


def local_identifier_from(response):
    match = re.search(r"/devices/([0-9a-f-]{36})/turn/start/", response.url)
    assert match, f"Sin identificador local en {response.url}"
    return uuid.UUID(match.group(1))


def test_student_index_lists_only_active_sessions_with_a_common_entry():
    active = active_session()
    prepared = prepared_session()

    response = Client().get(reverse("student-packages"))

    assert response.status_code == 200
    assert join_path(active.pk) in response.text
    assert join_path(prepared.pk) not in response.text


def test_two_browsers_join_one_link_and_keep_independent_turns():
    session = active_session(student_count=2, device_count=2)
    first_client = Client()
    second_client = Client()

    first_join = first_client.post(join_path(session.pk))
    second_join = second_client.post(join_path(session.pk))

    assert first_join.status_code == second_join.status_code == 302
    first_identifier = local_identifier_from(first_join)
    second_identifier = local_identifier_from(second_join)
    assert first_identifier != second_identifier

    first_start = first_client.post(
        first_join.url.replace("http://testserver", ""),
        {"display_name": "Luna"},
    )
    second_start = second_client.post(
        second_join.url.replace("http://testserver", ""),
        {"display_name": "Luna"},
    )
    assert first_start.status_code == second_start.status_code == 302

    turns = list(StudentTurn.objects.order_by("started_at", "id"))
    assert len(turns) == 2
    assert turns[0].pk != turns[1].pk
    assert turns[0].assignment_id != turns[1].assignment_id

    first_cookie = first_client.cookies["aulalista.student-turn"].value
    second_cookie = second_client.cookies["aulalista.student-turn"].value
    assert first_cookie and second_cookie and first_cookie != second_cookie

    activity = reverse("student-activity", args=[session.pk])
    assert first_client.get(activity).status_code == 200
    assert second_client.get(activity).status_code == 200


def test_returning_browser_keeps_its_own_assignment():
    session = active_session(student_count=2, device_count=2)
    client = Client()

    first_join = client.post(join_path(session.pk))
    identifier = local_identifier_from(first_join)
    started = client.post(
        first_join.url.replace("http://testserver", ""),
        {"display_name": "Luna"},
    )
    assert started.status_code == 302
    finished = client.post(reverse("student-turn-ready", args=[session.pk]))
    assert finished.status_code == 302

    returning = client.post(join_path(session.pk))

    assert returning.status_code == 302
    assert local_identifier_from(returning) == identifier


def test_join_does_not_claim_a_second_device_and_reports_when_none_is_free():
    session = active_session(student_count=1, device_count=1)
    first_client = Client()
    second_client = Client()

    first_join = first_client.post(join_path(session.pk))
    started = first_client.post(
        first_join.url.replace("http://testserver", ""),
        {"display_name": "Luna"},
    )
    assert started.status_code == 302

    # The same browser never claims a second assignment.
    again = first_client.post(join_path(session.pk))
    assert again.status_code == 302
    assert DeviceAssignment.objects.filter(session=session).count() == 1

    blocked = second_client.post(join_path(session.pk))

    assert blocked.status_code == 409
    assert JOIN_ERROR_UNAVAILABLE in blocked.text


def test_join_rejects_sessions_that_are_not_active():
    prepared = prepared_session()
    closed = active_session()
    closed.close()

    prepared_get = Client().get(join_path(prepared.pk))
    prepared_post = Client().post(join_path(prepared.pk))
    closed_post = Client().post(join_path(closed.pk))

    assert prepared_get.status_code == prepared_post.status_code == 403
    assert closed_post.status_code == 403


def test_tutor_review_shows_one_link_and_qr_only_while_active():
    session = prepared_session()
    review_path = reverse("tutor-session-review", args=[session.pk])

    prepared_page = tutor_client().get(review_path)
    session.confirm()
    active_page = tutor_client().get(review_path)

    assert join_path(session.pk) not in prepared_page.text
    assert f'data-session-join-url href="http://testserver{join_path(session.pk)}"' in (
        active_page.text
    )
    assert "data-qr-value" not in active_page.text
    assert "AULALISTA_LAN_URL" in active_page.text


def test_sequential_multi_browser_joins_stay_consistent_under_sqlite_single_writer():
    """Deterministic multi-client incorporation probe.

    SQLite supports one writer at a time; the deployment scope is a single
    WSGI process with WAL and busy_timeout=5000. A threaded 30-writer probe
    was evaluated separately (see docs/evidence) and lock contention remains
    a documented limitation rather than a hidden retry policy.
    """

    session = active_session(student_count=4, device_count=4)
    identifiers = set()
    for _ in range(4):
        client = Client()
        joined = client.post(join_path(session.pk))
        assert joined.status_code == 302
        identifier = local_identifier_from(joined)
        assert identifier not in identifiers
        identifiers.add(identifier)
        started = client.post(
            joined.url.replace("http://testserver", ""),
            {"display_name": f"Estudiante-{len(identifiers)}"},
        )
        assert started.status_code == 302

    late = Client().post(join_path(session.pk))
    assert late.status_code == 409
    assert JOIN_ERROR_UNAVAILABLE in late.text
    assert StudentTurn.objects.filter(status=StudentTurn.STATUS_ACTIVE).count() == 4
