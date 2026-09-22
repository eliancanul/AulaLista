"""Integration tests for AulaLista V0 Curriculum Interpretation Flow."""

from pathlib import Path
import hashlib
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

import copy
from curriculum.models import (
    CurriculumImportJob,
    CurriculumPackage,
    PLATFORM_ADMINISTRATOR_GROUP_NAME,
)
from curriculum.source_interpreter import (
    AnnexReference,
    ORIGIN_TEACHER_ENTERED,
    REVIEW_PENDING,
)
from helpers import tutor_client

pytestmark = pytest.mark.django_db

C01_PATH = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
C01_SHA256 = "33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648"
C04_PATH = Path("/Users/dojo/Downloads/planeacion-julio-quinto-grado.pdf")


def _upload_c01_job(client):
    """Upload C01 PDF as an authenticated teacher and return the resulting job."""
    content = C01_PATH.read_bytes()
    upload = SimpleUploadedFile(
        "prueba-semana-01.pdf",
        content,
        content_type="application/pdf",
    )
    resp = client.post(reverse("tutor-import-upload"), {"pdf": upload})
    assert resp.status_code == 302
    job = CurriculumImportJob.objects.latest("id")
    return job


def test_v0_upload_and_navigate_to_interpretation():
    """Verify that uploading C01 allows accessing the V0 interpretation view."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Check tutor-import-detail links to V0 interpretation
    detail_resp = client.get(reverse("tutor-import-detail", args=[job.pk]))
    assert detail_resp.status_code == 200
    assert "Asistente de planeación · Interpretación de guía docente (V0)" in detail_resp.content.decode("utf-8")
    assert reverse("tutor-import-interpretation", args=[job.pk]) in detail_resp.content.decode("utf-8")

    # Navigate to interpretation
    interp_resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert interp_resp.status_code == 200
    html = interp_resp.content.decode("utf-8")

    # Verify header metadata
    assert "Asistente de Planeación Semanal" in html
    assert "El uso de las vocales y la letra M" in html
    assert "Lenguajes" in html
    assert "Aprendizaje basado en Problemas (ABP)" in html
    assert "Aula" in html

    job.refresh_from_db()
    assert job.interpretation_dossier is not None
    assert job.interpretation_dossier["version"] == 1
    assert job.interpretation_dossier["source_sha256"] == C01_SHA256


def test_v0_interpretation_session_moments_and_provenance():
    """Verify Session 1 extraction: moments, materials, execution context and source links."""
    client = tutor_client()
    job = _upload_c01_job(client)

    resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")

    # Moments
    assert "Lunes - Sesión 1: Identificación" in html
    assert "juego de repaso de las vocales" in html
    assert "dibujen y decoren" in html
    assert "tarea para la casa" in html

    # Provenance links
    source_page_1 = reverse("tutor-import-source-page", args=[job.pk, 1])
    source_page_2 = reverse("tutor-import-source-page", args=[job.pk, 2])
    assert source_page_1 in html
    assert source_page_2 in html

    # Candidate annex links for Session 1 (Anexo 1 -> Pág 3, Anexo 2 -> Pág 4)
    source_page_3 = reverse("tutor-import-source-page", args=[job.pk, 3])
    source_page_4 = reverse("tutor-import-source-page", args=[job.pk, 4])
    assert source_page_3 in html
    assert source_page_4 in html

    # Multidimensional uncertainty tags
    assert "tag-origin" in html
    assert "tag-supported" in html
    assert "tag-ambiguous" in html  # Contexto aula vs casa
    assert "tag-pending" in html


def test_v0_teacher_correction_and_reopening():
    """Teacher corrects fields, confirms annexes, saves, and reopens with versioning."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial GET creates version 1
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))

    # POST teacher corrections
    post_data = {
        "action": "save_corrections",
        "expected_version": "1",
        "session_number": 1,
        "proyecto": "El uso de las vocales y la letra M (adaptado Grupo 1B)",
        "campos_formativos": "Lenguajes, Saberes y Pensamiento Científico",
        "proposito": "Propósito revisado por la docente titular.",
        "finalidad": "Finalidad docente confirmada.",
        "metodologia": "ABP con adaptaciones lúdicas",
        "escenario_proyecto": "Aula",
        "inicio": "Inicio corregido: Ronda de presentación de vocales.",
        "desarrollo": "Desarrollo enriquecido con materiales táctiles.",
        "cierre": "Cierre presencial con reflexión colectiva.",
        "materiales": "Fichas de letras, plastilina, tijeras.",
        "evaluacion": "Observación formativa y lista de cotejo.",
        "contexto_ejecucion": "Aula (completamente presencial)",
        "annex_confirm_1": "3",
        "annex_confirm_2": "4",
    }

    save_resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), post_data)
    assert save_resp.status_code == 200
    save_html = save_resp.content.decode("utf-8")
    assert "Versión 2 registrada" in save_html

    # Check database state
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 2
    assert dossier.general_fields["proyecto"].value == "El uso de las vocales y la letra M (adaptado Grupo 1B)"
    assert dossier.general_fields["proyecto"].review == "corrected"
    assert dossier.general_fields["proyecto"].origin == "teacher_entered"
    assert dossier.general_fields["proyecto"].original_value == "El uso de las vocales y la letra M"

    # Evidence is preserved!
    assert len(dossier.general_fields["proyecto"].evidence) > 0
    assert dossier.general_fields["proyecto"].evidence[0].page_number == 1

    # Session 1 checks
    s1 = dossier.sessions[0]
    assert s1.fields["inicio"].value == "Inicio corregido: Ronda de presentación de vocales."
    assert s1.fields["inicio"].review == "corrected"
    assert s1.fields["contexto_ejecucion"].value == "Aula (completamente presencial)"

    # Annex confirmation
    a1 = next(a for a in s1.annex_references if a.annex_number == "1")
    assert a1.confirmed_page == 3
    assert a1.review == "confirmed"

    # Reopening via GET loads version 2
    reopen_resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert reopen_resp.status_code == 200
    reopen_html = reopen_resp.content.decode("utf-8")
    assert "v2" in reopen_html
    assert "El uso de las vocales y la letra M (adaptado Grupo 1B)" in reopen_html
    assert "Inicio corregido: Ronda de presentación de vocales." in reopen_html
    assert "Historial de Decisiones Editoriales" in reopen_html
    assert "Resolución v2" in reopen_html


def test_v0_annex_source_page_serving_security():
    """Verify that candidate annex pages are served inline only to the owner teacher."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Valid page 3
    page3_resp = client.get(reverse("tutor-import-source-page", args=[job.pk, 3]))
    assert page3_resp.status_code == 200
    assert page3_resp["Content-Type"] == "application/pdf"
    assert "inline" in page3_resp["Content-Disposition"]

    # Out of range page 99
    page99_resp = client.get(reverse("tutor-import-source-page", args=[job.pk, 99]))
    assert page99_resp.status_code == 404


def test_v0_session_switching():
    """Verify teacher can view and interpret Session 2 (Martes)."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Switch to session 2 by query param
    resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session=2")
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "Martes - Sesión 2: Recuperación" in html
    assert "vocales mayúsculas y minúsculas" in html

    # Annex 3 candidate page 5
    source_page_5 = reverse("tutor-import-source-page", args=[job.pk, 5])
    assert source_page_5 in html
    assert "Anexo 3" in html


def test_v0_session_selection_404_on_nonexistent():
    """P0-2: Selecting a nonexistent session must return HTTP 404 instead of silent fallback."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial GET creates dossier
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))

    # Request out of range session number
    resp_num = client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session=999")
    assert resp_num.status_code == 404

    # Request nonexistent session_id
    resp_id = client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session_id=p99_s99")
    assert resp_id.status_code == 404


def test_v0_confirm_all_action_preserves_unconfirmed_annexes_and_missing_fields():
    """P0-3: confirm_all marks supported fields confirmed, but leaves annexes and ambiguous fields pending."""
    client = tutor_client()
    job = _upload_c01_job(client)

    resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "confirm_all", "session_number": 1},
    )
    assert resp.status_code == 200
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 2

    # Supported fields ARE confirmed
    assert dossier.general_fields["proyecto"].review == "confirmed"
    assert dossier.sessions[0].fields["inicio"].review == "confirmed"

    # Ambiguous field (contexto_ejecucion with home task) stays pending
    assert dossier.sessions[0].fields["contexto_ejecucion"].review == "pending"

    # P0-3: Candidate annexes are NOT auto-confirmed; confirmed_page remains None
    for a in dossier.sessions[0].annex_references:
        assert a.confirmed_page is None
        assert a.review == "pending"


def test_v0_tampered_pdf_blocks_mutation_with_409():
    """P0-1: If PDF source SHA-256 changes on disk, mutation actions return 409 Conflict."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial extraction
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.status == "active"

    # Simulate tampered PDF by overwriting file content on disk
    with job.pdf.open("wb") as stream:
        stream.write(b"%PDF-1.4 TAMPERED CONTENT " + b"0" * 200)

    # 1. GET detects tamper, redirects to wait without mutating DB or dossier
    get_resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert get_resp.status_code == 302
    assert get_resp.headers["Location"] == reverse("tutor-import-wait", args=[job.pk])

    job.refresh_from_db()
    dossier_tampered = job.get_interpretation_dossier()
    assert dossier_tampered.status == "active"
    assert not any(h.get("action") == "tamper_detected" for h in dossier_tampered.history)

    # 2. Attempting save_corrections returns 409 Conflict
    save_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "expected_version": str(dossier_tampered.version),
            "inicio": "Modificación ilegítima sobre PDF alterado",
        },
    )
    assert save_resp.status_code == 409
    assert "Conflicto de integridad" in save_resp.content.decode("utf-8")

    # 3. Attempting confirm_all returns 409 Conflict
    confirm_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "confirm_all",
            "expected_version": str(dossier_tampered.version),
        },
    )
    assert confirm_resp.status_code == 409

    # 4. Explicit reextract from a valid new PDF restores active state and archives history
    # Write a valid PDF (reuse C01 bytes)
    with job.pdf.open("wb") as stream:
        stream.write(C01_PATH.read_bytes())

    reextract_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "reextract",
            "expected_version": str(dossier_tampered.version),
        },
    )
    assert reextract_resp.status_code == 200
    job.refresh_from_db()
    dossier_reextracted = job.get_interpretation_dossier()
    assert dossier_reextracted.status == "active"
    assert any(h.get("action") == "reextract" for h in dossier_reextracted.history)


def test_v0_partial_post_preserves_untouched_fields():
    """P1-6: Partial POST must preserve untouched fields in the dossier."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial extraction
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    orig_desarrollo = job.get_interpretation_dossier().sessions[0].fields["desarrollo"].value
    orig_cierre = job.get_interpretation_dossier().sessions[0].fields["cierre"].value

    # Post only 'inicio'
    resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_number": 1,
            "inicio": "Inicio parcialmente actualizado.",
        },
    )
    assert resp.status_code == 200
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    s1 = dossier.sessions[0]
    assert s1.fields["inicio"].value == "Inicio parcialmente actualizado."
    # Untouched fields must NOT be emptied
    assert s1.fields["desarrollo"].value == orig_desarrollo
    assert s1.fields["cierre"].value == orig_cierre


def test_tampered_pdf_blocks_source_page_serving_with_409():
    """Sol Item 4: tutor-import-source-page returns 409 Conflict when PDF was tampered."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial extraction creates dossier
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))

    # Valid page 3 before tampering
    p3_ok = client.get(reverse("tutor-import-source-page", args=[job.pk, 3]))
    assert p3_ok.status_code == 200

    # Tamper PDF content on disk
    with job.pdf.open("wb") as stream:
        stream.write(b"%PDF-1.4 TAMPERED CONTENT " + b"0" * 200)

    # Serving page 3 must now be blocked with 409 Conflict
    p3_tampered = client.get(reverse("tutor-import-source-page", args=[job.pk, 3]))
    assert p3_tampered.status_code == 409
    assert "Conflicto de integridad" in p3_tampered.content.decode("utf-8")


def test_first_get_with_invalid_session_returns_404():
    """Sol Item 1: Initial visit with invalid session_id or session_number returns 404 (no silent fallback)."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # No dossier exists yet; initial GET with nonexistent session_id
    resp_id = client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session_id=p999_s999")
    assert resp_id.status_code == 404

    # Initial GET with nonexistent session number
    resp_num = client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session=999")
    assert resp_num.status_code == 404


def test_invalid_annex_confirmation_post_returns_400_and_does_not_version():
    """Sol Item 2: Submitting non-candidate page for annex confirmation returns 400 and does NOT bump version."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial extraction creates version 1
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == 1

    # Attempt to confirm page 1 for Annex 1 (whose candidates are [3])
    post_data = {
        "action": "save_corrections",
        "expected_version": "1",
        "session_number": 1,
        "annex_confirm_1": "1",
    }
    resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), post_data)
    assert resp.status_code == 400
    assert "no es una lámina candidata válida" in resp.content.decode("utf-8")

    # Version must NOT be bumped
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == 1


def test_confirm_all_does_not_mark_session_confirmed_when_unresolved():
    """Sol Item 3: confirm_all leaves SessionPlan.review='pending' when session has ambiguous fields or pending annexes."""
    client = tutor_client()
    job = _upload_c01_job(client)

    resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "confirm_all", "session_number": 1},
    )
    assert resp.status_code == 200
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    s1 = dossier.sessions[0]
    # SessionPlan.review MUST be pending
    assert s1.review == "pending"
    assert s1.fields["contexto_ejecucion"].review == "pending"
    assert s1.annex_references[0].review == "pending"


def test_timeout_and_cancellation_connected_to_job():
    """Sol Item 5: Cancellation/timeout connected to CurriculumImportJob preserves existing valid dossier."""
    client = tutor_client()
    job = _upload_c01_job(client)

    # Initial extraction creates valid dossier
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    assert job.interpretation_dossier is not None
    orig_dossier_version = job.interpretation_dossier["version"]

    # Request cancellation on job
    job.cancel_requested = True
    job.save(update_fields=["cancel_requested"])

    # Attempt reextract with cancellation active
    from curriculum.source_interpreter import (
        CurriculumSourceInterpreter,
        InterpretationCancelledError,
    )
    with pytest.raises((TimeoutError, InterpretationCancelledError)) as exc:
        CurriculumSourceInterpreter.prepare(job, job=job)
    assert "cancelada cooperativamente" in str(exc.value)

    # Job is marked cancelled and existing valid dossier is preserved intact
    job.refresh_from_db()
    assert job.cancelled_at is not None
    assert job.interpretation_dossier["version"] == orig_dossier_version


def test_successful_v0_does_not_leave_job_running_forever():
    """Gate Final Sol: Successful initial GET finishes stage, clears progress_stage, sets progress_finished_at, and detail returns 200."""
    client = tutor_client()
    job = _upload_c01_job(client)
    assert client.get(reverse("tutor-import-interpretation", args=[job.pk])).status_code == 200
    job.refresh_from_db()
    assert job.progress_stage == ""
    assert job.progress_finished_at is not None
    detail = client.get(reverse("tutor-import-detail", args=[job.pk]))
    assert detail.status_code == 200


def test_invalid_post_session_id_does_not_mutate_first_session():
    """Gate Final Sol: POST with nonexistent session_id returns 400/404 and does not mutate session 0 or bump version."""
    client = tutor_client()
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    before = job.get_interpretation_dossier()
    old_inicio = before.sessions[0].fields["inicio"].value
    version = before.version

    response = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "session_id": "does-not-exist",
            "session_number": "1",
            "inicio": "WRONG SESSION",
        },
    )
    assert response.status_code in (400, 404)
    job.refresh_from_db()
    after = job.get_interpretation_dossier()
    assert after.version == version
    assert after.sessions[0].fields["inicio"].value == old_inicio


def test_dossier_page_warnings_and_layout_fidelity_rendered_in_ui():
    """Gate Final: Ensure page_warnings and layout_fidelity limitation are visible in the HTML UI."""
    client = tutor_client()
    job = _upload_c01_job(client)
    resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "linearized_heuristics" not in html

    # Now inject a page warning into dossier and verify rendering
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    dossier.page_warnings[3] = "Página 3 contiene tablas complejas."
    job.save_interpretation_dossier(dossier)

    resp_warned = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    html_warned = resp_warned.content.decode("utf-8")
    assert "Advertencias de lectura en páginas fuente" in html_warned
    assert "Página 3:" in html_warned
    assert "Página 3 contiene tablas complejas." in html_warned


def test_advanced_audit_non_owner_cannot_read_dossier_or_pdf():
    """Advanced audit Item 2: non-owner gets 404 on interpretation and source pages."""
    owner = tutor_client()
    job = _upload_c01_job(owner)
    owner.get(reverse("tutor-import-interpretation", args=[job.pk]))
    stranger = tutor_client(username="other-teacher")
    assert stranger.get(reverse("tutor-import-interpretation", args=[job.pk])).status_code == 404
    assert stranger.get(reverse("tutor-import-source-page", args=[job.pk, 1])).status_code == 404


def test_advanced_audit_reextract_recovers_when_new_pdf_has_different_session_ids():
    """Advanced audit Item 2: explicit reextract adapts safely when new PDF lacks previous session IDs."""
    if not C04_PATH.exists():
        pytest.skip("C04 not available.")
    client = tutor_client()
    job = _upload_c01_job(client)
    assert client.get(reverse("tutor-import-interpretation", args=[job.pk]) + "?session_id=p2_s2").status_code == 200
    with job.pdf.open("wb") as stream:
        stream.write(C04_PATH.read_bytes())
    response = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract", "expected_version": "1"},
    )
    assert response.status_code == 200
    job.refresh_from_db()
    d = job.get_interpretation_dossier()
    assert d.source_sha256 == hashlib.sha256(C04_PATH.read_bytes()).hexdigest()
    assert d.status == "active"
    assert d.selection.get("session_id") in {s.session_id for s in d.sessions}
    assert any(h.get("action") == "reextract" for h in d.history)
    assert any(h.get("action") == "selection_reset" for h in d.history)


def test_advanced_audit_explicit_reextract_can_retry_after_cancel_request():
    """Advanced audit Item 3: explicit reextract resets cancel_requested and finishes stage cleanly."""
    client = tutor_client()
    job = _upload_c01_job(client)
    assert client.get(reverse("tutor-import-interpretation", args=[job.pk])).status_code == 200
    job.cancel_requested = True
    job.save(update_fields=["cancel_requested"])
    response = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract", "expected_version": "1"},
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.cancel_requested is False
    assert job.progress_stage == ""
    assert job.get_interpretation_dossier() is not None


def test_advanced_audit_stale_form_version_cannot_overwrite_newer_correction():
    """Advanced audit Item 5: stale form submission with old expected_version rejected with 409."""
    client = tutor_client()
    job = _upload_c01_job(client)
    response = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert 'name="expected_version"' in html
    first = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "session_id": "p2_s1",
            "expected_version": "1",
            "proyecto": "Edición A",
        },
    )
    assert first.status_code == 200
    stale = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "session_id": "p2_s1",
            "expected_version": "1",
            "proyecto": "Edición obsoleta B",
        },
    )
    assert stale.status_code == 409
    job.refresh_from_db()
    d = job.get_interpretation_dossier()
    assert d.version == 2
    assert d.general_fields["proyecto"].value == "Edición A"


def test_advanced_audit_malformed_or_missing_expected_version_cannot_bypass_lock():
    """Final Polish Item 1: malformed or missing expected_version returns 400 and blocks mutation."""
    client = tutor_client()
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    malformed = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "session_id": "p2_s1",
            "expected_version": "abc",
            "proyecto": "BYPASS",
        },
    )
    assert malformed.status_code == 400
    missing = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "session_id": "p2_s1",
            "proyecto": "BYPASS",
        },
    )
    assert missing.status_code in (400, 409)

    # Reextract without expected_version on existing active dossier must be rejected
    missing_reextract = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract"},
    )
    assert missing_reextract.status_code in (400, 409)

    job.refresh_from_db()
    d = job.get_interpretation_dossier()
    assert d.version == 1
    assert d.source_sha256 == C01_SHA256
    assert d.status == "active"
    assert d.general_fields["proyecto"].value != "BYPASS"


def test_advanced_audit_reextract_invalid_pdf_is_controlled_and_preserves_last_dossier():
    """Final Polish Item 2: reextract with corrupt PDF returns 400/422, preserves last dossier, and cleans progress_stage."""
    client = tutor_client()
    client.raise_request_exception = False
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    previous = job.interpretation_dossier.copy()
    with job.pdf.open("wb") as stream:
        stream.write(b"not a pdf")
    response = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "reextract",
            "expected_version": str(previous["version"]),
        },
    )
    assert response.status_code in (400, 422)
    job.refresh_from_db()
    assert job.interpretation_dossier["source_sha256"] == previous["source_sha256"]
    assert job.interpretation_dossier["version"] == previous["version"]
    assert job.progress_stage == ""


def test_advanced_audit_reextract_after_cancellation_clears_error_message_and_records_retry_in_history():
    """Final Polish Item 3: successful reextract after cancel clears obsolete error_message, progress_stage='', preserves cancelled_at, and records retry."""
    from django.utils import timezone
    client = tutor_client()
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    now_dt = timezone.now()
    job.cancel_requested = True
    job.cancelled_at = now_dt
    job.error_message = "Preserved legacy error message"
    job.interpretation_error_message = "Extracción cancelada a petición."
    job.progress_stage = "reading_pdf"
    job.save(update_fields=["cancel_requested", "cancelled_at", "error_message", "interpretation_error_message", "progress_stage", "updated_at"])

    response = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract", "expected_version": "1"},
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.cancel_requested is False
    assert job.interpretation_error_message == ""
    assert job.error_message == "Preserved legacy error message"
    assert job.progress_stage == ""
    assert job.cancelled_at == now_dt
    d = job.get_interpretation_dossier()
    assert d.version == 2
    reextract_h = next((h for h in d.history if h.get("action") == "reextract"), None)
    assert reextract_h is not None
    assert reextract_h.get("retry_after_cancel") is True


def test_platform_administrator_denied_teacher_v0_routes():
    """Blocker B2: Platform administrators (superuser and group members) fail closed with 403 on teacher routes."""
    User = get_user_model()
    users = [
        User.objects.create_user(username="super-admin-reg-v0", password="x", is_staff=True, is_superuser=True),
    ]
    grouped = User.objects.create_user(username="group-admin-reg-v0", password="x", is_staff=True)
    grouped.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMINISTRATOR_GROUP_NAME)[0])
    users.append(grouped)

    for user in users:
        client = Client()
        client.force_login(user)
        assert client.get(reverse("tutor-import-upload")).status_code == 403
        job = CurriculumImportJob.objects.create(
            pdf=SimpleUploadedFile(f"{user.username}.pdf", C01_PATH.read_bytes(), content_type="application/pdf"),
            created_by=user,
        )
        assert client.get(reverse("tutor-import-interpretation", args=[job.pk])).status_code == 403
        assert client.get(reverse("tutor-import-detail", args=[job.pk])).status_code == 403


def test_convert_selected_atomic_rollback_on_invalid_activity_index():
    """Blocker B3: Invalid select indices fail validation cleanly and rollback any packages in transaction."""
    client = tutor_client("atomic-convert-reg-v0")
    client.raise_request_exception = False
    user = get_user_model().objects.get(username="atomic-convert-reg-v0")
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("atomic-reg.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        created_by=user,
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        activities=[
            {
                "is_valid": True,
                "proposal": {
                    "title": "No debe persistir en fallo",
                    "objective": "Objetivo",
                    "micro_lesson": "Micro",
                    "final_explanation": "Final",
                    "questions": [],
                },
            }
        ],
    )
    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected", "select": ["0", "999"]},
    )
    assert response.status_code != 500
    assert not CurriculumPackage.objects.filter(created_by=user, title="No debe persistir en fallo").exists()
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED


def test_session_navigation_request_local_preserves_dossier_in_db():
    """Blocker B4: GET session navigation and POST switch_session are request-local and do not mutate DB dossier."""
    client = tutor_client("nav-concurrency-reg-v0")
    job = _upload_c01_job(client)
    initial = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert initial.status_code == 200
    job.refresh_from_db()
    before = job.interpretation_dossier.copy()

    navigated = client.get(reverse("tutor-import-interpretation", args=[job.pk]), {"session_id": "p2_s2"})
    assert navigated.status_code == 200
    assert navigated.context["active_session_id"] == "p2_s2"
    job.refresh_from_db()
    assert job.interpretation_dossier == before

    switched = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "switch_session", "session_id": "p2_s2", "expected_version": str(before["version"])},
    )
    assert switched.status_code in (200, 302)
    job.refresh_from_db()
    assert job.interpretation_dossier == before
    if switched.status_code == 200:
        assert switched.context["active_session_id"] == "p2_s2"


def test_reextract_without_expected_version_fails_400_during_tamper_and_cancel():
    """Requirement 1: reextract without expected_version must return 400 and preserve dossier even when tampered or cancel_requested."""
    client = tutor_client("reextract-no-version-reg-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    before = job.interpretation_dossier.copy()

    # Simulate tampered PDF
    with job.pdf.open("wb") as stream:
        stream.write(b"%PDF-1.4 tampered bytes")
    tampered_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract"},
    )
    assert tampered_resp.status_code in (400, 409)
    job.refresh_from_db()
    assert job.interpretation_dossier["version"] == before["version"]
    assert job.interpretation_dossier["source_sha256"] == before["source_sha256"]

    # Restore PDF and simulate cancel_requested
    with job.pdf.open("wb") as stream:
        stream.write(C01_PATH.read_bytes())
    job.cancel_requested = True
    job.save(update_fields=["cancel_requested", "updated_at"])

    cancel_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "reextract"},
    )
    assert cancel_resp.status_code in (400, 409)
    job.refresh_from_db()
    assert job.interpretation_dossier["version"] == before["version"]


def test_convert_selected_rejects_incomplete_proposal_before_any_write():
    """Requirement 2: proposal missing micro_lesson/final_explanation rejects before writing any package, failing job without 500."""
    client = tutor_client("convert-incomplete-reg-v0")
    client.raise_request_exception = False
    user = get_user_model().objects.get(username="convert-incomplete-reg-v0")
    valid_act = {
        "is_valid": True,
        "proposal": {
            "title": "Actividad Válida",
            "objective": "Objetivo",
            "micro_lesson": "Micro lección",
            "final_explanation": "Explicación final",
            "questions": [],
        },
    }
    incomplete_act = {
        "is_valid": True,
        "proposal": {
            "title": "Actividad Incompleta",
            "objective": "Objetivo",
            "questions": [],
        },
    }
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("incomplete.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        created_by=user,
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        activities=[valid_act, incomplete_act],
    )
    resp = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected", "select": ["0", "1"]},
    )
    assert resp.status_code != 500
    assert not CurriculumPackage.objects.filter(created_by=user).exists()
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED


def test_convert_selected_rejects_integer_title_before_write():
    """Requirement: proposal title with int (e.g. 42) must reject before write, returning non-500, 0 packages, and job failed."""
    client = tutor_client("convert-int-title-v0")
    client.raise_request_exception = False
    user = get_user_model().objects.get(username="convert-int-title-v0")
    proposal = {
        "title": 42,
        "objective": "Objetivo",
        "micro_lesson": "Micro lección",
        "final_explanation": "Explicación final",
        "questions": [],
    }
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("int_title.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        created_by=user,
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        activities=[{"is_valid": True, "proposal": proposal}],
    )
    resp = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected", "select": ["0"]},
    )
    assert resp.status_code != 500
    assert not CurriculumPackage.objects.filter(created_by=user).exists()
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED


def test_convert_selected_rejects_unknown_block_type_before_write():
    """Requirement: question with unknown block_type must reject before write, returning non-500, 0 packages, and job failed."""
    client = tutor_client("convert-unknown-block-v0")
    client.raise_request_exception = False
    user = get_user_model().objects.get(username="convert-unknown-block-v0")
    proposal = {
        "title": "Actividad con reactivo desconocido",
        "objective": "Objetivo",
        "micro_lesson": "Micro lección",
        "final_explanation": "Explicación final",
        "questions": [{"block_type": "desconocido", "value": {}}],
    }
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("unknown_block.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        created_by=user,
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
        activities=[{"is_valid": True, "proposal": proposal}],
    )
    resp = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected", "select": ["0"]},
    )
    assert resp.status_code != 500
    assert not CurriculumPackage.objects.filter(created_by=user).exists()
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED


def test_browser_post_unmodified_form_is_noop_byte_equal_and_shows_sin_cambios():
    """F1: Full browser form POST without edits (with CRLF and empty annex radios) is no-op, byte-equal, and shows 'sin cambios'."""
    client = tutor_client("unmodified-form-v0")
    job = _upload_c01_job(client)

    # Initial GET creates version 1
    get_resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert get_resp.status_code == 200
    job.refresh_from_db()
    initial_dossier_json = copy.deepcopy(job.interpretation_dossier)
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 1

    s1 = dossier.sessions[0]
    # Build complete browser POST payload mimicking real browser submission:
    # Textarea fields include CRLF (\r\n) newlines; annex radios sent empty
    post_data = {
        "action": "save_corrections",
        "expected_version": "1",
        "session_id": s1.session_id,
        "session_number": s1.session_number,
        "proyecto": dossier.general_fields["proyecto"].value,
        "proposito": dossier.general_fields["proposito"].value.replace("\n", "\r\n"),
        "finalidad": dossier.general_fields["finalidad"].value.replace("\n", "\r\n"),
        "metodologia": dossier.general_fields["metodologia"].value,
        "escenario_proyecto": dossier.general_fields["escenario_proyecto"].value,
        "campos_formativos": dossier.general_fields["campos_formativos"].value,
        "inicio": s1.fields["inicio"].value.replace("\n", "\r\n"),
        "desarrollo": s1.fields["desarrollo"].value.replace("\n", "\r\n"),
        "cierre": s1.fields["cierre"].value.replace("\n", "\r\n"),
        "materiales": s1.fields["materiales"].value.replace("\n", "\r\n"),
        "evaluacion": s1.fields["evaluacion"].value.replace("\n", "\r\n"),
        "contexto_ejecucion": s1.fields["contexto_ejecucion"].value,
        "annex_confirm_1": "",
        "annex_confirm_2": "",
    }

    resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), post_data)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "sin cambios" in html.lower()

    job.refresh_from_db()
    assert job.interpretation_dossier == initial_dossier_json
    dossier_after = job.get_interpretation_dossier()
    assert dossier_after.version == 1
    assert len(dossier_after.history) == len(dossier.history)
    # No false confirmations / corrections
    for field_name, f in dossier_after.general_fields.items():
        assert f.review == REVIEW_PENDING, f"General field {field_name} falsely reviewed"
        assert f.origin != ORIGIN_TEACHER_ENTERED, f"General field {field_name} falsely teacher_entered"
    for s_name, sf in dossier_after.sessions[0].fields.items():
        assert sf.review == REVIEW_PENDING, f"Session field {s_name} falsely reviewed"
        assert sf.origin != ORIGIN_TEACHER_ENTERED, f"Session field {s_name} falsely teacher_entered"


def test_campos_formativos_structured_round_trip_preserves_etica_naturaleza_y_sociedades():
    """F2: campos_formativos uses structured controls, preserving 'Ética, naturaleza y sociedades' without comma fragmentation."""
    client = tutor_client("campos-structured-v0")
    job = _upload_c01_job(client)

    # Initial GET: Verify structured controls (checkboxes), NOT a flat text input
    resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert 'type="checkbox"' in html
    assert 'name="campos_formativos"' in html
    assert 'value="Ética, naturaleza y sociedades"' in html

    # Submit structured list containing 'Ética, naturaleza y sociedades'
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    s1 = dossier.sessions[0]
    post_data = {
        "action": "save_corrections",
        "expected_version": "1",
        "session_id": s1.session_id,
        "session_number": s1.session_number,
        "campos_formativos": ["Ética, naturaleza y sociedades", "Lenguajes"],
    }
    post_resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), post_data)
    assert post_resp.status_code == 200

    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    cf = dossier.general_fields["campos_formativos"]
    # Must NOT be split into ['Ética', 'naturaleza y sociedades', 'Lenguajes']!
    assert cf.value == ["Ética, naturaleza y sociedades", "Lenguajes"]

    # Reopen via GET: both options must be checked
    reopen_resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    reopen_html = reopen_resp.content.decode("utf-8")
    assert 'value="Ética, naturaleza y sociedades"' in reopen_html
    assert 'value="Lenguajes"' in reopen_html
    assert "checked" in reopen_html
    import re as py_re
    assert py_re.search(r'value="Ética, naturaleza y sociedades"\s+checked', reopen_html)
    assert py_re.search(r'value="Lenguajes"\s+checked', reopen_html)


def test_http_rejects_duplicate_scalars_with_400_and_no_mutation():
    """B1: Any semantically scalar field with multiple values in POST must return 400 without mutating."""
    from django.http import QueryDict
    from bs4 import BeautifulSoup

    client = tutor_client("dup-scalar-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    s1 = dossier.sessions[0]
    orig_version = dossier.version
    orig_proyecto = dossier.general_fields["proyecto"].value

    scalar_test_cases = [
        [("proyecto", "VAL_UNO"), ("proyecto", "VAL_DOS")],
        [("expected_version", "1"), ("expected_version", "2")],
        [("action", "save_corrections"), ("action", "confirm_all")],
        [("session_id", s1.session_id), ("session_id", "otra_sesion")],
        [("session_number", "1"), ("session_number", "2")],
        [("inicio", "Texto A"), ("inicio", "Texto B")],
        [("desarrollo", "Dev A"), ("desarrollo", "Dev B")],
        [("cierre", "Cierre A"), ("cierre", "Cierre B")],
        [("materiales", "Mat A"), ("materiales", "Mat B")],
        [("evaluacion", "Eval A"), ("evaluacion", "Eval B")],
        [("contexto_ejecucion", "Aula"), ("contexto_ejecucion", "Patio")],
        [("annex_confirm_1", "3"), ("annex_confirm_1", "4")],
    ]

    for duplicates in scalar_test_cases:
        q = QueryDict("", mutable=True)
        q.appendlist("action", "save_corrections")
        q.appendlist("expected_version", str(orig_version))
        q.appendlist("session_id", s1.session_id)
        q.appendlist("session_number", str(s1.session_number))
        for k, v in duplicates:
            q.appendlist(k, v)

        resp = client.post(
            reverse("tutor-import-interpretation", args=[job.pk]),
            data=q.urlencode(),
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400, f"Expected 400 for duplicate field in {duplicates}, got {resp.status_code}"
        job.refresh_from_db()
        d_after = job.get_interpretation_dossier()
        assert d_after.version == orig_version, f"Version bumped on duplicate error in {duplicates}"
        assert d_after.general_fields["proyecto"].value == orig_proyecto

    # Verify campos_formativos IS allowed to be multivalued (it is a checkbox set)
    q_valid = QueryDict("", mutable=True)
    q_valid.appendlist("action", "save_corrections")
    q_valid.appendlist("expected_version", str(orig_version))
    q_valid.appendlist("session_id", s1.session_id)
    q_valid.appendlist("session_number", str(s1.session_number))
    q_valid.appendlist("campos_formativos", "Lenguajes")
    q_valid.appendlist("campos_formativos", "Saberes y pensamiento científico")
    valid_resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), q_valid)
    assert valid_resp.status_code == 200
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == orig_version + 1


def test_campos_formativos_legacy_string_renders_checked_and_preserves_on_roundtrip():
    """B3: Legacy scalar string in dossier renders as checked checkbox and persists cleanly."""
    from bs4 import BeautifulSoup
    from curriculum.source_interpreter import STATUS_MISSING, REVIEW_PENDING
    from django.http import QueryDict

    client = tutor_client("legacy-campos-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    dossier.general_fields["campos_formativos"].value = "Legado no canónico"
    job.save_interpretation_dossier(dossier)

    # 1. Render GET: 'Legado no canónico' must be an option and checked
    resp = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "Legado no canónico" in html
    soup = BeautifulSoup(html, "html.parser")
    legacy_cb = soup.find("input", {"name": "campos_formativos", "value": "Legado no canónico"})
    assert legacy_cb is not None, "Legacy checkbox not found in rendered HTML"
    assert legacy_cb.has_attr("checked"), "Legacy checkbox is not checked"

    # 2. Clearing checkboxes with sentinel sets value to [] and status=missing
    q_clear = QueryDict("", mutable=True)
    q_clear.appendlist("action", "save_corrections")
    q_clear.appendlist("expected_version", str(dossier.version))
    q_clear.appendlist("session_id", dossier.sessions[0].session_id)
    q_clear.appendlist("session_number", str(dossier.sessions[0].session_number))
    q_clear.appendlist("campos_formativos_present", "1")
    resp_clear = client.post(reverse("tutor-import-interpretation", args=[job.pk]), q_clear)
    assert resp_clear.status_code == 200

    job.refresh_from_db()
    d_cleared = job.get_interpretation_dossier()
    cf = d_cleared.general_fields["campos_formativos"]
    assert cf.value == []
    assert cf.status == STATUS_MISSING
    assert cf.review == REVIEW_PENDING

    # 3. Omission (no campos_formativos and no sentinel) causes no mutation
    v_cleared = d_cleared.version
    q_omit = QueryDict("", mutable=True)
    q_omit.appendlist("action", "save_corrections")
    q_omit.appendlist("expected_version", str(v_cleared))
    q_omit.appendlist("session_id", dossier.sessions[0].session_id)
    q_omit.appendlist("session_number", str(dossier.sessions[0].session_number))
    resp_omit = client.post(reverse("tutor-import-interpretation", args=[job.pk]), q_omit)
    assert resp_omit.status_code == 200
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == v_cleared


def test_legacy_payload_without_sentinel_does_not_split_canonical_comma():
    """B3: Legacy payload without sentinel containing comma must be preserved atomically without comma splitting."""
    from django.http import QueryDict

    client = tutor_client("legacy-comma-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()

    q = QueryDict("", mutable=True)
    for k, v in [
        ("action", "save_corrections"),
        ("expected_version", "1"),
        ("session_id", dossier.sessions[0].session_id),
        ("session_number", "1"),
        ("campos_formativos", "Lenguajes, Ética, naturaleza y sociedades"),
    ]:
        q.appendlist(k, v)

    resp = client.post(reverse("tutor-import-interpretation", args=[job.pk]), q)
    assert resp.status_code == 200
    job.refresh_from_db()
    value = job.get_interpretation_dossier().general_fields["campos_formativos"].value
    assert value == ["Lenguajes, Ética, naturaleza y sociedades"]


def test_duplicate_campos_formativos_present_sentinel_returns_400():
    """B1 residual: campos_formativos_present is scalar; duplicate values (identical or distinct) return 400."""
    from django.http import QueryDict

    client = tutor_client("sentinel-dup-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    s1 = dossier.sessions[0]
    orig_version = dossier.version

    # Case A: distinct values ('1' and '')
    q1 = QueryDict("", mutable=True)
    q1.appendlist("action", "save_corrections")
    q1.appendlist("expected_version", str(orig_version))
    q1.appendlist("session_id", s1.session_id)
    q1.appendlist("session_number", str(s1.session_number))
    q1.appendlist("campos_formativos_present", "1")
    q1.appendlist("campos_formativos_present", "")
    resp1 = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        data=q1.urlencode(),
        content_type="application/x-www-form-urlencoded",
    )
    assert resp1.status_code == 400
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == orig_version

    # Case B: identical values ('1' and '1')
    q2 = QueryDict("", mutable=True)
    q2.appendlist("action", "save_corrections")
    q2.appendlist("expected_version", str(orig_version))
    q2.appendlist("session_id", s1.session_id)
    q2.appendlist("session_number", str(s1.session_number))
    q2.appendlist("campos_formativos_present", "1")
    q2.appendlist("campos_formativos_present", "1")
    resp2 = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        data=q2.urlencode(),
        content_type="application/x-www-form-urlencoded",
    )
    assert resp2.status_code == 400
    job.refresh_from_db()
    assert job.get_interpretation_dossier().version == orig_version


def test_ambiguous_legacy_comma_string_renders_exactly_one_checked_option_and_roundtrips():
    """B3: Atomic legacy string containing canonical commas renders EXACTLY ONE checked checkbox and roundtrips without version bump."""
    from bs4 import BeautifulSoup
    from django.http import QueryDict

    client = tutor_client("ambiguous-legacy-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()

    legacy = "Lenguajes, Ética, naturaleza y sociedades"
    dossier.general_fields["campos_formativos"].value = legacy
    job.save_interpretation_dossier(dossier)
    orig_version = dossier.version

    # 1. GET request: verify that EXACTLY ONE checkbox is checked (the legacy atomic one)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")
    checked_nodes = soup.select('input[name="campos_formativos"]:checked')
    checked_values = [n.get("value") for n in checked_nodes]
    # Must NOT have 3 checked checkboxes ('Lenguajes', 'Ética...', legacy). Only the legacy option!
    assert checked_values == [legacy]

    # Verify canonical checkboxes exist but are NOT checked
    lenguajes_cb = soup.find("input", {"name": "campos_formativos", "value": "Lenguajes"})
    assert lenguajes_cb is not None
    assert not lenguajes_cb.has_attr("checked")
    etica_cb = soup.find("input", {"name": "campos_formativos", "value": "Ética, naturaleza y sociedades"})
    assert etica_cb is not None
    assert not etica_cb.has_attr("checked")

    # 2. Browser-shaped POST: submitting the exactly checked form controls without modification
    q = QueryDict("", mutable=True)
    q.appendlist("action", "save_corrections")
    q.appendlist("expected_version", str(orig_version))
    q.appendlist("session_id", dossier.sessions[0].session_id)
    q.appendlist("session_number", "1")
    q.appendlist("campos_formativos_present", "1")
    q.appendlist("campos_formativos", legacy)

    post_resp = client.post(
        url,
        data=q.urlencode(),
        content_type="application/x-www-form-urlencoded",
    )
    assert post_resp.status_code == 200
    assert "sin cambios" in post_resp.content.decode("utf-8").lower()

    # Verify no-op: version unchanged, value preserved as legacy string
    job.refresh_from_db()
    d_after = job.get_interpretation_dossier()
    assert d_after.version == orig_version
    assert d_after.general_fields["campos_formativos"].value == legacy


def test_f3_reextract_records_structured_diff_in_history():
    """F3: Re-extraction records structured diff of added/removed/changed fields in history entry deltas."""
    client = tutor_client("reextract-deltas-v0")
    job = _upload_c01_job(client)
    client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 1

    # Modify a general field and save
    post_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": "p2_s1",
            "session_number": "1",
            "proyecto": "Título Modificado Docente",
        },
    )
    assert post_resp.status_code == 200
    job.refresh_from_db()
    dossier_v2 = job.get_interpretation_dossier()
    assert dossier_v2.version == 2
    assert dossier_v2.general_fields["proyecto"].value == "Título Modificado Docente"

    # Now execute reextract
    re_resp = client.post(
        reverse("tutor-import-interpretation", args=[job.pk]),
        {
            "action": "reextract",
            "expected_version": "2",
        },
    )
    assert re_resp.status_code == 200
    job.refresh_from_db()
    dossier_v3 = job.get_interpretation_dossier()
    assert dossier_v3.version == 3

    # History must contain reextract entry with deltas
    reextract_entry = next((h for h in dossier_v3.history if h.get("action") == "reextract"), None)
    assert reextract_entry is not None
    assert "deltas" in reextract_entry
    assert len(reextract_entry["deltas"]) >= 1
    # Check that 'proyecto' changed from "Título Modificado Docente" back to the newly extracted value
    proj_delta = next((d for d in reextract_entry["deltas"] if d.get("field") == "proyecto"), None)
    assert proj_delta is not None
    assert proj_delta["scope"] == "general"
    assert proj_delta["before"]["value"] == "Título Modificado Docente"
    assert proj_delta["after"]["value"] != "Título Modificado Docente"


def test_f4_ui_hides_reason_box_for_resolved_fields_and_shows_pending():
    """F4: UI hides yellow reason-box once field is resolved/confirmed, but shows it when empty/missing."""
    from bs4 import BeautifulSoup
    client = tutor_client("f4-ui-test")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    # 1. Initial GET: pending fields show pending action / yellow warning box
    get_resp = client.get(url)
    assert get_resp.status_code == 200
    soup1 = BeautifulSoup(get_resp.content.decode("utf-8"), "html.parser")
    card_proj1 = soup1.find("div", {"id": "card-proyecto"})
    assert card_proj1 is not None
    assert card_proj1.find("div", class_="reason-box") is not None

    # 2. Confirm field explicitly
    confirm_resp = client.post(
        url,
        {
            "action": "confirm_all",
            "expected_version": "1",
            "session_id": "p2_s1",
            "session_number": "1",
        },
    )
    assert confirm_resp.status_code == 200
    soup2 = BeautifulSoup(confirm_resp.content.decode("utf-8"), "html.parser")
    card_proj2 = soup2.find("div", {"id": "card-proyecto"})
    assert card_proj2 is not None
    # Yellow reason box must disappear for confirmed/resolved field!
    assert card_proj2.find("div", class_="reason-box") is None

    # 3. Empty the field: must now show warning box requesting content
    empty_resp = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "2",
            "session_id": "p2_s1",
            "session_number": "1",
            "proyecto": "",
        },
    )
    assert empty_resp.status_code == 200
    soup3 = BeautifulSoup(empty_resp.content.decode("utf-8"), "html.parser")
    card_proj3 = soup3.find("div", {"id": "card-proyecto"})
    assert card_proj3 is not None
    reason_box3 = card_proj3.find("div", class_="reason-box")
    assert reason_box3 is not None
    assert "requiere" in reason_box3.text.lower() or "captura" in reason_box3.text.lower()


def test_f6_manual_annex_association_http_flow():
    """F6: HTTP flow for manual annex association:
    - Page 0 or > page_count rejected with 400.
    - Duplicate scalar rejected with 400.
    - Merely entering page without confirm checkbox is not associated.
    - Valid page with confirmation checkbox persists confirmed_page and teacher_selected_source_page.
    - Viewer link rendered.
    - Disassociation works.
    """
    from bs4 import BeautifulSoup
    from django.http import QueryDict

    client = tutor_client("f6-http-flow")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    # Ensure annex 1 has candidate_pages = []
    sess = dossier.sessions[0]
    annex = sess.annex_references[0]
    annex.candidate_pages = []
    annex.confirmed_page = None
    job.save_interpretation_dossier(dossier)

    # 1. Reject invalid manual page 0 (HTTP 400)
    resp_zero = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": sess.session_id,
            "session_number": str(sess.session_number),
            f"annex_manual_page_{annex.annex_number}": "0",
            f"annex_manual_confirm_{annex.annex_number}": "1",
        },
    )
    assert resp_zero.status_code == 400

    # 2. Reject invalid manual page > page_count (HTTP 400)
    resp_over = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": sess.session_id,
            "session_number": str(sess.session_number),
            f"annex_manual_page_{annex.annex_number}": "99",
            f"annex_manual_confirm_{annex.annex_number}": "1",
        },
    )
    assert resp_over.status_code == 400

    # 3. Reject duplicate scalar for manual page (HTTP 400)
    q_dup = QueryDict("", mutable=True)
    q_dup.appendlist("action", "save_corrections")
    q_dup.appendlist("expected_version", "1")
    q_dup.appendlist("session_id", sess.session_id)
    q_dup.appendlist("session_number", str(sess.session_number))
    q_dup.appendlist(f"annex_manual_page_{annex.annex_number}", "4")
    q_dup.appendlist(f"annex_manual_page_{annex.annex_number}", "5")
    q_dup.appendlist(f"annex_manual_confirm_{annex.annex_number}", "1")
    resp_dup = client.post(
        url,
        data=q_dup.urlencode(),
        content_type="application/x-www-form-urlencoded",
    )
    assert resp_dup.status_code == 400

    # 4. Merely entering page number WITHOUT confirm checkbox is NOT associated
    resp_noconf = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": sess.session_id,
            "session_number": str(sess.session_number),
            f"annex_manual_page_{annex.annex_number}": "4",
            # No annex_manual_confirm_N sent!
        },
    )
    assert resp_noconf.status_code == 200
    job.refresh_from_db()
    d_unconf = job.get_interpretation_dossier()
    assert d_unconf.version == 1  # No-op, no mutation
    assert d_unconf.sessions[0].annex_references[0].confirmed_page is None

    # 5. Valid manual page (e.g. 4) WITH confirm checkbox -> Associated and confirmed!
    resp_ok = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": sess.session_id,
            "session_number": str(sess.session_number),
            f"annex_manual_page_{annex.annex_number}": "4",
            f"annex_manual_confirm_{annex.annex_number}": "1",
        },
    )
    assert resp_ok.status_code == 200
    job.refresh_from_db()
    d_ok = job.get_interpretation_dossier()
    assert d_ok.version == 2
    annex_res = d_ok.sessions[0].annex_references[0]
    assert annex_res.confirmed_page == 4
    assert annex_res.origin == "teacher_selected_source_page"
    assert annex_res.review == "confirmed"

    # GET response includes viewer link for page 4
    expected_page_link = reverse("tutor-import-source-page", args=[job.pk, 4])
    soup_ok = BeautifulSoup(resp_ok.content.decode("utf-8"), "html.parser")
    page_4_links = [a.get("href") for a in soup_ok.find_all("a") if a.get("href") and expected_page_link in a.get("href")]
    assert len(page_4_links) >= 1

    # 6. Disassociate manual annex
    resp_disassoc = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "2",
            "session_id": sess.session_id,
            "session_number": str(sess.session_number),
            f"annex_disassociate_{annex.annex_number}": "1",
        },
    )
    assert resp_disassoc.status_code == 200
    job.refresh_from_db()
    d_dis = job.get_interpretation_dossier()
    assert d_dis.version == 3
    annex_dis = d_dis.sessions[0].annex_references[0]
    assert annex_dis.confirmed_page is None
    assert annex_dis.review == "pending"


def test_b4_http_strict_positive_integer_rejections():
    """B4: HTTP layer strictly rejects non-canonical integer strings for expected_version and manual page with HTTP 400.
    Rejects: '+1', '01', ' 1 ', '1.0', '1e0'.
    """
    client = tutor_client("b4-http-strict")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    sess = dossier.sessions[0]
    annex = sess.annex_references[0]

    for bad_ver in ["+1", "01", " 1 ", "1.0", "1e0", "true", "True"]:
        resp = client.post(
            url,
            {
                "action": "save_corrections",
                "expected_version": bad_ver,
                "session_id": sess.session_id,
                "session_number": "1",
            },
        )
        assert resp.status_code == 400, f"Expected 400 for expected_version={bad_ver!r}, got {resp.status_code}"

    for bad_page in ["+1", "01", " 1 ", "1.0", "1e0"]:
        resp = client.post(
            url,
            {
                "action": "save_corrections",
                "expected_version": "1",
                "session_id": sess.session_id,
                "session_number": "1",
                f"annex_manual_page_{annex.annex_number}": bad_page,
                f"annex_manual_confirm_{annex.annex_number}": "1",
            },
        )
        assert resp.status_code == 400, f"Expected 400 for manual_page={bad_page!r}, got {resp.status_code}"


def test_b6_http_annex_controls_use_reference_id_and_isolated_updates():
    """B6: Template renders controls using reference_id and handles duplicate annex numbers without collisions."""
    from bs4 import BeautifulSoup
    client = tutor_client("b6-http-flow")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    sess = dossier.sessions[0]

    # Inject two annexes with distinct annex_numbers "1" and "2"
    ref_a = AnnexReference(
        annex_number="1",
        raw_mention="Primer anexo 1",
        source_pages=[2],
        candidate_pages=[4],
    )
    ref_b = AnnexReference(
        annex_number="2",
        raw_mention="Segundo anexo 2",
        source_pages=[2],
        candidate_pages=[5],
    )
    sess.annex_references = [ref_a, ref_b]
    job.save_interpretation_dossier(dossier)

    # GET response should render unique reference_id input names
    resp_get = client.get(url)
    assert resp_get.status_code == 200
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    r0 = dossier.sessions[0].annex_references[0]
    r1 = dossier.sessions[0].annex_references[1]
    assert r0.reference_id != ""
    assert r1.reference_id != ""
    assert r0.reference_id != r1.reference_id

    soup = BeautifulSoup(resp_get.content.decode("utf-8"), "html.parser")
    # Verify inputs are named by reference_id
    input_r0 = soup.find("input", {"name": f"annex_confirm_{r0.reference_id}"})
    input_r1 = soup.find("input", {"name": f"annex_confirm_{r1.reference_id}"})
    assert input_r0 is not None
    assert input_r1 is not None

    # POST confirm ONLY r1
    post_resp = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": sess.session_id,
            "session_number": "1",
            f"annex_confirm_{r1.reference_id}": "5",
        },
    )
    assert post_resp.status_code == 200
    job.refresh_from_db()
    dossier_v2 = job.get_interpretation_dossier()
    after_r0 = dossier_v2.sessions[0].annex_references[0]
    after_r1 = dossier_v2.sessions[0].annex_references[1]
    assert after_r0.confirmed_page is None
    assert after_r1.confirmed_page == 5


def test_f7_http_duplicate_annex_numbers_fail_closed():
    """F7: Duplicate annex_number in same session is ambiguous and fails closed with 400."""
    client = tutor_client("f7-dup-annex-flow")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    sess = dossier.sessions[0]

    # Inject two annexes with identical annex_number "1"
    ref_a = AnnexReference(
        annex_number="1",
        raw_mention="Primer anexo 1",
        source_pages=[2],
        candidate_pages=[4],
    )
    ref_b = AnnexReference(
        annex_number="1",
        raw_mention="Segundo anexo 1",
        source_pages=[2],
        candidate_pages=[5],
    )
    sess.annex_references = [ref_a, ref_b]
    job.interpretation_dossier = dossier.to_dict()
    job.save(update_fields=["interpretation_dossier"])

    # GET response must fail closed with 400
    resp_get = client.get(url)
    assert resp_get.status_code == 400



def test_b4_final_review_http_post_session_number_empty_string_rejected():
    """B4 final review: HTTP POST with valid session_id but session_number='' MUST return 400."""
    client = tutor_client()
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    post_resp = client.post(
        url,
        {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": "p2_s1",
            "session_number": "",
        },
    )
    assert post_resp.status_code == 400


def test_b4_closure_review_switch_session_empty_string_rejected():
    """B4 closure review: POST action=switch_session with valid session_id and session_number='' must return 400."""
    client = tutor_client()
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    resp = client.post(
        url,
        {
            "action": "switch_session",
            "session_id": "p2_s1",
            "session_number": "",
        },
    )
    assert resp.status_code == 400


def test_b4_closure_review_switch_session_whitespace_and_noncanonical_rejected():
    """B4 closure review: POST action=switch_session with valid session_id and non-canonical session_number must return 400."""
    client = tutor_client()
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)

    bad_values = ["   ", "\t", "+1", "-1", "01", "1.0", "1e0", "abc"]
    for bad_val in bad_values:
        resp = client.post(
            url,
            {
                "action": "switch_session",
                "session_id": "p2_s1",
                "session_number": bad_val,
            },
        )
        assert resp.status_code == 400, f"Expected 400 for session_number={bad_val!r}, got {resp.status_code}"


def test_b4_closure_review_switch_session_absent_accepted():
    """B4 closure review: POST action=switch_session with valid session_id and session_number ABSENT must return 200 and switch."""
    client = tutor_client()
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)

    resp = client.post(
        url,
        {
            "action": "switch_session",
            "session_id": "p2_s2",
        },
    )
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "p2_s2" in html
















# ---------------------------------------------------------------------------
# F7: UX Review Queue and Priority Progression Integration Tests
# ---------------------------------------------------------------------------

def test_f7_ui_render_queue_single_active_item_and_collapsed_details():
    """F7: UI renders sticky summary, exactly ONE active decision panel, and collapses secondary details."""
    from bs4 import BeautifulSoup
    client = tutor_client("f7-single-active")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(url)
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")

    # 1. Sticky summary bar is present
    summary_bar = soup.find(id="priority-summary-bar")
    assert summary_bar is not None, "Sticky summary bar not found in DOM"

    # 2. Exactly ONE active decision card is rendered for pending item
    active_cards = soup.find_all("section", class_="active-decision-card")
    assert len(active_cards) == 1, f"Expected exactly 1 active decision card, found {len(active_cards)}"

    active_card = active_cards[0]
    assert active_card.find("h2", class_="decision-title") is not None
    confirm_btn = active_card.find("button", {"name": "action", "value": "confirm_queue_item"}) or active_card.find("button", {"name": "confirm_field"})
    assert confirm_btn is not None, "Confirm button not found in active decision card"

    # 3. Secondary/technical details eliminated from canonical UI; history details closed by default
    tech_details = soup.find("details", class_="technical-details")
    assert tech_details is None, "Technical details must be eliminated from canonical UI"

    hist_details = soup.find("details", class_="history-details")
    assert hist_details is not None
    assert not hist_details.has_attr("open"), "History details must be collapsed by default"

    full_fields = soup.find("details", class_="full-fields-details")
    assert full_fields is not None
    assert not full_fields.has_attr("open"), "Full fields accordion must be collapsed by default"

    rev_details = soup.find("details", class_="reviewed-items-collapse")
    assert rev_details is not None
    assert not rev_details.has_attr("open"), "Reviewed items details must be collapsed when pending remain"


def test_f7_ui_persistent_summary_counts_match_queue_items():
    """F7: Sticky summary counts match the DOM queue items 1:1."""
    from bs4 import BeautifulSoup
    client = tutor_client("f7-counts-match")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(url)
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")

    req_count = int(soup.find(id="count-requires-resolution").text.strip())
    pending_count = int(soup.find(id="count-pending-review").text.strip())
    reviewed_count = int(soup.find(id="count-reviewed").text.strip())
    not_spec_count = int(soup.find(id="count-not-specified").text.strip())

    dom_red_items = soup.select(".queue-item.item-red")
    dom_yellow_items = soup.select(".queue-item.item-yellow")
    dom_neutral_items = soup.select(".queue-item.item-neutral")
    dom_green_items = soup.select(".queue-item.item-green")

    assert req_count == len(dom_red_items), f"Red count mismatch: summary {req_count} vs DOM {len(dom_red_items)}"
    assert pending_count == len(dom_yellow_items), f"Yellow count mismatch: summary {pending_count} vs DOM {len(dom_yellow_items)}"
    assert not_spec_count == len(dom_neutral_items), f"Neutral count mismatch: summary {not_spec_count} vs DOM {len(dom_neutral_items)}"
    assert reviewed_count == len(dom_green_items), f"Green count mismatch: summary {reviewed_count} vs DOM {len(dom_green_items)}"


def test_f7_ui_labels_in_spanish_and_clean_presentation():
    """F7: UI presents Spanish human-readable labels and avoids raw technical keys."""
    client = tutor_client("f7-spanish-labels")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")

    # Header and summary labels
    assert "Revisa tu planeación" in html
    assert "Por resolver:" in html
    assert "Por revisar:" in html
    assert "Revisados:" in html
    assert "No especificado:" in html
    assert "Alcance: Documento completo" in html

    # Buttons
    assert "Está bien, continuar" in html
    assert "Corregir" in html
    assert "Revisar después" in html


def test_f7_confirm_single_field_action():
    """F7: Confirming a single field via confirm_field updates only that item without auto-confirming others."""
    client = tutor_client("f7-confirm-single")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    # Initial state: version 1, proyecto is pending
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 1
    assert dossier.general_fields["proyecto"].review == "pending"
    assert dossier.general_fields["proposito"].review == "pending"

    # Submit single confirm_field for 'general:proyecto'
    post_data = {
        "action": "save_corrections",
        "expected_version": "1",
        "session_id": dossier.sessions[0].session_id,
        "session_number": dossier.sessions[0].session_number,
        "confirm_field": "general:proyecto",
    }
    resp = client.post(url, post_data)
    assert resp.status_code == 200

    job.refresh_from_db()
    dossier2 = job.get_interpretation_dossier()
    assert dossier2.version == 2
    # Only proyecto was confirmed!
    assert dossier2.general_fields["proyecto"].review == "confirmed"
    # proposito MUST remain pending!
    assert dossier2.general_fields["proposito"].review == "pending"


def test_f7_mere_navigation_does_not_mutate_version_or_confirm():
    """F7: Selecting a different item or session via GET does not mutate version or accept decisions."""
    client = tutor_client("f7-no-mutation-nav")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    # Initial GET
    client.get(url)
    job.refresh_from_db()
    dossier1 = job.get_interpretation_dossier()
    v1 = dossier1.version

    # Navigate to specific item and session
    resp_nav = client.get(f"{url}?session_id=p2_s2&item=session:p2_s2:inicio")
    assert resp_nav.status_code == 200

    job.refresh_from_db()
    dossier2 = job.get_interpretation_dossier()
    assert dossier2.version == v1, "Version must not increment on GET navigation"
    assert len(dossier2.history) == len(dossier1.history), "History must not change on GET navigation"


def test_f7_dirty_guard_script_and_indicator_present():
    """F7: Dirty guard script and indicator are present in the DOM for progressive enhancement."""
    client = tutor_client("f7-dirty-guard")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")

    assert 'id="dirty-guard-script"' in html
    assert 'id="dirty-indicator"' in html
    assert 'beforeunload' in html
    assert 'Modificado sin guardar' in html


def test_f7_all_reviewed_empty_state_shows_revision_terminada():
    """F7: When all items in the queue are reviewed, UI shows 'Revisión terminada' empty state."""
    from bs4 import BeautifulSoup
    from curriculum.source_interpreter import REVIEW_CONFIRMED, STATUS_SUPPORTED, SourceReference
    client = tutor_client("f7-complete-state")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()

    # Mark all fields and annexes confirmed
    for gf in dossier.general_fields.values():
        gf.review = REVIEW_CONFIRMED
        gf.status = STATUS_SUPPORTED
    for s in dossier.sessions:
        for sf in s.fields.values():
            sf.review = REVIEW_CONFIRMED
            sf.status = STATUS_SUPPORTED
        for ref in s.annex_references:
            target_p = ref.candidate_pages[0] if ref.candidate_pages else 3
            ref.confirmed_page = target_p
            ref.review = REVIEW_CONFIRMED
            ref.status = STATUS_SUPPORTED
            ref.source_pages = [target_p]
            existing_ex = next((ev.excerpt for ev in ref.evidence if ev.page_number == target_p and ev.excerpt), f"ANEXO # {int(ref.annex_number):02d}")
            ref.evidence = [
                SourceReference(
                    page_number=target_p,
                    role="teacher_selected_source_page",
                    document_sha256=dossier.source_sha256,
                    excerpt=existing_ex,
                )
            ]
    job.save_interpretation_dossier(dossier)

    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # 1. 'Revisión terminada' is displayed prominently
    assert "Revisión terminada" in html
    completion_card = soup.find("div", class_="completion-card")
    assert completion_card is not None, "Completion card not found when all items are reviewed"

    # 2. No active decision card for pending items is displayed
    active_cards = soup.find_all("section", class_="active-decision-card")
    assert len(active_cards) == 0, "Active decision card should not be shown when review is complete"

    # 3. Reviewed items details remains closed by default at all times (per B6)
    rev_details = soup.find("details", class_="reviewed-items-collapse")
    assert rev_details is not None
    assert not rev_details.has_attr("open"), "Reviewed items details should remain closed by default at all times"


def test_f7_real_button_confirm_queue_item_b1():
    """F7 (B1): Real button POST with action=confirm_queue_item and item_id executes confirmation without full form."""
    client = tutor_client("f7-real-button-b1")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    assert dossier.version == 1
    assert dossier.general_fields["proyecto"].review == "pending"

    from curriculum.source_interpreter import derive_operational_queue
    queue = derive_operational_queue(dossier)
    proyecto_item = next(it for it in queue.items if it.field_name == "proyecto")

    # Real button submit: only action, expected_version, item_id (no session_id/session_number/confirm_field)
    post_payload = {
        "action": "confirm_queue_item",
        "expected_version": "1",
        "item_id": proyecto_item.item_id,
    }
    resp = client.post(url, post_payload)
    assert resp.status_code == 200

    job.refresh_from_db()
    dossier2 = job.get_interpretation_dossier()
    assert dossier2.version == 2
    assert dossier2.general_fields["proyecto"].review == "confirmed"
    # Other items remain pending
    assert dossier2.general_fields["proposito"].review == "pending"


def test_f7_atomicity_rejects_extraneous_keys_b2():
    """F7 (B2): POST with action=confirm_queue_item rejecting unauthorized unrelated keys with HTTP 400."""
    client = tutor_client("f7-atomicity-b2")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()

    from curriculum.source_interpreter import derive_operational_queue
    queue = derive_operational_queue(dossier)
    proyecto_item = next(it for it in queue.items if it.field_name == "proyecto")

    # Attempt to confirm proyecto while piggybacking unrelated field 'proposito'
    post_payload = {
        "action": "confirm_queue_item",
        "expected_version": "1",
        "item_id": proyecto_item.item_id,
        "proposito": "UNRELATED_MUTATION",
    }
    resp = client.post(url, post_payload)
    assert resp.status_code == 400
    assert "Claves no autorizadas" in resp.content.decode("utf-8")

    job.refresh_from_db()
    dossier_after = job.get_interpretation_dossier()
    assert dossier_after.version == 1
    assert dossier_after.general_fields["proyecto"].review == "pending"
    assert dossier_after.general_fields["proposito"].value != "UNRELATED_MUTATION"


def test_f7_adversarial_confirm_field_rejections_b3():
    """F7 (B3): Strict validation on confirm_field rejects malformed syntax, cross-session mutation, and collisions with HTTP 400."""
    client = tutor_client("f7-adversarial-b3")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    first_session = dossier.sessions[0]

    # 1. Malformed colon injection in general field
    resp1 = client.post(url, {
        "action": "save_corrections",
        "expected_version": "1",
        "session_id": first_session.session_id,
        "confirm_field": "general:proyecto:inject",
    })
    assert resp1.status_code == 400

    # 2. Unknown or nonexistent queue item_id
    resp2 = client.post(url, {
        "action": "confirm_queue_item",
        "expected_version": "1",
        "item_id": "nonexistent_fake_item_id",
    })
    assert resp2.status_code == 400

    # 3. Cross-session mutation attempt: confirm field in session B while session_id points to session A
    if len(dossier.sessions) > 1:
        other_session = dossier.sessions[1]
        resp3 = client.post(url, {
            "action": "save_corrections",
            "expected_version": "1",
            "session_id": first_session.session_id,
            "confirm_field": f"session:{other_session.session_id}:inicio",
        })
        assert resp3.status_code == 400


def test_f7_save_queue_item_and_leave_pending():
    """F7: Test save_queue_item edits single field and leave_queue_item_pending advances without mutating version."""
    client = tutor_client("f7-save-pending")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()

    from curriculum.source_interpreter import derive_operational_queue
    queue = derive_operational_queue(dossier)
    proyecto_item = next(it for it in queue.items if it.field_name == "proyecto")

    # 1. Save queue item: edits only proyecto
    resp_save = client.post(url, {
        "action": "save_queue_item",
        "expected_version": "1",
        "item_id": proyecto_item.item_id,
        "proyecto": "Proyecto Editado por F7",
    })
    assert resp_save.status_code == 200

    job.refresh_from_db()
    dossier2 = job.get_interpretation_dossier()
    assert dossier2.version == 2
    assert dossier2.general_fields["proyecto"].value == "Proyecto Editado por F7"
    assert dossier2.general_fields["proyecto"].review == "corrected"

    # 2. Leave pending: does not mutate version
    queue2 = derive_operational_queue(dossier2)
    next_item = queue2.items[1]
    resp_pending = client.post(url, {
        "action": "leave_queue_item_pending",
        "expected_version": "2",
        "item_id": next_item.item_id,
    })
    assert resp_pending.status_code == 200

    job.refresh_from_db()
    dossier3 = job.get_interpretation_dossier()
    assert dossier3.version == 2, "Leave pending must not bump dossier version"


def test_f7_scope_filtering_in_ui_b4():
    """F7 (B4): Scope filter sets queue.session_filter, displays Alcance: Sesión, and hides full document label."""
    from bs4 import BeautifulSoup
    client = tutor_client("f7-scope-ui-b4")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    target_s = dossier.sessions[0]

    resp = client.get(f"{url}?session_id={target_s.session_id}&scope={target_s.session_id}")
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    summary_bar = soup.find(id="priority-summary-bar")
    assert summary_bar is not None
    # Must show 'Alcance: Sesión' and NOT 'Alcance: Documento completo'
    assert f"Alcance: Sesión {target_s.session_number}" in summary_bar.get_text()
    assert "Alcance: Documento completo" not in summary_bar.get_text()

    # Ambiguous scope filter: non-existent raises 404
    resp_404 = client.get(f"{url}?scope=nonexistent_session_id")
    assert resp_404.status_code == 404


def test_f7_neutral_collapse_remains_closed_b6():
    """F7 (B6): Neutral items collapse (<details class='not-specified-collapse'>) remains closed by default."""
    from bs4 import BeautifulSoup
    client = tutor_client("f7-neutral-closed-b6")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    resp = client.get(url)
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.content.decode("utf-8"), "html.parser")

    neutral_details = soup.find("details", class_="not-specified-collapse")
    if neutral_details:
        assert not neutral_details.has_attr("open"), "Neutral items collapse must not be open by default"


def test_f7_residual_extra_value_in_confirm_rejected_400():
    """Residual: Extra value field in confirm_queue_item must be rejected with 400."""
    from curriculum.source_interpreter import derive_operational_queue
    client = tutor_client("f7-res-extra-val")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    q = derive_operational_queue(dossier)
    item = q.items[0]
    resp = client.post(
        url,
        {
            "action": "confirm_queue_item",
            "expected_version": str(dossier.version),
            "item_id": item.item_id,
            "proyecto": dossier.general_fields["proyecto"].value,
            "value": "UNAUTHORIZED",
        },
    )
    assert resp.status_code == 400


def test_f7_residual_duplicate_item_id_rejected_400():
    """Residual: Duplicate item_id scalar key in POST payload must be rejected with 400."""
    from curriculum.source_interpreter import derive_operational_queue
    client = tutor_client("f7-res-dup-item")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    item = derive_operational_queue(dossier).items[0]
    resp = client.post(
        url,
        {
            "action": "confirm_queue_item",
            "expected_version": str(dossier.version),
            "item_id": [item.item_id, item.item_id],
        },
    )
    assert resp.status_code == 400


def test_f7_residual_document_scope_reuse_rejected_400():
    """Residual: Mutating a session-scoped item using scope='document' must be rejected with 400."""
    from curriculum.source_interpreter import derive_operational_queue
    client = tutor_client("f7-res-scope-reuse")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    client.get(url)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    q = derive_operational_queue(dossier)
    session_item = next(it for it in q.items if it.scope == "session" and it.session_id == "p2_s2")
    resp = client.post(
        url,
        {
            "action": "confirm_queue_item",
            "expected_version": str(dossier.version),
            "item_id": session_item.item_id,
            "scope": "document",
        },
    )
    assert resp.status_code == 400


def test_f7_residual_general_scope_label_rendered():
    """Residual: scope=general must render 'Alcance: Datos generales del documento'."""
    client = tutor_client("f7-res-gen-label")
    job = _upload_c01_job(client)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    resp = client.get(f"{url}?scope=general")
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "Alcance: Datos generales del documento" in html
    assert "Alcance: Sesión" not in html
