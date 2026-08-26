import hashlib
import json
import os
import re

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def _published_snapshot():
    from curriculum.models import CurriculumPackage, PublishedPackageSnapshot

    package = CurriculumPackage.objects.create(title="Paquete flujo")
    revision = package.save_revision()
    payload = {"title": "Paquete flujo", "questions": []}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{package.pk}",
        ),
    )


def test_anonymous_users_are_redirected_to_login_from_tutor_routes():
    routes = [
        reverse("tutor-import-upload"),
        reverse("tutor-session-prepare", args=[1]),
        reverse("tutor-session-review", args=[1]),
        reverse("tutor-session-close", args=[1]),
        reverse("tutor-session-export", args=[1]),
        reverse("tutor-sessions"),
    ]
    for route in routes:
        response = Client().get(route)
        assert response.status_code == 302, route
        assert "login" in response["Location"].lower(), route


def test_authenticated_non_staff_gets_forbidden_on_tutor_routes():
    get_user_model().objects.create_user(
        username="plain",
        password="test-password",
    )
    client = Client()
    client.force_login(get_user_model().objects.get(username="plain"))

    for route in [
        reverse("tutor-import-upload"),
        reverse("tutor-session-review", args=[1]),
        reverse("tutor-session-prepare", args=[1]),
        reverse("tutor-sessions"),
    ]:
        response = client.get(route)
        assert response.status_code == 403, route


def test_sessions_listing_shows_statuses_in_teacher_language():
    """#21: navegación de estados — la maestra encuentra sus sesiones."""

    snapshot = _published_snapshot()
    from curriculum.models import ClassroomSession

    prepared = ClassroomSession.prepare_from_snapshot(snapshot, 2, 2)
    active = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1)
    active.confirm()

    listing = tutor_client().get(reverse("tutor-sessions"))
    assert listing.status_code == 200
    assert "Preparada" in listing.text
    assert "Activa" in listing.text
    assert reverse("tutor-session-review", args=[prepared.pk]) in listing.text
    # Sin identificadores técnicos crudos en el listado.
    for session in (prepared, active):
        for assignment in session.device_assignments.all():
            assert str(assignment.local_identifier) not in listing.text
    assert not UUID_RE.search(listing.text)


def test_full_journey_prepare_activate_close_results_from_ui():
    """#21: recorrido completo preparar → activar → cerrar → resultados.

    Ninguna pantalla del maestro muestra identificadores técnicos crudos.
    """

    snapshot = _published_snapshot()
    client = tutor_client()
    pages = {}

    prepare_redirect = client.post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {"student_count": "3", "device_count": "2"},
    )
    assert prepare_redirect.status_code == 302

    from curriculum.models import ClassroomSession

    session = ClassroomSession.objects.get()
    review_url = reverse("tutor-session-review", args=[session.pk])

    review = client.get(review_url)
    assert review.status_code == 200
    pages["revisar"] = review.text
    assert "Preparada" in review.text

    confirm_redirect = client.post(reverse("tutor-session-confirm", args=[session.pk]))
    assert confirm_redirect.status_code == 302
    active = client.get(confirm_redirect["Location"])
    assert active.status_code == 200
    pages["activa"] = active.text
    assert "Activa" in active.text
    assert "Acceso común de dispositivos" in active.text
    assert "data-session-join-url" in active.text

    close_redirect = client.post(reverse("tutor-session-close", args=[session.pk]))
    assert close_redirect.status_code == 302
    closed = client.get(close_redirect["Location"])
    assert closed.status_code == 200
    pages["cerrada"] = closed.text
    assert "Cerrada" in closed.text
    assert "Agregados" in closed.text

    export = client.post(
        reverse("tutor-session-export", args=[session.pk]),
        {"format": "json"},
    )
    assert export.status_code == 200

    # Prueba de contenido: ningún identificador técnico crudo en las pantallas.
    raw_ids = {
        str(assignment.local_identifier)
        for assignment in session.device_assignments.all()
    }
    for screen, text in pages.items():
        for raw_id in raw_ids:
            assert raw_id not in text, screen
        assert not UUID_RE.search(text), screen


def test_staff_teacher_can_access_import_and_review_routes():
    from curriculum.models import (
        ClassroomSession,
        CurriculumPackage,
        CurriculumImportJob,
        PublishedPackageSnapshot,
    )
    import hashlib

    package = CurriculumPackage.objects.create(title="Paquete T17")
    revision = package.save_revision()
    payload = {"title": "Paquete T17", "questions": []}
    canonical = json_canonical(payload)
    snapshot = PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{package.pk}",
        ),
    )
    session = ClassroomSession.prepare_from_snapshot(snapshot, 2, 2)

    upload_page = tutor_client().get(reverse("tutor-import-upload"))
    review = tutor_client().get(reverse("tutor-session-review", args=[session.pk]))

    assert upload_page.status_code == 200
    assert "tutor_nav" not in upload_page.text  # include renders as nav content
    assert "<nav" in upload_page.text
    assert review.status_code == 200
    # Lenguaje docente: etiquetas operativas, no identificadores técnicos.
    assert "Dispositivo 1" in review.text
    assert "Dispositivo 2" in review.text
    assert str(session.device_assignments.first().local_identifier) not in review.text
    # La revisión comunica exactamente qué snapshot publicado se activará.
    assert f"versión {snapshot.version}" in review.text
    assert snapshot.sha256[:8] in review.text


def json_canonical(payload):
    import json

    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
