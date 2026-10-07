"""Synthetic persistence contracts for worker completion; no private PDF inputs."""

import hashlib
import io
import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone

from curriculum import interpretation_commands, verification
from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import (
    ImportDossier, InterpretedField, SessionPlan, STATUS_MISSING,
    REQUIRED_GENERAL_FIELDS, REQUIRED_SESSION_FIELDS,
)
from helpers import MINIMAL_VALID_PDF_BYTES


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def worker():
    token = uuid.uuid4()
    now = timezone.now()
    dossier = ImportDossier(
        source_sha256=hashlib.sha256(MINIMAL_VALID_PDF_BYTES).hexdigest(),
        source_name="synthetic.pdf",
        page_count=1,
        general_fields={
            name: InterpretedField(name, "", status=STATUS_MISSING)
            for name in REQUIRED_GENERAL_FIELDS
        },
        sessions=[SessionPlan(
            "session-1", 1, "Sesión sintética", pages=[1],
            fields={
                name: InterpretedField(name, "", status=STATUS_MISSING)
                for name in REQUIRED_SESSION_FIELDS
            },
        )],
    )
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("synthetic.pdf", MINIMAL_VALID_PDF_BYTES),
        interpretation_claim_token=token,
        interpretation_claimed_at=now - timedelta(seconds=1),
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        interpretation_dossier={"history": [{"action": "prior teacher decision"}]},
        interpretation_error_message="Prior interpretation error",
        error_message="Legacy stage error",
        progress_stage="interpreting",
        progress_started_at=now - timedelta(seconds=2),
        progress_done=3,
        progress_total=5,
        page_count=5,
    )
    return job, token, dossier, now


FAILURES = [
    ("initial_read", "No se pudo leer el archivo PDF original de la planeación."),
    ("blocked_report", "La planeación contiene inconsistencias físicas o citas contradictorias con el PDF."),
    ("missing_report", "La planeación contiene inconsistencias físicas o citas contradictorias con el PDF."),
    ("verification_error", "La planeación contiene inconsistencias físicas o citas contradictorias con el PDF."),
    ("invalid_integrity", "Dossier generado no cumple el contrato de integridad física."),
    ("changed_source", "El archivo PDF fue modificado concurrentemente durante la operación."),
    ("final_read", "No se pudo comprobar el archivo PDF antes de persistir."),
]


@pytest.mark.parametrize("failure,message", FAILURES, ids=[row[0] for row in FAILURES])
@pytest.mark.parametrize("owns_claim", [True, False], ids=["owner", "foreign-owner"])
def test_rejected_completion_preserves_prior_dossier_and_claim_ownership(
    worker, monkeypatch, failure, message, owns_claim,
):
    job, token, dossier, now = worker
    if not owns_claim:
        # The in-memory worker still holds its old token after a successor claims.
        CurriculumImportJob.objects.filter(pk=job.pk).update(
            interpretation_claim_token=uuid.uuid4(),
        )
    before = CurriculumImportJob.objects.values().get(pk=job.pk)

    reads = []

    def read_source(mode):
        assert mode == "rb"
        reads.append(connection.in_atomic_block)
        if failure == "initial_read" or (failure == "final_read" and len(reads) == 2):
            raise OSError("Injected synthetic storage failure")
        if failure == "changed_source" and len(reads) == 2:
            return io.BytesIO(MINIMAL_VALID_PDF_BYTES + b"\n% changed source\n")
        return io.BytesIO(MINIMAL_VALID_PDF_BYTES)

    monkeypatch.setattr(job.pdf, "open", read_source)
    if failure == "blocked_report":
        monkeypatch.setattr(
            verification, "verify_curriculum_dossier",
            lambda *args: verification.VerificationReport(is_valid=False, blocked_count=1),
        )
    elif failure == "missing_report":
        monkeypatch.setattr(verification, "verify_curriculum_dossier", lambda *args: None)
    elif failure == "verification_error":
        def reject_verification(*args):
            raise RuntimeError("Injected synthetic verification failure")

        monkeypatch.setattr(verification, "verify_curriculum_dossier", reject_verification)
    elif failure == "invalid_integrity":
        monkeypatch.setattr(
            interpretation_commands, "validate_ready_dossier_integrity",
            lambda *args, **kwargs: False,
        )

    rows = interpretation_commands.finish_worker_success(job, token, dossier, now=now)

    expected = dict(before)
    if owns_claim:
        expected.update(
            interpretation_claim_token=None,
            interpretation_claimed_at=None,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
            interpretation_error_message=message,
            progress_stage="",
            progress_finished_at=now,
            updated_at=now,
        )
    assert rows == int(owns_claim)
    assert CurriculumImportJob.objects.values().get(pk=job.pk) == expected
    assert reads == ([False, True] if failure in {"changed_source", "final_read"} else [False])


def test_valid_completion_persists_real_canonical_report(worker):
    job, token, dossier, now = worker
    rows = interpretation_commands.finish_worker_success(job, token, dossier, now=now)

    job.refresh_from_db()
    assert rows == 1
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.interpretation_claim_token is None
    assert job.interpretation_claimed_at is None
    assert job.interpretation_error_message == ""
    assert job.error_message == "Legacy stage error"
    assert job.progress_finished_at == now
    assert job.updated_at == now
    assert job.page_count == job.progress_done == job.progress_total == 1
    assert job.interpretation_dossier["history"] == [{"action": "prior teacher decision"}]
    assert job.has_valid_ready_dossier()


@pytest.mark.parametrize("token", [None, "", "not-a-uuid"])
def test_invalid_token_does_not_read_source_or_change_job(worker, monkeypatch, token):
    job, _, dossier, now = worker
    before = CurriculumImportJob.objects.values().get(pk=job.pk)

    def unexpected_read(*args):
        pytest.fail("Invalid owner token must be rejected before reading storage")

    monkeypatch.setattr(job.pdf, "open", unexpected_read)
    with pytest.raises(ValueError, match="owner_token must be a valid"):
        interpretation_commands.finish_worker_success(job, token, dossier, now=now)
    assert CurriculumImportJob.objects.values().get(pk=job.pk) == before
