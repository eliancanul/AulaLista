"""Regression for project plans organized by phases instead of numbered sessions."""

import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from curriculum.models import CurriculumImportJob
from curriculum.source_interpreter import CurriculumSourceInterpreter
from helpers import tutor_client
from test_t15_curriculum_import import make_minimal_pdf


SOURCE = Path(__file__).resolve().parents[1] / "docs/PLANEACIONES/738632554-3er-Grado-Junio-02-Tu-Historia-de-Transformacion-2023-2024.pdf"


def test_phase_based_plan_has_a_reviewable_project_without_invented_sessions():
    pages = [
        "Fase 4 Grado 3° Campo Lenguajes\nProyecto Tu historia de transformación Escenario\nAula.\n"
        "Metodología Aprendizaje basado en proyectos Tiempo de Se sugiere dos",
        "comunitarios. aplicación semanas\nDESARROLLO DEL PROYECTO\nFase #1. Planeación\n"
        "Actividad colectiva de observación y diálogo.",
        "Fase #2. Acción\nActividad de escritura colectiva.",
        "ANEXO\nEjercicio impreso.",
    ]
    sessions = CurriculumSourceInterpreter._detect_sessions(pages, "a" * 64, [], {})
    assert len(sessions) == 1
    assert sessions[0].status == "ambiguous"
    assert "sin sesiones explícitas" in sessions[0].title.lower()
    assert sessions[0].project_title == "Tu historia de transformación"
    assert sessions[0].pages == [2, 3]
    # Moments proposed from activities without inventing session cardinality or minutes
    assert len(sessions[0].activities) == 2
    assert sessions[0].fields["inicio"].value == "Actividad colectiva de observación y diálogo."
    assert sessions[0].fields["inicio"].origin == "proposed"
    assert sessions[0].fields["inicio"].status == "ambiguous"
    assert sessions[0].fields["desarrollo"].value == "Actividad de escritura colectiva."
    assert sessions[0].fields["desarrollo"].origin == "proposed"
    assert sessions[0].fields["duracion"].status == "missing"


def test_phase_based_pdf_passes_physical_verification_without_a_session_header():
    pdf = make_minimal_pdf([
        "Fase 4 Grado 3 Campo Lenguajes\nProyecto Historia de ejemplo Escenario\nAula.\n"
        "Metodologia Aprendizaje basado en proyectos Tiempo de dos semanas",
        "DESARROLLO DEL PROYECTO\nFase #1. Planeacion\nActividad de dialogo.",
        "Fase #2. Accion\nActividad de escritura.",
        "ANEXO\nEjercicio impreso.",
    ])
    dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(pdf))
    assert dossier.general_fields["grado"].value == "3"
    assert dossier.general_fields["duracion_proyecto"].value == "dos semanas"
    assert dossier.sessions[0].status == "ambiguous"
    assert dossier.sessions[0].fields["inicio"].value == "Actividad de dialogo."
    assert dossier.sessions[0].fields["desarrollo"].value == "Actividad de escritura."
    assert dossier.verification_report["is_valid"] is True
    assert dossier.verification_report["blocked_count"] == 0


@pytest.mark.skipif(not SOURCE.exists(), reason="PDF local no distribuido con el repositorio")
def test_lainitas_pdf_prepares_a_physically_valid_review_dossier():
    dossier = CurriculumSourceInterpreter.prepare(SOURCE)
    assert dossier.general_fields["grado"].value == "3"
    assert dossier.general_fields["metodologia"].value == "Aprendizaje basado en proyectos"
    # Implicit finalidad detected as ambiguous candidate pending teacher review
    assert dossier.general_fields["finalidad"].status == "ambiguous"
    assert dossier.general_fields["finalidad"].origin == "proposed"
    assert dossier.general_fields["finalidad"].value.strip()
    assert dossier.general_fields["finalidad"].evidence[0].page_number == 1
    assert dossier.general_fields["finalidad"].evidence[0].excerpt.strip()
    # Global duration across pages 1 and 2
    assert dossier.general_fields["duracion_proyecto"].value == "Se sugiere dos semanas"
    assert len(dossier.general_fields["duracion_proyecto"].evidence) == 2
    # Proposed first activity as inicio with verified provenance
    assert dossier.sessions
    assert dossier.sessions[0].status == "ambiguous"
    assert dossier.sessions[0].fields["inicio"].value.strip()
    assert dossier.sessions[0].fields["inicio"].evidence[0].page_number == 2
    assert dossier.sessions[0].fields["inicio"].origin == "proposed"
    assert dossier.verification_report["is_valid"] is True
    assert dossier.verification_report["blocked_count"] == 0


@pytest.mark.django_db
@pytest.mark.skipif(not SOURCE.exists(), reason="PDF local no distribuido con el repositorio")
def test_lainitas_pdf_upload_reaches_ready_for_teacher_review(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    client = tutor_client("phase-project-teacher")
    with override_settings(AULALISTA_IMPORT_ASYNC=False):
        response = client.post(
            reverse("tutor-import-upload"),
            {"pdf": SimpleUploadedFile(SOURCE.name, SOURCE.read_bytes(), content_type="application/pdf")},
        )
    assert response.status_code == 302
    job = CurriculumImportJob.objects.get(created_by__username="phase-project-teacher")
    assert job.interpretation_state == CurriculumImportJob.INTERPRETATION_STATE_READY
    assert job.has_valid_ready_dossier()
