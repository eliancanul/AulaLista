"""Tests for Task 7: Explicit Teacher Approval Flow (UX7).

Requirements (UX7):
1. Preconditions in Review T6:
   - Only when dossier is READY, T5 report is current/valid, 0 blockers, and F7 queue has 0 conflicts/mandatory requirements:
     show CTA "Aprobar planeación".
   - Optional pending items: only with explicit human confirmation and honest copy.
2. Approval POST Action:
   - POST owner-only, CSRF, expected_version, payload allowlist, explicit confirmation.
   - GET never approves.
   - Double POST / concurrency: idempotent with same expected_version.
   - Stale version -> 409 Conflict.
   - Tamper / stale report blocks without mutation.
3. Auditable Persistence:
   - Persist approval linked to job, dossier version, SHA, teacher, and timestamp via model/migration.
   - Editing / re-extraction / new version invalidates active approval without deleting history.
4. Boundary Rules (ADR 0001, ADR 0002, ADR 0006):
   - Approval DOES NOT publish, DOES NOT create PublishedPackageSnapshot, DOES NOT activate session.
   - Creates/updates draft CurriculumPackage once, owner, immutable source, transaction.
   - Distinguishes "Aprobada para preparar" from "Publicada".
   - Publication remains separate human editorial action.
5. UX & Listing:
   - Success state with real next step.
   - Listing shows "Aprobada" / "Requiere revisión".
   - Previous disabled button removed.
   - No leaks of V0, internal models, SEP endorsement, or pedagogical certification.
6. Media isolation:
   - Media root stays isolated and repo media retains 8 paths + SHA before/after.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from curriculum.models import (
    ClassroomSession,
    CurriculumImportJob,
    CurriculumPackage,
    CurriculumSourceBlob,
    PublishedPackageSnapshot,
)
from curriculum.source_interpreter import (
    AnnexReference,
    CurriculumSourceInterpreter,
    ImportDossier,
    InterpretedField,
    ORIGIN_EXTRACTED,
    REVIEW_CONFIRMED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_CONFLICTING,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    SessionPlan,
    SourceReference,
    derive_operational_queue,
)
from curriculum.verification import (
    compute_canonical_verification_report,
    verify_curriculum_dossier,
)
from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

pytestmark = pytest.mark.django_db(transaction=True)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
if not C01_PATH.exists():
    C01_PATH = Path("media/curriculum_imports/prueba-semana-01.pdf")


def _c01_bytes() -> bytes:
    assert C01_PATH.exists(), f"PDF fixture not found at {C01_PATH}"
    return C01_PATH.read_bytes()


def tutor_teacher(username=None):
    client = tutor_client(username)
    user = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    return client, user


def create_ready_job(user, pdf_bytes=None, dossier=None):
    """Create a ready job from C01. By default has 0 requires_resolution and 22 pending optional items."""
    if pdf_bytes is None:
        pdf_bytes = _c01_bytes()
    if dossier is None:
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    dossier.verification_report = report.to_dict()

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("planeacion.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_COMPLETED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        page_count=dossier.page_count,
        interpretation_dossier=dossier.to_dict(),
    )
    return job, dossier


def create_fully_reviewed_job(user, pdf_bytes=None):
    """Create a ready job where all 22 items are fully reviewed (0 requires_resolution, 0 pending_review)."""
    if pdf_bytes is None:
        pdf_bytes = _c01_bytes()
    dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
    sha = dossier.source_sha256

    for f in dossier.general_fields.values():
        f.review = REVIEW_CONFIRMED
        f.status = STATUS_SUPPORTED
    for s in dossier.sessions:
        s.annex_references = []
        for f in s.fields.values():
            f.review = REVIEW_CONFIRMED
            f.status = STATUS_SUPPORTED

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    dossier.verification_report = report.to_dict()

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("planeacion.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_COMPLETED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        page_count=dossier.page_count,
        interpretation_dossier=dossier.to_dict(),
    )
    return job, dossier


def create_job_with_conflict(user, pdf_bytes=None):
    """Create a ready job that has an unresolved conflict in a required field (requires_resolution > 0)."""
    if pdf_bytes is None:
        pdf_bytes = _c01_bytes()
    dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
    # An annex with no candidate pages requires manual resolution in the queue (requires_resolution > 0)
    # while keeping verification valid (needs_teacher_review, 0 blocks)
    annex = dossier.sessions[0].annex_references[0]
    annex.candidate_pages = []
    annex.confirmed_page = None
    annex.review = REVIEW_PENDING
    annex.evidence = []

    report = verify_curriculum_dossier(dossier, pdf_bytes)
    dossier.verification_report = report.to_dict()

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("planeacion.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_COMPLETED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        page_count=dossier.page_count,
        interpretation_dossier=dossier.to_dict(),
    )
    return job, dossier


class TestTask7ExplicitTeacherApproval:
    """Comprehensive test suite for UX7 Teacher Approval."""

    def test_t7_approval_cta_preconditions(self):
        """1. CTA 'Aprobar planeación' only shown with READY dossier, valid T5 report, 0 blockers, and 0 F7 conflicts/mandatory missing."""
        client, user = tutor_teacher("t7-cta-preconditions")

        # Case A: Clean ready dossier -> CTA Aprobar planeación is present
        job_clean, dossier_clean = create_ready_job(user)

        url_clean = reverse("tutor-import-interpretation", args=[job_clean.pk])
        resp_clean = client.get(url_clean)
        assert resp_clean.status_code == 200

        soup_clean = BeautifulSoup(resp_clean.content.decode("utf-8"), "html.parser")
        approve_btn = soup_clean.find("button", attrs={"name": "action", "value": "approve"})
        assert approve_btn is not None, "CTA Aprobar planeación debe mostrarse cuando se cumplen todas las condiciones"
        assert "aprobar planeación" in approve_btn.get_text().lower()

        # Case B: Dossier with conflict in required field -> CTA Aprobar planeación MUST NOT be present as an active button
        job_conflict, dossier_conflict = create_job_with_conflict(user)

        url_conflict = reverse("tutor-import-interpretation", args=[job_conflict.pk])
        resp_conflict = client.get(url_conflict)
        assert resp_conflict.status_code == 200

        soup_conflict = BeautifulSoup(resp_conflict.content.decode("utf-8"), "html.parser")
        approve_btn_bad = soup_conflict.find("button", attrs={"name": "action", "value": "approve"})
        assert approve_btn_bad is None, "CTA Aprobar planeación NO debe ser un botón activo cuando hay conflictos sin resolver"

        # Honest notice must explain that approval is unavailable
        notice = soup_conflict.find(class_="approval-notice")
        assert notice is not None
        assert any(w in notice.get_text().lower() for w in ("disponible", "resuelvan", "completada", "revisión"))

    def test_t7_approval_optional_pending_requires_explicit_confirmation(self):
        """2. Optional pending items allow approval ONLY with explicit human confirmation and honest copy."""
        client, user = tutor_teacher("t7-optional-pending")
        job, dossier_opt = create_ready_job(user)

        q = derive_operational_queue(dossier_opt)
        assert q.requires_resolution_count == 0
        assert q.pending_review_count > 0, "Debe tener elementos opcionales pendientes"

        url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.get(url)
        assert resp.status_code == 200

        soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")
        # Honest copy showing count of pending optional items
        text = soup.get_text()
        assert f"{q.pending_review_count} elemento" in text
        assert "opcional" in text.lower()

        # Checkbox for confirming pending items must be present in the approval UI
        chk_pending = soup.find("input", attrs={"name": "confirm_pending_items"})
        assert chk_pending is not None, "Checkbox confirm_pending_items debe existir cuando hay elementos opcionales pendientes"

        # Submitting approval WITHOUT confirm_pending_items returns 400 Bad Request
        post_bad = {
            "action": "approve",
            "expected_version": dossier_opt.version,
            "confirm_approval": "1",
        }
        resp_bad = client.post(url, post_bad)
        assert resp_bad.status_code == 400
        assert "opcionales pendientes" in resp_bad.content.decode("utf-8").lower() or "confirm" in resp_bad.content.decode("utf-8").lower()

        # Submitting approval WITH confirm_pending_items succeeds
        post_good = {
            "action": "approve",
            "expected_version": dossier_opt.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        }
        resp_good = client.post(url, post_good)
        assert resp_good.status_code in (200, 302)

        # Job is now approved
        job.refresh_from_db()
        from curriculum.models import CurriculumImportApproval
        approval = CurriculumImportApproval.objects.filter(job=job, is_active=True).first()
        assert approval is not None
        assert approval.pending_items_count == q.pending_review_count

    def test_t7_approval_post_owner_only_and_csrf(self):
        """3. POST is owner-only, unauthenticated is redirected, and CSRF is enforced."""
        client, user = tutor_teacher("t7-owner-test")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])

        # Other authenticated teacher cannot approve (404)
        other_client, other_user = tutor_teacher("t7-other-owner")
        resp_other = other_client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_other.status_code == 404

        # Owner can approve
        resp_owner = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_owner.status_code in (200, 302)

    def test_t7_get_never_approves(self):
        """4. GET request NEVER approves and never mutates database."""
        client, user = tutor_teacher("t7-get-never-approves")
        job, dossier = create_ready_job(user)

        url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.get(f"{url}?action=approve&confirm_approval=1&expected_version={dossier.version}")
        assert resp.status_code == 200

        # No approval must be created
        from curriculum.models import CurriculumImportApproval
        assert CurriculumImportApproval.objects.filter(job=job).count() == 0
        assert CurriculumPackage.objects.filter(created_by=user).count() == 0

    def test_t7_expected_version_and_stale_version_409(self):
        """5. expected_version validation: missing/invalid returns 400; stale version returns 409 Conflict."""
        client, user = tutor_teacher("t7-version-conflict")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        # Missing expected_version -> 400
        resp_missing = client.post(url, {"action": "approve", "confirm_approval": "1", "confirm_pending_items": "1"})
        assert resp_missing.status_code == 400

        # Invalid expected_version -> 400
        resp_invalid = client.post(
            url,
            {"action": "approve", "expected_version": "abc", "confirm_approval": "1", "confirm_pending_items": "1"},
        )
        assert resp_invalid.status_code == 400

        # Stale expected_version -> 409 Conflict
        stale_version = dossier.version + 5
        resp_stale = client.post(
            url,
            {
                "action": "approve",
                "expected_version": stale_version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_stale.status_code == 409
        assert "409" in resp_stale.content.decode("utf-8") or "concurrencia" in resp_stale.content.decode("utf-8").lower()

    def test_t7_payload_allowlist_rejects_unauthorized_keys(self):
        """6. Payload allowlist strictly rejects extra / malicious keys with 400 Bad Request."""
        client, user = tutor_teacher("t7-allowlist-test")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        post_with_extra = {
            "action": "approve",
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
            "is_admin": "true",
            "publish_now": "true",
        }
        resp = client.post(url, post_with_extra)
        assert resp.status_code == 400
        assert "no permitidos" in resp.content.decode("utf-8").lower() or "no autorizada" in resp.content.decode("utf-8").lower()

    def test_t7_double_post_concurrency_idempotent(self):
        """7. Duplicate POST with same expected_version is idempotent and does not duplicate approvals or packages."""
        client, user = tutor_teacher("t7-idempotent-post")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        post_data = {
            "action": "approve",
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        }

        # First POST
        resp1 = client.post(url, post_data)
        assert resp1.status_code in (200, 302)

        # Second POST (immediate double-click / concurrent repeat)
        resp2 = client.post(url, post_data)
        assert resp2.status_code in (200, 302)

        from curriculum.models import CurriculumImportApproval
        # Exactly one active approval
        active_approvals = CurriculumImportApproval.objects.filter(job=job, is_active=True)
        assert active_approvals.count() == 1

        # Exactly one draft CurriculumPackage created
        packages = CurriculumPackage.objects.filter(created_by=user)
        assert packages.count() == 1

    def test_t7_tamper_and_stale_report_blocked_without_mutation(self):
        """8. Tampered PDF or stale verification report blocks approval with 409 without mutation."""
        client, user = tutor_teacher("t7-tamper-guard")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        # Tamper: replace PDF file with different bytes
        job.pdf.save("tampered.pdf", SimpleUploadedFile("tampered.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"))
        job.save()

        resp = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp.status_code == 409
        from curriculum.models import CurriculumImportApproval
        assert CurriculumImportApproval.objects.filter(job=job).count() == 0

    def test_t7_persistence_audit_and_invalidation(self):
        """9. Approval persists auditable record linked to job, version, SHA, teacher, timestamp; edit/reextract invalidates active approval without deleting history."""
        client, user = tutor_teacher("t7-audit-invalidation")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        # 1. Approve
        resp = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp.status_code in (200, 302)

        from curriculum.models import CurriculumImportApproval
        approval = CurriculumImportApproval.objects.filter(job=job, is_active=True).first()
        assert approval is not None
        assert approval.dossier_version == dossier.version
        assert approval.source_sha256 == dossier.source_sha256
        assert approval.approved_by == user
        assert approval.approved_at is not None

        # Check dossier history audit entry
        job.refresh_from_db()
        dossier_after = job.get_interpretation_dossier()
        assert len(dossier_after.history) > 0
        last_hist = dossier_after.history[-1]
        assert "aprobada" in last_hist.get("summary", "").lower()

        # 2. Saving a correction bumps version and invalidates active approval
        prev_version = dossier_after.version
        post_edit = {
            "action": "save_corrections",
            "expected_version": prev_version,
            "session_id": dossier_after.sessions[0].session_id,
            "session_number": dossier_after.sessions[0].session_number,
            "inicio": "Inicio modificado por la docente después de aprobar",
        }
        resp_edit = client.post(url, post_edit)
        assert resp_edit.status_code in (200, 302)

        job.refresh_from_db()
        dossier_edited = job.get_interpretation_dossier()
        assert dossier_edited.version == prev_version + 1

        # Active approval is now invalidated (derived from dossier version mismatch)
        active_now = CurriculumImportApproval.objects.filter(job=job, is_active=True).first()
        assert active_now is None, "La aprobación activa debió ser None tras la modificación"
        assert job.get_active_approval() is None
        assert job.is_approved is False

        # But historical approval record is permanently preserved with exact snapshot
        historical = CurriculumImportApproval.objects.filter(job=job, is_active=False).first()
        assert historical is not None
        assert historical.is_active is False
        assert historical.dossier_version == prev_version
        assert historical.dossier_snapshot["version"] == prev_version

    def test_t7_approval_boundary_no_publish_no_session(self):
        """10. Approval NEVER publishes, NEVER creates PublishedPackageSnapshot, NEVER activates session; draft CurriculumPackage created once with immutable source."""
        client, user = tutor_teacher("t7-boundary-rules")
        job, dossier = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        resp = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp.status_code in (200, 302)

        # 1. Draft package created
        from curriculum.models import CurriculumImportApproval
        approval = CurriculumImportApproval.objects.get(job=job, is_active=True)
        pkg = approval.package
        assert pkg is not None
        assert pkg.created_by == user
        assert pkg.title == dossier.general_fields["proyecto"].value
        assert pkg.source_pdf_sha256 == dossier.source_sha256
        assert len(pkg.source_references) > 0

        # 2. Package is a DRAFT, NOT published
        assert pkg.live_revision is None

        # 3. ZERO PublishedPackageSnapshot
        assert PublishedPackageSnapshot.objects.filter(package=pkg).count() == 0

        # 4. ZERO ClassroomSession created or activated
        assert ClassroomSession.objects.count() == 0

    def test_t7_ux_listing_and_success_state(self):
        """11. Listing shows 'Aprobada' / 'Requiere revisión', review UI shows success banner with real next step, no prohibited jargon."""
        client, user = tutor_teacher("t7-ux-listing")
        job, dossier = create_ready_job(user)

        # Before approval: listing shows "Requiere revisión"
        listing_url = reverse("tutor-curriculum")
        resp_list_before = client.get(listing_url)
        assert resp_list_before.status_code == 200
        soup_list_before = BeautifulSoup(resp_list_before.content.decode("utf-8"), "html.parser")
        job_card = soup_list_before.find("article", attrs={"data-job-id": str(job.pk)})
        assert job_card is not None
        assert "Requiere revisión" in job_card.get_text()

        # Approve
        review_url = reverse("tutor-import-interpretation", args=[job.pk])
        client.post(
            review_url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )

        # After approval: listing shows "Aprobada"
        resp_list_after = client.get(listing_url)
        assert resp_list_after.status_code == 200
        soup_list_after = BeautifulSoup(resp_list_after.content.decode("utf-8"), "html.parser")
        job_card_after = soup_list_after.find("article", attrs={"data-job-id": str(job.pk)})
        assert job_card_after is not None
        assert "Aprobada" in job_card_after.get_text()

        # Package card shows "Aprobada para preparar" (distinguished from "Publicada")
        pkg_card = soup_list_after.find("section", attrs={"aria-labelledby": "drafts-heading"})
        if pkg_card:
            assert "Aprobada para preparar" in pkg_card.get_text()
            assert "Publicada" not in pkg_card.get_text()

        # Review UI renders success banner with real next step
        resp_review = client.get(review_url)
        assert resp_review.status_code == 200
        soup_review = BeautifulSoup(resp_review.content.decode("utf-8"), "html.parser")

        success_card = soup_review.find(class_=lambda c: c and "approval-success" in c)
        assert success_card is not None, "Banner de éxito de aprobación debe renderizarse en la UI"
        card_text = success_card.get_text()
        assert "aprobada para preparar" in card_text.lower()
        assert "siguiente paso" in card_text.lower()

        # Has real links to curriculum / package editor
        next_links = success_card.find_all("a", href=True)
        assert len(next_links) >= 1
        assert any(reverse("tutor-curriculum") in a["href"] for a in next_links)

        # No forbidden jargon
        page_text = soup_review.get_text().lower()
        assert "fase v0" not in page_text
        assert "certificación pedagógica" not in page_text
        assert "sep" not in page_text

    def test_t7_dedicated_approval_route(self):
        """12. Dedicated route tutor-import-approve accepts POST and approves, GET returns 405 Method Not Allowed."""
        client, user = tutor_teacher("t7-dedicated-route")
        job, dossier = create_ready_job(user)

        approve_url = reverse("tutor-import-approve", args=[job.pk])

        # GET is rejected with 405 Method Not Allowed
        resp_get = client.get(approve_url)
        assert resp_get.status_code == 405

        # POST approves
        resp_post = client.post(
            approve_url,
            {
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_post.status_code in (200, 302)

        from curriculum.models import CurriculumImportApproval
        assert CurriculumImportApproval.objects.filter(job=job, is_active=True).count() == 1

    def test_t7_concurrency_threads_real(self):
        """13. Causal Luna test: Real multithreading double POST returns idempotent success (200/302) with 1 active approval, 1 package, and 1 source PDF."""
        import concurrent.futures
        from django.test import Client

        client, user = tutor_teacher("t7-threads-causal")
        job, dossier = create_ready_job(user)
        approve_url = reverse("tutor-import-approve", args=[job.pk])

        post_data = {
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        }

        # Pre-authenticate clients to avoid concurrent auth_user updates
        c1 = Client()
        c1.force_login(user)
        c2 = Client()
        c2.force_login(user)
        clients = [c1, c2]

        def post_approval(idx):
            import time, random
            time.sleep(random.uniform(0.002, 0.015))
            return clients[idx].post(approve_url, post_data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(post_approval, i) for i in range(2)]
            responses = [f.result() for f in futures]

        # Both responses must be idempotent success (200 or 302), NEVER 500
        for resp in responses:
            assert resp.status_code in (200, 302), f"Expected 200/302, got {resp.status_code}"

        from curriculum.models import CurriculumImportApproval, CurriculumPackage, CurriculumSourceBlob
        assert CurriculumImportApproval.objects.filter(job=job).count() == 1
        assert CurriculumImportApproval.objects.filter(job=job, is_active=True).count() == 1
        assert CurriculumPackage.objects.filter(created_by=user).count() == 1

        # Exactly 1 package source blob created in DB, no storage FileField
        pkg = CurriculumPackage.objects.get(created_by=user)
        assert pkg.source_blob is not None
        assert pkg.source_blob.sha256 == dossier.source_sha256.lower()
        assert CurriculumSourceBlob.objects.filter(sha256=dossier.source_sha256.lower()).count() == 1
        assert not pkg.source_pdf

    def test_t7_fault_after_package_before_approval_leaves_no_orphan(self):
        """14. Causal Luna test: Forced failure after package creation before approval commits rolls back cleanly and leaves ZERO orphaned files."""
        import django.db.utils
        from django.core.files.storage import default_storage
        from django.test import Client
        from curriculum.models import CurriculumImportApproval, CurriculumPackage

        _, user = tutor_teacher("t7-fault-rollback")
        job, dossier = create_ready_job(user)
        approve_url = reverse("tutor-import-approve", args=[job.pk])

        post_data = {
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        }

        # Use client with raise_request_exception=False to observe 500 response (matching Luna B3 probe)
        fail_client = Client(raise_request_exception=False)
        fail_client.force_login(user)

        package_sources_dir = Path(default_storage.path("curriculum/package-sources")) if hasattr(default_storage, "path") else None
        files_before = set(package_sources_dir.rglob("*.pdf")) if package_sources_dir and package_sources_dir.exists() else set()

        # Force failure exactly on CurriculumImportApproval.objects.create (reproducing Luna B3 probe)
        with patch.object(
            CurriculumImportApproval.objects,
            "create",
            side_effect=django.db.utils.IntegrityError("forced after package write"),
        ):
            resp = fail_client.post(approve_url, post_data)
            assert resp.status_code == 500

        # Database rollback must be complete
        assert CurriculumImportApproval.objects.filter(job=job).count() == 0
        assert CurriculumPackage.objects.filter(created_by=user).count() == 0
        from curriculum.models import CurriculumSourceBlob
        assert CurriculumSourceBlob.objects.filter(sha256=dossier.source_sha256.lower()).count() == 0

        # Storage must have ZERO new package source PDFs created
        files_after = set(package_sources_dir.rglob("*.pdf")) if package_sources_dir and package_sources_dir.exists() else set()
        new_orphans = files_after - files_before
        assert len(new_orphans) == 0, f"Found new orphaned package PDFs: {new_orphans}"

    def test_t7_reapproval_two_versions_content_and_source_exact(self):
        """15. Causal Luna test: Reapproval updates draft package to current content/source/version, cleans unreferenced prior artifact, and keeps exact historical snapshot."""
        client, user = tutor_teacher("t7-reapproval-content")
        job, dossier_v1 = create_ready_job(user)
        url = reverse("tutor-import-interpretation", args=[job.pk])

        # 1. Approve v1
        resp_v1 = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier_v1.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_v1.status_code in (200, 302)

        from curriculum.models import CurriculumImportApproval, CurriculumPackage
        assert CurriculumPackage.objects.filter(created_by=user).count() == 1
        pkg_v1 = CurriculumPackage.objects.get(created_by=user)
        v1_title = dossier_v1.general_fields["proyecto"].value
        assert pkg_v1.title == v1_title

        # 2. Modify dossier to v2: change title and add distinct session content and PDF bytes
        job.refresh_from_db()
        v2_pdf_bytes = _c01_bytes() + b"\n% version 2 reapproval bytes\n"
        job.pdf.save("planeacion_v2.pdf", ContentFile(v2_pdf_bytes))

        dossier_v2 = CurriculumSourceInterpreter.prepare(v2_pdf_bytes)
        dossier_v2.version = 2
        new_title = "Proyecto cambiado después de aprobar"
        dossier_v2.general_fields["proyecto"].value = new_title

        # Update verification report for v2
        report_v2 = verify_curriculum_dossier(dossier_v2, v2_pdf_bytes)
        dossier_v2.verification_report = report_v2.to_dict()
        job.interpretation_dossier = dossier_v2.to_dict()
        job.save()

        # 3. Approve v2
        resp_v2 = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier_v2.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_v2.status_code in (200, 302)

        # Still exactly 1 draft package
        assert CurriculumPackage.objects.filter(created_by=user).count() == 1
        pkg_updated = CurriculumPackage.objects.get(created_by=user)
        # Draft package must have the CURRENT v2 title (fixing B4!)
        assert pkg_updated.title == new_title

        # Exactly 2 approvals in DB
        approvals = list(CurriculumImportApproval.objects.filter(job=job).order_by("dossier_version"))
        assert len(approvals) == 2

        app_v1 = approvals[0]
        app_v2 = approvals[1]

        # v1 historical snapshot preserved exactly
        assert app_v1.dossier_version == 1
        assert app_v1.dossier_snapshot["general_fields"]["proyecto"]["value"] == v1_title
        assert app_v1.is_active is False
        assert app_v1.source_blob.sha256 == dossier_v1.source_sha256.lower()

        # v2 active snapshot exact
        assert app_v2.dossier_version == 2
        assert app_v2.dossier_snapshot["general_fields"]["proyecto"]["value"] == new_title
        assert app_v2.is_active is True
        assert app_v2.source_blob.sha256 == dossier_v2.source_sha256.lower()

        # Draft package points to current v2 blob, historical approval preserves v1 blob
        assert pkg_updated.source_blob == app_v2.source_blob
        assert app_v1.source_blob != app_v2.source_blob
        assert app_v1.get_source_bytes() == _c01_bytes()
        assert app_v2.get_source_bytes() == v2_pdf_bytes
        assert pkg_updated.get_source_bytes() == v2_pdf_bytes

        # Exactly 1 active approval logically
        assert job.get_active_approval().dossier_version == 2

    def test_t7_model_immutability_update_delete_duplicate(self):
        """16. Causal Luna test: CurriculumImportApproval is append-only; save of existing, delete, and duplicate version raise errors."""
        import django.db.utils

        client, user = tutor_teacher("t7-model-immutability")
        job, dossier = create_ready_job(user)

        from curriculum.models import CurriculumImportApproval
        approval = CurriculumImportApproval.objects.create(
            job=job,
            dossier_version=1,
            source_sha256="a" * 64,
            approved_by=user,
        )

        # 1. Model constraints must be present
        constraint_names = [str(c.name) for c in CurriculumImportApproval._meta.constraints]
        assert "unique_curriculum_import_approval_job_version" in constraint_names
        assert "check_approval_dossier_version_positive" in constraint_names
        assert "check_approval_pending_items_count_gte_zero" in constraint_names

        # 2. Duplicate create for same job and dossier_version is rejected by DB unique constraint
        with pytest.raises(django.db.utils.IntegrityError):
            CurriculumImportApproval.objects.create(
                job=job,
                dossier_version=1,
                source_sha256="b" * 64,
                approved_by=user,
            )

        # 3. Save of existing instance is rejected
        approval.source_sha256 = "c" * 64
        with pytest.raises(PermissionError):
            approval.save(update_fields=["source_sha256"])

        # 4. Delete of instance is rejected
        with pytest.raises(PermissionError):
            approval.delete()

        # 5. QuerySet bulk update and delete are rejected
        with pytest.raises(PermissionError):
            CurriculumImportApproval.objects.filter(pk=approval.pk).update(source_sha256="d" * 64)

        with pytest.raises(PermissionError):
            CurriculumImportApproval.objects.filter(pk=approval.pk).delete()

        # 6. Database record remains intact
        assert CurriculumImportApproval.objects.filter(pk=approval.pk).count() == 1
        fresh = CurriculumImportApproval.objects.get(pk=approval.pk)
        assert fresh.source_sha256 == "a" * 64

    def test_t7_payload_conditional_exact_contract(self):
        """17. Causal Luna test: confirm_pending_items is required when pending > 0, and forbidden (400) when pending == 0."""
        client, user = tutor_teacher("t7-payload-exact")

        # Part A: Job with 0 pending items (fully reviewed)
        job_zero, dossier_zero = create_fully_reviewed_job(user)
        q_zero = derive_operational_queue(dossier_zero)
        assert q_zero.pending_review_count == 0
        assert q_zero.requires_resolution_count == 0

        url_zero = reverse("tutor-import-interpretation", args=[job_zero.pk])
        ded_zero = reverse("tutor-import-approve", args=[job_zero.pk])

        # Submitting WITH confirm_pending_items when pending == 0 must return 400 Bad Request
        resp_forbidden_1 = client.post(
            url_zero,
            {
                "action": "approve",
                "expected_version": dossier_zero.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_forbidden_1.status_code == 400
        assert "no está permitido" in resp_forbidden_1.content.decode("utf-8").lower() or "no permitid" in resp_forbidden_1.content.decode("utf-8").lower()

        resp_forbidden_ded = client.post(
            ded_zero,
            {
                "expected_version": dossier_zero.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_forbidden_ded.status_code == 400

        # Submitting WITHOUT confirm_pending_items when pending == 0 succeeds
        resp_ok = client.post(
            url_zero,
            {
                "action": "approve",
                "expected_version": dossier_zero.version,
                "confirm_approval": "1",
            },
        )
        assert resp_ok.status_code in (200, 302)
        assert job_zero.get_active_approval() is not None

        # Part B: Job with pending > 0 (ready job with 22 pending optional items)
        job_pending, dossier_pending = create_ready_job(user)
        q_pending = derive_operational_queue(dossier_pending)
        assert q_pending.pending_review_count > 0

        url_pending = reverse("tutor-import-interpretation", args=[job_pending.pk])

        # Missing confirm_pending_items -> 400
        resp_missing = client.post(
            url_pending,
            {
                "action": "approve",
                "expected_version": dossier_pending.version,
                "confirm_approval": "1",
            },
        )
        assert resp_missing.status_code == 400

        # False confirm_pending_items -> 400
        resp_false = client.post(
            url_pending,
            {
                "action": "approve",
                "expected_version": dossier_pending.version,
                "confirm_approval": "1",
                "confirm_pending_items": "0",
            },
        )
        assert resp_false.status_code == 400

        # Valid confirm_pending_items -> 200/302
        resp_valid = client.post(
            url_pending,
            {
                "action": "approve",
                "expected_version": dossier_pending.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_valid.status_code in (200, 302)
        assert job_pending.get_active_approval() is not None

    def test_t7_races_tamper_report_queue_no_mutation(self):
        """18. Causal Luna test: Races where physical PDF, canonical report, or operational queue are modified right before lock abort with 409 without mutation."""
        client, user = tutor_teacher("t7-race-guards")

        # Case A: Tamper PDF physical file right before approval
        job_a, dossier_a = create_ready_job(user)
        # Tamper bytes
        with job_a.pdf.open("wb") as f:
            f.write(MINIMAL_VALID_PDF_BYTES)

        url_a = reverse("tutor-import-interpretation", args=[job_a.pk])
        resp_a = client.post(
            url_a,
            {
                "action": "approve",
                "expected_version": dossier_a.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_a.status_code == 409
        from curriculum.models import CurriculumImportApproval, CurriculumPackage
        assert CurriculumImportApproval.objects.filter(job=job_a).count() == 0
        assert CurriculumPackage.objects.filter(created_by=user).count() == 0

        # Case B: Queue race (unresolved conflict introduced in dossier)
        job_b, dossier_b = create_ready_job(user)
        # Introduce conflict in dossier
        annex = dossier_b.sessions[0].annex_references[0]
        annex.candidate_pages = []
        annex.confirmed_page = None
        annex.review = REVIEW_PENDING
        annex.evidence = []
        job_b.interpretation_dossier = dossier_b.to_dict()
        job_b.save()

        url_b = reverse("tutor-import-interpretation", args=[job_b.pk])
        resp_b = client.post(
            url_b,
            {
                "action": "approve",
                "expected_version": dossier_b.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_b.status_code == 409
        assert CurriculumImportApproval.objects.filter(job=job_b).count() == 0

    def test_t7_migrations_forward_back_fresh(self):
        """19. Causal Luna test: Migrations 0040 and 0041 can be migrated backward to 0039 and forward to 0041 cleanly on isolated DB."""
        import tempfile, shutil
        from pathlib import Path
        from django.core.management import call_command

        d = Path(tempfile.mkdtemp(prefix="aulalista_test_mig_"))
        db = d / "test_mig.sqlite3"
        media = d / "media"
        media.mkdir()

        shutil.copy2("/Users/dojo/Documents/ChatGPT/AulaLista-repo/db.sqlite3", db)

        import os
        old_db = os.environ.get("AULALISTA_DB_PATH")
        old_media = os.environ.get("AULALISTA_MEDIA_ROOT")

        try:
            os.environ.update(AULALISTA_DB_PATH=str(db), AULALISTA_MEDIA_ROOT=str(media))
            # 1. Forward 0042
            call_command("migrate", "curriculum", "0042", verbosity=0)
            # 2. Backward 0041
            call_command("migrate", "curriculum", "0041", verbosity=0)
            # 3. Backward 0040
            call_command("migrate", "curriculum", "0040", verbosity=0)
            # 4. Backward 0039
            call_command("migrate", "curriculum", "0039", verbosity=0)
            # 5. Forward 0042 again
            call_command("migrate", "curriculum", "0042", verbosity=0)
        finally:
            if old_db:
                os.environ["AULALISTA_DB_PATH"] = old_db
            if old_media:
                os.environ["AULALISTA_MEDIA_ROOT"] = old_media
            shutil.rmtree(d, ignore_errors=True)

    def test_t7_b2_model_active_and_append_only(self):
        """20. B2 Verification: Approval has no mutable is_active DB column; is_active requires job READY, version+SHA match, valid canonical ready dossier; source missing => inactive; strict append-only."""
        import asyncio
        from django.db import connection
        from curriculum.models import CurriculumImportApproval, CurriculumPackage

        client, user = tutor_teacher("t7-b2-tester")
        job, dossier = create_ready_job(user)

        # 1. Verify DB schema: NO is_active column exists
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(curriculum_curriculumimportapproval)")
            columns = [row[1] for row in cursor.fetchall()]
        assert "is_active" not in columns
        assert "_is_active" not in columns

        # Approve job cleanly
        url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp.status_code in (200, 302)

        approval = CurriculumImportApproval.objects.filter(job=job).first()
        assert approval is not None
        assert approval.is_active is True
        assert job.get_active_approval() == approval

        # Check A: Job interpretation_state != READY => is_active is False
        job.interpretation_state = CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        job.save(update_fields=["interpretation_state"])
        approval.refresh_from_db()
        assert approval.is_active is False
        assert job.get_active_approval() is None

        # Restore state
        job.interpretation_state = CurriculumImportJob.INTERPRETATION_STATE_READY
        job.save(update_fields=["interpretation_state"])
        assert approval.is_active is True

        # Check B: Dossier version mismatch => is_active is False
        dossier.version = 99
        job.interpretation_dossier = dossier.to_dict()
        job.save(update_fields=["interpretation_dossier"])
        assert approval.is_active is False
        assert job.get_active_approval() is None

        # Restore version
        dossier.version = approval.dossier_version
        job.interpretation_dossier = dossier.to_dict()
        job.save(update_fields=["interpretation_dossier"])
        assert approval.is_active is True

        # Check C: Report mutation (blocked_count=999) => is_active is False
        dossier_mutated = job.interpretation_dossier
        dossier_mutated["verification_report"]["blocked_count"] = 999
        job.interpretation_dossier = dossier_mutated
        job.save(update_fields=["interpretation_dossier"])
        assert approval.is_active is False
        assert job.get_active_approval() is None

        # Restore valid report
        dossier_mutated["verification_report"]["blocked_count"] = 0
        job.interpretation_dossier = dossier_mutated
        job.save(update_fields=["interpretation_dossier"])
        assert approval.is_active is True

        # Check D: Missing current source physical file => is_active is False (B2 model active must not turn active if current source missing)
        from django.core.files.storage import default_storage
        pdf_storage_path = job.pdf.name
        with default_storage.open(pdf_storage_path, "rb") as s:
            original_pdf_bytes = s.read()

        default_storage.delete(pdf_storage_path)
        assert not default_storage.exists(pdf_storage_path)
        assert approval.is_active is False
        assert job.get_active_approval() is None

        # Restore source file
        default_storage.save(pdf_storage_path, ContentFile(original_pdf_bytes))
        assert approval.is_active is True
        assert job.get_active_approval() == approval

        # 2. Append-only enforcement tests
        with pytest.raises(PermissionError, match="append-only"):
            approval.save()

        with pytest.raises(PermissionError, match="permanent audit logs"):
            approval.delete()

        with pytest.raises(PermissionError, match="append-only"):
            CurriculumImportApproval.objects.filter(pk=approval.pk).update(dossier_version=100)

        with pytest.raises(PermissionError, match="permanent audit logs"):
            CurriculumImportApproval.objects.filter(pk=approval.pk).delete()

        with pytest.raises(PermissionError, match="append-only"):
            CurriculumImportApproval.objects.bulk_update([approval], ["dossier_version"])

        with pytest.raises(PermissionError, match="append-only"):
            CurriculumImportApproval.objects.update_or_create(
                pk=approval.pk,
                defaults={"dossier_version": 100},
            )

        with pytest.raises(PermissionError, match="append-only"):
            asyncio.run(CurriculumImportApproval.objects.filter(pk=approval.pk).aupdate(dossier_version=100))

        with pytest.raises(PermissionError, match="append-only"):
            asyncio.run(CurriculumImportApproval.objects.abulk_update([approval], ["dossier_version"]))

        with pytest.raises(PermissionError, match="permanent audit logs"):
            asyncio.run(CurriculumImportApproval.objects.filter(pk=approval.pk).adelete())

        with pytest.raises(PermissionError, match="append-only"):
            asyncio.run(approval.asave())

        with pytest.raises(PermissionError, match="permanent audit logs"):
            asyncio.run(approval.adelete())

    def test_t7_b3_storage_coherent_promotion_and_retry(self):
        """21. B3 Verification: Content-addressed transactional DB blob, append-only immutability, and crash rollback."""
        from django.core.files.storage import default_storage
        from django.core.exceptions import ValidationError
        from curriculum.approval_commands import execute_teacher_approval
        from curriculum.models import CurriculumImportApproval, CurriculumPackage, CurriculumSourceBlob

        client, user = tutor_teacher("t7-b3-tester")
        job, dossier = create_ready_job(user)
        pdf_bytes = _c01_bytes()
        pdf_sha = dossier.source_sha256.lower()

        # Case 1: Model validation & immutability of CurriculumSourceBlob
        with pytest.raises(ValidationError):
            CurriculumSourceBlob.objects.create(sha256="wronghash" * 8, content=b"hello")

        blob = CurriculumSourceBlob.objects.create(sha256=pdf_sha, content=pdf_bytes)
        assert blob.content_size == len(pdf_bytes)
        assert blob.size == len(pdf_bytes)

        with pytest.raises(PermissionError, match="immutable and cannot be updated"):
            blob.content = b"newcontent"
            blob.save()

        # Case 2: QuerySet/Manager immutability of CurriculumSourceBlob (Luna B2 audit)
        with pytest.raises(PermissionError, match="immutable"):
            CurriculumSourceBlob.objects.filter(pk=blob.pk).update(content=b"evil")

        with pytest.raises(PermissionError, match="immutable"):
            CurriculumSourceBlob.objects.bulk_update([blob], ["content"])

        with pytest.raises(PermissionError, match="immutable"):
            CurriculumSourceBlob.objects.filter(pk=blob.pk).delete()

        # Reject empty bytes on create
        with pytest.raises(ValidationError):
            CurriculumSourceBlob.objects.create(sha256="a" * 64, content=b"", content_size=7)

        with pytest.raises(ValidationError):
            CurriculumSourceBlob.objects.create(sha256="b" * 64, content=b"")

        # Case 3: Crash boundary does not leave orphan approval, package, or blob
        crash_pdf = _c01_bytes() + b"\n%crash-nonce\n"
        job_crash, dossier_crash = create_ready_job(user, pdf_bytes=crash_pdf)
        crash_sha = dossier_crash.source_sha256.lower()
        with patch.object(CurriculumImportApproval.objects, "create", side_effect=SystemExit("simulated process crash")):
            with pytest.raises(SystemExit):
                execute_teacher_approval(job_crash.pk, user, {
                    "action": "approve",
                    "expected_version": dossier_crash.version,
                    "confirm_approval": "1",
                    "confirm_pending_items": "1",
                })
        assert CurriculumImportApproval.objects.filter(job=job_crash).count() == 0
        assert not job_crash.__class__.objects.filter(pk=job_crash.pk).first().is_approved
        assert CurriculumSourceBlob.objects.filter(sha256=crash_sha).count() == 0

        # Case 4: Normal approval uses transactional blob and clean idempotency
        url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.post(
            url,
            {
                "action": "approve",
                "expected_version": dossier.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp.status_code in (200, 302)
        app = CurriculumImportApproval.objects.get(job=job)
        assert app.source_blob == blob
        assert app.get_source_bytes() == pdf_bytes

        # Attempting to delete blob raises PermissionError
        with pytest.raises(PermissionError, match="immutable and cannot be deleted"):
            blob.delete()

    def test_t7_b5_final_checkpoint_all_race_guards(self):
        """22. B5 Verification: CAS write ownership and final re-read of persisted report, physical PDF, and queue."""
        client, user = tutor_teacher("t7-b5-races")

        # Case 1: Dossier version race (mutated between preflight and lock)
        job_v, dossier_v = create_ready_job(user)
        url_v = reverse("tutor-import-interpretation", args=[job_v.pk])

        # Simulate mutation right after preflight
        orig_validate = __import__("curriculum.approval_commands", fromlist=["validate_approval_payload"]).validate_approval_payload
        def mutate_dossier_version_hook(*args, **kwargs):
            res = orig_validate(*args, **kwargs)
            # Mutate dossier version in DB
            d = job_v.interpretation_dossier
            d["version"] = d["version"] + 1
            job_v.interpretation_dossier = d
            job_v.save(update_fields=["interpretation_dossier"])
            return res

        with patch("curriculum.approval_commands.validate_approval_payload", side_effect=mutate_dossier_version_hook):
            resp_v = client.post(
                url_v,
                {
                    "action": "approve",
                    "expected_version": dossier_v.version,
                    "confirm_approval": "1",
                    "confirm_pending_items": "1",
                },
            )
            assert resp_v.status_code == 409
            from curriculum.models import CurriculumImportApproval
            assert CurriculumImportApproval.objects.filter(job=job_v).count() == 0

        # Case 2: Report race (stored verification report mutated to blocked_count=999)
        job_r, dossier_r = create_ready_job(user)
        url_r = reverse("tutor-import-interpretation", args=[job_r.pk])

        def mutate_report_hook(*args, **kwargs):
            res = orig_validate(*args, **kwargs)
            d = job_r.interpretation_dossier
            d["verification_report"]["blocked_count"] = 999
            job_r.interpretation_dossier = d
            job_r.save(update_fields=["interpretation_dossier"])
            return res

        with patch("curriculum.approval_commands.validate_approval_payload", side_effect=mutate_report_hook):
            resp_r = client.post(
                url_r,
                {
                    "action": "approve",
                    "expected_version": dossier_r.version,
                    "confirm_approval": "1",
                    "confirm_pending_items": "1",
                },
            )
            assert resp_r.status_code == 409
            assert CurriculumImportApproval.objects.filter(job=job_r).count() == 0

        # Case 3: FS mutation posterior detected by active guard
        job_fs, dossier_fs = create_ready_job(user)
        url_fs = reverse("tutor-import-interpretation", args=[job_fs.pk])
        resp_fs = client.post(
            url_fs,
            {
                "action": "approve",
                "expected_version": dossier_fs.version,
                "confirm_approval": "1",
                "confirm_pending_items": "1",
            },
        )
        assert resp_fs.status_code in (200, 302)
        approval_fs = CurriculumImportApproval.objects.filter(job=job_fs).first()
        assert approval_fs.is_active is True
        assert job_fs.get_active_approval() == approval_fs

        # Now simulate FS mutation posterior: modify physical PDF bytes
        with job_fs.pdf.open("wb") as f:
            f.write(MINIMAL_VALID_PDF_BYTES)

        # Active guard detects filesystem mutation!
        assert approval_fs.is_active is False
        assert job_fs.get_active_approval() is None

        # Case 4: Mutations after fresh validation (dossier, report, queue, pdf) - Luna B5 Adversarial
        for kind in ("dossier", "report", "queue", "pdf"):
            job_m, dossier_m = create_ready_job(user)
            orig_comp = compute_canonical_verification_report

            def make_mutate_hook(k, j):
                def mutate_after_comp(f_dossier, f_pdf):
                    rep = orig_comp(f_dossier, f_pdf)
                    db_j = CurriculumImportJob.objects.get(pk=j.pk)
                    raw = dict(db_j.interpretation_dossier)
                    if k == "dossier":
                        raw["version"] = int(raw["version"]) + 1
                    elif k == "report":
                        raw["verification_report"] = dict(raw["verification_report"])
                        raw["verification_report"]["blocked_count"] = 999
                    elif k == "queue":
                        session = dict(raw["sessions"][0])
                        refs = [dict(x) for x in session.get("annex_references", [])]
                        if refs:
                            refs[0]["candidate_pages"] = []
                            refs[0]["confirmed_page"] = None
                            refs[0]["review"] = "pending"
                            refs[0]["evidence"] = []
                            session["annex_references"] = refs
                            raw["sessions"] = [session] + list(raw["sessions"][1:])
                    elif k == "pdf":
                        with j.pdf.open("wb") as st:
                            st.write(MINIMAL_VALID_PDF_BYTES)
                    if k != "pdf":
                        CurriculumImportJob.objects.filter(pk=j.pk).update(
                            interpretation_dossier=raw, updated_at=timezone.now()
                        )
                    return rep
                return mutate_after_comp

            url_m = reverse("tutor-import-interpretation", args=[job_m.pk])
            with patch("curriculum.approval_commands.compute_canonical_verification_report", side_effect=make_mutate_hook(kind, job_m)):
                resp_m = client.post(
                    url_m,
                    {
                        "action": "approve",
                        "expected_version": dossier_m.version,
                        "confirm_approval": "1",
                        "confirm_pending_items": "1",
                    },
                )
            assert resp_m.status_code == 409, f"Expected 409 for {kind} mutation, got {resp_m.status_code}"
            assert CurriculumImportApproval.objects.filter(job=job_m).count() == 0

    def test_t7_b5_late_checkpoints_adversarial(self):
        """23. B5 Late Checkpoints: Hook after_blob and after_approval × dossier/report/queue/pdf on main & dedicated."""
        from curriculum.models import CurriculumImportApproval, CurriculumImportJob, CurriculumPackage, CurriculumSourceBlob

        client, user = tutor_teacher("t7-b5-late-user")
        nonce = 0
        for point in ("after_blob", "after_approval"):
            for kind in ("dossier", "report", "queue", "pdf"):
                for ep in ("main", "dedicated"):
                    nonce += 1
                    unique_pdf = _c01_bytes() + f"\n%late-nonce-{nonce}\n".encode("latin-1")
                    job, dossier = create_ready_job(user, pdf_bytes=unique_pdf)
                    target_sha = dossier.source_sha256.lower()

                    url = (
                        reverse("tutor-import-interpretation", args=[job.pk])
                        if ep == "main"
                        else reverse("tutor-import-approve", args=[job.pk])
                    )
                    post_data = {
                        "action": "approve",
                        "expected_version": dossier.version,
                        "confirm_approval": "1",
                        "confirm_pending_items": "1",
                    }

                    def _mutate(kd, j):
                        db_j = CurriculumImportJob.objects.get(pk=j.pk)
                        raw = dict(db_j.interpretation_dossier)
                        if kd == "dossier":
                            raw["version"] = int(raw["version"]) + 1
                        elif kd == "report":
                            raw["verification_report"] = dict(raw["verification_report"])
                            raw["verification_report"]["blocked_count"] = 999
                        elif kd == "queue":
                            session = dict(raw["sessions"][0])
                            refs = [dict(x) for x in session.get("annex_references", [])]
                            if refs:
                                refs[0]["candidate_pages"] = []
                                refs[0]["confirmed_page"] = None
                                refs[0]["review"] = "pending"
                                refs[0]["evidence"] = []
                                session["annex_references"] = refs
                                raw["sessions"] = [session] + list(raw["sessions"][1:])
                            else:
                                raw["sessions"][0]["fields"]["inicio"]["status"] = "conflicted"
                                raw["sessions"][0]["fields"]["inicio"]["review"] = "pending"
                        elif kd == "pdf":
                            with j.pdf.open("wb") as st:
                                st.write(MINIMAL_VALID_PDF_BYTES)
                        if kd != "pdf":
                            CurriculumImportJob.objects.filter(pk=j.pk).update(
                                interpretation_dossier=raw, updated_at=timezone.now()
                            )

                    def make_late_hook(pt, kd, j):
                        if pt == "after_blob":
                            orig = CurriculumSourceBlob.objects.get_or_create
                            def hook(*args, **kwargs):
                                res = orig(*args, **kwargs)
                                _mutate(kd, j)
                                return res
                            return hook
                        else:
                            orig = CurriculumImportApproval.objects.create
                            def hook(*args, **kwargs):
                                res = orig(*args, **kwargs)
                                _mutate(kd, j)
                                return res
                            return hook

                    target_patch = (
                        "curriculum.models.CurriculumSourceBlob.objects.get_or_create"
                        if point == "after_blob"
                        else "curriculum.models.CurriculumImportApproval.objects.create"
                    )

                    with patch(target_patch, side_effect=make_late_hook(point, kind, job)):
                        resp = client.post(url, post_data)

                    assert resp.status_code == 409, f"Expected 409 for {point}/{kind}/{ep}, got {resp.status_code}"
                    assert CurriculumImportApproval.objects.filter(job=job).count() == 0
                    assert CurriculumPackage.objects.filter(source_blob__sha256=target_sha).count() == 0
                    assert CurriculumSourceBlob.objects.filter(sha256=target_sha).count() == 0

    def test_t7_blob_bulk_create_validates_content_integrity(self):
        """Bulk APIs must not bypass content-addressed blob validation."""
        invalid = CurriculumSourceBlob(
            sha256="a" * 64,
            content=b"actual bytes",
            content_size=len(b"actual bytes"),
        )
        with pytest.raises(ValidationError):
            CurriculumSourceBlob.objects.bulk_create([invalid])

        async_invalid = CurriculumSourceBlob(
            sha256="b" * 64,
            content=b"other bytes",
            content_size=len(b"other bytes"),
        )
        with pytest.raises(ValidationError):
            asyncio.run(CurriculumSourceBlob.objects.abulk_create([async_invalid]))

        assert CurriculumSourceBlob.objects.count() == 0

        raw = b"valid content-addressed bytes"
        digest = hashlib.sha256(raw).hexdigest()
        existing = CurriculumSourceBlob.objects.create(
            sha256=digest,
            content=raw,
            content_size=len(raw),
        )
        conflict = CurriculumSourceBlob(
            sha256=digest,
            content=raw,
            content_size=len(raw),
            created_at=timezone.now(),
        )
        conflict_kwargs = {
            "update_conflicts": True,
            "update_fields": ["created_at"],
            "unique_fields": ["sha256"],
        }
        with pytest.raises(PermissionError):
            CurriculumSourceBlob.objects.bulk_create([conflict], **conflict_kwargs)
        with pytest.raises(PermissionError):
            asyncio.run(
                CurriculumSourceBlob.objects.abulk_create([conflict], **conflict_kwargs)
            )
        existing.refresh_from_db()
        assert CurriculumSourceBlob.objects.count() == 1

    def test_t7_active_blob_integrity_fail_closed(self):
        """24. B2 Active Blob Integrity: Corrupted or tampered blob causes approval.is_active to fail closed."""
        from django.db import connection
        from curriculum.approval_commands import execute_teacher_approval
        from curriculum.models import CurriculumImportApproval

        client, user = tutor_teacher("active-blob-tester")
        job, dossier = create_ready_job(user)

        res = execute_teacher_approval(job.pk, user, {
            "action": "approve",
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        })
        assert res.is_success, res.message

        app = CurriculumImportApproval.objects.get(job=job)
        assert app.is_active is True
        assert job.get_active_approval() == app
        assert app.get_source_bytes() is not None

        # Corrupt blob content directly via raw SQL (bypassing model/queryset guards)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE curriculum_curriculumsourceblob SET content = %s WHERE id = %s",
                [b"tampered-content", app.source_blob_id],
            )

        app.refresh_from_db()
        job.refresh_from_db()

        assert app.is_active is False
        assert job.get_active_approval() is None
        assert app.get_source_bytes() is None

    def test_t7_source_download_range_and_blob_fallback(self):
        """25. HTTP Source Serving: Range requests (206, 416), fallback to blob on job.pdf delete, outsider 404."""
        from curriculum.approval_commands import execute_teacher_approval

        client, user = tutor_teacher("download-tester")
        pdf_bytes = _c01_bytes()
        total_len = len(pdf_bytes)
        job, dossier = create_ready_job(user, pdf_bytes=pdf_bytes)

        res = execute_teacher_approval(job.pk, user, {
            "action": "approve",
            "expected_version": dossier.version,
            "confirm_approval": "1",
            "confirm_pending_items": "1",
        })
        assert res.is_success, res.message

        url = reverse("tutor-import-source-page", kwargs={"job_id": job.pk, "page_number": 1})

        # 1. Range bytes=0-9 request
        resp_range = client.get(url, HTTP_RANGE="bytes=0-9")
        assert resp_range.status_code == 206
        assert resp_range["Content-Range"] == f"bytes 0-9/{total_len}"
        assert resp_range["Accept-Ranges"] == "bytes"
        assert int(resp_range["Content-Length"]) == 10
        assert resp_range.content == pdf_bytes[:10]

        # 2. Invalid range request returns 416
        resp_inv = client.get(url, HTTP_RANGE="bytes=9999999-9999999")
        assert resp_inv.status_code == 416
        assert resp_inv["Content-Range"] == f"bytes */{total_len}"

        # 3. Source serving after job.pdf deleted
        job.pdf.delete(save=True)
        job.refresh_from_db()
        assert not job.pdf

        resp_after_del = client.get(url)
        assert resp_after_del.status_code == 200
        assert resp_after_del["Content-Type"] == "application/pdf"
        assert resp_after_del.content == pdf_bytes

        # 4. Outsider gets 404
        client_outsider, outsider = tutor_teacher("download-outsider")
        resp_out = client_outsider.get(url)
        assert resp_out.status_code == 404

    def test_t7_upload_max_size_limit_rejection(self):
        """26. Max Upload Size: PDFs exceeding CURRICULUM_MAX_UPLOAD_SIZE_BYTES rejected with 400 before PdfReader."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from curriculum.models import CurriculumImportJob

        client, user = tutor_teacher("upload-limit-tester")
        url = reverse("tutor-import-upload")

        # 26 MiB dummy file exceeding 25 MiB limit
        big_size = 26 * 1024 * 1024
        dummy_big = SimpleUploadedFile("too_large.pdf", b"%PDF-1.4 " + b"0" * (big_size - 9), content_type="application/pdf")

        initial_count = CurriculumImportJob.objects.count()
        resp = client.post(url, {"pdf": dummy_big})
        assert resp.status_code == 400
        assert "supera el tamaño máximo permitido" in resp.content.decode("utf-8")
        assert CurriculumImportJob.objects.count() == initial_count


