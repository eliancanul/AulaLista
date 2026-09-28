"""Django persistence and teacher authority tests for GREEN 9.

Verifies:
1. Real database persistence: saving and reloading a corrected ImportDossier via tutor_import_interpretation.
2. Survival across DB reload: corrected value, original_value, review status, and audit history deltas.
3. Teacher authority invariant: CurriculumProgress and editorial models (CurriculumPackage) do NOT advance or change.
4. Source integrity invariant: Source PDF bytes and SHA-256 hash in CurriculumImportJob do NOT change after saving corrections
   and after postponing/rejecting (clearing) a suggestion.
5. All test data is 100% synthetic (no private PDF phrases).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from curriculum.models import (
    CurriculumImportJob,
    CurriculumPackage,
    CurriculumProgress,
)
from curriculum.source_interpreter import (
    ORIGIN_PROPOSED,
    ORIGIN_TEACHER_ENTERED,
    REVIEW_CORRECTED,
    REVIEW_PENDING,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_SUPPORTED,
    CurriculumSourceInterpreter,
    ImportDossier,
    derive_operational_queue,
)
from curriculum.verification import verify_curriculum_dossier
from helpers import tutor_client
from test_t15_curriculum_import import make_minimal_pdf

pytestmark = pytest.mark.django_db(transaction=True)


def _setup_synthetic_job(username: str = "tutor_green9_test"):
    """Create an authenticated teacher client, synthetic PDF, and a ready CurriculumImportJob in the database."""
    pdf_bytes = make_minimal_pdf([
        "Planeacion Didactica Educacion Primaria 2023-2024\n"
        "Fase 4 Grado 3 Campo Lenguajes\n"
        "Proyecto Guardianes del Bosque Escenario Aula.\n"
        "Paginas de la 10 a la 25\n"
        "Explorar leyendas tradicionales sobre los animales de la region y crear un compendio colectivo "
        "ilustrado para fomentar la preservacion de la fauna silvestre en la comunidad escolar.\n"
        "Campo Contenidos Proceso de desarrollo de aprendizajes\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "comunitarios. aplicacion semanas\n"
        "DESARROLLO DEL PROYECTO\n"
        "Fase #1. Planeacion\n"
        "Actividad de bienvenida y dialogo sobre la fauna.",
    ])

    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf_bytes))
    report = verify_curriculum_dossier(dossier, pdf_bytes)
    assert report.is_valid is True
    assert report.blocked_count == 0
    dossier.verification_report = report.to_dict()

    client = tutor_client(username)
    user = get_user_model().objects.get(pk=client.session["_auth_user_id"])

    job = CurriculumImportJob.objects.create(
        created_by=user,
        pdf=SimpleUploadedFile("planeacion_sintetica_green9.pdf", pdf_bytes, content_type="application/pdf"),
        status=CurriculumImportJob.STATUS_COMPLETED,
        interpretation_state=CurriculumImportJob.INTERPRETATION_STATE_READY,
        page_count=dossier.page_count,
        interpretation_dossier=dossier.to_dict(),
    )
    return client, user, job, pdf_bytes, dossier


class TestImplicitFinalityPersistenceAndAuthority:
    """GREEN 9: Real Django persistence, teacher authority, and source integrity."""

    def test_green_9_save_corrections_persists_implicit_finality_and_preserves_invariants(self):
        """1. Save corrected implicit finality, reload from DB, and verify all audit and authority invariants."""
        client, user, job, pdf_bytes, initial_dossier = _setup_synthetic_job("green9_save_teacher")

        # Initial baseline assertions
        with job.pdf.open("rb") as stream:
            initial_source_bytes = stream.read()
        initial_source_sha256 = hashlib.sha256(initial_source_bytes).hexdigest()
        assert initial_source_sha256 == initial_dossier.source_sha256

        initial_progress_count = CurriculumProgress.objects.count()
        initial_package_count = CurriculumPackage.objects.count()

        fin_initial = initial_dossier.general_fields["finalidad"]
        assert fin_initial.value.startswith("Explorar leyendas tradicionales")
        assert fin_initial.origin == ORIGIN_PROPOSED
        assert fin_initial.status == STATUS_AMBIGUOUS
        assert fin_initial.review == REVIEW_PENDING
        assert fin_initial.original_value is None
        orig_finalidad_text = fin_initial.value
        orig_version = initial_dossier.version

        # Teacher accesses interpretation view (GET)
        interp_url = reverse("tutor-import-interpretation", args=[job.pk])
        get_response = client.get(interp_url)
        assert get_response.status_code == 200

        # Teacher saves editorial correction on finalidad (POST action="save_corrections")
        corrected_finalidad = (
            "Finalidad comunitaria editada por la docente para el rescate y difusión de "
            "leyendas sobre la fauna silvestre en la comunidad escolar."
        )
        post_data = {
            "action": "save_corrections",
            "expected_version": str(orig_version),
            "finalidad": corrected_finalidad,
        }
        post_response = client.post(interp_url, post_data)
        assert post_response.status_code == 200

        # Reload job and dossier directly from Django persistence (database)
        job.refresh_from_db()
        reloaded_dossier = job.get_interpretation_dossier()
        assert reloaded_dossier is not None
        assert reloaded_dossier.version == orig_version + 1

        # Check survival of corrected value, original value, and review status
        reloaded_fin = reloaded_dossier.general_fields["finalidad"]
        assert reloaded_fin.value == corrected_finalidad
        assert reloaded_fin.original_value == orig_finalidad_text
        assert reloaded_fin.origin == ORIGIN_TEACHER_ENTERED
        assert reloaded_fin.review == REVIEW_CORRECTED
        assert reloaded_fin.status == STATUS_SUPPORTED

        # Check survival of audit trail in history
        assert len(reloaded_dossier.history) >= 1
        recent_entry = reloaded_dossier.history[-1]
        assert recent_entry.get("version") == reloaded_dossier.version
        assert "actor" in recent_entry
        expected_actor = user.get_full_name().strip() or user.username
        assert recent_entry["actor"] == expected_actor
        assert "timestamp" in recent_entry

        all_deltas = [d for h in reloaded_dossier.history for d in h.get("deltas", [])]
        fin_delta = next(d for d in all_deltas if d.get("field") == "finalidad")
        assert fin_delta["change_type"] == "modified"
        assert fin_delta["before"]["value"] == orig_finalidad_text
        assert fin_delta["after"]["value"] == corrected_finalidad

        # Invariant: Teacher authority — CurriculumProgress does NOT advance
        assert CurriculumProgress.objects.count() == initial_progress_count
        assert CurriculumProgress.objects.filter(confirmed_by=user).count() == 0

        # Invariant: No CurriculumPackage or published snapshot is created
        assert CurriculumPackage.objects.count() == initial_package_count

        # Invariant: Source PDF bytes and SHA-256 are completely unmodified
        with job.pdf.open("rb") as stream:
            current_pdf_bytes = stream.read()
        assert current_pdf_bytes == initial_source_bytes
        assert hashlib.sha256(current_pdf_bytes).hexdigest() == initial_source_sha256
        assert reloaded_dossier.source_sha256 == initial_source_sha256

    def test_green_9_postpone_and_clear_suggestion_persists_and_preserves_invariants(self):
        """2. Postpone a suggestion, then clear/reject it, verifying persistence and non-authoritarian invariants."""
        client, user, job, pdf_bytes, initial_dossier = _setup_synthetic_job("green9_postpone_teacher")

        # Initial baseline assertions
        with job.pdf.open("rb") as stream:
            initial_source_bytes = stream.read()
        initial_source_sha256 = hashlib.sha256(initial_source_bytes).hexdigest()

        initial_progress_count = CurriculumProgress.objects.count()
        initial_package_count = CurriculumPackage.objects.count()

        orig_finalidad_text = initial_dossier.general_fields["finalidad"].value
        orig_version = initial_dossier.version

        # Locate the operational queue item for implicit finalidad
        queue = derive_operational_queue(initial_dossier)
        fin_queue_items = [it for it in queue.items if it.field_name == "finalidad"]
        assert len(fin_queue_items) == 1
        fin_item = fin_queue_items[0]
        assert fin_item.priority_state == "pending_review"

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])

        # Step A: POST action="postpone_queue_item"
        postpone_data = {
            "action": "postpone_queue_item",
            "expected_version": str(orig_version),
            "item_id": fin_item.item_id,
            "scope": "general",
        }
        postpone_resp = client.post(interp_url, postpone_data)
        assert postpone_resp.status_code == 200

        # Reload from database and verify postponed state survives
        job.refresh_from_db()
        postponed_dossier = job.get_interpretation_dossier()
        assert postponed_dossier.version == orig_version + 1
        postponed_fin = postponed_dossier.general_fields["finalidad"]
        assert postponed_fin.review == "postponed"
        assert postponed_fin.value == orig_finalidad_text

        # Verify postponed audit delta
        postpone_delta = next(
            d for h in postponed_dossier.history for d in h.get("deltas", []) if d.get("field") == "finalidad"
        )
        assert postpone_delta["change_type"] == "postponed"

        # Verify invariants after postpone
        assert CurriculumProgress.objects.count() == initial_progress_count
        assert CurriculumPackage.objects.count() == initial_package_count
        with job.pdf.open("rb") as stream:
            current_bytes = stream.read()
        assert current_bytes == initial_source_bytes
        assert hashlib.sha256(current_bytes).hexdigest() == initial_source_sha256

        # Step B: Reject/clear the suggestion via save_queue_item with empty value
        postponed_queue = derive_operational_queue(postponed_dossier)
        postponed_fin_item = next(it for it in postponed_queue.items if it.field_name == "finalidad")
        clear_data = {
            "action": "save_queue_item",
            "expected_version": str(postponed_dossier.version),
            "item_id": postponed_fin_item.item_id,
            "value": "",
        }
        clear_resp = client.post(interp_url, clear_data)
        assert clear_resp.status_code == 200

        # Reload from database and verify cleared/rejected state survives
        job.refresh_from_db()
        cleared_dossier = job.get_interpretation_dossier()
        assert cleared_dossier.version == postponed_dossier.version + 1

        cleared_fin = cleared_dossier.general_fields["finalidad"]
        assert cleared_fin.value == ""
        assert cleared_fin.original_value == orig_finalidad_text
        assert cleared_fin.status == STATUS_MISSING
        assert cleared_fin.review == REVIEW_PENDING
        assert cleared_fin.origin == ORIGIN_TEACHER_ENTERED

        # Verify cleared audit delta
        clear_delta = next(
            d for h in cleared_dossier.history for d in h.get("deltas", [])
            if d.get("field") == "finalidad" and d.get("change_type") == "cleared"
        )
        assert clear_delta["before"]["value"] == orig_finalidad_text
        assert clear_delta["after"]["value"] == ""

        # Verify invariants after rejection/clearing
        assert CurriculumProgress.objects.count() == initial_progress_count
        assert CurriculumProgress.objects.filter(confirmed_by=user).count() == 0
        assert CurriculumPackage.objects.count() == initial_package_count
        with job.pdf.open("rb") as stream:
            current_cleared_bytes = stream.read()
        assert current_cleared_bytes == initial_source_bytes
        assert hashlib.sha256(current_cleared_bytes).hexdigest() == initial_source_sha256
        assert cleared_dossier.source_sha256 == initial_source_sha256

    def test_green_9_save_corrections_after_postpone_preserves_audit_trail_and_invariants(self):
        """3. Full lifecycle: suggestion -> postponed -> teacher corrected, verifying full history and source integrity."""
        client, user, job, pdf_bytes, initial_dossier = _setup_synthetic_job("green9_lifecycle_teacher")

        with job.pdf.open("rb") as stream:
            initial_source_bytes = stream.read()
        initial_source_sha256 = hashlib.sha256(initial_source_bytes).hexdigest()
        orig_finalidad_text = initial_dossier.general_fields["finalidad"].value
        orig_version = initial_dossier.version

        interp_url = reverse("tutor-import-interpretation", args=[job.pk])

        # 1. Postpone
        queue = derive_operational_queue(initial_dossier)
        fin_item = next(it for it in queue.items if it.field_name == "finalidad")
        client.post(interp_url, {
            "action": "postpone_queue_item",
            "expected_version": str(orig_version),
            "item_id": fin_item.item_id,
            "scope": "general",
        })

        job.refresh_from_db()
        d_postponed = job.get_interpretation_dossier()
        assert d_postponed.version == orig_version + 1

        # 2. Later, teacher decides to correct it
        editorial_text = "Finalidad redactada formalmente tras reconsideración docente."
        client.post(interp_url, {
            "action": "save_corrections",
            "expected_version": str(d_postponed.version),
            "finalidad": editorial_text,
        })

        job.refresh_from_db()
        d_final = job.get_interpretation_dossier()
        assert d_final.version == orig_version + 2

        fin_final = d_final.general_fields["finalidad"]
        assert fin_final.value == editorial_text
        assert fin_final.original_value == orig_finalidad_text
        assert fin_final.review == REVIEW_CORRECTED

        # History preserves both steps
        history_deltas = [d for h in d_final.history for d in h.get("deltas", []) if d.get("field") == "finalidad"]
        assert len(history_deltas) == 2
        assert history_deltas[0]["change_type"] == "postponed"
        assert history_deltas[1]["change_type"] == "modified"
        assert history_deltas[1]["after"]["value"] == editorial_text

        # Invariants preserved across all steps
        assert CurriculumProgress.objects.count() == 0
        assert CurriculumPackage.objects.count() == 0
        with job.pdf.open("rb") as stream:
            current_pdf_bytes = stream.read()
        assert current_pdf_bytes == initial_source_bytes
        assert hashlib.sha256(current_pdf_bytes).hexdigest() == initial_source_sha256
