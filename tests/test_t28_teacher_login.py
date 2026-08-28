"""Issue #83: Wagtail-backed authentication for teacher operations."""

import os
from urllib.parse import quote

import django
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402

from curriculum.models import CurriculumPackage, PublishedPackageSnapshot  # noqa: E402

pytestmark = pytest.mark.django_db


def published_snapshot(owner=None):
    owner = owner or get_user_model().objects.create_user(username="publisher")
    package = CurriculumPackage.objects.create(
        title="Sesión autenticada",
        created_by=owner,
    )
    revision = package.save_revision(user=owner)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload={"title": package.title, "questions": []},
        sha256="a" * 64,
        source_revision=revision,
        published_by=owner,
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
    teacher = get_user_model().objects.create_user(
        username="teacher",
        password="test-password",
        is_staff=True,
    )
    snapshot = published_snapshot(owner=teacher)
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


@pytest.mark.parametrize(
    "malicious_next",
    [
        "https://evil.example",
        "//evil.com",
        "/\\evil.com",
        "///evil.com",
    ],
)
def test_wagtail_login_returns_to_requested_teacher_page_and_rejects_open_redirects(
    malicious_next,
):
    user = get_user_model().objects.create_user(
        username="returning-teacher",
        password="test-password",
        is_staff=True,
    )
    snapshot = published_snapshot(owner=user)
    target = reverse("tutor-session-prepare", args=[snapshot.pk])
    client = Client()

    # Exercise the complete protected-view flow: redirect to login, then back
    # to the requested teacher page after a valid login.
    login_response = client.get(target)
    login_url = login_response["Location"]
    assert f"next={target}" in login_url
    completed_login = client.post(
        login_url,
        {
            "username": user.username,
            "password": "test-password",
            "next": target,
        },
        follow=True,
    )
    assert completed_login.status_code == 200
    assert completed_login.request["PATH_INFO"] == target

    # The Wagtail login must not turn its ``next`` field into an external redirect.
    client.logout()
    encoded_next = quote(malicious_next, safe="")
    unsafe_login = client.get(f"/cms/login/?next={encoded_next}")
    assert unsafe_login.status_code == 200
    completed_login = client.post(
        unsafe_login.wsgi_request.path + f"?next={encoded_next}",
        {
            "username": user.username,
            "password": "test-password",
            "next": malicious_next,
        },
    )
    assert completed_login.status_code == 302
    assert completed_login["Location"] == "/cms/"
