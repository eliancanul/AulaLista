"""Tests for Task 5: Deterministic mechanical verification with evidence before teacher review.

Requirements (UX5):
1. Pure verification module (curriculum/verification.py):
   - normalize_text_for_evidence_check: unifies whitespace/newlines, case-folds, normalizes
     diacritics, strips punctuation variations, strictly rejects token-bag / scrambled / invented matches,
     never allows empty matches.
   - verify_curriculum_dossier: pure function emitting a versioned JSON report tied to
     dossier.version and source_sha256.
   - Covers all scopes: dossier identity, general fields, session fields, annex references,
     and queue items.
   - Categorization:
     - blocked (hard failure): schema/identity mismatch, wrong SHA, pages out of bounds,
       evidence SHA mismatch, cited excerpt not found on physical page (physical contradiction).
     - needs_teacher_review: empty/missing values, ambiguous/conflicting fields, proposed/inferred
       fields without sufficient evidence, unconfirmed annexes, scanned pages without text.
     - checked: physical evidence matched on physical page under strict normalization.
2. Lifecycle & Command Seams:
   - finish_worker_success: runs verification. Transitions to READY only when blocked_count == 0
     and attaches verification_report. If blocked_count > 0, fails closed to FAILED without
     clobbering history or violating CAS invariants.
   - save_interpretation_dossier_command: re-verifies and updates verification_report on version bump.
   - Review Guard (tutor_import_interpretation): requires valid ready dossier WITH valid, fresh,
     unblocked verification_report matching dossier.version and source_sha256.
     Redirects to wait on GET, returns 409 on POST if report is missing, stale, or blocked.
3. Review UI:
   - Renders teacher-facing banner "Comprobación automática completada".
   - Shows counts for checked, needs review, and 0 blocked.
   - Provides safe links to physical pages (#page=N) via owner-scoped tutor-import-source-page.
   - NEVER claims "validado por SEP" nor "correcto pedagógicamente".
4. Regressions:
   - Preserves T1-T4, wait, V0, T94 invariants.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import uuid
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from curriculum.interpretation_commands import (
    claim_interpretation_worker,
    finish_worker_success,
    save_interpretation_dossier_command,
)
from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import (
    AnnexReference,
    CurriculumSourceInterpreter,
    ImportDossier,
    InterpretedField,
    ORIGIN_EXTRACTED,
    ORIGIN_PROPOSED,
    REVIEW_CONFIRMED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    SessionPlan,
    SourceReference,
    resolve,
)
from curriculum.verification import (
    STATUS_BLOCKED,
    STATUS_CHECKED,
    STATUS_NEEDS_TEACHER_REVIEW,
    VerificationItem,
    VerificationReport,
    _read_pdf_source,
    compute_canonical_verification_report,
    normalize_text_for_evidence_check,
    validate_canonical_verification_report,
    verify_curriculum_dossier,
)
from helpers import tutor_client

pytestmark = pytest.mark.django_db(transaction=True)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
if not C01_PATH.exists():
    C01_PATH = Path("media/curriculum_imports/prueba-semana-01.pdf")


def tutor_teacher(username=None):
    from django.contrib.auth import get_user_model
    client = tutor_client(username)
    user = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    return client, user


def _c01_bytes() -> bytes:
    assert C01_PATH.exists(), f"Fixture C01 missing at {C01_PATH}"
    return C01_PATH.read_bytes()


def _c01_sha256() -> str:
    return hashlib.sha256(_c01_bytes()).hexdigest()


def _c01_job(user) -> CurriculumImportJob:
    b = _c01_bytes()
    sha = hashlib.sha256(b).hexdigest()
    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("prueba-semana-01.pdf", b, content_type="application/pdf"),
        page_count=5,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
    )
    return job


# ==============================================================================
# Group 1: Normalization Tests
# ==============================================================================


class TestNormalization:
    """Strict unit tests for normalize_text_for_evidence_check."""

    def test_whitespace_and_newlines_collapsed_and_stripped(self):
        raw = "  Sesión   1:\n\nInicio de la\t\tclase  \r\ncon   materiales.  "
        expected = "sesion 1: inicio de la clase con materiales."
        assert normalize_text_for_evidence_check(raw) == expected

    def test_non_breaking_spaces_and_unicode_spaces(self):
        raw = "Vocales\u00a0y\u2009consonantes\u2003en\u2002el\u3000aula"
        expected = "vocales y consonantes en el aula"
        assert normalize_text_for_evidence_check(raw) == expected

    def test_case_folding_and_diacritics_normalization(self):
        raw_upper_accents = "SESIÓN DE EDUCACIÓN ARTÍSTICA Y MATEMÁTICAS"
        raw_decomposed = "sesio\u0301n de educacio\u0301n arti\u0301stica y matema\u0301ticas"
        raw_plain = "sesion de educacion artistica y matematicas"

        norm_upper = normalize_text_for_evidence_check(raw_upper_accents)
        norm_decomposed = normalize_text_for_evidence_check(raw_decomposed)
        norm_plain = normalize_text_for_evidence_check(raw_plain)

        assert norm_upper == norm_plain
        assert norm_decomposed == norm_plain
        assert norm_upper == "sesion de educacion artistica y matematicas"

    def test_punctuation_and_quote_unification(self):
        raw = '“Inicio”: ‘Presentar’ — las «letras» – mayúsculas'
        normalized = normalize_text_for_evidence_check(raw)
        assert '"inicio"' in normalized
        assert "'presentar'" in normalized
        assert "-" in normalized

    def test_rejects_token_bag_scrambled_words(self):
        """Token-bag permutation must NOT match: sequence must be strictly contiguous."""
        page_text = "El alumno debe correr al patio y no gritar en el aula."
        norm_page = normalize_text_for_evidence_check(page_text)

        # Scrambled words from the page that reverse or distort meaning
        distorted_excerpt = "El alumno no debe correr"
        norm_distorted = normalize_text_for_evidence_check(distorted_excerpt)

        # Contiguous check must fail
        assert norm_distorted not in norm_page

    def test_rejects_empty_and_whitespace_matches(self):
        assert normalize_text_for_evidence_check("") == ""
        assert normalize_text_for_evidence_check("   ") == ""
        assert normalize_text_for_evidence_check("\n\t\r") == ""
        assert normalize_text_for_evidence_check(None) == ""


# ==============================================================================
# Group 2: Mechanical Verification on Real PDF (C01)
# ==============================================================================


class TestMechanicalVerification:
    """Tests for pure function verify_curriculum_dossier against physical PDF."""

    @pytest.fixture
    def c01_prepared(self):
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        return dossier, pdf_bytes

    def test_verify_valid_c01_dossier_passes_with_zero_blocks(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        report = verify_curriculum_dossier(dossier, pdf_bytes)

        assert isinstance(report, VerificationReport)
        assert report.is_valid is True
        assert report.blocked_count == 0
        assert (report.checked_count, report.needs_review_count, report.blocked_count, report.total_items) == (21, 30, 0, 51)
        assert report.dossier_version == dossier.version
        assert report.source_sha256 == dossier.source_sha256
        assert report.schema_version == 1

        # Verify items cover all scopes
        scopes = {item["scope"] for item in report.items}
        assert "dossier" in scopes
        assert "general" in scopes
        assert "session" in scopes
        assert "annex" in scopes

    def test_hard_block_on_dossier_sha_mismatch(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        dossier.source_sha256 = "0" * 64

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        assert report.is_valid is False
        assert report.blocked_count >= 1

        sha_items = [i for i in report.items if i["target"] == "source_sha256"]
        assert len(sha_items) == 1
        assert sha_items[0]["status"] == "blocked"
        assert "SHA-256" in sha_items[0]["message"]

    def test_hard_block_on_page_out_of_bounds(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        # Add an evidence pointing to page 99 (PDF has only 5 pages)
        dossier.general_fields["proyecto"].evidence.append(
            SourceReference(
                document_sha256=dossier.source_sha256,
                page_number=99,
                excerpt="Proyecto",
            )
        )

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        assert report.is_valid is False
        assert report.blocked_count >= 1

        bad_page_items = [
            i for i in report.items
            if i["status"] == "blocked" and i.get("page_number") == 99
        ]
        assert len(bad_page_items) >= 1
        assert "fuera de rango" in bad_page_items[0]["message"].lower()

    def test_hard_block_on_evidence_sha_mismatch(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        # Corrupt the document_sha256 of an evidence reference
        dossier.general_fields["proyecto"].evidence[0].document_sha256 = "a" * 64

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        assert report.is_valid is False
        assert report.blocked_count >= 1

        blocked = [i for i in report.items if i["status"] == "blocked"]
        assert any("SHA" in b["message"] for b in blocked)

    def test_hard_block_on_physical_contradiction_missing_cited_text(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        # Field cites text that simply does not exist on page 1
        dossier.general_fields["proyecto"].evidence[0].excerpt = (
            "Este texto jamás fue escrito en la planeación y contradice la fuente física"
        )

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        assert report.is_valid is False
        assert report.blocked_count >= 1

        contradictions = [
            i for i in report.items
            if i["status"] == "blocked" and "no se encuentra en la página" in i["message"]
        ]
        assert len(contradictions) >= 1

    def test_hard_block_on_page_count_mismatch(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        dossier.page_count = 100  # Real PDF has 5 pages

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        assert report.is_valid is False
        assert report.blocked_count >= 1
        assert any("Total de páginas" in i["message"] for i in report.items if i["status"] == "blocked")

    def test_needs_review_on_unconfirmed_annex(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        report = verify_curriculum_dossier(dossier, pdf_bytes)

        # In C01, annexes are extracted but not yet confirmed by teacher
        annex_review_items = [
            i for i in report.items
            if i["scope"] == "annex" and i["status"] == "needs_teacher_review"
        ]
        assert len(annex_review_items) >= 1
        assert any("sin confirmar" in i["message"].lower() for i in annex_review_items)

    def test_needs_review_on_empty_or_ambiguous_fields(self, c01_prepared):
        dossier, pdf_bytes = c01_prepared
        # Introduce an empty and an ambiguous field
        dossier.general_fields["situacion_problema"] = InterpretedField(
            name="situacion_problema",
            value="",
            status=STATUS_MISSING,
        )
        dossier.general_fields["metodologia"].status = STATUS_AMBIGUOUS

        report = verify_curriculum_dossier(dossier, pdf_bytes)
        # Does NOT block readiness, but marks as needs review
        assert report.blocked_count == 0
        missing_item = [i for i in report.items if i["target"] == "general.situacion_problema"]
        assert len(missing_item) == 1
        assert missing_item[0]["status"] == "needs_teacher_review"

        ambig_item = [
            i for i in report.items
            if i["target"] == "general.metodologia" and i["status"] == "needs_teacher_review"
        ]
        assert len(ambig_item) == 1
        assert ambig_item[0]["status"] == "needs_teacher_review"


# ==============================================================================
# Group 3: Lifecycle and Command Seam Integration
# ==============================================================================


class TestLifecycleSeams:
    """Tests for integration of verification with CAS transitions and command seams."""

    def test_finish_worker_success_persists_verification_report_and_sets_ready(self):
        client, user = tutor_teacher("t5-worker-user")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)

        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        rows = finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        assert rows == 1

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert job.has_valid_ready_dossier() is True

        persisted_dossier = job.interpretation_dossier
        assert "verification_report" in persisted_dossier
        report = persisted_dossier["verification_report"]
        assert report["is_valid"] is True
        assert report["blocked_count"] == 0
        assert report["checked_count"] > 0
        assert report["dossier_version"] == 1
        assert report["source_sha256"] == _c01_sha256()

    def test_finish_worker_success_fails_closed_when_dossier_has_hard_blocks(self):
        client, user = tutor_teacher("t5-worker-fail")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)

        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        # Inject physical contradiction into dossier
        dossier.general_fields["proyecto"].evidence[0].excerpt = "Texto inexistente y contradictorio"

        rows = finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        assert rows == 1

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.interpretation_claim_token is None
        assert "inconsistencias" in job.interpretation_error_message.lower() or "integridad" in job.interpretation_error_message.lower() or "verificación" in job.interpretation_error_message.lower()
        # Job must NOT be considered ready
        assert job.has_valid_ready_dossier() is False

    def test_save_interpretation_dossier_command_updates_report_on_version_bump(self):
        client, user = tutor_teacher("t5-save-bump")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        job.refresh_from_db()
        initial_version = job.interpretation_dossier["version"]
        assert initial_version == 1

        # Teacher makes an editorial correction: bump version to 2
        dossier_obj = job.get_interpretation_dossier()
        dossier_obj.version = 2
        dossier_obj.general_fields["proyecto"].value = "Nuevo nombre editado por el docente"
        # Save via command seam
        target_state = save_interpretation_dossier_command(job, dossier=dossier_obj)
        assert target_state == CurriculumImportJob.INTERPRETATION_STATE_READY

        job.refresh_from_db()
        saved_dossier = job.interpretation_dossier
        assert saved_dossier["version"] == 2
        report = saved_dossier["verification_report"]
        assert report["dossier_version"] == 2
        assert report["blocked_count"] == 0

    def test_review_guard_redirects_to_wait_when_report_is_stale_or_tampered(self):
        client, user = tutor_teacher("t5-guard-stale")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        # Tamper: bump dossier.version in DB without updating verification_report
        job.refresh_from_db()
        dossier_dict = job.interpretation_dossier
        dossier_dict["version"] = 99  # Stale report
        CurriculumImportJob.objects.filter(pk=job.pk).update(interpretation_dossier=dossier_dict)

        # GET tutor-import-interpretation must redirect to wait
        review_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.get(review_url)
        assert resp.status_code == 302
        assert reverse("tutor-import-wait", args=[job.pk]) in resp["Location"]

    def test_review_guard_post_returns_409_when_report_has_blocks(self):
        client, user = tutor_teacher("t5-guard-block-post")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        # Tamper: set blocked_count = 1 in verification report
        job.refresh_from_db()
        dossier_dict = job.interpretation_dossier
        dossier_dict["verification_report"]["blocked_count"] = 1
        dossier_dict["verification_report"]["is_valid"] = False
        CurriculumImportJob.objects.filter(pk=job.pk).update(interpretation_dossier=dossier_dict)

        # POST editorial action must be rejected with 409
        review_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.post(review_url, {
            "action": "save_field",
            "field": "proyecto",
            "value": "Nuevo proyecto",
            "expected_version": 1,
        })
        assert resp.status_code == 409
        assert "integridad" in resp.content.decode("utf-8").lower() or "bloqueada" in resp.content.decode("utf-8").lower()


# ==============================================================================
# Group 4: Review UI Banner Tests
# ==============================================================================


class TestReviewUIBanner:
    """Tests for teacher-facing automatic verification banner in review template."""

    def test_review_view_renders_automatic_verification_banner(self):
        client, user = tutor_teacher("t5-ui-banner")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        review_url = reverse("tutor-import-interpretation", args=[job.pk])
        resp = client.get(review_url)
        assert resp.status_code == 200

        html = resp.content.decode("utf-8")
        # Exact teacher-facing copy required by spec
        assert "Comprobación automática completada" in html
        assert "validado por SEP" not in html
        assert "correcto pedagógicamente" not in html

        soup = BeautifulSoup(html, "html.parser")
        banner = soup.select_one(".verification-banner") or soup.select_one("#verification-report-card")
        assert banner is not None, "Verification banner element missing in template"

        # Checked count against physical pages
        banner_text = banner.get_text()
        assert "cotejados contra páginas físicas" in banner_text or "verificados contra páginas" in banner_text or "cotejados" in banner_text
        assert "requieren revisión" in banner_text

        # Verify page links exist within the review view
        page_links = banner.select(f"a[href*='/tutor/imports/{job.pk}/fuente/']")
        assert len(page_links) >= 1, "Expected links to physical pages in verification banner"
        for link in page_links:
            href = link["href"]
            assert f"/tutor/imports/{job.pk}/fuente/" in href
            assert "#page=" in href

    def test_physical_page_links_are_owner_scoped(self):
        owner_client, owner_user = tutor_teacher("t5-owner-docente")
        other_client, other_user = tutor_teacher("t5-other-docente")

        job = _c01_job(owner_user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        page_url = reverse("tutor-import-source-page", args=[job.pk, 1])

        # Owner can view physical page
        resp_owner = owner_client.get(page_url)
        assert resp_owner.status_code == 200
        assert resp_owner["Content-Type"] == "application/pdf"

        # Foreign teacher cannot view (404 owner scoped)
        resp_other = other_client.get(page_url)
        assert resp_other.status_code == 404


# ==============================================================================
# Group 5: Luna B1–B5 Specific Probes & Regressions
# ==============================================================================


class TestLunaB1ToB5Corrections:
    """Rigorous probes covering all points identified in Luna review (B1-B5)."""

    def test_b1_missing_report_rejects_ready_integrity_and_model(self):
        client, user = tutor_teacher("t5-luna-b1-missing")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        job.refresh_from_db()
        dossier_dict = copy.deepcopy(job.interpretation_dossier)
        # Strip verification_report completely
        dossier_dict.pop("verification_report", None)
        CurriculumImportJob.objects.filter(pk=job.pk).update(interpretation_dossier=dossier_dict)

        from curriculum.interpretation_commands import validate_ready_dossier_integrity
        from curriculum.verification import validate_canonical_verification_report

        # 1. validate_ready_dossier_integrity MUST be False
        assert validate_ready_dossier_integrity(job, dossier_dict) is False

        # 2. validate_canonical_verification_report MUST be False on missing report
        assert validate_canonical_verification_report(dossier_dict, job.pdf, None) is False

        # 3. Model has_valid_ready_dossier MUST be False
        job.refresh_from_db()
        assert job.has_valid_ready_dossier() is False

        # 4. GET review redirects to wait
        resp_get = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert resp_get.status_code == 302
        assert reverse("tutor-import-wait", args=[job.pk]) in resp_get["Location"]

        # 5. POST review fails closed with 409
        resp_post = client.post(reverse("tutor-import-interpretation", args=[job.pk]), {
            "action": "save_field",
            "field": "proyecto",
            "value": "Nuevo valor",
            "expected_version": 1,
        })
        assert resp_post.status_code == 409

    def test_b1_forged_counts_and_items_rejected_by_canonical_validator(self):
        client, user = tutor_teacher("t5-luna-b1-forged")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        job.refresh_from_db()
        genuine_report = copy.deepcopy(job.interpretation_dossier["verification_report"])
        from curriculum.verification import validate_canonical_verification_report

        # Probe A: forged checked_count
        forged_checked = copy.deepcopy(genuine_report)
        forged_checked["checked_count"] += 1
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_checked) is False

        # Probe B: is_valid=False
        forged_valid = copy.deepcopy(genuine_report)
        forged_valid["is_valid"] = False
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_valid) is False

        # Probe C: extra blocked item with blocked_count=0
        forged_extra = copy.deepcopy(genuine_report)
        extra_item = copy.deepcopy(genuine_report["items"][0])
        extra_item["item_id"] = "extra_forged"
        extra_item["status"] = "blocked"
        forged_extra["items"].append(extra_item)
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_extra) is False

        # Probe D: stale dossier_version
        forged_version = copy.deepcopy(genuine_report)
        forged_version["dossier_version"] = 99
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_version) is False

        # Probe E: stale source_sha256
        forged_sha = copy.deepcopy(genuine_report)
        forged_sha["source_sha256"] = "f" * 64
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_sha) is False

    def test_b2_traversal_covers_f7_queue_items_without_collisions(self):
        client, user = tutor_teacher("t5-luna-b2-f7")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)

        report = verify_curriculum_dossier(dossier, job.pdf)
        assert report.is_valid is True

        # F7 Queue items must be exactly 22 on C01
        queue_items = [i for i in report.items if i["scope"] == "queue"]
        assert len(queue_items) == 22, f"Expected 22 F7 queue items on C01, got {len(queue_items)}"

        # Every item must have unique item_id, path, and target (zero collisions)
        item_ids = [i["item_id"] for i in report.items]
        paths = [i["path"] for i in report.items]
        targets = [i["target"] for i in report.items]

        assert len(item_ids) == len(set(item_ids)), f"Collision in item_ids: {[x for x in item_ids if item_ids.count(x) > 1]}"
        assert len(paths) == len(set(paths)), f"Collision in paths: {[x for x in paths if paths.count(x) > 1]}"
        assert len(targets) == len(set(targets)), f"Collision in targets: {[x for x in targets if targets.count(x) > 1]}"

    def test_b2_structurally_empty_and_malformed_structures_block(self):
        client, user = tutor_teacher("t5-luna-b2-malformed")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)

        # 1. Structurally empty dossier (empty general_fields and sessions)
        empty_dossier = copy.deepcopy(dossier.to_dict())
        empty_dossier["general_fields"] = {}
        empty_dossier["sessions"] = []
        empty_dossier["annex_candidates"] = []
        rep_empty = verify_curriculum_dossier(empty_dossier, job.pdf)
        assert rep_empty.is_valid is False
        assert rep_empty.blocked_count >= 1
        assert any("vacío" in i["message"].lower() for i in rep_empty.items if i["status"] == "blocked")

        # 2. Malformed general_fields list instead of map
        mal_dossier = copy.deepcopy(dossier.to_dict())
        mal_dossier["general_fields"] = ["not-a-map"]
        rep_mal = verify_curriculum_dossier(mal_dossier, job.pdf)
        assert rep_mal.is_valid is False
        assert rep_mal.blocked_count >= 1

        # 3. Candidate without page
        cand_dossier = copy.deepcopy(dossier.to_dict())
        cand_dossier["annex_candidates"] = [{"label": "forged-without-page"}]
        rep_cand = verify_curriculum_dossier(cand_dossier, job.pdf)
        assert rep_cand.is_valid is False
        assert rep_cand.blocked_count >= 1

        # 4. Missing canonical general field emits needs_teacher_review (heterogeneity), does not block
        dossier_missing = copy.deepcopy(dossier.to_dict())
        dossier_missing["general_fields"].pop("finalidad", None)
        rep_missing = verify_curriculum_dossier(dossier_missing, job.pdf)
        missing_items = [i for i in rep_missing.items if i["target"] == "general.finalidad"]
        assert len(missing_items) == 1
        assert missing_items[0]["status"] == "needs_teacher_review"
        assert rep_missing.is_valid is True
        assert rep_missing.blocked_count == 0

    def test_b3_exact_classification_rules(self):
        client, user = tutor_teacher("t5-luna-b3-class")
        job = _c01_job(user)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)

        # Rule 1: Conflicting status emits blocked and NO second checked item
        d_conflict = copy.deepcopy(dossier)
        d_conflict.general_fields["proyecto"].status = "conflicting"
        rep_conflict = verify_curriculum_dossier(d_conflict, job.pdf)
        assert rep_conflict.is_valid is False
        p_items = [i for i in rep_conflict.items if i["target"].startswith("general.proyecto")]
        assert any(i["status"] == "blocked" for i in p_items)
        assert not any(i["status"] == "checked" for i in p_items)

        # Rule 2: Proposed/Inferred produces EXACTLY ONE item teacher_review per field/target
        d_proposed = copy.deepcopy(dossier)
        d_proposed.general_fields["proyecto"].origin = "proposed"
        d_proposed.general_fields["proyecto"].status = "supported"
        rep_prop = verify_curriculum_dossier(d_proposed, job.pdf)
        p_prop_items = [i for i in rep_prop.items if i["target"].startswith("general.proyecto")]
        assert len(p_prop_items) == 1
        assert p_prop_items[0]["status"] == "needs_teacher_review"
        assert p_prop_items[0]["item_id"] == "gen_proyecto_value"
        citations = p_prop_items[0]["details"].get("evidence_citations", [])
        assert len(citations) >= 1
        assert any(c.get("matched") is True for c in citations)

        # Rule 3: Empty excerpt on supported evidence emits blocked
        d_empty_ex = copy.deepcopy(dossier)
        d_empty_ex.general_fields["proyecto"].evidence[0].excerpt = "   "
        rep_empty = verify_curriculum_dossier(d_empty_ex, job.pdf)
        assert rep_empty.is_valid is False
        assert any(i["status"] == "blocked" and "vacío" in i["message"].lower() for i in rep_empty.items)

        # Rule 4: Annex candidates within page range are NEVER checked, always review
        cand_items = [i for i in rep_prop.items if i["scope"] == "annex" and "cand" in i["item_id"]]
        for ci in cand_items:
            assert ci["status"] == "needs_teacher_review"

        # Rule 5: Confirmed annex without coherent evidence is BLOCKED (not review!)
        d_conf = copy.deepcopy(dossier)
        annex_ref = d_conf.sessions[0].annex_references[0]
        annex_ref.review = "confirmed"
        annex_ref.confirmed_page = 3
        # Clear evidence
        annex_ref.evidence = []
        rep_conf = verify_curriculum_dossier(d_conf, job.pdf)
        conf_items = [i for i in rep_conf.items if i["item_id"] == f"annex_{d_conf.sessions[0].session_id}_{annex_ref.reference_id}_conf"]
        assert len(conf_items) == 1
        assert conf_items[0]["status"] == "blocked"

        # Rule 5a: Confirmed annex with teacher_selected_source_page and empty excerpt is strictly BLOCKED
        d_empty_ex = copy.deepcopy(dossier)
        annex_ref_empty = d_empty_ex.sessions[0].annex_references[0]
        annex_ref_empty.review = "confirmed"
        annex_ref_empty.confirmed_page = 3
        annex_ref_empty.evidence = [
            SourceReference(
                document_sha256=d_empty_ex.source_sha256,
                page_number=3,
                printed_label="Página 3 asociada manualmente",
                excerpt="",
                role="teacher_selected_source_page",
            )
        ]
        rep_empty_ex = verify_curriculum_dossier(d_empty_ex, job.pdf)
        conf_empty = [i for i in rep_empty_ex.items if i["item_id"] == f"annex_{d_empty_ex.sessions[0].session_id}_{annex_ref_empty.reference_id}_conf"]
        assert len(conf_empty) == 1
        assert conf_empty[0]["status"] == "blocked"
        assert "carece de evidencia física coherente" in conf_empty[0]["message"]

        # Rule 5b: Confirmed annex with contradictory excerpt is BLOCKED
        d_contra = copy.deepcopy(dossier)
        annex_ref_contra = d_contra.sessions[0].annex_references[0]
        annex_ref_contra.review = "confirmed"
        annex_ref_contra.confirmed_page = 3
        annex_ref_contra.evidence = [
            SourceReference(
                document_sha256=d_contra.source_sha256,
                page_number=3,
                printed_label="Lámina",
                excerpt="Texto inventado que no existe en el pdf",
                role="teacher_selected_source_page",
            )
        ]
        rep_contra = verify_curriculum_dossier(d_contra, job.pdf)
        conf_contra = [i for i in rep_contra.items if i["item_id"] == f"annex_{d_contra.sessions[0].session_id}_{annex_ref_contra.reference_id}_conf"]
        assert len(conf_contra) == 1
        assert conf_contra[0]["status"] == "blocked"
        assert "Contradicción física" in conf_contra[0]["message"]

        # Rule 5c: Confirmed annex with matching physical excerpt is CHECKED
        d_ok_annex = copy.deepcopy(dossier)
        annex_ref_ok = d_ok_annex.sessions[0].annex_references[0]
        annex_ref_ok.review = "confirmed"
        annex_ref_ok.confirmed_page = 3
        annex_ref_ok.evidence = [
            SourceReference(
                document_sha256=d_ok_annex.source_sha256,
                page_number=3,
                printed_label="ANEXO # 01",
                excerpt="ANEXO # 01",
                role="teacher_selected_source_page",
            )
        ]
        rep_ok_annex = verify_curriculum_dossier(d_ok_annex, job.pdf)
        conf_ok = [i for i in rep_ok_annex.items if i["item_id"] == f"annex_{d_ok_annex.sessions[0].session_id}_{annex_ref_ok.reference_id}_conf"]
        assert len(conf_ok) == 1
        assert conf_ok[0]["status"] == "checked"

        # Rule 5d: Annex with review='pending' produces needs_teacher_review (never blocked, never checked)
        d_pending_annex = copy.deepcopy(dossier)
        annex_ref_p = d_pending_annex.sessions[0].annex_references[0]
        annex_ref_p.review = "pending"
        annex_ref_p.confirmed_page = 3
        annex_ref_p.evidence = [
            SourceReference(
                document_sha256=d_pending_annex.source_sha256,
                page_number=3,
                printed_label="Página 3 seleccionada sin texto digital",
                excerpt="",
                role="teacher_selected_source_page",
            )
        ]
        rep_p_annex = verify_curriculum_dossier(d_pending_annex, job.pdf)
        conf_p = [i for i in rep_p_annex.items if i["item_id"] == f"annex_{d_pending_annex.sessions[0].session_id}_{annex_ref_p.reference_id}_conf"]
        assert len(conf_p) == 1
        assert conf_p[0]["status"] == "needs_teacher_review"

    def test_b4_pure_get_snapshots_and_save_command_seams(self):
        client, user = tutor_teacher("t5-luna-b4-pure")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        job.refresh_from_db()

        def _row_snapshot():
            return CurriculumImportJob.objects.filter(pk=job.pk).values(
                "page_count", "progress_stage", "progress_finished_at", "updated_at",
                "interpretation_state", "interpretation_dossier",
            ).first()

        # 1. GET tutor-import-source-page is 100% pure read
        snap_before_source = _row_snapshot()
        resp_page = client.get(reverse("tutor-import-source-page", args=[job.pk, 1]))
        assert resp_page.status_code == 200
        snap_after_source = _row_snapshot()
        assert snap_before_source == snap_after_source

        # 2. GET tutor-import-interpretation is 100% pure read
        snap_before_review = _row_snapshot()
        resp_review = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert resp_review.status_code == 200
        snap_after_review = _row_snapshot()
        assert snap_before_review == snap_after_review

        # 3. Editorial no-op in save_interpretation_dossier_command preserves exact bytes
        dossier_obj = job.get_interpretation_dossier()
        snap_before_noop = _row_snapshot()
        state = save_interpretation_dossier_command(job, dossier=dossier_obj)
        assert state == CurriculumImportJob.INTERPRETATION_STATE_READY
        snap_after_noop = _row_snapshot()
        assert snap_before_noop == snap_after_noop

        # 4. Blocked save_interpretation_dossier_command does NOT overwrite valid dossier in DB
        broken_dossier = copy.deepcopy(job.interpretation_dossier)
        broken_dossier["source_sha256"] = "0" * 64
        target_state = save_interpretation_dossier_command(job, dossier=broken_dossier)
        assert target_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        # Dossier in DB must NOT be overwritten by the broken dossier
        assert job.interpretation_dossier["source_sha256"] != "0" * 64
        assert job.interpretation_dossier["source_sha256"] == _c01_sha256()

    def test_b5_banner_copy_derived_from_code_not_persisted_json(self):
        client, user = tutor_teacher("t5-luna-b5-banner")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        # GET review renders code-constructed copy and derived counts
        resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")

        # Verify exact teacher-facing copy required
        assert "Comprobación automática completada" in html
        assert "validado por SEP" not in html
        assert "correcto pedagógicamente" not in html
        assert "cotejados contra páginas físicas" in html
        assert "requieren revisión humana" in html
        assert "0 bloqueos detectados" in html

    def test_b1_forged_verified_items_and_extra_keys_rejected(self):
        client, user = tutor_teacher("t5-luna-b1-forged-probe")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        job.refresh_from_db()
        genuine_report = job.interpretation_dossier["verification_report"]

        # Probe A: Injected extra key 'summary_message' with script
        forged_summary = copy.deepcopy(genuine_report)
        forged_summary["summary_message"] = "<script>alert('pwn')</script>"
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_summary) is False

        # Probe B: Injected extra key 'verified_items' alias with forged external link
        forged_items = copy.deepcopy(genuine_report)
        forged_items["verified_items"] = [{"page_number": 1, "link": "http://evil.com"}]
        assert validate_canonical_verification_report(job.interpretation_dossier, job.pdf, forged_items) is False

        # Probe C: Persisting forged report in DB fails GET review guard and redirects to wait
        job.interpretation_dossier["verification_report"] = forged_items
        job.save(update_fields=["interpretation_dossier"])
        resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert resp.status_code == 302
        assert reverse("tutor-import-wait", args=[job.pk]) in resp.url

    def test_b2_heterogeneity_partial_fields_reach_ready_while_empty_structure_fails_closed(self):
        client, user = tutor_teacher("t5-luna-b2-hetero-ready")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        job.refresh_from_db()
        prior_dossier = copy.deepcopy(job.interpretation_dossier)
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY

        # Probe A: Heterogeneous structure - missing 'finalidad' still transitions to READY with review count
        worker_token_2 = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=worker_token_2, allow_retry=True)
        cand_1 = copy.deepcopy(dossier)
        cand_1.general_fields.pop("finalidad", None)
        rows_1 = finish_worker_success(job, owner_token=worker_token_2, dossier=cand_1)
        assert rows_1 == 1
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        assert "finalidad" not in job.interpretation_dossier["general_fields"]
        v_rep = job.interpretation_dossier["verification_report"]
        assert v_rep["blocked_count"] == 0
        assert v_rep["needs_review_count"] >= 1
        assert any(it["target"] == "general.finalidad" and it["status"] == "needs_teacher_review" for it in v_rep["items"])

        # Probe B: Heterogeneous structure - only 'proyecto' in general_fields is READY
        worker_token_3 = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=worker_token_3, allow_retry=True)
        cand_2 = copy.deepcopy(dossier)
        cand_2.general_fields = {"proyecto": cand_2.general_fields["proyecto"]}
        rows_2 = finish_worker_success(job, owner_token=worker_token_3, dossier=cand_2)
        assert rows_2 == 1
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        v_rep2 = job.interpretation_dossier["verification_report"]
        assert v_rep2["blocked_count"] == 0
        assert v_rep2["needs_review_count"] >= 3

        # Probe C: Structurally empty general_fields = {} FAILS closed and preserves prior valid dossier
        valid_prior_dossier = copy.deepcopy(job.interpretation_dossier)
        worker_token_4 = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=worker_token_4, allow_retry=True)
        bad_cand = copy.deepcopy(dossier)
        bad_cand.general_fields = {}
        rows_3 = finish_worker_success(job, owner_token=worker_token_4, dossier=bad_cand)
        assert rows_3 == 1
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert job.interpretation_dossier == valid_prior_dossier

    def test_b4_invalid_excerpt_save_preserves_exact_prior(self):
        client, user = tutor_teacher("t5-luna-b4-invalid-ex")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        job.refresh_from_db()
        prior_dossier = copy.deepcopy(job.interpretation_dossier)

        # Candidate dossier with empty/whitespace excerpt on supported evidence
        cand_invalid = copy.deepcopy(dossier)
        cand_invalid.general_fields["proyecto"].evidence[0].excerpt = "   \n\t  "
        target_state = save_interpretation_dossier_command(job, dossier=cand_invalid)
        assert target_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        # DB interpretation_dossier must be identical to prior valid dossier
        assert job.interpretation_dossier == prior_dossier

    def test_b4_tamper_interleaving_before_final_cas_fails_closed(self):
        client, user = tutor_teacher("t5-luna-b4-interleaving")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)

        original_open = job.pdf.open
        read_counter = 0

        class _TamperStreamWrapper:
            def __init__(self, original_stream, is_tampered):
                self._stream = original_stream
                self._is_tampered = is_tampered

            def read(self):
                data = self._stream.read()
                if self._is_tampered:
                    return data + b"TAMPERED_IN_FLIGHT"
                return data

            def __enter__(self):
                self._stream.__enter__()
                return self

            def __exit__(self, *args):
                return self._stream.__exit__(*args)

        def mock_open(mode="rb"):
            nonlocal read_counter
            read_counter += 1
            real_stream = original_open(mode)
            # First read is genuine, second read (inside CAS atomic) is tampered
            return _TamperStreamWrapper(real_stream, is_tampered=(read_counter >= 2))

        with mock.patch.object(job.pdf, "open", side_effect=mock_open):
            res = finish_worker_success(job, owner_token=owner_token, dossier=dossier)
            assert res == 1

        job.refresh_from_db()
        assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        assert "modificado concurrentemente" in job.interpretation_error_message
        # Candidate dossier was NOT written to DB
        assert not job.interpretation_dossier

    def test_b4_interpretation_get_opens_pdf_exactly_once(self):
        client, user = tutor_teacher("t5-luna-b4-single-open")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)
        job.refresh_from_db()

        from django.db.models.fields.files import FieldFile
        real_open = FieldFile.open
        open_call_count = 0

        def _counting_open(self_field, *args, **kwargs):
            nonlocal open_call_count
            open_call_count += 1
            return real_open(self_field, *args, **kwargs)

        with mock.patch.object(FieldFile, "open", _counting_open):
            resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
            assert resp.status_code == 200

        # Must open the PDF at most / exactly 1 time in the view!
        assert open_call_count == 1, f"Expected 1 PDF open, got {open_call_count}"

    def test_b5_banner_uses_canonical_checked_items_and_links(self):
        client, user = tutor_teacher("t5-luna-b5-checked-links")
        job = _c01_job(user)
        owner_token = uuid.uuid4()
        claim_interpretation_worker(job, owner_token=owner_token)
        dossier = CurriculumSourceInterpreter.prepare(job.pdf)
        finish_worker_success(job, owner_token=owner_token, dossier=dossier)

        resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")

        # Must contain canonical owner-scoped links for checked items
        expected_link_p1 = reverse("tutor-import-source-page", args=[job.pk, 1])
        assert expected_link_p1 in html

        # Verify verified_items alias is not in the rendered HTML or context
        assert "verified_items" not in html


class TestTask5ClosureFix4Seams:
    """Rigorous closure tests for B1 (resolve & physical sources) and B2 (malformed handling)."""

    def test_b1_resolve_invented_prior_evidence_not_reused_remains_pending(self):
        """B1: resolve() must NOT reuse invented prior evidence like 'TEXTO INVENTADO QUE NO ESTA'."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        sess = dossier.sessions[0]
        # Attach invented evidence to annex
        ref = AnnexReference(
            annex_number="99",
            raw_mention="ver Anexo 99",
            source_pages=[1],
            candidate_pages=[2],
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
            evidence=[
                SourceReference(
                    document_sha256=dossier.source_sha256,
                    page_number=2,
                    excerpt="TEXTO INVENTADO QUE NO ESTA EN EL PDF",
                    role="extracted_mention",
                )
            ],
        )
        sess.annex_references.append(ref)

        resolved = resolve(
            dossier,
            {"session_id": sess.session_id, "annex_confirmations": {"99": "2"}},
            pdf_source=pdf_bytes,
        )
        target = next(r for r in resolved.sessions[0].annex_references if r.annex_number == "99")
        assert target.confirmed_page == 2
        assert target.review == REVIEW_PENDING
        assert not any(getattr(ev, "role", "") == "teacher_selected_source_page" for ev in target.evidence)

    def test_b1_resolve_forged_candidate_label_not_reused_remains_pending(self):
        """B1: resolve() must NOT confirm using a forged candidate label that is not present in physical PDF."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        sess = dossier.sessions[0]
        dossier.annex_candidates.append({"page": 2, "label": "ETIQUETA FABRICADA NO PRESENTE EN EL PDF"})
        ref = AnnexReference(
            annex_number="98",
            raw_mention="ver Anexo 98",
            source_pages=[1],
            candidate_pages=[2],
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
            evidence=[],
        )
        sess.annex_references.append(ref)

        resolved = resolve(
            dossier,
            {"session_id": sess.session_id, "annex_confirmations": {"98": "2"}},
            pdf_source=pdf_bytes,
        )
        target = next(r for r in resolved.sessions[0].annex_references if r.annex_number == "98")
        assert target.confirmed_page == 2
        assert target.review == REVIEW_PENDING
        assert not any(getattr(ev, "role", "") == "teacher_selected_source_page" for ev in target.evidence)

    def test_b1_resolve_scanned_page_with_candidate_remains_pending(self):
        """B1: On a scanned/empty PDF without digital text, an annex candidate must NOT become confirmed."""
        pdf_source = (b"%PDF-1.4", "sha_scanned", ["", "", "", ""])
        dossier = ImportDossier(
            source_sha256="sha_scanned",
            source_name="scanned.pdf",
            page_count=4,
            sessions=[
                SessionPlan(
                    session_id="s1",
                    session_number=1,
                    title="Sesión 1",
                    pages=[1],
                    annex_references=[
                        AnnexReference(
                            annex_number="1",
                            raw_mention="Anexo 1",
                            source_pages=[1],
                            candidate_pages=[3],
                            status=STATUS_SUPPORTED,
                            review=REVIEW_PENDING,
                        )
                    ],
                )
            ],
            annex_candidates=[{"page": 3, "label": "Lámina 1"}],
        )

        resolved = resolve(
            dossier,
            {"session_id": "s1", "annex_confirmations": {"1": "3"}},
            pdf_source=pdf_source,
        )
        annex = resolved.sessions[0].annex_references[0]
        assert annex.confirmed_page == 3
        assert annex.review == REVIEW_PENDING
        assert not any(getattr(ev, "role", "") == "teacher_selected_source_page" for ev in annex.evidence)

    def test_b1_resolve_foreign_corrections_pdf_source_ignored(self):
        """B1: resolve() strictly ignores corrections['pdf_source'] payload; only explicit argument is used."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        sess = dossier.sessions[0]
        ref = AnnexReference(
            annex_number="97",
            raw_mention="ver Anexo 97",
            source_pages=[1],
            candidate_pages=[2],
            status=STATUS_SUPPORTED,
            review=REVIEW_PENDING,
        )
        sess.annex_references.append(ref)

        foreign_pdf = (b"%PDF", "fake_sha", ["foreign text"])
        # Pass foreign source in corrections payload, but None as explicit pdf_source
        resolved = resolve(
            dossier,
            {"session_id": sess.session_id, "annex_confirmations": {"97": "2"}, "pdf_source": foreign_pdf},
            pdf_source=None,
        )
        target = next(r for r in resolved.sessions[0].annex_references if r.annex_number == "97")
        assert target.confirmed_page == 2
        # Without explicit authorized pdf_source, it MUST NOT confirm!
        assert target.review == REVIEW_PENDING

    def test_b1_pdf_handle_position_restored_eof_and_nonzero(self):
        """B1: _read_pdf_source and verification restore exact handle position on success and failure."""
        pdf_bytes = _c01_bytes()
        handle = io.BytesIO(pdf_bytes)

        # 1. Handle at EOF
        handle.seek(0, io.SEEK_END)
        eof_pos = handle.tell()
        assert eof_pos > 0

        _, sha, pages = _read_pdf_source(handle)
        assert handle.tell() == eof_pos
        assert len(pages) > 0

        # 2. Handle at nonzero arbitrary position
        handle.seek(123)
        _, sha2, pages2 = _read_pdf_source(handle)
        assert handle.tell() == 123
        assert sha2 == sha

        # 3. Exception in handle read restores position in finally
        bad_handle = io.BytesIO(b"not a valid pdf")
        bad_handle.seek(5)
        with pytest.raises(Exception):
            _read_pdf_source(bad_handle)
        assert bad_handle.tell() == 5

    def test_b2_verifier_validates_raw_dict_and_deserialized_field_schema_keys(self):
        """B2: Field map ready requires schema keys ('name,value,status,origin,review,evidence').
        Missing key in present field emits localized blocked. Heterogeneity by absent key emits review.
        """
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        raw = dossier.to_dict()

        # Incomplete schema: missing 'status' and 'review' in 'proyecto'
        raw["general_fields"]["proyecto"] = {
            "name": "proyecto",
            "value": "Proyecto Incompleto",
            # 'status', 'origin', 'review', 'evidence' missing!
        }
        report = verify_curriculum_dossier(raw, pdf_bytes)
        assert report.is_valid is False
        blocked_items = [i for i in report.items if i["status"] == STATUS_BLOCKED]
        schema_blocked = [i for i in blocked_items if i["item_id"] == "gen_proyecto_schema_missing_keys"]
        assert len(schema_blocked) == 1
        assert "status" in schema_blocked[0]["message"]

        # Also when passing via ImportDossier.from_dict()
        dossier_from_raw = ImportDossier.from_dict(raw)
        report_deserialized = verify_curriculum_dossier(dossier_from_raw, pdf_bytes)
        assert report_deserialized.is_valid is False
        schema_blocked_deser = [i for i in report_deserialized.items if i["item_id"] == "gen_proyecto_schema_missing_keys"]
        assert len(schema_blocked_deser) == 1

        # Heterogeneity: completely absent key 'finalidad' still emits needs_teacher_review (not blocked)
        raw_full = dossier.to_dict()
        raw_full["general_fields"].pop("finalidad", None)
        report_hetero = verify_curriculum_dossier(raw_full, pdf_bytes)
        assert report_hetero.is_valid is True
        fin_review = [i for i in report_hetero.items if i["target"] == "general.finalidad"]
        assert len(fin_review) == 1
        assert fin_review[0]["status"] == STATUS_NEEDS_TEACHER_REVIEW

    def test_b2_scalar_in_annex_list_localized_blocked_not_generic_error(self):
        """B2: Scalar in annex_references produces localized blocked item with unique id/path, not generic queue error."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        raw = dossier.to_dict()
        raw["sessions"][0]["annex_references"] = [12345]

        report = verify_curriculum_dossier(raw, pdf_bytes)
        assert report.is_valid is False
        malformed_annex = [i for i in report.items if "annex" in i["scope"] and i["status"] == STATUS_BLOCKED]
        assert len(malformed_annex) >= 1
        assert any("malformed" in i["item_id"] for i in malformed_annex)
        # Must NOT emit generic queue_derivation_error
        assert not any(i["item_id"] == "queue_derivation_error" for i in report.items)

    def test_b2_duplicate_session_id_localized_blocked_with_unique_item_ids(self):
        """B2: Duplicate session_id detected as localized blocked item, and all report items remain 100% unique."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        raw = dossier.to_dict()

        # Duplicate session_id
        dup_session = copy.deepcopy(raw["sessions"][0])
        dup_session["session_number"] = 99
        raw["sessions"].append(dup_session)

        report = verify_curriculum_dossier(raw, pdf_bytes)
        assert report.is_valid is False
        dup_items = [i for i in report.items if "duplicate" in i["item_id"]]
        assert len(dup_items) >= 1
        assert dup_items[0]["status"] == STATUS_BLOCKED

        # Crucial invariant: ALL item_id, path, and target in report MUST BE UNIQUE
        all_ids = [i["item_id"] for i in report.items]
        all_paths = [i["path"] for i in report.items]
        all_targets = [i["target"] for i in report.items]
        assert len(all_ids) == len(set(all_ids)), f"Duplicate item_ids found: {len(all_ids) - len(set(all_ids))}"
        assert len(all_paths) == len(set(all_paths)), f"Duplicate paths found: {len(all_paths) - len(set(all_paths))}"
        assert len(all_targets) == len(set(all_targets)), f"Duplicate targets found: {len(all_targets) - len(set(all_targets))}"

    def test_b2_malformed_evidence_in_field_preserved_and_blocked(self):
        """B2: Scalar in field evidence is NOT silently dropped by from_dict and is blocked by verifier."""
        pdf_bytes = _c01_bytes()
        dossier = CurriculumSourceInterpreter.prepare(pdf_bytes)
        raw = dossier.to_dict()
        raw["general_fields"]["proyecto"]["evidence"] = [999]

        dossier_loaded = ImportDossier.from_dict(raw)
        # Must not be silently dropped!
        assert len(dossier_loaded.general_fields["proyecto"].evidence) == 1

        report = verify_curriculum_dossier(dossier_loaded, pdf_bytes)
        assert report.is_valid is False
        ev_blocked = [i for i in report.items if i["item_id"] == "gen_proyecto_ev_0"]
        assert len(ev_blocked) == 1
        assert ev_blocked[0]["status"] == STATUS_BLOCKED


