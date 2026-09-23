"""Tests for Task 4: Retiring tutor-import-detail from canonical teacher flow while preserving direct legacy compatibility.

Requirements:
1. tutor_curriculum uses teacher language "planeación" and cards with canonical destinations:
   - READY + valid dossier -> tutor-import-interpretation, CTA "Revisar planeación"
   - ORGANIZING / delayed / FAILED -> tutor-import-wait, CTA "Ver progreso" / "Resolver e intentar de nuevo"
   - NOT_STARTED / unstarted legacy -> tutor-import-upload, CTA "Importar planeación" (no detail, no GET activation)
   - Causal DOM association via data attributes, scoped by owner.
2. Wait / status do not generate or link detail in canonical flow:
   - Eliminates #assistant-retry-link and legacy JS selector/toggle.
   - status redirect_url: interpretation only when READY + valid dossier; wait for any other canonical state (never detail).
   - cancel from wait redirects to tutor-curriculum (listado de planeaciones), never detail; POST enforces ownership & CAS.
   - Fallbacks of wait for canonical jobs do not redirect to detail. Explicit legacy session marker returns to legacy panel,
     proving it is unreachable from canonical upload/list/wait/review.
3. In review (tutor-import-interpretation), the back link points to tutor-curriculum ("← Volver a planeaciones"), not detail.
4. Route detail and direct legacy operations remain functional and authorized for compatibility.
   No main CTA contains "V0", "modelo", "bitácora", "currícula".
5. HTTP crawl matrix from landing -> upload -> wait -> review -> list + failed/retry/cancel:
   No response HTML, Location header, or status redirect_url references detail.
   All GETs remain 100% pure reads.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from curriculum.models import (
    CurriculumImportJob,
    CurriculumPackage,
    PublishedPackageSnapshot,
)
from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.views import _is_valid_ready_interpretation_dossier
from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

pytestmark = pytest.mark.django_db(transaction=True)


def _valid_dossier_dict(sha256_hex):
    gen_names = ["proyecto", "campos_formativos", "proposito", "finalidad", "metodologia", "escenario_proyecto", "grado"]
    sess_names = ["inicio", "desarrollo", "cierre", "materiales", "evaluacion", "contexto_ejecucion"]
    dossier = {
        "version": 1,
        "source_sha256": sha256_hex,
        "source_name": "planeacion-test.pdf",
        "page_count": 1,
        "status": "active",
        "created_at": timezone.now().isoformat(),
        "updated_at": timezone.now().isoformat(),
        "history": [{"action": "prepare", "version": 1, "timestamp": timezone.now().isoformat()}],
        "campo_formativo": "Lenguajes",
        "proyecto": "Proyecto Comunitario",
        "proposito": "Propósito formativo",
        "finalidad": "Finalidad educativa",
        "metodologia": "Aprendizaje Basado en Proyectos",
        "escenario_proyecto": "Aula",
        "general_fields": {
            k: {"name": k, "value": f"Val {k}", "status": "missing", "origin": "extracted", "review": "pending", "evidence": []}
            for k in gen_names
        },
        "sessions": [
            {
                "session_id": "s_1",
                "session_number": 1,
                "pages": [1],
                "continues_on": [],
                "fields": {
                    k: {"name": k, "value": f"Val {k}", "status": "missing", "origin": "extracted", "review": "pending", "evidence": []}
                    for k in sess_names
                },
                "annex_references": [],
            }
        ],
        "annex_candidates": [],
        "references": [],
    }
    from curriculum.verification import compute_canonical_verification_report
    rep = compute_canonical_verification_report(dossier, MINIMAL_VALID_PDF_BYTES)
    dossier["verification_report"] = rep
    return dossier


def _create_sample_job(owner, *, state="not_started", error_msg=""):
    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    now = timezone.now()

    dossier = {}
    claim_token = None
    claimed_at = None
    interp_state = CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
    progress_stage = ""

    if state == "ready":
        dossier = _valid_dossier_dict(sha)
        interp_state = CurriculumImportJob.INTERPRETATION_STATE_READY
    elif state == "organizing":
        interp_state = CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        claim_token = uuid.uuid4()
        claimed_at = now
        progress_stage = "interpreting"
    elif state == "delayed":
        interp_state = CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
        claim_token = uuid.uuid4()
        claimed_at = now - timedelta(minutes=120)
        progress_stage = "interpreting"
    elif state == "failed":
        interp_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
        error_msg = error_msg or "Error durante la interpretación"

    job = CurriculumImportJob.objects.create(
        created_by=owner,
        pdf=SimpleUploadedFile("planeacion-test.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=interp_state,
        interpretation_dossier=dossier,
        interpretation_claim_token=claim_token,
        interpretation_claimed_at=claimed_at,
        interpretation_error_message=error_msg,
        error_message=error_msg,
        progress_stage=progress_stage,
        progress_started_at=claimed_at,
        page_count=3,
    )
    return job


# =========================================================================
# 1. tutor_curriculum Cards and Language Specification
# =========================================================================

def test_tutor_curriculum_cards_canonical_destinations_by_state():
    """Requirement 1: tutor_curriculum renders teacher language 'planeación' and cards
    with canonical destination URLs and CTA text based on job state:
    - READY + valid dossier -> tutor-import-interpretation, CTA 'Revisar planeación'
    - ORGANIZING -> tutor-import-wait, CTA 'Ver progreso'
    - delayed -> tutor-import-wait, CTA 'Ver progreso'
    - FAILED -> tutor-import-wait, CTA 'Resolver e intentar de nuevo'
    - NOT_STARTED / legacy -> tutor-import-upload, CTA 'Importar planeación' (no detail, no GET trigger)
    DOM elements causally associated via data-job-id and data-canonical-state.
    No CTA contains 'V0', 'modelo', 'bitácora', 'currícula'.
    """
    client = tutor_client("t4-cards-teacher")
    owner = get_user_model().objects.get(username="t4-cards-teacher")

    job_ready = _create_sample_job(owner, state="ready")
    job_org = _create_sample_job(owner, state="organizing")
    job_delayed = _create_sample_job(owner, state="delayed")
    job_failed = _create_sample_job(owner, state="failed")
    job_not_started = _create_sample_job(owner, state="not_started")

    resp = client.get(reverse("tutor-curriculum"))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Header action check: uses 'planeación', not 'currícula'
    header_cta = soup.find("a", class_="primary-action")
    assert header_cta is not None
    assert "planeación" in header_cta.get_text().lower()
    assert "currícula" not in header_cta.get_text().lower()
    assert header_cta["href"] == reverse("tutor-import-upload")

    # Inspect cards by data-job-id
    card_specs = [
        (job_ready, "ready", reverse("tutor-import-interpretation", args=[job_ready.pk]), "Revisar planeación"),
        (job_org, "organizing", reverse("tutor-import-wait", args=[job_org.pk]), "Ver progreso"),
        (job_delayed, "delayed", reverse("tutor-import-wait", args=[job_delayed.pk]), "Ver progreso"),
        (job_failed, "failed", reverse("tutor-import-wait", args=[job_failed.pk]), "Resolver e intentar de nuevo"),
        (job_not_started, "not_started", reverse("tutor-import-upload"), "Importar planeación"),
    ]

    for job, expected_canonical_state, expected_url, expected_cta in card_specs:
        card = soup.find("article", attrs={"data-job-id": str(job.pk)})
        assert card is not None, f"Card for job {job.pk} ({expected_canonical_state}) not found in DOM!"
        assert card.get("data-canonical-state") == expected_canonical_state

        action_link = card.find("a", class_="secondary-action")
        assert action_link is not None, f"Action link missing in card for job {job.pk}"
        assert action_link["href"] == expected_url, (
            f"Job {job.pk} ({expected_canonical_state}) expected url {expected_url} but got {action_link['href']}"
        )
        cta_text = action_link.get_text().strip().replace(" →", "")
        assert expected_cta in cta_text, (
            f"Job {job.pk} ({expected_canonical_state}) expected CTA '{expected_cta}' but got '{cta_text}'"
        )

        # Ensure NO card links to tutor-import-detail
        assert reverse("tutor-import-detail", args=[job.pk]) != action_link["href"]

        # Ensure NO CTA contains banned technical/legacy jargon
        banned = ["v0", "modelo", "bitácora", "currícula"]
        for term in banned:
            assert term not in cta_text.lower(), f"Banned jargon '{term}' found in CTA '{cta_text}'"


def test_tutor_curriculum_ownership_and_security():
    """tutor_curriculum respects ownership strictly: another teacher's cards never appear.
    Anonymous user is redirected to login. Pure GET with zero mutations."""
    client_a = tutor_client("t4-owner-a")
    owner_a = get_user_model().objects.get(username="t4-owner-a")
    client_b = tutor_client("t4-owner-b")
    owner_b = get_user_model().objects.get(username="t4-owner-b")

    job_a = _create_sample_job(owner_a, state="ready")
    job_b = _create_sample_job(owner_b, state="ready")

    updated_at_a = job_a.updated_at
    updated_at_b = job_b.updated_at

    resp_a = client_a.get(reverse("tutor-curriculum"))
    assert resp_a.status_code == 200
    html_a = resp_a.content.decode("utf-8")
    assert f'data-job-id="{job_a.pk}"' in html_a
    assert f'data-job-id="{job_b.pk}"' not in html_a

    # Purity check: zero DB mutations on GET
    job_a.refresh_from_db()
    job_b.refresh_from_db()
    assert job_a.updated_at == updated_at_a
    assert job_b.updated_at == updated_at_b

    # Anonymous visitor check
    anon_resp = Client().get(reverse("tutor-curriculum"))
    assert anon_resp.status_code == 302
    assert "/cms/login/" in anon_resp["Location"]


# =========================================================================
# 2. Wait and Status: Elimination of Detail Affordances
# =========================================================================

def test_wait_view_eliminates_legacy_detail_retry_link():
    """Requirement 2: #assistant-retry-link is completely eliminated from tutor_import_wait.html.
    No link to tutor-import-detail is emitted in wait HTML for organizing, delayed, or failed states."""
    client = tutor_client("t4-wait-elimination-teacher")
    owner = get_user_model().objects.get(username="t4-wait-elimination-teacher")

    for state in ("organizing", "delayed", "failed"):
        job = _create_sample_job(owner, state=state)
        resp = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")

        assert soup.find(id="assistant-retry-link") is None, (
            f"Legacy #assistant-retry-link still present in wait HTML for state {state}!"
        )
        assert soup.find("a", href=reverse("tutor-import-detail", args=[job.pk])) is None, (
            f"Link to tutor-import-detail found in wait HTML for state {state}!"
        )
        assert f'href="{reverse("tutor-import-detail", args=[job.pk])}"' not in html, (
            f"Link to tutor-import-detail found in wait HTML for state {state}!"
        )


def test_assistant_progress_js_eliminates_legacy_retry_selector_and_binding():
    """Requirement 2: static/curriculum/assistant_progress.js does not contain #assistant-retry-link
    or legacyRetry variable/usage."""
    js_path = Path("static/curriculum/assistant_progress.js")
    js_code = js_path.read_text(encoding="utf-8")
    assert "assistant-retry-link" not in js_code, "Reference to #assistant-retry-link remains in assistant_progress.js!"
    assert "legacyRetry" not in js_code, "legacyRetry reference remains in assistant_progress.js!"


def test_status_endpoint_redirect_url_never_points_to_detail():
    """Requirement 2: tutor_import_status redirect_url points to tutor-import-interpretation
    ONLY when state is finished AND interpretation_state == READY with valid dossier.
    For ANY other state (organizing, waiting, delayed, error, failed, not_started),
    redirect_url points to tutor-import-wait, NEVER tutor-import-detail."""
    client = tutor_client("t4-status-redirect-teacher")
    owner = get_user_model().objects.get(username="t4-status-redirect-teacher")

    # 1. Ready state -> interpretation
    job_ready = _create_sample_job(owner, state="ready")
    resp_ready = client.get(reverse("tutor-import-status", args=[job_ready.pk]))
    assert resp_ready.status_code == 200
    data_ready = resp_ready.json()
    assert data_ready["state"] == "finished"
    assert data_ready["redirect_url"] == reverse("tutor-import-interpretation", args=[job_ready.pk])

    # 2. Non-ready states -> tutor-import-wait, NEVER detail
    non_ready_states = ("organizing", "delayed", "failed", "not_started")
    for st in non_ready_states:
        job = _create_sample_job(owner, state=st)
        resp = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["redirect_url"] == reverse("tutor-import-wait", args=[job.pk]), (
            f"Status redirect_url for state {st} was {data['redirect_url']}; expected wait URL!"
        )
        assert reverse("tutor-import-detail", args=[job.pk]) != data["redirect_url"]


def test_cancel_from_wait_redirects_to_curriculum_listing():
    """Requirement 2: tutor_import_cancel redirects to tutor-curriculum (listado de planeaciones),
    never detail. Follows ownership and sets cancel_requested under CAS."""
    client = tutor_client("t4-cancel-teacher")
    owner = get_user_model().objects.get(username="t4-cancel-teacher")

    job = _create_sample_job(owner, state="organizing")
    cancel_url = reverse("tutor-import-cancel", args=[job.pk])

    # POST to cancel
    resp = client.post(cancel_url)
    assert resp.status_code in (302, 303)
    assert resp["Location"] == reverse("tutor-curriculum"), (
        f"Cancel redirected to {resp['Location']}; expected tutor-curriculum listing!"
    )

    job.refresh_from_db()
    assert job.cancel_requested is True

    # Security: foreign owner cannot cancel
    client_foreign = tutor_client("t4-foreign-cancel-teacher")
    resp_foreign = client_foreign.post(cancel_url)
    assert resp_foreign.status_code == 404

    # GET method not allowed
    resp_get = client.get(cancel_url)
    assert resp_get.status_code == 405


def test_wait_fallback_for_canonical_jobs_never_redirects_to_detail():
    """Requirement 2: Wait view fallbacks for canonical jobs (without legacy session marker)
    never redirect to tutor-import-detail. Only explicit legacy session marker returns to detail."""
    client = tutor_client("t4-fallback-teacher")
    owner = get_user_model().objects.get(username="t4-fallback-teacher")

    # Canonical job without topics or progress
    job_canonical = _create_sample_job(owner, state="not_started")
    resp = client.get(reverse("tutor-import-wait", args=[job_canonical.pk]))
    assert resp.status_code in (200, 302)
    if resp.status_code == 302:
        assert reverse("tutor-import-detail", args=[job_canonical.pk]) not in resp["Location"]
        assert resp["Location"] == reverse("tutor-curriculum")

    # Canonical job finished topics but NO legacy session marker
    job_topics = _create_sample_job(owner, state="not_started")
    CurriculumImportJob.objects.filter(pk=job_topics.pk).update(
        topics=[{"titulo": "Tema A"}],
        progress_finished_at=timezone.now(),
        progress_stage="",
    )
    resp_topics = client.get(reverse("tutor-import-wait", args=[job_topics.pk]))
    assert resp_topics.status_code in (200, 302)
    if resp_topics.status_code == 302:
        assert reverse("tutor-import-detail", args=[job_topics.pk]) not in resp_topics["Location"]
        assert resp_topics["Location"] == reverse("tutor-curriculum")


# =========================================================================
# 3. Review View Back-Link Points to Curriculum Listing
# =========================================================================

def test_review_back_link_points_to_curriculum_listing_not_detail():
    """Requirement 3: In tutor-import-interpretation, the 'volver' link points to
    tutor-curriculum ('← Volver a planeaciones'), never tutor-import-detail."""
    client = tutor_client("t4-review-backlink-teacher")
    owner = get_user_model().objects.get(username="t4-review-backlink-teacher")

    job = _create_sample_job(owner, state="ready")
    review_url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(review_url)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    back_link = soup.find("a", class_="back-link")
    assert back_link is not None, "Back link not found in tutor_import_interpretation.html!"
    assert back_link["href"] == reverse("tutor-curriculum"), (
        f"Back link href was {back_link['href']}; expected {reverse('tutor-curriculum')}"
    )
    assert soup.find("a", href=reverse("tutor-import-detail", args=[job.pk])) is None
    assert f'href="{reverse("tutor-import-detail", args=[job.pk])}"' not in html


# =========================================================================
# 4. Legacy Route and Direct Compatibility Preserved
# =========================================================================

def test_legacy_direct_detail_route_remains_functional_and_authorized():
    """Requirement 4: The tutor-import-detail route and legacy actions remain functional
    for direct access. Ownership and security are preserved."""
    client = tutor_client("t4-legacy-compat-teacher")
    owner = get_user_model().objects.get(username="t4-legacy-compat-teacher")

    job = _create_sample_job(owner, state="not_started")
    detail_url = reverse("tutor-import-detail", args=[job.pk])

    # 1. Direct GET by owner is 200 OK
    resp = client.get(detail_url)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "revisar importación" in html.lower()

    # 2. Logs remain accessible
    assert client.get(reverse("tutor-import-log-md", args=[job.pk])).status_code == 200
    assert client.get(reverse("tutor-import-log-json", args=[job.pk])).status_code == 200

    # 3. Foreign teacher receives 404
    client_foreign = tutor_client("t4-legacy-foreign-teacher")
    assert client_foreign.get(detail_url).status_code == 404

    # 4. Anonymous visitor redirected to login
    assert Client().get(detail_url).status_code == 302


# =========================================================================
# 5. Canonical HTTP Crawl Matrix: Zero Detail References
# =========================================================================

def test_canonical_http_crawl_matrix_zero_detail_references():
    """Requirement 5: Full crawl of canonical journey:
    landing -> upload -> wait -> review -> list + failed / retry / cancel
    Zero references to tutor-import-detail in response HTML, Location, or status redirect_url.
    All GET requests are pure reads."""
    client = tutor_client("t4-crawl-teacher")
    owner = get_user_model().objects.get(username="t4-crawl-teacher")

    detail_fragment = f"/tutor/imports/"

    # Step 1: Landing
    r_landing = client.get(reverse("tutor-sessions"))
    assert r_landing.status_code == 200
    soup_landing = BeautifulSoup(r_landing.content.decode("utf-8"), "html.parser")
    import_cta = soup_landing.find("a", href=reverse("tutor-import-upload"))
    assert import_cta is not None
    assert "planeación" in import_cta.get_text().lower()

    # Step 2: Upload GET
    r_upload_get = client.get(reverse("tutor-import-upload"))
    assert r_upload_get.status_code == 200
    assert "tutor-import-detail" not in r_upload_get.content.decode("utf-8")

    # Step 3: Upload POST (valid PDF) -> 302 to wait
    pdf = SimpleUploadedFile("plan.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf")
    r_upload_post = client.post(reverse("tutor-import-upload"), {"pdf": pdf})
    assert r_upload_post.status_code in (302, 303)
    loc = r_upload_post["Location"]
    job_id = int(loc.split("/")[-3])
    job = CurriculumImportJob.objects.get(pk=job_id)
    detail_url = reverse("tutor-import-detail", args=[job.pk])
    wait_url = reverse("tutor-import-wait", args=[job.pk])
    assert loc == wait_url
    assert loc != detail_url

    # Step 4: Wait GET (pure read, zero detail links)
    snap_before = job.updated_at
    r_wait = client.get(loc)
    assert r_wait.status_code == 200
    html_wait = r_wait.content.decode("utf-8")
    assert f'href="{detail_url}"' not in html_wait
    assert "assistant-retry-link" not in html_wait
    job.refresh_from_db()
    assert job.updated_at == snap_before

    # Step 5: Status GET (pure read, zero detail redirect)
    r_status = client.get(reverse("tutor-import-status", args=[job.pk]))
    assert r_status.status_code == 200
    data_status = r_status.json()
    expected_status_redirect = (
        reverse("tutor-import-interpretation", args=[job.pk])
        if (job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY and _is_valid_ready_interpretation_dossier(job))
        else wait_url
    )
    assert data_status["redirect_url"] == expected_status_redirect

    # Step 6: Cancel POST -> redirects to tutor-curriculum (never detail)
    r_cancel = client.post(reverse("tutor-import-cancel", args=[job.pk]))
    assert r_cancel.status_code in (302, 303)
    assert r_cancel["Location"] == reverse("tutor-curriculum")
    assert r_cancel["Location"] != detail_url

    # Step 7: Retry POST -> redirects to wait, never detail
    CurriculumImportJob.objects.filter(pk=job.pk).update(
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_error_message="Fallo recuperable",
    )
    r_retry = client.post(reverse("tutor-import-retry", args=[job.pk]))
    assert r_retry.status_code in (302, 303)
    assert r_retry["Location"] in (
        wait_url,
        reverse("tutor-import-interpretation", args=[job.pk]),
    )
    assert r_retry["Location"] != detail_url

    # Step 8: Set READY and check Review GET -> back-link to tutor-curriculum
    CurriculumImportJob.objects.filter(pk=job.pk).update(
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_dossier=_valid_dossier_dict(hashlib.sha256(MINIMAL_VALID_PDF_BYTES).hexdigest()),
        interpretation_error_message="",
        error_message="",
        progress_stage="",
    )
    r_review = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert r_review.status_code == 200
    html_review = r_review.content.decode("utf-8")
    assert f'href="{detail_url}"' not in html_review
    soup_rev = BeautifulSoup(html_review, "html.parser")
    assert soup_rev.find("a", class_="back-link")["href"] == reverse("tutor-curriculum")

    # Step 9: List GET -> cards point to canonical URLs, never detail
    r_list = client.get(reverse("tutor-curriculum"))
    assert r_list.status_code == 200
    html_list = r_list.content.decode("utf-8")
    assert f'href="{detail_url}"' not in html_list


# =========================================================================
# 6. Luna B1/B2/B3 Corrections Causal Suite
# =========================================================================

def _model_snapshot(job):
    import copy
    job.refresh_from_db()
    return {
        "status": job.status,
        "interpretation_state": job.interpretation_state,
        "interpretation_dossier": copy.deepcopy(job.interpretation_dossier),
        "interpretation_claim_token": job.interpretation_claim_token,
        "interpretation_claimed_at": job.interpretation_claimed_at,
        "interpretation_error_message": job.interpretation_error_message,
        "progress_stage": job.progress_stage,
        "progress_finished_at": job.progress_finished_at,
        "cancel_requested": job.cancel_requested,
        "cancelled_at": job.cancelled_at,
        "updated_at": job.updated_at,
    }


def test_b1_direct_get_review_on_tampered_or_invalid_redirects_wait_with_zero_db_mutations():
    """B1: Direct GET tutor-import-interpretation on invalid/tampered/not_ready NEVER returns 200.
    Redirects 302 to wait and keeps DB 100% byte-identical (no persisted invalidation during GET)."""
    import copy
    client = tutor_client("t4-b1-tamper-guard-teacher")
    user = get_user_model().objects.get(username="t4-b1-tamper-guard-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(sha)

    # 1. Tampered source PDF
    job_tampered = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("plan_tampered.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_dossier=dossier,
    )
    # Tamper file on disk
    Path(job_tampered.pdf.path).write_bytes(b"%PDF-1.4 altered bytes")

    snap_before_tampered = _model_snapshot(job_tampered)
    resp_tampered = client.get(reverse("tutor-import-interpretation", args=[job_tampered.pk]))
    assert resp_tampered.status_code == 302
    assert resp_tampered.headers["Location"] == reverse("tutor-import-wait", args=[job_tampered.pk])
    snap_after_tampered = _model_snapshot(job_tampered)
    assert snap_after_tampered == snap_before_tampered
    assert snap_after_tampered["interpretation_dossier"]["status"] == "active"

    # 2. Invalid status dossier
    dossier_invalid = copy.deepcopy(dossier)
    dossier_invalid["status"] = "inactive"
    job_invalid = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("plan_invalid.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_dossier=dossier_invalid,
    )
    snap_before_invalid = _model_snapshot(job_invalid)
    resp_invalid = client.get(reverse("tutor-import-interpretation", args=[job_invalid.pk]))
    assert resp_invalid.status_code == 302
    assert resp_invalid.headers["Location"] == reverse("tutor-import-wait", args=[job_invalid.pk])
    snap_after_invalid = _model_snapshot(job_invalid)
    assert snap_after_invalid == snap_before_invalid

    # 3. NOT_STARTED state
    job_not_started = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("plan_not_started.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
    )
    snap_before_ns = _model_snapshot(job_not_started)
    resp_ns = client.get(reverse("tutor-import-interpretation", args=[job_not_started.pk]))
    assert resp_ns.status_code == 302
    assert resp_ns.headers["Location"] == reverse("tutor-import-wait", args=[job_not_started.pk])
    snap_after_ns = _model_snapshot(job_not_started)
    assert snap_after_ns == snap_before_ns


def test_b1_editorial_mutations_blocked_with_409_on_tampered_source_while_reextract_succeeds():
    """B1: POST editorial actions return 409 Conflict if source is tampered.
    Only explicit action='reextract' is capable of accepting a physically changed source PDF."""
    client = tutor_client("t4-b1-mutate-conflict-teacher")
    user = get_user_model().objects.get(username="t4-b1-mutate-conflict-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("plan_mutate.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_dossier=dossier,
    )

    interp_url = reverse("tutor-import-interpretation", args=[job.pk])

    # Overwrite PDF on disk to tamper it
    Path(job.pdf.path).write_bytes(b"%PDF-1.4 tampered bytes for POST test")

    # 1. save_corrections is blocked with 409
    resp_save = client.post(interp_url, {
        "action": "save_corrections",
        "expected_version": "1",
        "session_number": "1",
        "inicio": "Intento de mutación con PDF alterado",
    })
    assert resp_save.status_code == 409

    # 2. confirm_all is blocked with 409
    resp_confirm = client.post(interp_url, {
        "action": "confirm_all",
        "expected_version": "1",
        "session_number": "1",
    })
    assert resp_confirm.status_code == 409

    # 3. Explicit reextract succeeds and restores READY with valid matching hash
    from tests.test_t18_task2_transition import C01_PATH
    Path(job.pdf.path).write_bytes(C01_PATH.read_bytes())

    resp_reextract = client.post(interp_url, {
        "action": "reextract",
        "expected_version": "1",
    })
    assert resp_reextract.status_code in (200, 302)
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert _is_valid_ready_interpretation_dossier(job) is True


def test_b1_wait_and_status_expose_needs_reextract_form_for_tampered_job():
    """B1: Wait and status for integrity conflict expose needs_reextract=True and POST reextract form.
    Does NOT offer misleading retry form."""
    client = tutor_client("t4-b1-reextract-form-teacher")
    user = get_user_model().objects.get(username="t4-b1-reextract-form-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("plan_tampered_wait.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_dossier=dossier,
    )
    Path(job.pdf.path).write_bytes(b"%PDF-1.4 tampered bytes")

    # Status GET
    resp_status = client.get(reverse("tutor-import-status", args=[job.pk]))
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["state"] == "error"
    assert status_data["needs_reextract"] is True
    assert status_data["can_retry"] is False
    assert status_data["retry_url"] is None
    assert status_data["reextract_url"] == reverse("tutor-import-interpretation", args=[job.pk])

    # Wait GET (without JS)
    resp_wait = client.get(reverse("tutor-import-wait", args=[job.pk]))
    assert resp_wait.status_code == 200
    html_wait = resp_wait.content.decode("utf-8")
    soup_wait = BeautifulSoup(html_wait, "html.parser")

    # assistant-reextract-form is present and not hidden
    reextract_form = soup_wait.find("form", id="assistant-reextract-form")
    assert reextract_form is not None
    assert "hidden" not in reextract_form.attrs
    assert reextract_form["action"] == reverse("tutor-import-interpretation", args=[job.pk])
    action_input = reextract_form.find("input", {"name": "action"})
    assert action_input is not None
    assert action_input["value"] == "reextract"

    # assistant-retry-form is NOT rendered at all when needs_reextract is true
    retry_form = soup_wait.find("form", id="assistant-retry-form")
    assert retry_form is None


def test_b2_cards_single_pass_hash_instrumentation():
    """B2 Gate: GET tutor-curriculum executes at most 1 FieldFile.open per card READY,
    and 0 FieldFile.open for non-READY cards (ORGANIZING, FAILED, NOT_STARTED with or without dossier). Zero DB mutations."""
    from django.db.models.fields.files import FieldFile

    client = tutor_client("t4-b2-instrument-teacher")
    user = get_user_model().objects.get(username="t4-b2-instrument-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    # Create 4 READY cards
    ready_jobs = []
    for i in range(4):
        j = CurriculumImportJob.objects.create(
            created_by=user,
            pdf=SimpleUploadedFile(f"ready_{i}.pdf", pdf_bytes, content_type="application/pdf"),
            status=CurriculumImportJob.STATUS_UPLOADED,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
            interpretation_dossier=_valid_dossier_dict(sha),
        )
        ready_jobs.append(j)

    # Create non-READY cards: 1 ORGANIZING, 1 FAILED, 1 NOT_STARTED without dossier, 1 NOT_STARTED with dossier
    import uuid
    job_org = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("org.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        interpretation_claim_token=uuid.uuid4(),
        interpretation_claimed_at=timezone.now(),
    )
    job_failed = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("fail.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_error_message="Error de prueba",
    )
    job_ns = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("ns.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
    )
    job_ns_with_dossier = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("ns_dossier.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        interpretation_dossier=_valid_dossier_dict(sha),
    )

    open_calls_by_file = {}
    original_open = FieldFile.open

    def instrumented_open(self, *args, **kwargs):
        name = getattr(self, "name", "unknown")
        open_calls_by_file[name] = open_calls_by_file.get(name, 0) + 1
        return original_open(self, *args, **kwargs)

    with patch.object(FieldFile, "open", instrumented_open):
        resp = client.get(reverse("tutor-curriculum"))
        assert resp.status_code == 200

    # Verify: At most 1 open per READY card (total ready opens <= 4)
    for rj in ready_jobs:
        file_name = rj.pdf.name
        opens = open_calls_by_file.get(file_name, 0)
        assert opens <= 1, f"READY job {rj.pk} opened file {opens} times (expected <= 1)!"

    # Verify: Exactly 0 opens for non-READY cards (including NOT_STARTED with dossier)
    assert open_calls_by_file.get(job_org.pdf.name, 0) == 0, "ORGANIZING card opened PDF!"
    assert open_calls_by_file.get(job_failed.pdf.name, 0) == 0, "FAILED card opened PDF!"
    assert open_calls_by_file.get(job_ns.pdf.name, 0) == 0, "NOT_STARTED card opened PDF!"
    assert open_calls_by_file.get(job_ns_with_dossier.pdf.name, 0) == 0, "NOT_STARTED with dossier card opened PDF!"


def test_b3_failed_state_takes_precedence_over_stale_claim():
    """B3: interpretation_state == FAILED with a stale claim (> 90 min) derives state 'error' (NOT 'delayed').
    Status GET does not mutate claim."""
    client = tutor_client("t4-b3-precedence-teacher")
    user = get_user_model().objects.get(username="t4-b3-precedence-teacher")

    stale_time = timezone.now() - timedelta(hours=2)
    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("failed_stale.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_claim_token=uuid.uuid4(),
        interpretation_claimed_at=stale_time,
        progress_started_at=stale_time,
        progress_stage="reading_pdf",
        interpretation_error_message="Error durante interpretación",
    )

    snap_before = _model_snapshot(job)
    resp = client.get(reverse("tutor-import-status", args=[job.pk]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "error", f"Expected error state, got {data['state']}"
    assert data["interpretation_state"] == "failed"
    assert data["can_retry"] is True

    snap_after = _model_snapshot(job)
    assert snap_after == snap_before
    assert snap_after["interpretation_claim_token"] == snap_before["interpretation_claim_token"]


def test_retry_tampered_returns_409_and_leaves_db_snapshot_identical():
    """B1: POST to tutor-import-retry on a job with prior dossier and tampered PDF
    returns HTTP 409 Conflict, never calls prepare(), and leaves the DB row 100% identical."""
    client = tutor_client("t4-retry-409-teacher")
    user = get_user_model().objects.get(username="t4-retry-409-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    original_sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(original_sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("retry_tamper.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_dossier=dossier,
        interpretation_error_message="Error previo antes de reintento",
    )
    Path(job.pdf.path).write_bytes(b"%PDF-1.4 completely different content for tamper test")

    snap_before = _model_snapshot(job)

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        resp = client.post(reverse("tutor-import-retry", args=[job.pk]))

    assert resp.status_code == 409
    assert "reextracción explícita" in resp.content.decode("utf-8").lower()
    assert not prepare_called, "prepare() must NOT be called when retry preflight detects tamper!"

    snap_after = _model_snapshot(job)
    assert snap_after == snap_before, "Database row was mutated during failed retry!"


def test_retry_command_direct_raises_reextract_required_with_zero_mutations():
    """B1: Direct call to retry_job_interpretation on tampered/mismatched source
    raises ReextractRequired without taking any claim or mutating the database row."""
    from curriculum.interpretation_commands import retry_job_interpretation, ReextractRequired

    user = get_user_model().objects.create_user(username="t4-cmd-teacher", password="p")
    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    original_sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(original_sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("cmd_tamper.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_dossier=dossier,
        interpretation_error_message="Fallo previo",
    )
    Path(job.pdf.path).write_bytes(b"%PDF-1.4 different bytes")

    snap_before = _model_snapshot(job)

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        with pytest.raises(ReextractRequired) as exc_info:
            retry_job_interpretation(job)

    assert "reextracción explícita" in str(exc_info.value).lower()
    assert not prepare_called

    snap_after = _model_snapshot(job)
    assert snap_after == snap_before, "retry_job_interpretation mutated DB before raising ReextractRequired!"


def test_retry_foreign_claim_race_leaves_foreign_claim_intact():
    """T3 Race preservation: Preflight passes, but a foreign claim is acquired concurrently
    before our CAS claim -> retry_job_interpretation returns None, ZERO mutation to foreign claim."""
    from curriculum.interpretation_commands import retry_job_interpretation

    user = get_user_model().objects.create_user(username="t4-race-teacher", password="p")
    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    original_sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(original_sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("race.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_dossier=dossier,
    )

    foreign_token = uuid.uuid4()
    foreign_claim_time = timezone.now()

    def simulate_race_claim_interpretation_worker(*args, **kwargs):
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            interpretation_claim_token=foreign_token,
            interpretation_claimed_at=foreign_claim_time,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        )
        return 0

    with patch("curriculum.interpretation_commands.claim_interpretation_worker", side_effect=simulate_race_claim_interpretation_worker):
        result = retry_job_interpretation(job)

    assert result is None
    job.refresh_from_db()
    assert job.interpretation_claim_token == foreign_token
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING


def test_not_started_with_dossier_never_opens_pdf_and_derives_waiting():
    """B2: A CurriculumImportJob with interpretation_state=NOT_STARTED that contains a dossier
    must NEVER open the physical PDF (FieldFile.open = 0), NEVER derive 'finished' or 'error',
    derives state='waiting', and its card in tutor_curriculum links to upload ('Importar planeación')."""
    from django.db.models.fields.files import FieldFile
    from curriculum.views import _get_derived_import_presentation

    client = tutor_client("t4-b2-notstarted-teacher")
    user = get_user_model().objects.get(username="t4-b2-notstarted-teacher")

    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("not_started_with_dossier.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
        interpretation_dossier=dossier,
    )

    open_calls = 0
    original_open = FieldFile.open

    def counting_open(self, *args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        return original_open(self, *args, **kwargs)

    with patch.object(FieldFile, "open", counting_open):
        pres = _get_derived_import_presentation(job)
        assert open_calls == 0, f"FieldFile.open was called {open_calls} times for NOT_STARTED job!"
        assert pres["state"] == "waiting", f"Expected state 'waiting', got '{pres['state']}'"
        assert pres["needs_reextract"] is False
        assert pres["has_valid_dossier"] is False
        assert pres["error"] == ""

        # GET tutor-curriculum card check
        resp = client.get(reverse("tutor-curriculum"))
        assert resp.status_code == 200
        assert open_calls == 0, f"FieldFile.open called {open_calls} times during tutor-curriculum rendering!"

    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("article", attrs={"data-job-id": str(job.pk)})
    assert card is not None, f"Card for job {job.pk} not found in DOM!"
    assert card.get("data-canonical-state") == "not_started"
    action_link = card.find("a", class_="secondary-action")
    assert action_link is not None
    assert action_link["href"] == reverse("tutor-import-upload")
    assert "Importar planeación" in action_link.text
    assert "Sin iniciar" in card.text


def test_retry_tamper_after_claim_fails_closed_under_owner_token():
    """T3 TOCTOU post-claim race: Preflight passes, CAS claim is acquired,
    but the physical file changes on disk while prepare() executes.
    Retry command rechecks physical file hash post-claim, marks FAILED under owner_token,
    and releases claim with finish_worker_failure."""
    from curriculum.interpretation_commands import retry_job_interpretation
    from curriculum.source_interpreter import ImportDossier

    user = get_user_model().objects.create_user(username="t4-toctou-teacher", password="p")
    pdf_bytes = MINIMAL_VALID_PDF_BYTES
    original_sha = hashlib.sha256(pdf_bytes).hexdigest()
    dossier = _valid_dossier_dict(original_sha)

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("toctou.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_dossier=dossier,
    )

    def tampering_prepare(fresh_job, *args, **kwargs):
        Path(fresh_job.pdf.path).write_bytes(b"%PDF-1.4 tampered during prepare")
        return ImportDossier(
            version=1,
            status="active",
            source_sha256=original_sha,
            source_name=Path(fresh_job.pdf.name).name,
            page_count=1,
            history=[],
        )

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=tampering_prepare):
        result = retry_job_interpretation(job)

    assert result is None
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert job.interpretation_claim_token is None
    assert "alterado durante el procesamiento" in job.interpretation_error_message
