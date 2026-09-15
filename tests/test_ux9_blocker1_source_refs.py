import hashlib
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from curriculum.models import CurriculumPackage, PublishedPackageSnapshot

pytestmark = pytest.mark.django_db


class MockPackage:
    title = "Mock Package"
    get_absolute_url = lambda self: "/mock-url/"


class MockSnapshot:
    pk = 123
    version = 1
    sha256 = "abcd"
    package = MockPackage()


def test_tutor_package_detail_legacy_pages_renders_successfully():
    # Legacy format with 'pages' instead of 'source_pages'
    source_refs = [{
        "session_id": "sess-1",
        "session_number": 1,
        "pages": [1, 2],
        "source_anchor": "Actividad 1",
    }]

    snapshot = MockSnapshot()
    payload = {"source_references": source_refs}

    # Must NOT raise NoReverseMatch; must render page links
    rendered = render_to_string("curriculum/tutor_package_detail.html", {
        "snapshot": snapshot,
        "payload": payload,
    })

    assert "/tutor/curricula/123/fuente/1/" in rendered
    assert "/tutor/curricula/123/fuente/2/" in rendered
    assert "Actividad 1" in rendered


def test_tutor_package_detail_legacy_snapshot_db_intact_and_urls_work():
    """ADR-0001: Legacy snapshots published with 'pages' in DB are NOT rewritten in DB,
    render detail successfully, and source-page URLs work."""
    User = get_user_model()
    teacher = User.objects.create_user(username="teacher_legacy_refs", password="password", is_staff=True)
    client = Client()
    client.force_login(teacher)

    pdf_content = b"%PDF-1.4 mock content for legacy test"
    pdf_hash = hashlib.sha256(pdf_content).hexdigest()

    pkg = CurriculumPackage.objects.create(
        title="Legacy Package",
        created_by=teacher,
    )
    revision = pkg.save_revision(user=teacher)
    legacy_payload = {
        "objective": "Objetivo legacy",
        "source_references": [
            {
                "session_id": "sess-legacy-1",
                "session_number": 1,
                "pages": [1, 2],
                "source_anchor": "Lamina 1",
            }
        ],
    }
    snapshot = PublishedPackageSnapshot.objects.create(
        package=pkg,
        published_by=teacher,
        source_revision=revision,
        version=1,
        sha256=pdf_hash,
        payload=legacy_payload,
        source_pdf=ContentFile(pdf_content, name="legacy_source.pdf"),
        source_pdf_sha256=pdf_hash,
    )

    # 1. GET detail view renders 200 and includes page links
    detail_url = reverse("tutor-package-detail", args=[snapshot.pk])
    resp = client.get(detail_url)
    assert resp.status_code == 200
    detail_content = resp.content.decode("utf-8")
    page_1_url = reverse("tutor-package-source-page", args=[snapshot.pk, 1])
    page_2_url = reverse("tutor-package-source-page", args=[snapshot.pk, 2])
    assert page_1_url in detail_content
    assert page_2_url in detail_content

    # 2. Source page URLs serve the PDF
    page_resp = client.get(page_1_url)
    assert page_resp.status_code == 200
    assert page_resp["Content-Type"] == "application/pdf"
    assert b"".join(page_resp.streaming_content) == pdf_content

    # 3. Verify DB payload was NOT mutated (persisted data remains intact)
    snapshot.refresh_from_db()
    ref_in_db = snapshot.payload["source_references"][0]
    assert "pages" in ref_in_db, "Legacy 'pages' key must be preserved in DB payload"
    assert ref_in_db["pages"] == [1, 2]
    assert "source_pages" not in ref_in_db, "DB payload must not be mutated to add source_pages"


def test_tutor_package_detail_source_refs_format_pass():
    # New working format with source_pages
    source_refs = [{
        "session_id": "sess-1",
        "session_number": 1,
        "source_pages": [1, 2],
        "source_pdf_sha256": "abcd",
        "source_anchor": "Test Title",
        "source_text": "Sample text",
        "source_urls": ["http://example.com"],
    }]

    snapshot = MockSnapshot()
    payload = {"source_references": source_refs}

    rendered = render_to_string("curriculum/tutor_package_detail.html", {
        "snapshot": snapshot,
        "payload": payload,
    })

    assert "Test Title" in rendered
    assert "http://example.com" in rendered
    assert "Sample text" in rendered
    assert "/tutor/curricula/123/fuente/1/" in rendered
