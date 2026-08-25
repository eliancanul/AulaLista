"""Issue #30 and #31: safe anonymous redirects and PDF filename sanitization."""

import os

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import CurriculumImportJob, curriculum_import_pdf_path  # noqa: E402

pytestmark = pytest.mark.django_db


def test_anonymous_tutor_route_redirects_to_wagtail_login():
    """Issue #30: anonymous access to tutor/* must redirect to the real login."""

    client = Client()
    url = reverse("tutor-import-upload")
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"].startswith("/cms/login/")
    assert f"next={url}" in response["Location"]

    # Same contract for detail routes.
    detail_url = reverse("tutor-import-detail", args=[999])
    response = client.get(detail_url)
    assert response.status_code == 302
    assert response["Location"].startswith("/cms/login/")


def test_anonymous_login_then_next_returns_to_original_page():
    """Issue #30: after login the teacher lands on the originally requested page."""

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user_model.objects.create_user(
        username="redirect-tutor",
        password="test-password",
        is_staff=True,
    )
    client = Client()
    target = reverse("tutor-import-upload")
    response = client.get(target)
    login_url = response["Location"]
    assert client.get(login_url).status_code == 200

    assert client.login(username="redirect-tutor", password="test-password")
    response = client.get(target)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "raw_name",
    [
        "x" * 300,
        "a" * 200 + ".pdf.pdf",
        "Currícula SEM 1 — Primaria   Rural (2026) 📚🔥 .pdf",
        "plan<>:\"/\\|?*de%estudios\".pdf",
        "   ",
        "!!!",
    ],
)
def test_sanitized_pdf_names_always_safe(raw_name):
    path = curriculum_import_pdf_path(None, raw_name)
    stem = os.path.basename(path)
    assert path.startswith("curriculum_imports/")
    assert stem.endswith(".pdf")
    assert len(stem.encode("utf-8")) <= 255
    assert not any(ch in stem for ch in '<>:"/\\|?*')
    assert "\x00" not in stem


def test_sanitized_pdf_name_falls_back_when_empty():
    assert (
        curriculum_import_pdf_path(None, "!!!.pdf")
        == "curriculum_imports/curriculo.pdf"
    )


def test_upload_with_huge_name_saves_without_error():
    """Issue #31: a 300+ char name uploads fine; the teacher renames nothing."""

    from helpers import tutor_client

    pdf = SimpleUploadedFile(
        "C" * 300 + ".pdf",
        b"%PDF-1.4 fake bytes",
        content_type="application/pdf",
    )
    response = tutor_client().post(reverse("tutor-import-upload"), {"pdf": pdf})
    assert response.status_code == 302

    job = CurriculumImportJob.objects.latest("id")
    stored = job.pdf.name
    assert stored.startswith("curriculum_imports/")
    assert os.path.basename(stored).endswith(".pdf")
    assert len(os.path.basename(stored).encode("utf-8")) <= 255
