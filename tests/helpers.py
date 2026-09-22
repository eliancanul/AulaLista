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


MINIMAL_VALID_PDF_BYTES = (
    b"%PDF-1.3\n%\xe2\xe3\xcf\xd3\n"
    b"1 0 obj\n<<\n/Producer (pypdf)\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Count 1\n/Kids [ 4 0 R ]\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"4 0 obj\n<<\n/Type /Page\n/Resources <<\n>>\n/MediaBox [ 0.0 0.0 72 72 ]\n/Parent 2 0 R\n>>\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n0000000015 00000 n \n0000000054 00000 n \n0000000113 00000 n \n0000000162 00000 n \n"
    b"trailer\n<<\n/Size 5\n/Root 3 0 R\n/Info 1 0 R\n>>\nstartxref\n254\n%%EOF\n"
)


def minimal_pdf_upload(name="curricula.pdf", content_type="application/pdf"):
    """Return a SimpleUploadedFile containing a valid 1-page PDF passing PdfReader."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, MINIMAL_VALID_PDF_BYTES, content_type=content_type)
