"""Issue #83: Wagtail-backed authentication for teacher operations."""

import os

import django
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402

from curriculum.models import CurriculumPackage, PublishedPackageSnapshot  # noqa: E402

pytestmark = pytest.mark.django_db


def published_snapshot():
    package = CurriculumPackage.objects.create(title="Sesión autenticada")
    revision = package.save_revision()
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload={"title": package.title, "questions": []},
        sha256="a" * 64,
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username="publisher"),
    )


def test_anonymous_prepare_is_redirected_to_wagtail_login_with_destination():
    snapshot = published_snapshot()
    target = reverse("tutor-session-prepare", args=[snapshot.pk])

    response = Client().get(target)

    assert response.status_code == 302
    assert response["Location"].startswith("/cms/login/")
    assert "next=" in response["Location"]
    assert target in response["Location"]


def test_authorized_staff_teacher_can_prepare_a_session():
    snapshot = published_snapshot()
    teacher = get_user_model().objects.create_user(
        username="teacher",
        password="test-password",
        is_staff=True,
    )
    client = Client()
    client.force_login(teacher)

    response = client.post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {"student_count": "2", "device_count": "1"},
    )

    assert response.status_code == 302
    assert response["Location"].startswith("/tutor/sessions/")


def test_authenticated_user_without_teacher_permissions_gets_403_without_mutation():
    snapshot = published_snapshot()
    user = get_user_model().objects.create_user(
        username="student-like-user",
        password="test-password",
        is_staff=False,
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {"student_count": "2", "device_count": "1"},
    )

    assert response.status_code == 403
    from curriculum.models import ClassroomSession

    assert ClassroomSession.objects.count() == 0


def test_wagtail_login_returns_to_requested_teacher_page_and_rejects_open_redirects():
    snapshot = published_snapshot()
    target = reverse("tutor-session-prepare", args=[snapshot.pk])
    user = get_user_model().objects.create_user(
        username="returning-teacher",
        password="test-password",
        is_staff=True,
    )
    client = Client()

    login_response = client.get(target)
    login_url = login_response["Location"]
    assert f"next={target}" in login_url
    assert client.get(login_url).status_code == 200
    assert client.login(username=user.username, password="test-password")
    assert client.get(target).status_code == 200

    # The Wagtail login accepts local destinations, but must not turn its
    # ``next`` field into an external redirect.
    client.logout()
    unsafe_login = client.get("/cms/login/?next=https%3A%2F%2Fevil.example")
    assert unsafe_login.status_code == 200
    completed_login = client.post(
        unsafe_login.request["PATH_INFO"] + "?next=https%3A%2F%2Fevil.example",
        {"username": user.username, "password": "test-password", "next": "https://evil.example"},
    )
    assert completed_login.status_code == 302
    assert url_has_allowed_host_and_scheme(
        completed_login["Location"], allowed_hosts={"testserver"}
    )
