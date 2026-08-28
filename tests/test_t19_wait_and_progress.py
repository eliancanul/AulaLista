"""Issues #32/#36: waiting pages with assistant status and live N/total."""

import json
import os
import time
from unittest.mock import patch

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.models import CurriculumImportJob  # noqa: E402

from helpers import tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db(transaction=True)


def pdf_upload():
    return SimpleUploadedFile(
        "curricula.pdf",
        b"%PDF-1.4 fake bytes",
        content_type="application/pdf",
    )


def completed_job():
    """A job whose hierarchy was confirmed by the teacher (no LLM involved)."""

    client = tutor_client()
    client.post(reverse("tutor-import-upload"), {"pdf": pdf_upload()})
    job = CurriculumImportJob.objects.get()
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
                        {"position": 2, "text": "2/6", "expected": False, "feedback": "Revisa."},
                    ],
                    "hints": ["Busca el denominador común."],
                },
            }
        ],
    }


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_extract_runs_in_background_and_wait_page_reports_it():
    client = tutor_client()
    client.post(reverse("tutor-import-upload"), {"pdf": pdf_upload()})
    job = CurriculumImportJob.objects.get()

    with patch.object(
        pipeline,
        "extract_pdf_pages",
        return_value=["página uno"],
    ), patch.object(
        pipeline,
        "identify_topics",
        return_value=[{"titulo": "Fracciones", "pagina_inicio": 1, "pagina_fin": 1}],
    ):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "extract"},
        )

        # The teacher immediately lands on the waiting page instead of a
        # frozen tab.
        assert response.status_code == 302
        assert response["Location"].endswith(f"/tutor/imports/{job.pk}/espera/")

        waiting = client.get(response["Location"])
        assert waiting.status_code == 200
        body = waiting.content.decode()
        assert 'id="assistant-wait-indicator"' in body
        assert "está leyendo los temas" in body

        # Keep the patches active until the background stage finishes.
        assert wait_until(
            lambda: (
                current := CurriculumImportJob.objects.get(pk=job.pk),
                not current.progress_stage,
            )[-1]
        )
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_TOPICS_PROPOSED
    assert job.progress_started_at is not None
    assert job.progress_finished_at >= job.progress_started_at
    # Once done, the waiting page hands control back to the review panel.
    response = client.get(reverse("tutor-import-wait", args=[job.pk]))
    assert response.status_code == 302
    assert response["Location"].endswith(f"/tutor/imports/{job.pk}/")


def test_generate_activities_interrupted_keeps_partial_results():
    client, job = completed_job()

    def fail_on_second(subtopic_title, context, count, *, feedback_issues=None):
        if subtopic_title.startswith("Resta"):
            raise OSError("modelo sin respuesta")
        return valid_proposal()

    with patch.object(
        pipeline, "propose_activities", side_effect=fail_on_second
    ):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "generate_activities"},
        )
        assert response.status_code == 302

        # Keep the patch active until the background stage finishes.
        assert wait_until(
            lambda: not CurriculumImportJob.objects.get(pk=job.pk).progress_stage
        )
    job.refresh_from_db()
    # Partial work survives the interruption and stays reviewable.
    assert job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    assert len(job.activities) == 1
    assert job.activities[0]["subtopic_title"] == "Suma de fracciones"
    assert "modelo sin respuesta" in job.error_message
    assert job.progress_finished_at >= job.progress_started_at


def test_wait_page_shows_live_counter_and_duration_warning():
    client, job = completed_job()
    job.progress_stage = "activities"
    job.progress_started_at = timezone.now()
    job.progress_total = 160
    job.progress_done = 37
    job.save()

    waiting = client.get(reverse("tutor-import-wait", args=[job.pk]))
    body = waiting.content.decode()
    assert 'id="assistant-progress-counter"' in body
    assert "37" in body and "160" in body
    assert "actividades" in body
    assert "varios minutos" in body


def test_detail_page_warns_about_expected_duration_before_generating():
    client, job = completed_job()
    response = client.get(reverse("tutor-import-detail", args=[job.pk]))
    body = response.content.decode()
    assert "data-generation-estimate" in body
    assert "~1 minuto por actividad" in body


def test_stale_running_stage_is_released_back_to_the_teacher():
    client, job = completed_job()
    job.progress_stage = "activities"
    job.progress_total = 2
    job.progress_started_at = timezone.now() - __import__("datetime").timedelta(
        minutes=120
    )
    job.save()

    response = client.get(reverse("tutor-import-wait", args=[job.pk]))
    assert response.status_code == 302
    job.refresh_from_db()
    assert job.progress_stage == ""
    assert "demasiado" in job.error_message
