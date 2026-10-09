"""
curriculum.interpretation_commands
----------------------------------
Deep command module defining the single, unified policy for all mutations
and CAS transitions of the V0 curriculum interpretation lifecycle.

Enforces:
- Predicated CAS updates on owner_token for workers.
- Fail-closed validation before persisting READY.
- Complete independence of interpretation and legacy pipeline stages.
- Reextract failures persisting FAILED while preserving dossier in DB.
- Cancellation safety without clobbering foreign or new claim tokens.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import timedelta
from typing import Any, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from curriculum.source_interpreter import CurriculumInterpretationError

logger = logging.getLogger(__name__)

HEX_64_REGEX = re.compile(r"^[0-9a-fA-F]{64}$")


class ReextractRequired(CurriculumInterpretationError):
    """Raised when an interpretation retry cannot proceed because the underlying
    source file has changed, is missing, or does not match the prior recorded dossier identity.
    An explicit re-extraction is required."""
    pass


def validate_claim_token(token: Any) -> uuid.UUID:
    """Validate that token is a valid, non-null UUID or UUID string.
    Raises ValueError if token is None, empty, or not a valid UUID."""
    if token is None:
        raise ValueError("owner_token must be a valid, non-null UUID")
    if isinstance(token, uuid.UUID):
        return token
    if isinstance(token, str):
        token_str = token.strip()
        if not token_str:
            raise ValueError("owner_token must be a valid, non-empty UUID string")
        try:
            return uuid.UUID(token_str)
        except (ValueError, AttributeError):
            raise ValueError(f"owner_token must be a valid UUID: {token!r}")
    raise ValueError(f"owner_token must be a valid UUID or string UUID, got {type(token).__name__}")


def validate_ready_dossier_integrity(job, dossier_dict: dict, pdf_bytes: bytes | None = None) -> bool:
    """Validate that dossier_dict conforms strictly to the active ready contract
    and matches the physical storage file of the given job.
    Strictly requires a fresh, canonical, and valid verification report."""
    if not isinstance(dossier_dict, dict) or not dossier_dict:
        return False
    version = dossier_dict.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return False
    if dossier_dict.get("status") != "active":
        return False
    source_sha = dossier_dict.get("source_sha256")
    if not isinstance(source_sha, str) or not bool(HEX_64_REGEX.match(source_sha.strip())):
        return False
    if not getattr(job, "pdf", None) or not getattr(job.pdf, "name", None):
        return False
    try:
        if pdf_bytes is None:
            with job.pdf.open("rb") as stream:
                pdf_bytes = stream.read()
        current_sha = hashlib.sha256(pdf_bytes).hexdigest()
        if current_sha.lower() != source_sha.strip().lower():
            return False
    except Exception:
        return False

    report = dossier_dict.get("verification_report")
    if not isinstance(report, dict) or not report:
        return False

    from curriculum.verification import validate_canonical_verification_report

    if not validate_canonical_verification_report(dossier_dict, pdf_bytes, report):
        return False

    return True


def claim_interpretation_worker(
    job,
    owner_token: Any,
    stale_threshold: Optional[timedelta] = None,
    now=None,
    allow_retry: bool = False,
) -> int:
    """Attempt CAS claim to organize interpretation for job.
    Rejects None, empty, or invalid owner_token before executing UPDATE."""
    from curriculum.models import CurriculumImportJob

    owner_token = validate_claim_token(owner_token)

    if now is None:
        now = timezone.now()
    if stale_threshold is None:
        stale_threshold = timedelta(minutes=90)
    cutoff = now - stale_threshold
    claim_filter = (
        Q(interpretation_claim_token__isnull=True)
        | Q(interpretation_claimed_at__lte=cutoff)
    )

    qs = CurriculumImportJob.objects.filter(pk=job.pk).filter(claim_filter)
    if not allow_retry:
        qs = qs.filter(
            Q(interpretation_dossier={})
            | Q(interpretation_dossier__isnull=True)
            | Q(interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED)
        )

    return qs.update(
        interpretation_claim_token=owner_token,
        interpretation_claimed_at=now,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        progress_stage="interpreting",
        progress_started_at=now,
        progress_finished_at=None,
        interpretation_error_message="",
        cancel_requested=False,
        cancelled_at=None,
        updated_at=now,
    )


def finish_worker_success(job, owner_token: Any, dossier, now=None) -> int:
    """CAS update: Worker successfully prepared a dossier.
    Validates dossier integrity before persisting READY. If invalid, fails closed to FAILED."""
    from curriculum.models import CurriculumImportJob
    from curriculum.verification import verify_curriculum_dossier

    owner_token = validate_claim_token(owner_token)

    if now is None:
        now = timezone.now()

    dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else dict(dossier)
    page_count = getattr(dossier, "page_count", None)

    # Preserve any prior audit history from existing dossier across retries
    if isinstance(job.interpretation_dossier, dict):
        prior_history = job.interpretation_dossier.get("history")
        if isinstance(prior_history, list) and prior_history:
            new_history = dossier_dict.get("history", [])
            combined = [h for h in prior_history if h not in new_history] + new_history
            dossier_dict["history"] = combined

    # Single read of physical PDF immediately before CAS update
    try:
        with job.pdf.open("rb") as stream:
            pdf_bytes = stream.read()
    except Exception as read_exc:
        logger.warning("No se pudo leer el archivo PDF en finish_worker_success: %s", read_exc)
        return finish_worker_failure(
            job,
            owner_token=owner_token,
            error_message="No se pudo leer el archivo PDF original de la planeación.",
            now=now,
        )

    # Run deterministic mechanical verification against physical PDF
    try:
        report = verify_curriculum_dossier(dossier, pdf_bytes)
    except Exception as v_exc:
        logger.warning("Error ejecutando verificación en finish_worker_success: %s", v_exc)
        report = None

    if report is None or not report.is_valid or report.blocked_count > 0:
        logger.warning(
            "Worker con token %s produjo un dossier con inconsistencias físicas (bloqueos=%s) en job %s",
            owner_token,
            getattr(report, "blocked_count", -1),
            job.pk,
        )
        return finish_worker_failure(
            job,
            owner_token=owner_token,
            error_message="La planeación contiene inconsistencias físicas o citas contradictorias con el PDF.",
            now=now,
        )

    dossier_dict["verification_report"] = report.to_dict()
    if hasattr(dossier, "verification_report"):
        dossier.verification_report = report.to_dict()

    if not validate_ready_dossier_integrity(job, dossier_dict, pdf_bytes=pdf_bytes):
        logger.warning(
            "Worker con token %s produjo un dossier que no cumple la validación física en job %s",
            owner_token,
            job.pk,
        )
        return finish_worker_failure(
            job,
            owner_token=owner_token,
            error_message="Dossier generado no cumple el contrato de integridad física.",
            now=now,
        )

    with transaction.atomic():
        # Final physical rehash immediately before CAS update to catch tamper interleaving
        # FS can change después y GET guard lo detecta.
        if getattr(job, "pdf", None):
            try:
                with job.pdf.open("rb") as stream:
                    final_bytes = stream.read()
                final_sha = hashlib.sha256(final_bytes).hexdigest()
                current_pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
                if final_sha.lower() != current_pdf_sha.lower():
                    logger.warning("Tamper interleaving detected in finish_worker_success for job %s", job.pk)
                    return finish_worker_failure(
                        job,
                        owner_token=owner_token,
                        error_message="El archivo PDF fue modificado concurrentemente durante la operación.",
                        now=now,
                    )
            except Exception as final_exc:
                logger.warning("Error re-leyendo PDF antes de CAS en finish_worker_success: %s", final_exc)
                return finish_worker_failure(
                    job,
                    owner_token=owner_token,
                    error_message="No se pudo comprobar el archivo PDF antes de persistir.",
                    now=now,
                )

        return (
            CurriculumImportJob.objects.filter(pk=job.pk)
            .filter(interpretation_claim_token=owner_token)
            .update(
                interpretation_dossier=dossier_dict,
                interpretation_claim_token=None,
                interpretation_claimed_at=None,
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
                progress_stage="",
                progress_finished_at=now,
                page_count=page_count,
                progress_done=page_count or 0,
                progress_total=page_count or 0,
                interpretation_error_message="",
                updated_at=now,
            )
        )

def finish_worker_failure(
    job,
    owner_token: Any,
    error_message: str,
    is_cancelled: bool = False,
    now=None,
) -> int:
    """CAS update: Worker failed or was cancelled.
    Updates only if interpretation_claim_token matches owner_token."""
    from curriculum.models import CurriculumImportJob

    owner_token = validate_claim_token(owner_token)

    if now is None:
        now = timezone.now()

    update_fields = {
        "interpretation_claim_token": None,
        "interpretation_claimed_at": None,
        "interpretation_state": CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        "progress_stage": "",
        "progress_finished_at": now,
        "interpretation_error_message": error_message,
        "updated_at": now,
    }
    if is_cancelled:
        update_fields["cancelled_at"] = now

    return (
        CurriculumImportJob.objects.filter(pk=job.pk)
        .filter(interpretation_claim_token=owner_token)
        .update(**update_fields)
    )


def record_upload_outer_failure(job, error_message: str, now=None) -> int:
    """Conditional update for upload outer except:
    Only update if the job is still in NOT_STARTED and has NO active claim token.
    If another owner already transitioned it to READY or claimed ORGANIZING,
    do NOT overwrite foreign state!"""
    from curriculum.models import CurriculumImportJob

    if now is None:
        now = timezone.now()

    return (
        CurriculumImportJob.objects.filter(
            pk=job.pk,
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
            interpretation_claim_token__isnull=True,
        ).update(
            interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
            interpretation_error_message=error_message,
            updated_at=now,
        )
    )


def record_reextract_failure(
    job,
    error_message: str,
    current_pdf_sha256: str = "",
    dossier=None,
    now=None,
) -> int:
    """Failed reextract: persist FAILED conditioned on job not having foreign claim
    so GET status reports error / no review (even if old dossier remains in DB)."""
    from curriculum.models import CurriculumImportJob

    if now is None:
        now = timezone.now()

    qs = CurriculumImportJob.objects.filter(pk=job.pk)
    qs = qs.filter(interpretation_claim_token__isnull=True)

    update_kwargs: dict[str, Any] = {
        "progress_stage": "",
        "interpretation_error_message": error_message,
        "interpretation_state": CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        "updated_at": now,
    }

    if dossier and current_pdf_sha256 and current_pdf_sha256 != getattr(dossier, "source_sha256", ""):
        dossier.status = "invalidated"
        update_kwargs["interpretation_dossier"] = (
            dossier.to_dict() if hasattr(dossier, "to_dict") else dict(dossier)
        )

    rows = qs.update(**update_kwargs)
    job.refresh_from_db()
    return rows


def finish_cancelled_stage(
    job,
    expected_claim_token: Optional[Any] = None,
    now=None,
) -> int:
    """Finish cooperative cancellation safely:
    - If expected_claim_token is provided: updates ONLY if interpretation_claim_token matches.
    - If no claim token is provided: updates ONLY if interpretation_claim_token is null.
      Total NO-OP if an active claim is present in DB (returns 0 without touching any fields)."""
    from curriculum.models import CurriculumImportJob

    if expected_claim_token is not None:
        expected_claim_token = validate_claim_token(expected_claim_token)

    if now is None:
        now = timezone.now()

    legacy_updates = {
        "progress_stage": "",
        "progress_finished_at": now,
        "cancelled_at": now,
        "updated_at": now,
    }

    if expected_claim_token:
        return (
            CurriculumImportJob.objects.filter(
                pk=job.pk,
                cancel_requested=True,
                interpretation_claim_token=expected_claim_token,
            ).update(
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
                interpretation_claim_token=None,
                interpretation_claimed_at=None,
                interpretation_error_message="La ayuda del asistente fue cancelada. Lo ya guardado sigue en revisión.",
                **legacy_updates,
            )
        )
    else:
        # Without expected claim token:
        # Attempt to mark failed ONLY if there is no active claim token in the DB.
        # If an active claim is present, rows is 0 and it is a total NO-OP.
        return (
            CurriculumImportJob.objects.filter(
                pk=job.pk,
                cancel_requested=True,
                interpretation_claim_token__isnull=True,
            ).update(
                interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
                interpretation_error_message="La ayuda del asistente fue cancelada. Lo ya guardado sigue en revisión.",
                **legacy_updates,
            )
        )


def reconcile_existing_ready_dossier(job, now=None) -> int:
    """Fast reconciliation for a job that already has a valid ready dossier in DB.
    Only updates state to READY if interpretation_claim_token is NULL.
    If a foreign claim is active, does NOT clear the claim token."""
    from curriculum.models import CurriculumImportJob

    if now is None:
        now = timezone.now()

    return CurriculumImportJob.objects.filter(
        pk=job.pk,
        interpretation_claim_token__isnull=True,
    ).update(
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        interpretation_error_message="",
        updated_at=now,
    )


def save_interpretation_dossier_command(
    job,
    dossier,
    explicit_state=None,
    error_message=None,
    owner_token: Optional[Any] = None,
    now=None,
) -> str:
    """Persist a versioned ImportDossier and derive/persist interpretation_state atomically.

    Single unified command for all dossier saves:
    - Structural active dossier matching source PDF -> READY.
    - Invalidated, tampered, or explicit failure status -> FAILED.
    - Corrupt / empty without valid structure -> NOT_STARTED.
    - Concurrency:
      - If owner_token provided: updates conditioned on interpretation_claim_token=owner_token.
      - If owner_token is None:
        - If active claim exists in DB: raises CurriculumInterpretationError (concurrency conflict)
          without altering DB.
        - If no active claim: updates conditioned on interpretation_claim_token__isnull=True.
    """
    from curriculum.models import CurriculumImportJob
    from curriculum.source_interpreter import CurriculumInterpretationError

    if owner_token is not None:
        owner_token = validate_claim_token(owner_token)

    if now is None:
        now = timezone.now()

    if hasattr(dossier, "to_dict"):
        dossier_dict = dossier.to_dict()
    elif isinstance(dossier, dict):
        dossier_dict = dict(dossier)
    else:
        dossier_dict = {}

    status_val = dossier_dict.get("status") if isinstance(dossier_dict, dict) else ""
    target_state = None
    if status_val in ("invalidated_source_tampered", "invalidated", "failed"):
        target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
    elif explicit_state in (
        CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        CurriculumImportJob.INTERPRETATION_STATE_ORGANIZING,
        CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED,
    ):
        target_state = explicit_state
    else:
        # Editorial no-op check: if dossier_dict is identical to current interpretation_dossier
        current_dossier = job.interpretation_dossier
        is_noop = (
            current_dossier == dossier_dict
            and explicit_state is None
            and owner_token is None
        )
        if not is_noop and isinstance(current_dossier, dict) and explicit_state is None and owner_token is None:
            try:
                from curriculum.source_interpreter import ImportDossier
                curr_obj = ImportDossier.from_dict(current_dossier)
                target_obj = ImportDossier.from_dict(dossier_dict)
                if curr_obj.to_dict() == target_obj.to_dict():
                    is_noop = True
            except Exception:
                pass

        if is_noop:
            return job.interpretation_state

        # ALWAYS compute/verify canonical report against physical PDF before READY
        pdf_bytes = None
        if getattr(job, "pdf", None):
            try:
                with job.pdf.open("rb") as stream:
                    pdf_bytes = stream.read()
            except Exception as read_exc:
                logger.warning("No se pudo leer el archivo PDF en save_interpretation_dossier_command: %s", read_exc)
                target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
                error_message = "No se pudo leer el archivo PDF original de la planeación."

        if target_state is None and pdf_bytes is not None:
            from curriculum.verification import verify_curriculum_dossier
            try:
                rep_obj = verify_curriculum_dossier(dossier_dict, pdf_bytes)
                if rep_obj.blocked_count > 0:
                    target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
                    error_message = "La planeación contiene inconsistencias físicas o citas contradictorias con el PDF."
                else:
                    dossier_dict["verification_report"] = rep_obj.to_dict()
                    if hasattr(dossier, "verification_report"):
                        dossier.verification_report = rep_obj.to_dict()
                    if validate_ready_dossier_integrity(job, dossier_dict, pdf_bytes=pdf_bytes):
                        target_state = CurriculumImportJob.INTERPRETATION_STATE_READY
                    else:
                        target_state = CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED
            except Exception as v_exc:
                logger.warning("Fallo al verificar en save_interpretation_dossier_command: %s", v_exc)
                target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
                error_message = "No se pudo comprobar la integridad del documento contra el PDF."
        elif target_state is None:
            target_state = CurriculumImportJob.INTERPRETATION_STATE_NOT_STARTED

    if owner_token is not None:
        qs = CurriculumImportJob.objects.filter(pk=job.pk, interpretation_claim_token=owner_token)
    else:
        active_claim = (
            CurriculumImportJob.objects.filter(pk=job.pk)
            .values_list("interpretation_claim_token", flat=True)
            .first()
        )
        if active_claim is not None:
            raise CurriculumInterpretationError(
                f"Conflicto de concurrencia: el trabajo #{job.pk} tiene un reclamo activo "
                f"(token={active_claim}) y no puede modificarse sin el token de reclamo."
            )
        qs = CurriculumImportJob.objects.filter(pk=job.pk, interpretation_claim_token__isnull=True)

    current_pdf_sha256 = ""
    if pdf_bytes is not None:
        current_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    dossier_sha = dossier_dict.get("source_sha256", "") if isinstance(dossier_dict, dict) else ""
    source_tampered = bool(
        current_pdf_sha256 and dossier_sha and dossier_sha.lower() != current_pdf_sha256.lower()
    )

    update_fields: dict[str, Any] = {
        "interpretation_state": target_state,
        "updated_at": now,
    }
    # Blocked/failed verification must NOT overwrite the prior valid dossier in DB
    if target_state != CurriculumImportJob.INTERPRETATION_STATE_FAILED:
        update_fields["interpretation_dossier"] = dossier_dict

    if target_state in (
        CurriculumImportJob.INTERPRETATION_STATE_READY,
        CurriculumImportJob.INTERPRETATION_STATE_FAILED,
    ):
        update_fields["interpretation_claim_token"] = None
        update_fields["interpretation_claimed_at"] = None

    if error_message is not None:
        update_fields["interpretation_error_message"] = error_message
    elif target_state == CurriculumImportJob.INTERPRETATION_STATE_READY:
        update_fields["interpretation_error_message"] = ""

    with transaction.atomic():
        # Final physical rehash immediately before CAS UPDATE to catch tamper interleaving
        # FS can change después y GET guard lo detecta.
        if getattr(job, "pdf", None):
            try:
                with job.pdf.open("rb") as stream:
                    final_bytes = stream.read()
                final_sha = hashlib.sha256(final_bytes).hexdigest()
                if current_pdf_sha256 and final_sha.lower() != current_pdf_sha256.lower():
                    target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
                    error_message = "El archivo PDF fue modificado concurrentemente durante la operación."
                    update_fields.pop("interpretation_dossier", None)
                    update_fields["interpretation_state"] = target_state
                    update_fields["interpretation_error_message"] = error_message
                    update_fields["interpretation_claim_token"] = None
                    update_fields["interpretation_claimed_at"] = None
            except Exception as final_read_exc:
                logger.warning("Error re-leyendo PDF antes de CAS en save_interpretation_dossier_command: %s", final_read_exc)
                target_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
                error_message = "No se pudo comprobar el archivo PDF antes de persistir."
                update_fields.pop("interpretation_dossier", None)
                update_fields["interpretation_state"] = target_state
                update_fields["interpretation_error_message"] = error_message
                update_fields["interpretation_claim_token"] = None
                update_fields["interpretation_claimed_at"] = None

        rows = qs.update(**update_fields)
        if rows == 0 and owner_token is not None:
            raise CurriculumInterpretationError(
                f"Conflicto de concurrencia: el trabajo #{job.pk} no pudo actualizarse con el token proporcionado."
            )

    # Sync job instance in-memory (preserve prior dossier if failed/blocked)
    if target_state != CurriculumImportJob.INTERPRETATION_STATE_FAILED:
        job.interpretation_dossier = dossier_dict
    job.interpretation_state = target_state
    if target_state in (
        CurriculumImportJob.INTERPRETATION_STATE_READY,
        CurriculumImportJob.INTERPRETATION_STATE_FAILED,
    ):
        job.interpretation_claim_token = None
        job.interpretation_claimed_at = None
    if error_message is not None:
        job.interpretation_error_message = error_message
    elif target_state == CurriculumImportJob.INTERPRETATION_STATE_READY:
        job.interpretation_error_message = ""
    job.updated_at = now

    return target_state


def record_direct_timeout(
    job,
    error_message: str,
    expected_claim_token: Optional[Any] = None,
    now=None,
) -> int:
    """Record timeout failure without clobbering foreign claims."""
    from curriculum.models import CurriculumImportJob

    if expected_claim_token is not None:
        expected_claim_token = validate_claim_token(expected_claim_token)

    if now is None:
        now = timezone.now()

    qs = CurriculumImportJob.objects.filter(pk=job.pk)
    if expected_claim_token:
        qs = qs.filter(interpretation_claim_token=expected_claim_token)
    else:
        qs = qs.filter(interpretation_claim_token__isnull=True)

    return qs.update(
        interpretation_error_message=error_message,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_FAILED,
        progress_stage="",
        updated_at=now,
    )


def retry_job_interpretation(
    job,
    wait_timeout: float = 25.0,
    poll_interval: float = 0.05,
    stale_threshold: Optional[timedelta] = None,
    now=None,
):
    """Execute an idempotent retry of curriculum interpretation for a job via CAS.

    Reuses the existing job and PDF (zero new jobs created, zero published snapshots).
    Clears error message strictly upon acquiring a valid CAS claim.
    If already READY with valid dossier: returns immediately without reinterpreting.
    If already actively ORGANIZING: returns immediately without duplicate worker.
    """
    from curriculum.models import CurriculumImportJob
    from curriculum.source_interpreter import (
        CurriculumInterpretationError,
        CurriculumSourceInterpreter,
        InterpretationCancelledError,
    )

    if stale_threshold is None:
        stale_threshold = timedelta(minutes=90)
    elif isinstance(stale_threshold, (int, float)):
        stale_threshold = timedelta(seconds=stale_threshold)

    from curriculum.views import _execute_with_db_lock_retry

    def _read_fresh():
        return CurriculumImportJob.objects.filter(pk=job.pk).first()

    fresh = _execute_with_db_lock_retry(_read_fresh)
    if fresh is None:
        raise CurriculumInterpretationError(f"El trabajo de importación #{job.pk} no existe.")

    # 1. Shortcuts ONLY:
    # 1a. If already READY with valid dossier: fast return without calling prepare()
    if (
        fresh.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
        and fresh.has_valid_ready_dossier()
    ):
        return fresh.get_interpretation_dossier()

    # 1b. If actively organizing with non-stale claim: return without duplicate worker
    if fresh.interpretation_claim_token and not fresh.is_stage_stale():
        return None

    # 1c. PURE PREFLIGHT before claim if a prior dossier exists:
    # Prior dossier SHA identity must be explicit, valid, and match the current physical file.
    # If mismatch / ambiguous / missing file / corrupted -> raise ReextractRequired without any DB mutation!
    prior_dossier = fresh.interpretation_dossier
    if bool(prior_dossier):
        if not isinstance(prior_dossier, dict):
            raise ReextractRequired(
                "Alerta de integridad: El dossier previo está corrupto o tiene formato inválido. "
                "Se requiere una reextracción explícita."
            )
        prior_sha = prior_dossier.get("source_sha256")
        if not isinstance(prior_sha, str) or not bool(HEX_64_REGEX.match(prior_sha.strip())):
            raise ReextractRequired(
                "Alerta de integridad: La identidad previa del documento es inválida o ambigua. "
                "Se requiere una reextracción explícita."
            )
        expected_preflight_sha = prior_sha.strip().lower()

        if not fresh.pdf or not hasattr(fresh.pdf, "open"):
            raise ReextractRequired(
                "El archivo PDF de la planeación no está disponible o no se puede leer. "
                "Se requiere una reextracción explícita."
            )

        try:
            with fresh.pdf.open("rb") as stream:
                preflight_bytes = stream.read()
                preflight_sha = hashlib.sha256(preflight_bytes).hexdigest().lower()
        except Exception:
            raise ReextractRequired(
                "No se pudo leer el archivo PDF de la planeación. "
                "Se requiere una reextracción explícita."
            )

        if not preflight_bytes:
            raise ReextractRequired(
                "El archivo PDF de la planeación está vacío. "
                "Se requiere una reextracción explícita."
            )

        if preflight_sha != expected_preflight_sha:
            raise ReextractRequired(
                "Alerta de integridad: El archivo PDF de la planeación no coincide con la evidencia registrada. "
                "Se requiere reextracción explícita."
            )

    # 2. Acquire valid CAS claim FIRST (including stale takeover)
    owner_token = uuid.uuid4()
    if now is None:
        now = timezone.now()

    def _attempt_claim():
        return claim_interpretation_worker(
            fresh,
            owner_token=owner_token,
            stale_threshold=stale_threshold,
            now=now,
            allow_retry=True,
        )

    rows_claimed = _execute_with_db_lock_retry(_attempt_claim)
    if rows_claimed == 0:
        # Lost claim race or actively claimed by another worker: ZERO mutation!
        return None

    # 3. Post-claim: reload and perform all validations under owner_token protection
    fresh = _execute_with_db_lock_retry(_read_fresh)
    if fresh is None:
        return None

    # Captura identidad previa del dossier conservado después de claim;
    # no permitas que estado ORGANIZING invalide lectura del dossier histórico.
    prior_dossier = fresh.interpretation_dossier
    expected_sha = None

    if isinstance(prior_dossier, dict) and prior_dossier:
        prior_sha = prior_dossier.get("source_sha256")
        if not isinstance(prior_sha, str) or not bool(HEX_64_REGEX.match(prior_sha.strip())):
            now_dt = timezone.now()
            _execute_with_db_lock_retry(
                lambda: finish_worker_failure(
                    fresh,
                    owner_token=owner_token,
                    error_message="Alerta de integridad: El archivo PDF de la planeación no coincide con la evidencia registrada. Se requiere reextracción explícita.",
                    now=now_dt,
                )
            )
            return None
        expected_sha = prior_sha.strip().lower()

    if not fresh.pdf or not hasattr(fresh.pdf, "open"):
        now_dt = timezone.now()
        _execute_with_db_lock_retry(
            lambda: finish_worker_failure(
                fresh,
                owner_token=owner_token,
                error_message="El archivo PDF de la currícula no está disponible o no se puede leer.",
                now=now_dt,
            )
        )
        return None

    try:
        with fresh.pdf.open("rb") as stream:
            current_bytes = stream.read()
            current_sha = hashlib.sha256(current_bytes).hexdigest().lower()
    except Exception:
        now_dt = timezone.now()
        _execute_with_db_lock_retry(
            lambda: finish_worker_failure(
                fresh,
                owner_token=owner_token,
                error_message="El archivo PDF de la currícula no está disponible o no se puede leer.",
                now=now_dt,
            )
        )
        return None

    if not current_bytes:
        now_dt = timezone.now()
        _execute_with_db_lock_retry(
            lambda: finish_worker_failure(
                fresh,
                owner_token=owner_token,
                error_message="El archivo PDF de la currícula no está disponible o no se puede leer.",
                now=now_dt,
            )
        )
        return None

    if expected_sha is not None:
        if current_sha != expected_sha:
            now_dt = timezone.now()
            _execute_with_db_lock_retry(
                lambda: finish_worker_failure(
                    fresh,
                    owner_token=owner_token,
                    error_message="Alerta de integridad: El archivo PDF de la planeación no coincide con la evidencia registrada. Se requiere reextracción explícita.",
                    now=now_dt,
                )
            )
            return None
    else:
        expected_sha = current_sha

    # 4. Prepare worker execution (outside transaction)
    try:
        dossier = CurriculumSourceInterpreter.prepare(
            fresh,
            timeout_seconds=wait_timeout,
            is_cancelled=lambda: _execute_with_db_lock_retry(
                lambda: CurriculumImportJob.objects.filter(
                    pk=fresh.pk, cancel_requested=True
                ).exists()
            ),
        )
    except Exception as exc:
        logger.warning(
            "Fallo durante el reintento de interpretación del trabajo %s: %s", fresh.pk, exc
        )
        now_dt = timezone.now()
        _execute_with_db_lock_retry(
            lambda: finish_worker_failure(
                fresh,
                owner_token=owner_token,
                error_message=str(exc),
                is_cancelled=isinstance(exc, InterpretationCancelledError),
                now=now_dt,
            )
        )
        fresh_failed = _execute_with_db_lock_retry(_read_fresh)
        if fresh_failed:
            fresh.refresh_from_db()
        return None

    # 5. Final verification under owner_token: dossier SHA + rehash físico
    dossier_sha = getattr(dossier, "source_sha256", None)
    if not dossier_sha and isinstance(dossier, dict):
        dossier_sha = dossier.get("source_sha256")
    if isinstance(dossier_sha, str):
        dossier_sha = dossier_sha.strip().lower()

    verify_sha = None
    try:
        with fresh.pdf.open("rb") as stream:
            verify_sha = hashlib.sha256(stream.read()).hexdigest().lower()
    except Exception:
        verify_sha = None

    if dossier_sha != expected_sha or verify_sha != expected_sha:
        now_dt = timezone.now()
        _execute_with_db_lock_retry(
            lambda: finish_worker_failure(
                fresh,
                owner_token=owner_token,
                error_message="Alerta de integridad: El archivo PDF de la planeación fue alterado durante el procesamiento. Se requiere reextracción explícita.",
                now=now_dt,
            )
        )
        fresh_failed = _execute_with_db_lock_retry(_read_fresh)
        if fresh_failed:
            fresh.refresh_from_db()
        return None

    # 6. Worker succeeded: atomically persist dossier and transition to READY
    now_dt = timezone.now()
    _execute_with_db_lock_retry(
        lambda: finish_worker_success(
            fresh,
            owner_token=owner_token,
            dossier=dossier,
            now=now_dt,
        )
    )
    fresh_saved = _execute_with_db_lock_retry(_read_fresh)
    if fresh_saved:
        fresh.refresh_from_db()
    return fresh.get_interpretation_dossier()
