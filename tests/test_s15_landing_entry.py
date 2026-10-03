from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from helpers import tutor_client


pytestmark = pytest.mark.django_db
ENTRY_PATH = "/tutor/imports/new/"


def test_s15_anonymous_entry_preserves_login_and_return_path():
    assert reverse("tutor-import-upload") == ENTRY_PATH
    response = Client().get(ENTRY_PATH)
    assert response.status_code == 302
    target = urlsplit(response["Location"])
    assert target.path == "/cms/login/"
    assert parse_qs(target.query) == {"next": [ENTRY_PATH]}


def test_s15_teacher_entry_opens_real_upload_form():
    response = tutor_client(username="s15-teacher").get(ENTRY_PATH)
    assert response.status_code == 200
    assert 'name="pdf"' in response.text
    assert 'name="csrfmiddlewaretoken"' in response.text
    assert 'enctype="multipart/form-data"' in response.text


def test_s15_entry_rejects_account_without_teacher_access():
    user = get_user_model().objects.create_user(username="s15-no-teacher")
    client = Client()
    client.force_login(user)
    assert client.get(ENTRY_PATH).status_code == 403
