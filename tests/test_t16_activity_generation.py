import os
from unittest.mock import patch

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.models import (  # noqa: E402
    CurriculumImportJob,
    CurriculumPackage,
    PublishedPackageSnapshot,
)
from curriculum.curriculum_import import propose_activities  # noqa: E402


pytestmark = pytest.mark.django_db


def pdf_upload():
    return SimpleUploadedFile(
        "curricula.pdf",
        b"%PDF-1.4 fake bytes",
        content_type="application/pdf",
    )


def completed_job():
    client = Client()
    response = client.post(
        reverse("tutor-import-upload"), {"pdf": pdf_upload()}
    )
    job = CurriculumImportJob.objects.get()
    with patch.object(
        pipeline, "extract_pdf_pages", return_value=["página uno"]
    ):
        job.extract_text()
    job.topics = [
        {
            "titulo": "Fracciones",
            "pagina_inicio": 1,
            "pagina_fin": 2,
            "subtemas": [
                {"titulo": "Suma de fracciones", "actividades_sugeridas": 1},
                {"titulo": "Resta de fracciones", "actividades_sugeridas": 1},
            ],
        }
    ]
    job.status = CurriculumImportJob.STATUS_COMPLETED
    job.save()
    return client, job


def valid_proposal(title="Suma de fracciones"):
    return {
        "title": title,
        "objective": "Sumar fracciones con distinto denominador.",
        "micro_lesson": "Para sumar fracciones se busca un denominador común.",
        "final_explanation": "El denominador común permite sumar numeradores.",
        "questions": [
            {
                "block_type": "reactivo",
                "value": {
                    "prompt": "¿Cuánto es 1/2 + 1/4?",
                    "options": [
                        {"position": 1, "text": "3/4", "expected": True, "feedback": "Correcto."},
                        {"position": 2, "text": "2/6", "expected": False, "feedback": "Revisa la microlección."},
                    ],
                    "hints": ["Busca el denominador común."],
                },
            }
        ],
    }


def test_propose_activities_maps_llm_output_to_package_payload_shape():
    payload = {
        "objetivo": "Comparar fracciones.",
        "microleccion": "Igualar denominadores para comparar.",
        "explicacion_final": "Con el mismo denominador se comparan numeradores.",
        "reactivos": [
            {
                "enunciado": "¿Qué fracción es mayor?",
                "opciones": [
                    {"posicion": 1, "texto": "3/4", "correcta": True, "retroalimentacion": "Sí."},
                    {"posicion": 2, "texto": "1/4", "correcta": False, "retroalimentacion": "Revisa."},
                ],
                "pistas": ["Dibuja las fracciones."],
            }
        ],
    }

    def transport(request):
        import json

        return {"message": {"content": json.dumps(payload)}}

    proposal = propose_activities("Comparación", "contexto", 2, transport=transport)

    assert proposal["title"] == "Comparación"
    assert proposal["objective"] == "Comparar fracciones."
    assert proposal["questions"][0]["value"]["options"][0]["position"] == 1
    assert sum(o["expected"] for o in proposal["questions"][0]["value"]["options"]) == 1


def test_generate_activities_validates_each_proposal_structurally():
    client, job = completed_job()
    invalid = valid_proposal()
    invalid["micro_lesson"] = ""  # rompe la estructura a propósito

    def fake_propose(subtopic_title, context, count):
        return invalid if subtopic_title.startswith("Resta") else valid_proposal()

    with patch.object(pipeline, "propose_activities", side_effect=fake_propose):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "generate_activities"},
        )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    by_subtopic = {a["subtopic_title"]: a for a in job.activities}
    assert by_subtopic["Suma de fracciones"]["is_valid"] is True
    assert by_subtopic["Resta de fracciones"]["is_valid"] is False
    assert any("microlección" in issue.lower() for issue in by_subtopic["Resta de fracciones"]["issues"])
    assert CurriculumPackage.objects.count() == 0


def test_convert_selected_creates_only_ai_tagged_drafts_and_never_publications():
    client, job = completed_job()
    entries = [
        {"is_valid": True, "proposal": valid_proposal()},
        {
            "is_valid": False,
            "issues": ["incompleto"],
            "proposal": dict(valid_proposal(), title="Inválido"),
        },
    ]
    job.activities = entries
    job.status = CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    job.save()

    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected", "select": ["0", "1"]},
    )

    assert response.status_code == 200
    job.refresh_from_db()
    # El inválido se ignora aunque el formulario lo envíe marcado.
    assert CurriculumPackage.objects.count() == 1
    draft = CurriculumPackage.objects.get()
    assert draft.ai_assisted is True
    assert draft.title == "Suma de fracciones"
    assert PublishedPackageSnapshot.objects.count() == 0
    assert draft.live_revision_id is None  # borrador sin publicación alguna
    assert job.status == CurriculumImportJob.STATUS_CONVERTED


def test_convert_without_selection_is_rejected():
    client, job = completed_job()
    job.activities = [{"is_valid": True, "proposal": valid_proposal()}]
    job.status = CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    job.save()

    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "convert_selected"},
    )

    job.refresh_from_db()
    assert CurriculumPackage.objects.count() == 0
    assert job.status == CurriculumImportJob.STATUS_FAILED
