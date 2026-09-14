"""curriculum.approval_commands
----------------------------
Deep command module defining the single, unified policy and seam for all
teacher approval operations on imported curriculum planning jobs.

Enforces ADR 0001, ADR 0002, and ADR 0006:
1. Append-only persistency:
   - CurriculumImportApproval records an exact, immutable canonical snapshot
     of the approved dossier, version, SHA-256, teacher, pending acknowledgement,
     timestamp, and draft package.
   - Active status is derived strictly from match with current dossier version/SHA.
   - Existing approvals reject save() and delete().
2. Concurrency and Idempotency:
   - Safe under concurrent threads and processes on SQLite.
   - Bounded retries outside atomic transaction for locked/busy databases.
   - Each attempt opens a short atomic transaction and re-validates against a fresh row.
   - IntegrityError on duplicate approval re-reads the winner and returns idempotent success.
3. Storage Rollback Safety:
   - FileField is NEVER written inside a transaction susceptible to rollback.
   - Files are promoted to storage ONLY upon successful database transaction commit.
   - On rollback or injected failure, zero orphaned files are created.
   - Reapproval atomically updates the single draft package to current content/version/source,
     cleaning up the prior source artifact only if not referenced elsewhere.
4. Mutation-time Fresh Validation:
   - Owner, expected version, physical PDF SHA, canonical verification report,
     operational queue, and conflict/block counts are re-evaluated from fresh data
     inside the transaction immediately before persisting.
5. Exact Payload Schema:
   - `confirm_pending_items` is permitted and required if pending > 0.
   - `confirm_pending_items` is strictly forbidden (400) if pending == 0.
   - Shared between main interpretation view and dedicated approve endpoint.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models, transaction
import django.db.utils
from django.utils import timezone

from curriculum.models import (
    CurriculumImportApproval,
    CurriculumImportJob,
    CurriculumPackage,
    CurriculumSourceBlob,
    PublishedPackageSnapshot,
)
from curriculum.source_interpreter import (
    ImportDossier,
    SelectionError,
    derive_operational_queue,
)
from curriculum.verification import (
    compute_canonical_verification_report,
    validate_canonical_verification_report,
)

logger = logging.getLogger(__name__)

APPROVE_BASE_ALLOWED_KEYS = {
    "csrfmiddlewaretoken",
    "action",
    "expected_version",
    "confirm_approval",
}

APPROVE_MAIN_EXTRA_ALLOWED_KEYS = {
    "session_id",
    "session_number",
}


class ApprovalStatus(enum.Enum):
    SUCCESS = "success"
    ALREADY_APPROVED = "already_approved"
    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    VERSION_CONFLICT = "version_conflict"
    INTEGRITY_CONFLICT = "integrity_conflict"
    QUEUE_CONFLICT = "queue_conflict"


@dataclasses.dataclass(frozen=True)
class ApprovalResult:
    status: ApprovalStatus
    message: str
    http_status: int
    approval: Optional[CurriculumImportApproval] = None
    package: Optional[CurriculumPackage] = None

    @property
    def is_success(self) -> bool:
        return self.status in (ApprovalStatus.SUCCESS, ApprovalStatus.ALREADY_APPROVED)


def compute_canonical_approval_digest(
    dossier_dict: dict,
    report_dict: dict,
    queue_pending: int,
    queue_requires: int,
    pdf_bytes: bytes,
) -> str:
    """Compute an exact, deterministic canonical digest of dossier, verification report,
    operational queue state, and physical PDF bytes."""
    h = hashlib.sha256()
    dossier_json = json.dumps(dossier_dict, sort_keys=True, separators=(",", ":"))
    h.update(b"dossier:")
    h.update(dossier_json.encode("utf-8"))

    report_json = json.dumps(report_dict, sort_keys=True, separators=(",", ":"))
    h.update(b"|report:")
    h.update(report_json.encode("utf-8"))

    h.update(f"|queue:{queue_pending}:{queue_requires}".encode("utf-8"))

    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    h.update(f"|pdf:{pdf_sha}".encode("utf-8"))

    return h.hexdigest()


def parse_canonical_positive_int(value: Any) -> int:
    """Parse value as a positive canonical integer (> 0). Raises ValueError otherwise."""
    if value is None:
        raise ValueError("Value cannot be None")
    s = str(value).strip()
    if not s or not s.isdigit():
        raise ValueError(f"Value must be a positive integer: {value!r}")
    val = int(s)
    if val <= 0:
        raise ValueError(f"Value must be > 0: {val}")
    return val


def validate_approval_payload(
    post_data: dict,
    is_dedicated_route: bool,
    pending_count: int,
) -> tuple[bool, str, dict]:
    """Validate POST payload according to exact schema rules.

    Rules:
    - Dedicated route allows: csrfmiddlewaretoken, action, expected_version, confirm_approval.
    - Main route allows: above + session_id, session_number.
    - confirm_pending_items:
      - If pending_count > 0: PERMITTED and REQUIRED (must be truthy).
      - If pending_count == 0: STRICTLY FORBIDDEN (presence => 400).
    - Any unrecognized key => 400.
    - confirm_approval must be truthy.
    - expected_version must be a valid positive integer.
    """
    allowed_keys = set(APPROVE_BASE_ALLOWED_KEYS)
    if not is_dedicated_route:
        allowed_keys.update(APPROVE_MAIN_EXTRA_ALLOWED_KEYS)

    if pending_count > 0:
        allowed_keys.add("confirm_pending_items")

    # 1. Check for unauthorized keys
    extra_keys = [k for k in post_data.keys() if k not in allowed_keys]
    if extra_keys:
        if "confirm_pending_items" in extra_keys and pending_count == 0:
            return (
                False,
                "El parámetro 'confirm_pending_items' no está permitido cuando no hay elementos opcionales pendientes.",
                {},
            )
        return False, f"Claves no autorizadas en aprobación: {extra_keys}.", {}

    # 2. Check conditional pending items
    if pending_count > 0:
        if "confirm_pending_items" not in post_data:
            return (
                False,
                f"Existen {pending_count} elementos opcionales pendientes de revisión. "
                "Debe confirmar explícitamente que acepta continuar con los pendientes opcionales.",
                {},
            )
        pending_val = str(post_data.get("confirm_pending_items", "")).strip().lower()
        if pending_val not in ("1", "on", "true"):
            return (
                False,
                "Debe confirmar explícitamente los elementos opcionales pendientes.",
                {},
            )
    else:
        if "confirm_pending_items" in post_data:
            return (
                False,
                "El parámetro 'confirm_pending_items' no está permitido cuando no hay elementos opcionales pendientes.",
                {},
            )

    # 3. Check confirm_approval
    confirm_val = str(post_data.get("confirm_approval", "")).strip().lower()
    if confirm_val not in ("1", "on", "true"):
        return (
            False,
            "Debe confirmar explícitamente la aprobación de la planeación.",
            {},
        )

    # 4. Check expected_version
    raw_version = post_data.get("expected_version")
    if raw_version is None or str(raw_version).strip() == "":
        return (
            False,
            "El campo 'expected_version' es requerido para validar la concurrencia de la aprobación.",
            {},
        )
    try:
        expected_version = parse_canonical_positive_int(raw_version)
    except ValueError:
        return (
            False,
            "El campo 'expected_version' debe ser un número entero positivo válido.",
            {},
        )

    return True, "", {
        "expected_version": expected_version,
        "confirm_pending_items": bool(pending_count > 0),
    }


class ApprovalConflict(Exception):
    """Raised when concurrent mutation or integrity divergence is detected during approval."""
    pass


def _verify_and_repair_approval_source(
    approval: CurriculumImportApproval, job: CurriculumImportJob | None = None
) -> bool:
    """Verifies that the content-addressed source blob for the approval exists and has exact SHA."""
    expected_sha = str(approval.source_sha256 or "").strip().lower()
    if not expected_sha:
        return False

    if approval.source_blob_id and approval.source_blob:
        try:
            blob = approval.source_blob
            if blob.is_valid_blob() and (blob.sha256 or "").lower() == expected_sha:
                return True
        except Exception as exc:
            logger.warning("Error leyendo blob fuente de aprobación: %s", exc)

    return False


def _verify_precommit_checkpoint(
    job_id: int,
    expected_version: int,
    expected_source_sha: str,
    frozen_digest: str,
) -> tuple[CurriculumImportJob, ImportDossier, dict, int, bytes, str]:
    """Re-query DB and reread physical PDF from storage; verify dossier, report, queue, and frozen digest.
    Raises ApprovalConflict on any divergence."""
    job = (
        CurriculumImportJob.objects.select_for_update()
        .filter(pk=job_id)
        .first()
    )
    if not job:
        raise ApprovalConflict("El trabajo de importación no existe.")

    if job.interpretation_state != CurriculumImportJob.INTERPRETATION_STATE_READY:
        raise ApprovalConflict("La planeación debe estar en estado READY para ser aprobada.")

    dossier_dict = job.interpretation_dossier
    if not isinstance(dossier_dict, dict) or not dossier_dict:
        raise ApprovalConflict("Dossier canónico ausente en la base de datos.")

    version = dossier_dict.get("version")
    if version != expected_version:
        raise ApprovalConflict(
            f"Conflicto de concurrencia (409): El formulario fue cargado con la versión {expected_version}, "
            f"pero el documento ya se encuentra en la versión {version}."
        )

    if not job.pdf or not getattr(job.pdf, "name", None):
        raise ApprovalConflict("El archivo PDF fuente no está disponible.")

    try:
        with job.pdf.open("rb") as stream:
            pdf_bytes = stream.read()
    except Exception as exc:
        raise ApprovalConflict(f"Error al leer el archivo PDF fuente: {exc}")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    dossier_sha = str(dossier_dict.get("source_sha256") or "").strip()
    if (
        pdf_sha256.lower() != dossier_sha.lower()
        or pdf_sha256.lower() != expected_source_sha.lower()
    ):
        raise ApprovalConflict("Conflicto de integridad: El archivo PDF físico difiere de la huella registrada.")

    report = dossier_dict.get("verification_report")
    if not isinstance(report, dict) or not report:
        raise ApprovalConflict("El reporte de verificación persistido no se encuentra en el dossier.")
    if not report.get("is_valid") or report.get("blocked_count", 0) > 0:
        raise ApprovalConflict("No se puede aprobar la planeación: la comprobación automática contiene bloqueos.")

    dossier = job.get_interpretation_dossier()
    if not dossier or dossier.version != expected_version:
        raise ApprovalConflict("Error deserializando el dossier canónico de la base de datos.")

    try:
        queue = derive_operational_queue(dossier)
    except SelectionError as exc:
        raise ApprovalConflict(str(exc))

    if queue.requires_resolution_count > 0:
        raise ApprovalConflict(
            "No se puede aprobar la planeación: existen elementos en conflicto o requisitos obligatorios sin resolver."
        )

    digest = compute_canonical_approval_digest(
        dossier_dict=dossier_dict,
        report_dict=report,
        queue_pending=queue.pending_review_count,
        queue_requires=queue.requires_resolution_count,
        pdf_bytes=pdf_bytes,
    )

    if digest != frozen_digest:
        raise ApprovalConflict(
            "Conflicto de concurrencia (409): El estado del dossier, reporte, cola o archivo PDF cambió antes de persistir la aprobación."
        )

    return job, dossier, report, queue.pending_review_count, pdf_bytes, pdf_sha256


def execute_teacher_approval(
    job_id: int,
    user: Any,
    post_data: dict,
    is_dedicated_route: bool = False,
    max_retries: int = 10,
    base_delay: float = 0.04,
) -> ApprovalResult:

    """Deep seam executing the full teacher approval lifecycle with SQLite concurrency safety.

    - Outside atomic: reads job, checks ownership and pre-flight state.
    - Inside bounded retry loop:
      - Rereads winner if already committed, verifying and repairing source if missing/corrupted.
      - Enters short atomic block:
        - Obtains write ownership via atomic CAS on job against exact state/updated_at snapshot.
        - Reloads fresh job, validates persisted verification report (0 blockers, valid).
        - Reopens physical PDF from storage (no rehash cached) and validates source SHA match.
        - Recomputes canonical verification report and verifies exact match against persisted report.
        - Derives fresh operational queue (F7) from fresh dossier and validates 0 conflicts.
        - Re-validates exact payload contract against fresh queue count.
        - Persists immutable content-addressed CurriculumSourceBlob in database (B3).
        - Executes B5 precommit checkpoints before blob, after blob, and after approval.
        - Updates or creates draft package.
        - Persists append-only CurriculumImportApproval and updates dossier history.
    """
    expected_version = None
    initial_job = None

    # 2. Concurrency retry loop for SQLite lock/busy and atomic transaction
    for attempt in range(max_retries):
        try:
            # Quick initial pre-flight check inside retry loop
            initial_job = CurriculumImportJob.objects.filter(pk=job_id).first()
            if not initial_job or initial_job.created_by_id != user.id:
                return ApprovalResult(
                    status=ApprovalStatus.NOT_FOUND,
                    message="El trabajo de importación no existe.",
                    http_status=404,
                )

            if initial_job.interpretation_state != CurriculumImportJob.INTERPRETATION_STATE_READY:
                return ApprovalResult(
                    status=ApprovalStatus.INTEGRITY_CONFLICT,
                    message="La planeación debe estar en estado READY para ser aprobada.",
                    http_status=409,
                )

            initial_dossier = initial_job.get_interpretation_dossier()
            if not initial_dossier:
                return ApprovalResult(
                    status=ApprovalStatus.INTEGRITY_CONFLICT,
                    message="El trabajo no contiene un dossier canónico válido.",
                    http_status=409,
                )

            try:
                initial_queue = derive_operational_queue(initial_dossier)
            except SelectionError as exc:
                return ApprovalResult(
                    status=ApprovalStatus.BAD_REQUEST,
                    message=str(exc),
                    http_status=400,
                )

            # Initial payload validation against current queue count
            valid, err_msg, parsed_params = validate_approval_payload(
                post_data,
                is_dedicated_route=is_dedicated_route,
                pending_count=initial_queue.pending_review_count,
            )
            if not valid:
                return ApprovalResult(
                    status=ApprovalStatus.BAD_REQUEST,
                    message=err_msg,
                    http_status=400,
                )

            expected_version = parsed_params["expected_version"]
            snapshot_updated_at = initial_job.updated_at
            expected_source_sha = str(initial_dossier.source_sha256 or "").strip()
            preflight_report = initial_job.interpretation_dossier.get("verification_report") if isinstance(initial_job.interpretation_dossier, dict) else None

            # Quick idempotency check outside transaction: has winner already committed?
            existing_approval = (
                CurriculumImportApproval.objects.filter(
                    job_id=job_id,
                    dossier_version=expected_version,
                )
                .select_related("package")
                .first()
            )
            if existing_approval:
                if not _verify_and_repair_approval_source(existing_approval, initial_job):
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="El archivo fuente de la planeación aprobada no se encuentra disponible y no pudo ser reparado.",
                        http_status=500,
                    )
                return ApprovalResult(
                    status=ApprovalStatus.ALREADY_APPROVED,
                    message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                    http_status=200,
                    approval=existing_approval,
                    package=existing_approval.package,
                )

            # Ensure no orphan unreferenced storage artifact exists before approval
            stale_target = f"curriculum/package-sources/by-sha/{expected_source_sha.lower()}.pdf"
            if default_storage.exists(stale_target):
                if not CurriculumImportApproval.objects.filter(source_sha256=expected_source_sha.lower()).exists():
                    try:
                        default_storage.delete(stale_target)
                    except Exception:
                        pass

            with transaction.atomic():
                # Step 1: CAS on job row against snapshot exact to obtain write ownership in SQLite
                cas_count = CurriculumImportJob.objects.filter(
                    pk=job_id,
                    interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
                    updated_at=snapshot_updated_at,
                ).update(updated_at=timezone.now())

                if cas_count == 0:
                    # Check if another thread/process completed the approval
                    winning = (
                        CurriculumImportApproval.objects.filter(
                            job_id=job_id,
                            dossier_version=expected_version,
                        )
                        .select_related("package")
                        .first()
                    )
                    if winning:
                        if _verify_and_repair_approval_source(winning, initial_job):
                            return ApprovalResult(
                                status=ApprovalStatus.ALREADY_APPROVED,
                                message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                                http_status=200,
                                approval=winning,
                                package=winning.package,
                            )
                        return ApprovalResult(
                            status=ApprovalStatus.INTEGRITY_CONFLICT,
                            message="El archivo fuente de la planeación aprobada no se encuentra disponible y no pudo ser reparado.",
                            http_status=500,
                        )
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Conflicto de concurrencia: el trabajo de importación fue modificado simultáneamente.",
                        http_status=409,
                    )

                # Step 2: Tras CAS reload fresh_job and dossier REPORT PERSISTIDO
                fresh_job = (
                    CurriculumImportJob.objects.select_for_update()
                    .filter(pk=job_id)
                    .first()
                )
                if not fresh_job or fresh_job.created_by_id != user.id:
                    return ApprovalResult(
                        status=ApprovalStatus.FORBIDDEN,
                        message="El trabajo de importación no existe.",
                        http_status=404,
                    )

                if fresh_job.interpretation_state != CurriculumImportJob.INTERPRETATION_STATE_READY:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="La planeación debe estar en estado READY para ser aprobada.",
                        http_status=409,
                    )

                fresh_dossier_dict = fresh_job.interpretation_dossier
                if not isinstance(fresh_dossier_dict, dict) or not fresh_dossier_dict:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Dossier canónico ausente en la base de datos.",
                        http_status=409,
                    )

                fresh_dossier_version = fresh_dossier_dict.get("version")
                if fresh_dossier_version != expected_version:
                    win = (
                        CurriculumImportApproval.objects.filter(
                            job_id=job_id,
                            dossier_version=expected_version,
                        )
                        .select_related("package")
                        .first()
                    )
                    if win and _verify_and_repair_approval_source(win, fresh_job):
                        return ApprovalResult(
                            status=ApprovalStatus.ALREADY_APPROVED,
                            message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                            http_status=200,
                            approval=win,
                            package=win.package,
                        )
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.VERSION_CONFLICT,
                        message=(
                            f"Conflicto de concurrencia (409): El formulario fue cargado con la versión {expected_version}, "
                            f"pero el documento ya se encuentra en la versión {fresh_dossier_version}."
                        ),
                        http_status=409,
                    )

                fresh_dossier = fresh_job.get_interpretation_dossier()
                if not fresh_dossier or fresh_dossier.version != expected_version:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Error deserializando el dossier canónico de la base de datos.",
                        http_status=409,
                    )

                # Validate persisted report in fresh dossier
                persisted_report = fresh_dossier_dict.get("verification_report")
                if not isinstance(persisted_report, dict) or not persisted_report:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="El reporte de verificación persistido no se encuentra en el dossier.",
                        http_status=409,
                    )
                if not persisted_report.get("is_valid") or persisted_report.get("blocked_count", 0) > 0:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="No se puede aprobar la planeación: la comprobación automática contiene bloqueos.",
                        http_status=409,
                    )
                if preflight_report is not None and persisted_report != preflight_report:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Conflicto de integridad: el reporte persistido fue modificado concurrentemente.",
                        http_status=409,
                    )

                # Step 3: Reabre storage bytes (no rehash cached)
                try:
                    with fresh_job.pdf.open("rb") as stream:
                        fresh_pdf_bytes = stream.read()
                except Exception as exc:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message=f"Error al leer el archivo PDF fuente: {exc}",
                        http_status=409,
                    )

                fresh_pdf_sha256 = hashlib.sha256(fresh_pdf_bytes).hexdigest()
                dossier_source_sha = str(fresh_dossier.source_sha256 or "").strip()
                if fresh_pdf_sha256.lower() != dossier_source_sha.lower() or fresh_pdf_sha256.lower() != expected_source_sha.lower():
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Conflicto de integridad: El archivo PDF físico difiere de la huella registrada.",
                        http_status=409,
                    )

                current_sha = fresh_pdf_sha256

                # Step 4: Recomputa canonical report
                fresh_report = compute_canonical_verification_report(fresh_dossier, fresh_pdf_bytes)
                if fresh_report.get("blocked_count", 0) > 0 or not fresh_report.get("is_valid"):
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="No se puede aprobar la planeación: la comprobación automática contiene bloqueos.",
                        http_status=409,
                    )

                if not validate_canonical_verification_report(fresh_dossier, fresh_pdf_bytes, persisted_report):
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="Comprobación canónica de verificación inválida para el dossier actual.",
                        http_status=409,
                    )

                # Step 5: Operational queue (F7) derivado del fresh dossier
                try:
                    fresh_queue = derive_operational_queue(fresh_dossier)
                except SelectionError as exc:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.BAD_REQUEST,
                        message=str(exc),
                        http_status=400,
                    )

                if fresh_queue.requires_resolution_count > 0:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.QUEUE_CONFLICT,
                        message="No se puede aprobar la planeación: existen elementos en conflicto o requisitos obligatorios sin resolver.",
                        http_status=409,
                    )

                # Re-validate payload against fresh queue pending items count
                valid, err_msg, _ = validate_approval_payload(
                    post_data,
                    is_dedicated_route=is_dedicated_route,
                    pending_count=fresh_queue.pending_review_count,
                )
                if not valid:
                    transaction.set_rollback(True)
                    return ApprovalResult(
                        status=ApprovalStatus.BAD_REQUEST,
                        message=err_msg,
                        http_status=400,
                    )

                # Step 6: Freeze canonical digest of dossier, report, queue, and PDF bytes (B5)
                frozen_digest = compute_canonical_approval_digest(
                    dossier_dict=fresh_dossier_dict,
                    report_dict=persisted_report,
                    queue_pending=fresh_queue.pending_review_count,
                    queue_requires=fresh_queue.requires_resolution_count,
                    pdf_bytes=fresh_pdf_bytes,
                )

                # Step 7: PRECOMMIT CHECKPOINT 1 (before blob get/create)
                (
                    precommit_job,
                    precommit_dossier,
                    precommit_report,
                    queue_pending,
                    precommit_pdf_bytes,
                    precommit_pdf_sha256,
                ) = _verify_precommit_checkpoint(
                    job_id=job_id,
                    expected_version=expected_version,
                    expected_source_sha=expected_source_sha,
                    frozen_digest=frozen_digest,
                )

                # Step 8: Transactional BLOB persistence (B3)
                expected_sha_clean = expected_source_sha.lower()
                try:
                    blob, _ = CurriculumSourceBlob.objects.get_or_create(
                        sha256=expected_sha_clean,
                        defaults={
                            "content": precommit_pdf_bytes,
                            "content_size": len(precommit_pdf_bytes),
                        },
                    )
                except django.db.utils.IntegrityError:
                    blob = CurriculumSourceBlob.objects.get(sha256=expected_sha_clean)

                # Validate blob content
                if not blob.is_valid_blob() or (blob.sha256 or "").lower() != expected_sha_clean:
                    raise ApprovalConflict(
                        "Conflicto de integridad: el blob de almacenamiento no coincide con los bytes esperados."
                    )

                # Checkpoint 2: DESPUÉS de blob get/create (B5 late checkpoint 1)
                _verify_precommit_checkpoint(
                    job_id=job_id,
                    expected_version=expected_version,
                    expected_source_sha=expected_source_sha,
                    frozen_digest=frozen_digest,
                )

                # Prepare package data from precommit_dossier
                proj_title = (
                    precommit_dossier.general_fields.get("proyecto").value
                    if "proyecto" in precommit_dossier.general_fields
                    else ""
                )
                if isinstance(proj_title, list):
                    proj_title = ", ".join(proj_title)
                proj_title = (str(proj_title).strip() or "Planeación aprobada")[:160]

                proj_obj = (
                    precommit_dossier.general_fields.get("proposito").value
                    if "proposito" in precommit_dossier.general_fields
                    else ""
                )
                if not proj_obj and "finalidad" in precommit_dossier.general_fields:
                    proj_obj = precommit_dossier.general_fields.get("finalidad").value
                if isinstance(proj_obj, list):
                    proj_obj = ", ".join(proj_obj)
                proj_obj = str(proj_obj or "").strip()

                source_refs = []
                for s in precommit_dossier.sessions:
                    source_refs.append({
                        "session_id": s.session_id,
                        "session_number": s.session_number,
                        "pages": list(s.pages or []),
                    })

                past_approval = (
                    precommit_job.approvals.filter(package__isnull=False)
                    .select_related("package")
                    .first()
                )
                package = past_approval.package if past_approval else None

                if package is None:
                    package = CurriculumPackage(
                        title=proj_title,
                        objective=proj_obj,
                        micro_lesson=precommit_dossier.sessions[0].title if precommit_dossier.sessions else "",
                        created_by=user,
                        is_demo=False,
                        ai_assisted=False,
                        source_references=source_refs,
                        source_blob=blob,
                        source_pdf_sha256=expected_sha_clean,
                    )
                    package.save()
                else:
                    package.title = proj_title
                    package.objective = proj_obj
                    package.micro_lesson = precommit_dossier.sessions[0].title if precommit_dossier.sessions else ""
                    package.source_references = source_refs
                    package.source_blob = blob
                    package.source_pdf_sha256 = expected_sha_clean
                    package.save(update_fields=[
                        "title",
                        "objective",
                        "micro_lesson",
                        "source_references",
                        "source_blob",
                        "source_pdf_sha256",
                        "updated_at",
                    ])

                # Step 9: Persist append-only CurriculumImportApproval
                approval = CurriculumImportApproval.objects.create(
                    job=precommit_job,
                    dossier_version=precommit_dossier.version,
                    source_sha256=expected_sha_clean,
                    source_blob=blob,
                    dossier_snapshot=precommit_dossier.to_dict(),
                    approved_by=user,
                    approved_at=timezone.now(),
                    package=package,
                    pending_acknowledged=bool(queue_pending > 0),
                    pending_items_count=queue_pending,
                )

                # Checkpoint 3: DESPUÉS de Approval.objects.create (B5 late checkpoint 2)
                _verify_precommit_checkpoint(
                    job_id=job_id,
                    expected_version=expected_version,
                    expected_source_sha=expected_source_sha,
                    frozen_digest=frozen_digest,
                )

                actor_name = user.get_full_name().strip() or user.username
                precommit_dossier.history.append({
                    "version": precommit_dossier.version,
                    "timestamp": approval.approved_at.isoformat(),
                    "actor": actor_name,
                    "summary": f"Planeación aprobada por el docente ({actor_name}). Aprobada para preparar.",
                    "changes": [
                        {
                            "field": "approval",
                            "previous": None,
                            "new": {
                                "version": precommit_dossier.version,
                                "sha256": expected_sha_clean,
                                "package_id": package.pk,
                                "pending_items_count": queue_pending,
                            },
                        }
                    ],
                })
                precommit_job.interpretation_dossier = precommit_dossier.to_dict()
                precommit_job.save(update_fields=["interpretation_dossier"])

            return ApprovalResult(
                status=ApprovalStatus.SUCCESS,
                message="Planeación aprobada exitosamente. Aprobada para preparar.",
                http_status=200,
                approval=approval,
                package=package,
            )

        except ApprovalConflict as exc:
            logger.warning("Approval conflict on job %s: %s", job_id, exc)
            return ApprovalResult(
                status=ApprovalStatus.INTEGRITY_CONFLICT,
                message=str(exc),
                http_status=409,
            )

        except django.db.utils.IntegrityError as exc:
            winning = (
                CurriculumImportApproval.objects.filter(
                    job_id=job_id,
                    dossier_version=expected_version,
                )
                .select_related("package")
                .first()
            )
            if winning:
                if _verify_and_repair_approval_source(winning, initial_job):
                    return ApprovalResult(
                        status=ApprovalStatus.ALREADY_APPROVED,
                        message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                        http_status=200,
                        approval=winning,
                        package=winning.package,
                    )
                return ApprovalResult(
                    status=ApprovalStatus.INTEGRITY_CONFLICT,
                    message="El archivo fuente de la planeación aprobada no se encuentra disponible y no pudo ser reparado.",
                    http_status=500,
                )
            raise

        except django.db.utils.OperationalError as exc:
            err_text = str(exc).lower()
            if "locked" in err_text or "busy" in err_text:
                winning = (
                    CurriculumImportApproval.objects.filter(
                        job_id=job_id,
                        dossier_version=expected_version,
                    )
                    .select_related("package")
                    .first()
                )
                if winning:
                    if _verify_and_repair_approval_source(winning, initial_job):
                        return ApprovalResult(
                            status=ApprovalStatus.ALREADY_APPROVED,
                            message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                            http_status=200,
                            approval=winning,
                            package=winning.package,
                        )
                    return ApprovalResult(
                        status=ApprovalStatus.INTEGRITY_CONFLICT,
                        message="El archivo fuente de la planeación aprobada no se encuentra disponible y no pudo ser reparado.",
                        http_status=500,
                    )
                if attempt < max_retries - 1:
                    sleep_time = base_delay * (1.5 ** attempt) + random.uniform(0.01, 0.04)
                    time.sleep(sleep_time)
                    continue
            raise

        except Exception as exc:
            raise


    # If retries exhausted, check one last time for winner
    final_win = (
        CurriculumImportApproval.objects.filter(
            job_id=job_id,
            dossier_version=expected_version,
        )
        .select_related("package")
        .first()
    )
    if final_win:
        if _verify_and_repair_approval_source(final_win, initial_job):
            return ApprovalResult(
                status=ApprovalStatus.ALREADY_APPROVED,
                message=f"Planeación ya se encuentra aprobada para la versión {expected_version}.",
                http_status=200,
                approval=final_win,
                package=final_win.package,
            )
        return ApprovalResult(
            status=ApprovalStatus.INTEGRITY_CONFLICT,
            message="El archivo fuente de la planeación aprobada no se encuentra disponible y no pudo ser reparado.",
            http_status=500,
        )

    return ApprovalResult(
        status=ApprovalStatus.INTEGRITY_CONFLICT,
        message="No se pudo adquirir el bloqueo de base de datos tras reintentos.",
        http_status=409,
    )
