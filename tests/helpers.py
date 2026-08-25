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
