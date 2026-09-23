"""Tests for Task 3: Error recovery and idempotent retry (vertical slice).

Requirements:
1. When organization is in FAILED state:
   - Wait view (GET) shows brief, safe teacher message (no stack traces, no models/pipelines)
     and a POST form "Volver a intentar" with CSRF. GET does not mutate DB.
   - Status JSON exposes sanitized error, can_retry: true, and retry_url.
   - Accessible touch targets (>=44px), focus on error, role="alert".
2. POST retry semantics:
   - Reuses same job and PDF (no new job created, no published snapshots).
   - Clears error only upon acquiring a valid CAS claim.
   - Initiates exactly one new attempt via command seam.
   - Redirects to wait (or review if atomically READY).
   - Preserves previous history/dossier for audit until atomic success.
3. Idempotency & concurrency:
   - Double POST / concurrent requests do not duplicate workers or corrupt DB.
   - If already ORGANIZING with active claim, redirects to wait without launching worker.
   - If already READY with valid dossier, redirects to review without re-interpreting.
   - Stale claims taken over strictly under CAS rules.
   - Repeated failure returns to FAILED with updated safe error and permits subsequent retries.
4. Auth & security:
   - Non-owner / unauthenticated rejected (404 / 302).
   - GET on retry endpoint returns 405 Method Not Allowed.
   - Job with missing/tampered PDF fails closed without deleting evidence.
   - Cancelled jobs clear cancellation flags on retry without confusion.
   - Invalid dossiers never offer review.
"""

import hashlib
import io
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from curriculum.models import (
    CurriculumImportJob,
    CurriculumPackage,
    PublishedPackageSnapshot,
)
from curriculum.source_interpreter import (
    CurriculumInterpretationError,
    CurriculumSourceInterpreter,
    ImportDossier,
    SourcePdfReadError,
)
from helpers import tutor_client

pytestmark = pytest.mark.django_db(transaction=True)

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")


def _c01_upload():
    assert C01_PATH.exists(), f"Fixture C01 missing at {C01_PATH}"
    return SimpleUploadedFile(
        "prueba-semana-01.pdf",
        C01_PATH.read_bytes(),
        content_type="application/pdf",
    )


def _valid_dossier_dict_for_job(job):
    d = CurriculumSourceInterpreter.prepare(job.pdf)
    return d.to_dict()


def _create_failed_job(user, error_msg="Error de procesamiento simulado", with_dossier=False):
    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=_c01_upload(),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        interpretation_error_message=error_msg,
    )
    if with_dossier:
        with job.pdf.open("rb") as stream:
            pdf_bytes = stream.read()
        sha = hashlib.sha256(pdf_bytes).hexdigest()
        job.interpretation_dossier = {
            "version": 1,
            "status": "invalidated",
            "source_sha256": sha,
            "history": [
                {
                    "action": "prepare_initial",
                    "actor": "AuditTest",
                    "timestamp": "2026-09-12T00:00:00Z",
                    "summary": "Initial attempt",
                }
            ],
        }
        job.save(update_fields=["interpretation_dossier"])
    return job


# =========================================================================
# 1. Auth & Security Matrix
# =========================================================================

def test_retry_endpoint_rejects_unauthenticated():
    """Unauthenticated POST to retry endpoint redirects to login."""
    client = tutor_client("t3-auth-owner")
    owner_user = client.user if hasattr(client, "user") else CurriculumImportJob.objects.first()
    from django.contrib.auth import get_user_model
    owner = get_user_model().objects.get(username="t3-auth-owner")
    job = _create_failed_job(owner)

    anon_client = Client()
    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = anon_client.post(retry_url)
    assert resp.status_code in (302, 303)
    assert "/login" in resp["Location"] or "login" in resp["Location"]


def test_retry_endpoint_rejects_foreign_teacher_with_404():
    """Foreign teacher receives 404 on retry endpoint."""
    from django.contrib.auth import get_user_model
    client_owner = tutor_client("t3-owner-teacher")
    owner = get_user_model().objects.get(username="t3-owner-teacher")
    job = _create_failed_job(owner)

    client_stranger = tutor_client("t3-stranger-teacher")
    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client_stranger.post(retry_url)
    assert resp.status_code == 404


def test_retry_endpoint_nonexistent_job_returns_404():
    """Non-existent job returns 404."""
    client = tutor_client("t3-nonexistent-job-teacher")
    retry_url = reverse("tutor-import-retry", args=[999999])
    resp = client.post(retry_url)
    assert resp.status_code == 404


def test_retry_endpoint_rejects_get_with_405_method_not_allowed():
    """GET on retry endpoint returns 405 Method Not Allowed without mutating state."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-get-method-teacher")
    owner = get_user_model().objects.get(username="t3-get-method-teacher")
    job = _create_failed_job(owner, error_msg="Error original")

    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client.get(retry_url)
    assert resp.status_code == 405

    # Zero mutation verification
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert job.interpretation_error_message == "Error original"
    assert job.interpretation_claim_token is None


# =========================================================================
# 2. Wait View & Status JSON in FAILED State (Teacher Copy & Affordance)
# =========================================================================

def test_failed_job_wait_view_renders_safe_error_and_retry_form_csrf():
    """Wait page in FAILED state renders safe teacher copy and POST retry form with CSRF.
    GET must remain strictly pure/read-only."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-wait-view-teacher")
    owner = get_user_model().objects.get(username="t3-wait-view-teacher")

    # Raw technical stack trace in DB field
    raw_error = "Traceback (most recent call last):\n  File 'engine.py', line 42, in run\nOperationalError: database locked"
    job = _create_failed_job(owner, error_msg=raw_error)

    # Snapshot before GET
    initial_updated_at = job.updated_at
    wait_url = reverse("tutor-import-wait", args=[job.pk])

    resp = client.get(wait_url)
    assert resp.status_code == 200

    html = resp.content.decode("utf-8")

    # 1. Safe teacher copy: NO stack trace, NO database jargon, NO pipeline jargon
    assert "Traceback" not in html
    assert "OperationalError" not in html
    assert "engine.py" not in html
    assert "database locked" not in html

    # Safe message explains what happened and offers retry
    assert "volver a intentar" in html.lower() or "reintentar" in html.lower()
    assert "El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento." in html

    # 2. POST form with CSRF and action targeting retry endpoint
    retry_url = reverse("tutor-import-retry", args=[job.pk])
    assert f'action="{retry_url}"' in html
    assert 'method="post"' in html.lower()
    assert 'name="csrfmiddlewaretoken"' in html
    assert "Volver a intentar" in html

    # 3. Accessibility: role="alert", touch targets >= 44px, active copy hidden in FAILED
    assert 'role="alert"' in html
    assert "min-height: 44px" in html or 'class="button' in html

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    active_notice = soup.find(id="assistant-active-notice")
    assert active_notice is not None
    assert active_notice.has_attr("hidden"), "Active notice must be hidden in FAILED state"

    failed_guide = soup.find(id="assistant-failed-guide")
    assert failed_guide is not None
    assert not failed_guide.has_attr("hidden"), "Failed guide must be visible in FAILED state"
    assert "El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento." in failed_guide.get_text()

    error_container = soup.find(id="assistant-error-container")
    assert error_container is not None
    assert not error_container.has_attr("hidden"), "Error container must be visible in FAILED state"

    # 4. Zero mutation on GET
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert job.interpretation_error_message == raw_error
    assert job.updated_at == initial_updated_at


def test_failed_job_status_json_exposes_sanitized_error_and_retry_affordance():
    """Status JSON polling endpoint in FAILED state returns sanitized error and can_retry signal."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-status-json-teacher")
    owner = get_user_model().objects.get(username="t3-status-json-teacher")

    raw_error = "SyntaxError: invalid syntax in pipeline_v1_model_adapter"
    job = _create_failed_job(owner, error_msg=raw_error)

    status_url = reverse("tutor-import-status", args=[job.pk])
    resp = client.get(status_url)
    assert resp.status_code == 200
    data = resp.json()

    assert data["state"] == "error"
    assert data["interpretation_state"] == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert "SyntaxError" not in data["error"]
    assert "pipeline" not in data["error"].lower()
    assert "model" not in data["error"].lower()
    assert data.get("can_retry") is True
    assert data.get("retry_url") == reverse("tutor-import-retry", args=[job.pk])


def test_http_adverse_matrix_wait_and_status_fail_closed_without_secrets():
    """Adverse security matrix for wait HTML and status JSON endpoints.
    Verifies that paths (Unix & Windows), stack traces, SQL, emails, API keys, URLs,
    JWTs, model telemetry, and arbitrary exceptions are completely sanitized away,
    returning constant safe teacher copy without raw leaks."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-adverse-matrix-teacher")
    owner = get_user_model().objects.get(username="t3-adverse-matrix-teacher")

    adverse_payloads = [
        # Luna's exact probe:
        (
            "File '/srv/private/prompt.py', line 4\nRuntimeError: SELECT * FROM users WHERE email='a@b.test' api_key='sk-secret' https://internal.test/x?token=secret",
            ["/srv/private", "prompt.py", "RuntimeError", "SELECT", "users", "a@b.test", "sk-secret", "https://internal.test", "token=secret"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Internal server path and traceback:
        (
            "Traceback (most recent call last):\n  File '/app/backend/curriculum/pipeline.py', line 99, in <module>\nKeyError: 'secret_token'",
            ["Traceback", "/app/backend", "pipeline.py", "KeyError", "secret_token"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Windows system path:
        (
            "PermissionError: [WinError 5] Access is denied: 'C:\\Windows\\System32\\config\\SAM'",
            ["WinError", "System32", "config\\SAM", "PermissionError"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Unix sensitive path:
        (
            "FileNotFoundError: [Errno 2] No such file or directory: '/etc/shadow'",
            ["Errno 2", "/etc/shadow", "FileNotFoundError"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # SQL injection / destructive query:
        (
            "django.db.utils.OperationalError: SELECT password_hash FROM auth_user WHERE username='admin'",
            ["OperationalError", "SELECT", "password_hash", "auth_user", "username='admin'"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        (
            "DatabaseError: DROP TABLE auth_user CASCADE; DELETE FROM curriculum_curriculumpackage;",
            ["DatabaseError", "DROP TABLE", "auth_user", "CASCADE", "DELETE FROM"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Bearer token and multiple emails:
        (
            "HTTP 401: Unauthorized for user docente@colegio.edu, admin@super.test with Bearer sk-live-secret-key-12345",
            ["Bearer", "sk-live", "secret-key", "docente@colegio.edu", "admin@super.test"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # JWT header & API key:
        (
            "AuthError: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sk-secret-123 api_key=xyz secret=abc",
            ["Bearer", "eyJhbGci", "sk-secret", "api_key=xyz", "secret=abc"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # URL with query credentials:
        (
            "ConnectionError: https://api.internal.service/v1/auth?token=secret123&client_id=987",
            ["https://api.internal.service", "token=secret123", "client_id=987"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Internal model and prompt telemetry:
        (
            "ModelAdapterError: llm_model='gemini-ultra-private' prompt_tokens=8900 temperature=0.2 pipeline_v1",
            ["ModelAdapterError", "llm_model", "gemini-ultra-private", "prompt_tokens", "pipeline_v1"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        # Arbitrary exception names:
        (
            "ZeroDivisionError: division by zero in /var/log/app.log",
            ["ZeroDivisionError", "division by zero", "/var/log/app.log"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
        (
            "TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'",
            ["TypeError", "unsupported operand", "NoneType"],
            "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.",
        ),
    ]

    for raw_error, forbidden_tokens, expected_constant in adverse_payloads:
        job = _create_failed_job(owner, error_msg=raw_error)

        # 1. Wait HTML view:
        wait_url = reverse("tutor-import-wait", args=[job.pk])
        resp_wait = client.get(wait_url)
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")

        for token in forbidden_tokens:
            assert token not in html, f"Forbidden token {token!r} leaked into wait HTML!"

        # Safe fallback text and retry affordances present:
        assert expected_constant in html
        assert "Volver a intentar" in html
        assert "El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento." in html

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        active_notice = soup.find(id="assistant-active-notice")
        assert active_notice is not None
        assert active_notice.has_attr("hidden"), "Active notice must be hidden in FAILED state"

        failed_guide = soup.find(id="assistant-failed-guide")
        assert failed_guide is not None
        assert not failed_guide.has_attr("hidden"), "Failed guide must be visible in FAILED state"

        # 2. Status JSON endpoint:
        status_url = reverse("tutor-import-status", args=[job.pk])
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        data = resp_status.json()

        assert data["state"] == "error"
        assert data["interpretation_state"] == CurriculumImportJob.INTERPRETATION_STATE_FAILED
        for token in forbidden_tokens:
            assert token not in data["error"], f"Forbidden token {token!r} leaked into status JSON error!"

        assert data["error"] == expected_constant
        assert data.get("can_retry") is True


def test_b1_stream_exact_raw_message_is_never_leaked():
    """B1 causal verification: 'Stream corrupto durante reextracción simulada' and variants
    are strictly mapped to the fixed teacher constant, never leaking technical substrings
    or raw exceptions into wait HTML or status JSON."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-b1-stream-leak-teacher")
    owner = get_user_model().objects.get(username="t3-b1-stream-leak-teacher")

    raw_stream_errors = [
        "Stream corrupto durante reextracción simulada",
        "No se pudo leer el archivo PDF fuente: Stream corrupto durante reextracción simulada.",
        "SourcePdfReadError: Stream corrupto durante reextracción simulada",
    ]

    expected_teacher_copy = "No pudimos leer el archivo PDF de la planeación. Puedes volver a intentarlo."

    for raw_err in raw_stream_errors:
        job = _create_failed_job(owner, error_msg=raw_err)

        # Wait HTML view
        resp_wait = client.get(reverse("tutor-import-wait", args=[job.pk]))
        assert resp_wait.status_code == 200
        html = resp_wait.content.decode("utf-8")
        assert "Stream corrupto" not in html
        assert "simulada" not in html
        assert expected_teacher_copy in html

        # Status JSON endpoint
        resp_status = client.get(reverse("tutor-import-status", args=[job.pk]))
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["state"] == "error"
        assert data["error"] == expected_teacher_copy
        assert "Stream corrupto" not in data["error"]
        assert "simulada" not in data["error"]


# =========================================================================
# 3. POST Retry Semantics, Re-use & Idempotency
# =========================================================================

def test_post_retry_reuses_same_job_and_pdf_without_creating_new_job():
    """POST retry reuses the same job and PDF, never creates new jobs, packages, or published snapshots."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-reuse-job-teacher")
    owner = get_user_model().objects.get(username="t3-reuse-job-teacher")
    job = _create_failed_job(owner)

    old_pk = job.pk
    old_pdf_name = job.pdf.name
    old_pdf_path = job.pdf.path
    with job.pdf.open("rb") as stream:
        old_pdf_hash = hashlib.sha256(stream.read()).hexdigest()

    job_count_before = CurriculumImportJob.objects.count()
    pkg_count_before = CurriculumPackage.objects.count()
    snapshot_count_before = PublishedPackageSnapshot.objects.count()

    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client.post(retry_url)
    assert resp.status_code in (302, 303)

    # Invariants: Zero new jobs, zero new packages, zero new published snapshots
    assert CurriculumImportJob.objects.count() == job_count_before
    assert CurriculumPackage.objects.count() == pkg_count_before
    assert PublishedPackageSnapshot.objects.count() == snapshot_count_before

    job.refresh_from_db()
    assert job.pk == old_pk
    assert job.pdf.name == old_pdf_name
    assert job.pdf.path == old_pdf_path
    with job.pdf.open("rb") as stream:
        new_pdf_hash = hashlib.sha256(stream.read()).hexdigest()
    assert new_pdf_hash == old_pdf_hash


def test_post_retry_on_ready_job_redirects_directly_to_review_without_reinterpreting():
    """If job is already READY with valid dossier, retry redirects to review without calling prepare."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-ready-no-reinterp-teacher")
    owner = get_user_model().objects.get(username="t3-ready-no-reinterp-teacher")

    job = CurriculumImportJob.objects.create(
        created_by=owner,
        pdf=_c01_upload(),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
    )
    job.interpretation_dossier = _valid_dossier_dict_for_job(job)
    job.save(update_fields=["interpretation_dossier"])
    assert job.has_valid_ready_dossier()

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    expected_review_url = reverse("tutor-import-interpretation", args=[job.pk])
    assert resp["Location"] == expected_review_url
    assert not prepare_called, "prepare() must NOT be called when job is already READY!"


def test_post_retry_on_actively_organizing_job_redirects_to_wait_without_duplicate_worker():
    """If job is actively ORGANIZING with a fresh claim, retry redirects to wait without launching worker."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-organizing-no-dup-teacher")
    owner = get_user_model().objects.get(username="t3-organizing-no-dup-teacher")

    active_token = uuid.uuid4()
    job = CurriculumImportJob.objects.create(
        created_by=owner,
        pdf=_c01_upload(),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        interpretation_claim_token=active_token,
        interpretation_claimed_at=timezone.now(),
        progress_stage="interpreting",
        progress_started_at=timezone.now(),
    )

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    expected_wait_url = reverse("tutor-import-wait", args=[job.pk])
    assert resp["Location"] == expected_wait_url
    assert not prepare_called, "prepare() must NOT be called when job has an active claim!"

    # Claim token untouched
    job.refresh_from_db()
    assert job.interpretation_claim_token == active_token


def test_stale_claim_is_taken_over_by_retry_via_cas():
    """A stale claim (>90min) is taken over by retry via CAS and launches interpretation."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-stale-takeover-teacher")
    owner = get_user_model().objects.get(username="t3-stale-takeover-teacher")

    old_token = uuid.uuid4()
    stale_time = timezone.now() - timedelta(minutes=100)
    job = CurriculumImportJob.objects.create(
        created_by=owner,
        pdf=_c01_upload(),
        status=CurriculumImportJob.STATUS_UPLOADED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        interpretation_claim_token=old_token,
        interpretation_claimed_at=stale_time,
        progress_stage="interpreting",
        progress_started_at=stale_time,
    )

    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client.post(retry_url)
    assert resp.status_code in (302, 303)

    job.refresh_from_db()
    # Successfully reclaimed and completed to READY
    assert job.interpretation_claim_token is None  # Released upon success
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()


# =========================================================================
# 4. Concurrency & Causal Double-Submit Verification
# =========================================================================

def test_concurrent_double_post_retry_executes_worker_exactly_once():
    """Two concurrent POST retry requests execute the worker exactly once with zero lock errors."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-concurrency-teacher")
    owner = get_user_model().objects.get(username="t3-concurrency-teacher")
    job = _create_failed_job(owner)

    real_prepare = CurriculumSourceInterpreter.prepare
    prepare_calls = 0
    prepare_lock = threading.Lock()

    def slow_prepare(*args, **kwargs):
        nonlocal prepare_calls
        with prepare_lock:
            prepare_calls += 1
        time.sleep(0.15)
        return real_prepare(*args, **kwargs)

    clients = [Client(), Client()]
    clients[0].force_login(owner)
    clients[1].force_login(owner)

    barrier = threading.Barrier(2)
    results = [None, None]
    errors = [None, None]

    def worker_thread(idx):
        connections.close_all()
        try:
            barrier.wait(timeout=5.0)
            retry_url = reverse("tutor-import-retry", args=[job.pk])
            results[idx] = clients[idx].post(retry_url)
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=slow_prepare):
        t1 = threading.Thread(target=worker_thread, args=(0,))
        t2 = threading.Thread(target=worker_thread, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

    assert errors[0] is None, f"Thread 0 raised: {errors[0]}"
    assert errors[1] is None, f"Thread 1 raised: {errors[1]}"

    # Both requests succeed with redirects
    assert results[0].status_code in (302, 303)
    assert results[1].status_code in (302, 303)

    # Exactly 1 execution of prepare()!
    assert prepare_calls == 1, f"Expected exactly 1 prepare() call, got {prepare_calls}"

    # Final DB row snapshot is healthy READY
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()
    assert job.interpretation_claim_token is None


# =========================================================================
# 5. History & Dossier Preservation Until Atomic Success
# =========================================================================

def test_retry_preserves_previous_dossier_and_history_until_atomic_success():
    """Previous dossier and audit history remain in DB during retry, and are preserved if retry fails."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-history-audit-teacher")
    owner = get_user_model().objects.get(username="t3-history-audit-teacher")

    initial_history = [
        {"action": "attempt_1", "timestamp": "2026-09-12T10:00:00Z", "actor": "Auditor"},
    ]
    job = _create_failed_job(owner, with_dossier=True)
    job.interpretation_dossier["history"] = initial_history
    job.save(update_fields=["interpretation_dossier"])

    # 1. Simulate failure on retry: previous dossier and history must NOT be wiped!
    def failing_prepare(*args, **kwargs):
        raise ValueError("Simulated intermittent parse failure")

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=failing_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    # Crucial: History is preserved in the DB record!
    assert job.interpretation_dossier.get("history") == initial_history

    # 2. Subsequent retry succeeds: transitions to READY with valid dossier
    resp2 = client.post(retry_url)
    assert resp2.status_code in (302, 303)
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()


def test_repeated_failure_returns_to_failed_with_updated_safe_error_and_allows_subsequent_retry():
    """Repeated failures update error message safely and permit repeated retries."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-repeated-fail-teacher")
    owner = get_user_model().objects.get(username="t3-repeated-fail-teacher")
    job = _create_failed_job(owner, error_msg="Fallo número 1")

    # Retry 1: fails
    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=ValueError("Fallo número 2")):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp1 = client.post(retry_url)
        assert resp1.status_code in (302, 303)

    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert "Fallo número 2" in job.interpretation_error_message

    # Retry 2: succeeds
    resp2 = client.post(retry_url)
    assert resp2.status_code in (302, 303)
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()


# =========================================================================
# 6. Edge Cases: Cancelled Job & Missing PDF Fails Closed
# =========================================================================

def test_cancelled_job_retry_clears_cancellation_flags_and_succeeds():
    """A cancelled job retry clears cancel_requested and cancelled_at so new worker completes."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-cancelled-retry-teacher")
    owner = get_user_model().objects.get(username="t3-cancelled-retry-teacher")
    job = _create_failed_job(owner, error_msg="Interpretación cancelada a petición.")
    job.cancel_requested = True
    job.cancelled_at = timezone.now()
    job.save(update_fields=["cancel_requested", "cancelled_at"])

    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client.post(retry_url)
    assert resp.status_code in (302, 303)

    job.refresh_from_db()
    assert job.cancel_requested is False
    assert job.cancelled_at is None
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()


def test_retry_with_missing_pdf_fails_closed_without_erasing_evidence():
    """Job with missing PDF fails closed on retry, preserving the job row and evidence."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-missing-pdf-teacher")
    owner = get_user_model().objects.get(username="t3-missing-pdf-teacher")
    job = _create_failed_job(owner)
    job.pdf = None
    job.save(update_fields=["pdf"])

    retry_url = reverse("tutor-import-retry", args=[job.pk])
    resp = client.post(retry_url)
    assert resp.status_code in (302, 303)

    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    # Evidence / row not deleted
    assert CurriculumImportJob.objects.filter(pk=job.pk).exists()


def test_failed_job_with_valid_prior_dossier_can_be_retried():
    """B2 causal verification: A job in FAILED that retains an active, valid dossier
    must be retryable via POST retry. It must NOT take a shortcut to review without calling prepare.
    Retry executes prepare() once, preserves prior history, and transitions to READY."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-b2-failed-valid-dossier-teacher")
    owner = get_user_model().objects.get(username="t3-b2-failed-valid-dossier-teacher")

    job = _create_failed_job(owner, error_msg="Fallo simulado con dossier previo intacto")
    # Attach a valid, active dossier matching current PDF
    valid_dossier = _valid_dossier_dict_for_job(job)
    valid_dossier["history"] = [
        {"action": "previous_attempt", "actor": "Auditor", "timestamp": "2026-09-12T08:00:00Z"}
    ]
    job.interpretation_dossier = valid_dossier
    job.save(update_fields=["interpretation_dossier"])

    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert job.has_valid_ready_dossier() is True

    prepare_calls = 0
    real_prepare = CurriculumSourceInterpreter.prepare

    def counting_prepare(*args, **kwargs):
        nonlocal prepare_calls
        prepare_calls += 1
        return real_prepare(*args, **kwargs)

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=counting_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    assert prepare_calls == 1, f"Expected prepare() to be called exactly 1 time, got {prepare_calls}"

    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier() is True
    # Audit history from prior dossier must be preserved/merged
    history_actions = [h.get("action") for h in job.interpretation_dossier.get("history", [])]
    assert "previous_attempt" in history_actions


def test_retry_rejects_tampered_parseable_pdf_when_prior_dossier_exists():
    """B3 causal verification: If prior evidence/dossier exists, POST retry must verify
    that the physical PDF SHA matches source_sha256 in prior evidence.
    Replacing the file with a different parseable PDF must fail-closed WITHOUT calling prepare(),
    WITHOUT erasing or overwriting the prior dossier, and persist an integrity alert."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-b3-tamper-teacher")
    owner = get_user_model().objects.get(username="t3-b3-tamper-teacher")

    job = _create_failed_job(owner, error_msg="Error antes de tamper")
    original_dossier = _valid_dossier_dict_for_job(job)
    job.interpretation_dossier = original_dossier
    job.save(update_fields=["interpretation_dossier"])
    original_sha = original_dossier["source_sha256"]

    # Now replace the PDF with a different, valid parseable PDF
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buf)
    tampered_pdf_bytes = buf.getvalue()
    tampered_sha = hashlib.sha256(tampered_pdf_bytes).hexdigest()
    assert tampered_sha != original_sha

    # Overwrite the physical PDF file with tampered PDF
    with open(job.pdf.path, "wb") as f:
        f.write(tampered_pdf_bytes)

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    snap_before = {
        "status": job.status,
        "interpretation_state": job.interpretation_state,
        "interpretation_claim_token": job.interpretation_claim_token,
        "interpretation_error_message": job.interpretation_error_message,
        "interpretation_dossier": job.interpretation_dossier,
        "updated_at": job.updated_at,
    }

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code == 409
    assert "reextracción explícita" in resp.content.decode("utf-8").lower()
    # Fail-closed: prepare() must NOT be called!
    assert not prepare_called, "prepare() must NEVER be called when source PDF does not match prior evidence!"

    job.refresh_from_db()
    snap_after = {
        "status": job.status,
        "interpretation_state": job.interpretation_state,
        "interpretation_claim_token": job.interpretation_claim_token,
        "interpretation_error_message": job.interpretation_error_message,
        "interpretation_dossier": job.interpretation_dossier,
        "updated_at": job.updated_at,
    }
    # Zero DB mutation: snapshot before == snapshot after!
    assert snap_after == snap_before

    # Prior evidence is preserved byte-for-byte; NOT updated to tampered_sha
    assert job.interpretation_dossier["source_sha256"] == original_sha
    assert job.interpretation_dossier["source_sha256"] != tampered_sha


def test_retry_toctou_tamper_during_worker_execution_fails_closed():
    """B3 TOCTOU verification: If the PDF on disk is tampered while prepare() is executing,
    the retry command detects the SHA mismatch upon completion via physical disk rehash,
    fails closed with finish_worker_failure, releases the claim, and reports the TOCTOU alert.
    The mock returns the EXPECTED original SHA to prove that the final physical rehash
    is what detects the tamper."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-b3-toctou-teacher")
    owner = get_user_model().objects.get(username="t3-b3-toctou-teacher")

    job = _create_failed_job(owner, error_msg="Error inicial antes de TOCTOU")
    with job.pdf.open("rb") as s:
        expected_original_sha = hashlib.sha256(s.read()).hexdigest().lower()

    def tampering_prepare(fresh_job, *args, **kwargs):
        # Tamper ONLY the file on disk during execution of prepare
        buf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.write(buf)
        with open(fresh_job.pdf.path, "wb") as f:
            f.write(buf.getvalue())
        # Return a mock dossier reporting the EXPECTED original SHA
        # This isolates and proves that the physical rehash check catches the tamper!
        return ImportDossier(
            version=1,
            status="active",
            source_sha256=expected_original_sha,
            source_name=Path(fresh_job.pdf.name).name,
            page_count=1,
            history=[],
        )

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=tampering_prepare):
        retry_url = reverse("tutor-import-retry", args=[job.pk])
        resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    job.refresh_from_db()
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_FAILED
    assert "alterado durante el procesamiento" in job.interpretation_error_message
    assert job.interpretation_claim_token is None


def test_retry_race_foreign_claim_inserted_before_claim_attempt_leaves_foreign_claim_intact():
    """B3 causal verification: If a foreign recent claim is acquired right after the initial read,
    the CAS claim attempt fails (0 rows claimed). Retry does NOT perform any mutation:
    it does NOT overwrite the foreign claim token, does NOT set FAILED, does NOT clear dossier,
    and does NOT call prepare()."""
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-foreign-claim-race-teacher")
    owner = get_user_model().objects.get(username="t3-foreign-claim-race-teacher")

    job = _create_failed_job(owner, with_dossier=True)
    initial_dossier = dict(job.interpretation_dossier)

    foreign_token = uuid.uuid4()
    foreign_claimed_at = timezone.now()

    prepare_called = False

    def mock_prepare(*args, **kwargs):
        nonlocal prepare_called
        prepare_called = True
        return None

    from curriculum import interpretation_commands
    original_claim_worker = interpretation_commands.claim_interpretation_worker

    def race_claim_worker(fresh_job, *args, **kwargs):
        # Simulate race: right before the CAS claim executes, another worker acquires a recent claim
        CurriculumImportJob.objects.filter(pk=fresh_job.pk).update(
            interpretation_claim_token=foreign_token,
            interpretation_claimed_at=foreign_claimed_at,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
            progress_stage="interpreting",
        )
        return original_claim_worker(fresh_job, *args, **kwargs)

    with patch.object(CurriculumSourceInterpreter, "prepare", side_effect=mock_prepare):
        with patch.object(interpretation_commands, "claim_interpretation_worker", side_effect=race_claim_worker):
            retry_url = reverse("tutor-import-retry", args=[job.pk])
            resp = client.post(retry_url)

    assert resp.status_code in (302, 303)
    assert not prepare_called, "prepare() must NEVER be called when claim was lost to foreign worker!"

    job.refresh_from_db()
    # Foreign token and organizing state MUST remain intact!
    assert job.interpretation_claim_token == foreign_token
    assert job.interpretation_claimed_at == foreign_claimed_at
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING
    # Dossier must be preserved exactly
    assert job.interpretation_dossier == initial_dossier


# =========================================================================
# 7. Copy Separation & JS DOM Polling Transitions
# =========================================================================

def test_wait_view_active_vs_failed_copy_separation():
    """Causal verification of copy separation in tutor_import_wait view:
    1. Active organizing state:
       - Active notice 'Puedes dejar esta página abierta: al terminar continuarás automáticamente'
         is VISIBLE (no hidden attribute).
       - Failed guide 'El proceso se detuvo' and error container are HIDDEN.
    2. Active delayed state:
       - Active notice is VISIBLE (no hidden attribute).
       - Failed guide and error container are HIDDEN.
    3. FAILED state:
       - Active notice is HIDDEN (has hidden attribute).
       - Failed guide 'El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento.'
         is VISIBLE (no hidden attribute).
       - Error container is VISIBLE (no hidden attribute).
       - Retry form is present with CSRF.
    """
    from bs4 import BeautifulSoup
    from django.contrib.auth import get_user_model
    client = tutor_client("t3-copy-separation-teacher")
    owner = get_user_model().objects.get(username="t3-copy-separation-teacher")

    # 1. Active organizing state
    job_organizing = _create_failed_job(owner)
    CurriculumImportJob.objects.filter(pk=job_organizing.pk).update(
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        progress_stage="interpreting",
        interpretation_error_message="",
        error_message="",
    )
    resp_org = client.get(reverse("tutor-import-wait", args=[job_organizing.pk]))
    assert resp_org.status_code == 200
    soup_org = BeautifulSoup(resp_org.content.decode("utf-8"), "html.parser")

    active_notice_org = soup_org.find(id="assistant-active-notice")
    assert active_notice_org is not None
    assert not active_notice_org.has_attr("hidden"), "Active notice must be visible during organizing"
    assert "al terminar continuarás automáticamente" in active_notice_org.get_text()
    assert "se detuvo" not in resp_org.content.decode("utf-8")

    failed_guide_org = soup_org.find(id="assistant-failed-guide")
    assert failed_guide_org is not None
    assert failed_guide_org.has_attr("hidden"), "Failed guide must be hidden during organizing"

    error_cont_org = soup_org.find(id="assistant-error-container")
    assert error_cont_org is not None
    assert error_cont_org.has_attr("hidden"), "Error container must be hidden during organizing"

    # 2. Active delayed state (stale/delayed)
    job_delayed = _create_failed_job(owner)
    CurriculumImportJob.objects.filter(pk=job_delayed.pk).update(
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        progress_stage="interpreting",
        interpretation_claimed_at=timezone.now() - timedelta(minutes=15),
        interpretation_error_message="",
        error_message="",
    )
    resp_del = client.get(reverse("tutor-import-wait", args=[job_delayed.pk]))
    assert resp_del.status_code == 200
    assert "se detuvo" not in resp_del.content.decode("utf-8")
    soup_del = BeautifulSoup(resp_del.content.decode("utf-8"), "html.parser")

    active_notice_del = soup_del.find(id="assistant-active-notice")
    assert active_notice_del is not None
    assert not active_notice_del.has_attr("hidden"), "Active notice must be visible during delayed state"
    assert "al terminar continuarás automáticamente" in active_notice_del.get_text()

    failed_guide_del = soup_del.find(id="assistant-failed-guide")
    assert failed_guide_del is not None
    assert failed_guide_del.has_attr("hidden"), "Failed guide must be hidden during delayed state"

    error_cont_del = soup_del.find(id="assistant-error-container")
    assert error_cont_del is not None
    assert error_cont_del.has_attr("hidden"), "Error container must be hidden during delayed state"

    # 3. FAILED state
    job_failed = _create_failed_job(owner, error_msg="Error de procesamiento de prueba")
    resp_failed = client.get(reverse("tutor-import-wait", args=[job_failed.pk]))
    assert resp_failed.status_code == 200
    raw_failed_html = resp_failed.content.decode("utf-8")
    assert "se detuvo" in raw_failed_html
    assert "Puedes dejar esta página abierta" not in raw_failed_html
    soup_failed = BeautifulSoup(raw_failed_html, "html.parser")

    active_notice_failed = soup_failed.find(id="assistant-active-notice")
    assert active_notice_failed is not None
    assert active_notice_failed.has_attr("hidden"), "Active notice MUST have hidden attribute in FAILED state"

    failed_guide_failed = soup_failed.find(id="assistant-failed-guide")
    assert failed_guide_failed is not None
    assert not failed_guide_failed.has_attr("hidden"), "Failed guide MUST be visible in FAILED state"
    assert "El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento." in failed_guide_failed.get_text()

    error_cont_failed = soup_failed.find(id="assistant-error-container")
    assert error_cont_failed is not None
    assert not error_cont_failed.has_attr("hidden"), "Error container MUST be visible in FAILED state"
    assert error_cont_failed.get("role") == "alert"

    retry_btn = soup_failed.find(id="retry-organization-btn")
    assert retry_btn is not None
    assert retry_btn.get_text().strip() == "Volver a intentar"


def test_assistant_progress_js_dom_transitions():
    """Causal verification of client-side assistant_progress.js DOM transitions:
    - Active to FAILED polling transition:
      * #assistant-active-notice gets hidden = true
      * #assistant-progress-counter gets hidden = true
      * #assistant-failed-guide gets hidden = false
      * #assistant-error-container gets hidden = false
      * #retry-organization-btn receives focus
    - Error to Active polling transition (retry):
      * #assistant-active-notice gets hidden = false
      * #assistant-failed-guide gets hidden = true
      * #assistant-error-container gets hidden = true
    """
    import json
    import subprocess

    node_script = """
const fs = require("fs");
const vm = require("vm");

class Element {
  constructor(id, attrs = {}) {
    this.id = id;
    this.hidden = attrs.hidden || false;
    this.textContent = attrs.textContent || "";
    this.dataset = attrs.dataset || {};
    this.focused = false;
  }
  focus() { this.focused = true; }
}

const elements = {
  "[data-status-url]": new Element("indicator", { dataset: { statusUrl: "/status" } }),
  "#assistant-status-label": new Element("status-label"),
  "#assistant-progress-counter": new Element("counter", { hidden: false }),
  "#assistant-active-notice": new Element("active-notice", { hidden: false }),
  "#assistant-failed-guide": new Element("failed-guide", { hidden: true }),
  "#assistant-error-container": new Element("error-container", { hidden: true }),
  "#assistant-live-error": new Element("live-error"),
  "#assistant-retry-form": new Element("retry-form", { hidden: true }),
  "#retry-organization-btn": new Element("retry-btn"),
  "#assistant-retry-link": new Element("retry-link", { hidden: true }),
};

const document = {
  querySelector(sel) { return elements[sel] || null; }
};

let currentResponse = {
  ok: true,
  json: async () => ({ state: "error", interpretation_state: "failed", error: "Error de prueba" })
};

let pollFn = null;
const window = {
  setTimeout: (fn, ms) => {
    pollFn = fn;
    return 1;
  },
  location: { assign: () => {} }
};

const code = fs.readFileSync("static/curriculum/assistant_progress.js", "utf8");
vm.runInNewContext(code, {
  document,
  window,
  fetch: async () => currentResponse,
  console
});

(async () => {
  const results = {};
  results.initial = {
    activeHidden: elements["#assistant-active-notice"].hidden,
    counterHidden: elements["#assistant-progress-counter"].hidden,
    failedGuideHidden: elements["#assistant-failed-guide"].hidden,
    errorContainerHidden: elements["#assistant-error-container"].hidden,
  };

  // 1. Transition to error
  await pollFn();
  results.afterError = {
    activeHidden: elements["#assistant-active-notice"].hidden,
    counterHidden: elements["#assistant-progress-counter"].hidden,
    failedGuideHidden: elements["#assistant-failed-guide"].hidden,
    errorContainerHidden: elements["#assistant-error-container"].hidden,
    retryFocused: elements["#retry-organization-btn"].focused,
    liveError: elements["#assistant-live-error"].textContent,
  };

  // 2. Transition back to active
  currentResponse = {
    ok: true,
    json: async () => ({ state: "organizing", label: "Organizando...", done: 2, total: 10 })
  };
  await pollFn();
  results.afterActive = {
    activeHidden: elements["#assistant-active-notice"].hidden,
    failedGuideHidden: elements["#assistant-failed-guide"].hidden,
    errorContainerHidden: elements["#assistant-error-container"].hidden,
  };

  console.log(JSON.stringify(results));
})();
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)

    assert data["initial"]["activeHidden"] is False
    assert data["initial"]["counterHidden"] is False
    assert data["initial"]["failedGuideHidden"] is True
    assert data["initial"]["errorContainerHidden"] is True

    assert data["afterError"]["activeHidden"] is True
    assert data["afterError"]["counterHidden"] is True
    assert data["afterError"]["failedGuideHidden"] is False
    assert data["afterError"]["errorContainerHidden"] is False
    assert data["afterError"]["retryFocused"] is True
    assert data["afterError"]["liveError"] == "Error de prueba"

    assert data["afterActive"]["activeHidden"] is False
    assert data["afterActive"]["failedGuideHidden"] is True
    assert data["afterActive"]["errorContainerHidden"] is True
