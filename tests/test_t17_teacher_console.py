import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db


def test_anonymous_users_are_redirected_to_login_from_tutor_routes():
    routes = [
        reverse("tutor-import-upload"),
        reverse("tutor-session-prepare", args=[1]),
        reverse("tutor-session-review", args=[1]),
        reverse("tutor-session-close", args=[1]),
        reverse("tutor-session-export", args=[1]),
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
    ]:
        response = client.get(route)
        assert response.status_code == 403, route


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
