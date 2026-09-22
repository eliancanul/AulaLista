"""tests/test_ux9_p2_range_header.py
P2-1: Malformed Range header 'bytes=0' must return 416, not IndexError.
"""
import hashlib
import io

import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from curriculum.models import CurriculumImportJob

pytestmark = pytest.mark.django_db


def _upload_teacher_with_job():
    User = get_user_model()
    teacher = User.objects.create_user(
        username="range-test-teacher", is_staff=True
    )
    # Build a minimal valid PDF
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    job = CurriculumImportJob.objects.create(
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        created_by=teacher,
        source_text="Page 1",
        page_count=1,
    )
    from django.core.files.base import ContentFile
    job.pdf.save("test-range.pdf", ContentFile(pdf_bytes), save=True)
    return teacher, job, pdf_bytes


class TestMalformedRangeHeader:
    def test_range_bytes_no_hyphen_returns_416(self):
        """Range: bytes=0 (no hyphen) must return 416, not crash."""
        teacher, job, _ = _upload_teacher_with_job()
        client = Client()
        client.force_login(teacher)

        url = reverse("tutor-import-source-page", args=[job.pk, 1])
        response = client.get(url, HTTP_RANGE="bytes=0")
        assert response.status_code == 416, (
            f"Expected 416 for malformed Range 'bytes=0', got {response.status_code}"
        )
        assert "Content-Range" in response

    def test_valid_range_still_works(self):
        """Normal range request should still return 206."""
        teacher, job, pdf_bytes = _upload_teacher_with_job()
        client = Client()
        client.force_login(teacher)

        url = reverse("tutor-import-source-page", args=[job.pk, 1])
        response = client.get(url, HTTP_RANGE="bytes=0-99")
        assert response.status_code == 206
