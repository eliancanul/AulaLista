"""Issue #34: persistent technical log of every LLM exchange, downloadable."""

import json
import os
from unittest.mock import patch

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum import curriculum_import as pipeline  # noqa: E402
from curriculum.models import CurriculumImportJob  # noqa: E402

from helpers import tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db


def pdf_upload():
    return SimpleUploadedFile(
        "curricula.pdf",
        b"%PDF-1.4 fake bytes",
        content_type="application/pdf",
    )


def topics_transport(request):
    import json as jsonlib

    payload = jsonlib.loads(request.data)
    assert payload["messages"][0]["role"] == "system"
    captured_prompt = payload["messages"][1]["content"]
    return {
        "message": {
            "content": jsonlib.dumps(
                {"temas": [{"titulo": "Fracciones", "tipo": "tema"}]}
            )
        }
    }


def test_stage_records_full_exchange_in_job_trace():
    client = tutor_client()
    client.post(reverse("tutor-import-upload"), {"pdf": pdf_upload()})
    job = CurriculumImportJob.objects.get()

    captured = {}

    def fake_transport(request):
        captured["prompt"] = json.loads(request.data)["messages"][1]["content"]
        return {
            "message": {
                "content": json.dumps(
                    {"temas": [{"titulo": "Fracciones", "tipo": "tema"}]}
                )
            }
        }

    # Reference the real function before it gets patched out.
    real_identify = pipeline.identify_topics

    def fake_identify(chunk):
        return real_identify(chunk, transport=fake_transport)

    with patch.object(
        pipeline,
        "extract_pdf_pages",
        return_value=["página uno con fracciones"],
    ), patch.object(pipeline, "identify_topics", side_effect=fake_identify):
        from django.test import override_settings

        with override_settings(AULALISTA_IMPORT_ASYNC=False):
            client.post(
                reverse("tutor-import-detail", args=[job.pk]),
                {"action": "extract"},
                follow=True,
            )

    job.refresh_from_db()
    assert len(job.llm_trace) == 1
    entry = job.llm_trace[0]
    assert entry["stage"] == "identify_topics"
    assert entry["ok"] is True
    assert "fracciones" in entry["prompt"].lower()
    assert entry["system"]  # versioned system prompt recorded
    assert json.loads(entry["response_raw"])["temas"][0]["titulo"] == "Fracciones"
    assert entry["attempts"] >= 1
    assert isinstance(entry["duration_ms"], int)


def test_technical_log_markdown_download():
    client, job = _job_with_trace()
    response = client.get(reverse("tutor-import-log-md", args=[job.pk]))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/markdown")
    assert "attachment" in response["Content-Disposition"]
    body = response.content.decode()
    assert f"Importación #{job.pk}" in body
    assert "**Prompt (user)**" in body
    assert "**Respuesta cruda**" in body
    assert "identify_topics" in body


def test_technical_log_json_download():
    client, job = _job_with_trace()
    response = client.get(reverse("tutor-import-log-json", args=[job.pk]))
    assert response.status_code == 200
    data = json.loads(response.content.decode())
    assert data[0]["stage"] == "identify_topics"


def test_versioned_prompts_drive_the_prompts():
    """The stage prompts come from curriculum/prompts/*.md files."""

    template = pipeline.load_prompt_template("propose_subtopics")
    assert "$topic_title" in template and "$context" in template

    rendered = pipeline.render_prompt(
        "propose_subtopics", topic_title="X", context="Y"
    )
    assert "X" in rendered and "Y" in rendered


# --- helpers -----------------------------------------------------------------


def _job_with_trace():
    client = tutor_client()
    client.post(reverse("tutor-import-upload"), {"pdf": pdf_upload()})
    job = CurriculumImportJob.objects.get()
    job.llm_trace = [
        {
            "stage": "identify_topics",
            "model": pipeline.llm_model(),
            "system": pipeline.system_prompt(),
            "prompt": "prompt de prueba",
            "response_raw": '{"temas": []}',
            "duration_ms": 123,
            "attempts": 1,
            "errors": [],
            "ok": True,
        }
    ]
    job.save(update_fields=["llm_trace"])
    return client, job
