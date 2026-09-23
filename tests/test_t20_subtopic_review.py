"""Issue #35: subtopic review with full titles, per-activity X and top-ups."""

import json
import os
from unittest.mock import patch

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.models import CurriculumImportJob  # noqa: E402
from curriculum import views  # noqa: E402

from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db


def pdf_upload():
    return SimpleUploadedFile(
        "curricula.pdf",
        MINIMAL_VALID_PDF_BYTES,
        content_type="application/pdf",
    )


def activities_job(existing_count=1):
    """A job in activities_proposed with one short subtopic (1 of 2 asked)."""

    client = tutor_client()
    client.post(reverse("tutor-import-upload"), {"pdf": pdf_upload()})
    job = CurriculumImportJob.objects.get()
    job.topics = [
        {
            "titulo": "Fracciones",
            "pagina_inicio": 1,
            "pagina_fin": 2,
            "subtemas": [
                {"titulo": "Suma de fracciones", "actividades_sugeridas": 2},
                {"titulo": "Resta de fracciones", "actividades_sugeridas": 1},
            ],
        }
    ]
    job.activities = [
        {
            "id": "aaa111",
            "topic_title": "Fracciones",
            "subtopic_title": "Suma de fracciones",
            "is_valid": True,
            "issues": [],
            "proposal": {
                "title": "Suma de fracciones",
                "objective": "Objetivo original.",
                "micro_lesson": "Microlección original.",
                "final_explanation": "Explicación original.",
                "questions": [],
            },
            "selected": True,
        }
    ]
    job.status = CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    job.save()
    return client, job


def valid_proposal(title="Suma de fracciones"):
    return {
        "title": title,
        "objective": f"Objetivo de {title}.",
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


def test_incremental_prompt_declares_existing_immutable():
    captured = {}

    def transport(request):
        captured["request"] = json.loads(request.data)
        return {"message": {"content": json.dumps({"objetivo": "", "microleccion": "", "explicacion_final": "", "reactivos": []})}}

    pipeline.propose_activities_incremental(
        "Suma de fracciones",
        "contexto",
        1,
        ["Suma de fracciones: Objetivo original."],
        transport=transport,
    )
    prompt = captured["request"]["messages"][1]["content"]
    # El .md versionado puede partir frases en varias líneas.
    flat = " ".join(prompt.split())
    assert "NO las modifiques" in flat
    assert "NO las repitas" in flat
    assert "Suma de fracciones: Objetivo original." in flat
    assert "NUEVA" in flat


def test_remove_activity_drops_only_the_targeted_proposal():
    client, job = activities_job()
    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "remove_activity", "activity_id": "aaa111"},
    )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.activities == []
    # The hierarchy stays untouched; only staging proposals change.
    assert job.topics[0]["subtemas"][0]["titulo"] == "Suma de fracciones"


def test_remove_unknown_activity_reports_error_without_changes():
    client, job = activities_job()
    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {"action": "remove_activity", "activity_id": "no-existe"},
        follow=True,
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert len(job.activities) == 1
    assert "ya no está" in job.error_message


@override_settings(AULALISTA_IMPORT_ASYNC=False)
def test_topup_appends_missing_and_never_touches_existing():
    client, job = activities_job()

    called = []

    def fake_incremental(subtopic_title, context_text, count, summaries, *, feedback_issues=None):
        # Both subtopics are below their requested count and get a top-up.
        called.append((subtopic_title, count, list(summaries)))
        if subtopic_title == "Suma de fracciones":
            assert count == 1
            assert summaries == ["Suma de fracciones: Objetivo original."]
            return valid_proposal("Suma con distinto denominador")
        assert subtopic_title == "Resta de fracciones"
        assert summaries == []
        return valid_proposal("Resta de fracciones")

    with patch.object(
        pipeline,
        "propose_activities_incremental",
        side_effect=fake_incremental,
    ):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "add_missing_activities"},
            follow=True,
        )
    assert response.status_code == 200

    job.refresh_from_db()
    # Existing proposal survives byte-for-byte and stays first.
    first = job.activities[0]
    assert first["id"] == "aaa111"
    assert first["proposal"]["objective"] == "Objetivo original."
    # Exactly the missing activities were appended.
    assert len(job.activities) == 3
    appended = job.activities[1]
    assert appended["proposal"]["title"] == "Suma con distinto denominador"
    assert appended["added_by_topup"] is True
    assert ("Suma de fracciones", 1, ["Suma de fracciones: Objetivo original."]) in called
    assert ("Resta de fracciones", 1, []) in called
    assert job.error_message == ""
    assert job.progress_stage == ""


def test_review_screen_shows_full_titles_grouping_and_x_buttons():
    client, job = activities_job()
    response = client.get(reverse("tutor-import-detail", args=[job.pk]))
    body = response.content.decode()
    # Full titles are visible (not just "Subtema 1").
    assert "Suma de fracciones" in body
    assert "Resta de fracciones" in body
    assert "faltan 1 de 2" in body
    assert 'value="remove_activity"' in body
    assert 'name="activity_id" value="aaa111"' in body
    assert "Agregar las actividades que faltan" in body


# --- #49: regeneración automática hasta pasar la validación ------------------


def invalid_proposal(title="Suma de fracciones"):
    proposal = valid_proposal(title)
    proposal["micro_lesson"] = ""
    return proposal


def test_invalid_activity_regenerates_with_feedback_until_valid():
    from django.test import override_settings

    calls = []

    def flaky_propose(subtopic_title, context_text, count, summaries, *, feedback_issues=None):
        calls.append(list(feedback_issues or []))
        if len(calls) == 1:
            return invalid_proposal()
        return valid_proposal()

    with override_settings(AULALISTA_IMPORT_ASYNC=False):
        client, job = activities_job()
        with patch.object(
            pipeline,
            "propose_activities_incremental",
            side_effect=flaky_propose,
        ):
            response = client.post(
                reverse("tutor-import-detail", args=[job.pk]),
                {"action": "add_missing_activities"},
                follow=True,
            )

    assert response.status_code == 200
    # First call had no feedback; the retry received the exact issues.
    assert calls[0] == []
    assert calls[1] and "microlección" in calls[1][0].lower()
    job.refresh_from_db()
    new_entry = next(
        entry for entry in job.activities if entry.get("added_by_topup")
    )
    assert new_entry["is_valid"] is True


def test_regeneration_is_bounded_and_last_attempt_stays_flagged():
    from django.test import override_settings

    with override_settings(AULALISTA_IMPORT_ASYNC=False):
        client, job = activities_job()
        with patch.object(
            pipeline,
            "propose_activities_incremental",
            return_value=invalid_proposal(),
        ):
            client.post(
                reverse("tutor-import-detail", args=[job.pk]),
                {"action": "add_missing_activities"},
                follow=True,
            )

    job.refresh_from_db()
    new_entry = next(
        entry for entry in job.activities if entry.get("added_by_topup")
    )
    assert new_entry["is_valid"] is False
    assert new_entry["issues"]


def test_review_screen_renders_new_card_design():
    client, job = activities_job()
    response = client.get(reverse("tutor-import-detail", args=[job.pk]))
    body = response.content.decode()
    assert 'class="activity-card' in body
    assert "activity-head" in body
    assert "badge" in body
    assert 'form="convert-form"' in body
