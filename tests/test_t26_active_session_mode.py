import hashlib
import json
import os

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
    PublishedPackageSnapshot,
    StudentTurn,
)
from helpers import tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db


def published_snapshot():
    package = CurriculumPackage.objects.create(title="Paquete activo")
    revision = package.save_revision()
    payload = {"title": "Paquete activo", "questions": []}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=3,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"editor-activo-{package.pk}"
        ),
    )


def test_routes_split_teacher_control_from_public_projection_by_role():
    prepared = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    active = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    active.confirm()
    closed = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    closed.confirm()
    closed.close()

    assert tutor_client().get(reverse("tutor-session-active", args=[prepared.pk])).status_code == 200
    assert tutor_client().get(reverse("tutor-session-active", args=[active.pk])).status_code == 200
    assert tutor_client().get(reverse("tutor-session-active", args=[closed.pk])).status_code == 200
    for session in (prepared, active, closed):
        response = Client().get(reverse("session-projection", args=[session.pk]))
        assert response.status_code == 200
        assert "participant" in response.text.lower()

    anonymous = Client().get(reverse("tutor-session-active", args=[active.pk]))
    assert anonymous.status_code == 302
    assert "login" in anonymous["Location"].lower()


def test_authenticated_teacher_active_control_shows_only_active_aliases():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    session.confirm()
    assignment = session.device_assignments.get()
    assignment.reserve_turn("Luna")

    response = tutor_client().get(reverse("tutor-session-active", args=[session.pk]))

    assert response.status_code == 200
    assert response["Cache-Control"] == "max-age=0, no-cache, no-store, must-revalidate, private"
    assert "Luna" in response.text
    assert "Paquete activo" in response.text
    assert "versión 3" in response.text
    assert session.snapshot.sha256[:8] in response.text
    assert str(assignment.local_identifier) not in response.text
    assert "score" not in response.text.lower()


def test_public_projection_never_exposes_aliases_identifiers_or_teacher_controls():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    session.confirm()
    assignment = session.device_assignments.get()
    turn = assignment.reserve_turn("LunaPublica")
    response = Client().get(reverse("session-projection", args=[session.pk]))

    assert response.status_code == 200
    assert response["Cache-Control"] == "max-age=0, no-cache, no-store, must-revalidate, private"
    for forbidden in ("LunaPublica", str(assignment.local_identifier), str(turn.pk), "capacidad", "puntuación", "resultados"):
        assert forbidden.lower() not in response.text.lower()
    assert "Cerrar" not in response.text
    assert "LunaPublica" not in Client().get(
        reverse("session-projection", args=[session.pk])
    ).text


def test_reservation_counts_on_both_surfaces_and_authenticated_close_purges_session():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    session.confirm()
    assignment = session.device_assignments.get()
    teacher = tutor_client()
    public = Client()
    control_url = reverse("tutor-session-active", args=[session.pk])
    projection_url = reverse("session-projection", args=[session.pk])

    for url, client in ((control_url, teacher), (projection_url, public)):
        response = client.get(url)
        assert response.status_code == 200
        assert 'data-participant-count>0<' in response.text

    turn = assignment.reserve_turn("CierreAlias")

    for url, client in ((control_url, teacher), (projection_url, public)):
        response = client.get(url)
        assert response.status_code == 200
        assert 'data-participant-count>1<' in response.text

    close_response = teacher.post(reverse("tutor-session-close", args=[session.pk]))
    assert close_response.status_code == 302
    session.refresh_from_db()
    assert session.status == ClassroomSession.STATUS_CLOSED
    assert not StudentTurn.objects.filter(pk=turn.pk).exists()
    assert not session.device_assignments.exists()

    join_url = reverse("student-session-join", args=[session.pk])
    for url, client in ((control_url, teacher), (projection_url, public)):
        response = client.get(url)
        assert response.status_code == 200
        assert "CierreAlias" not in response.text
        assert "data-session-join-url" not in response.text
        assert join_url not in response.text


def test_prepared_and_closed_surfaces_have_no_aliases_and_get_cannot_change_state():
    prepared = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    active = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    active.confirm()
    active.device_assignments.get().reserve_turn("SeBorraAlCerrar")
    closed = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 1)
    closed.confirm()
    closed.close()

    for session in (prepared, closed):
        for name in ("tutor-session-active", "session-projection"):
            page = (tutor_client() if name.startswith("tutor") else Client()).get(reverse(name, args=[session.pk]))
            assert "SeBorraAlCerrar" not in page.text
            assert "join" not in page.text.lower() or session.status == "active"

    for name in ("tutor-session-confirm", "tutor-session-close"):
        response = tutor_client().get(reverse(name, args=[prepared.pk]))
        assert response.status_code == 405
    active.refresh_from_db()
    assert active.status == ClassroomSession.STATUS_ACTIVE
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(get_user_model().objects.create_user(username="csrf-teacher", is_staff=True))
    assert csrf_client.post(reverse("tutor-session-close", args=[active.pk])).status_code == 403
