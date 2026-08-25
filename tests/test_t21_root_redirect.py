"""Root path redirects to the student entry instead of 404."""

import os

import django
from django.test import Client


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()


def test_root_redirects_to_student_packages():
    response = Client().get("/")
    assert response.status_code == 302
    assert response["Location"].endswith("/student/")
