"""Shared test helpers."""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402


def tutor_client(username=None):
    """A Client logged in as a staff teacher account for tutor/* routes."""

    user_model = get_user_model()
    username = username or f"tutor-{user_model.objects.count() + 1}"
    user = user_model.objects.create_user(
        username=username,
        password="test-password",
        is_staff=True,
    )
    client = Client()
    client.force_login(user)
    return client


def tutor_client_for_sessions(*sessions, username=None):
    """Create the teacher that owns the explicitly supplied test sessions."""

    from curriculum.models import ClassroomSession

    client = tutor_client(username=username)
    ClassroomSession.objects.filter(pk__in=[session.pk for session in sessions]).update(
        created_by_id=client.session["_auth_user_id"],
    )
    return client
