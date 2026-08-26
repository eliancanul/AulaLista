"""Database contracts documented in docs/DATABASE.md, enforced here."""

import os

import django
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

pytestmark = pytest.mark.django_db


ACTIVITY_KEYS = {
    "id",
    "topic_title",
    "subtopic_title",
    "is_valid",
    "issues",
    "proposal",
    "selected",
}
PROPOSAL_KEYS = {"title", "objective", "micro_lesson", "final_explanation", "questions"}
TRACE_KEYS = {
    "stage",
    "model",
    "system",
    "prompt",
    "response_raw",
    "duration_ms",
    "attempts",
    "errors",
    "ok",
}
TOPIC_KEYS = {"titulo", "pagina_inicio", "pagina_fin", "subtemas"}


def make_job(**overrides):
    from curriculum.models import CurriculumImportJob

    job = CurriculumImportJob.objects.create()
    for field, value in overrides.items():
        setattr(job, field, value)
    return job


def test_topics_payload_contract():
    job = make_job(
        topics=[
            {
                "titulo": "Fracciones",
                "pagina_inicio": 1,
                "pagina_fin": 2,
                "subtemas": [{"titulo": "Suma", "actividades_sugeridas": 1}],
            }
        ]
    )
    for topic in job.topics:
        assert TOPIC_KEYS <= set(topic), f"faltan {TOPIC_KEYS - set(topic)}"
        for sub in topic["subtemas"]:
            assert {"titulo", "actividades_sugeridas"} <= set(sub)
            assert 1 <= sub["actividades_sugeridas"] <= 5
        assert topic["pagina_inicio"] <= topic["pagina_fin"]


def test_activities_payload_contract():
    job = make_job(
        activities=[
            {
                "id": "abc12345",
                "topic_title": "Fracciones",
                "subtopic_title": "Suma",
                "is_valid": True,
                "issues": [],
                "proposal": {
                    "title": "Suma",
                    "objective": "o",
                    "micro_lesson": "m",
                    "final_explanation": "f",
                    "questions": [],
                },
                "selected": True,
            }
        ]
    )
    for entry in job.activities:
        assert ACTIVITY_KEYS <= set(entry), f"faltan {ACTIVITY_KEYS - set(entry)}"
        assert PROPOSAL_KEYS <= set(entry["proposal"])
        # Invariante editorial: inválida ⇒ nunca seleccionada para convertir.
        if not entry["is_valid"]:
            assert entry["selected"] is False


def test_llm_trace_entries_contract():
    job = make_job(
        llm_trace=[
            {
                "stage": "identify_topics",
                "model": "qwen2.5:7b",
                "system": "s",
                "prompt": "p",
                "response_raw": "{}",
                "duration_ms": 10,
                "attempts": 1,
                "errors": [],
                "ok": True,
            }
        ]
    )
    for entry in job.llm_trace:
        assert TRACE_KEYS <= set(entry), f"faltan {TRACE_KEYS - set(entry)}"
        if entry["ok"] is False:
            # Todo fallo registrado debe decir por qué.
            assert entry["errors"], "fallo sin errores registrados"


def test_worker_failure_records_structured_error_with_traceback():
    """The worker buries exceptions into the job; the traceback must survive."""

    import json as jsonlib
    import os as oslib
    from unittest.mock import patch

    oslib.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")

    from curriculum import curriculum_import as pipeline
    from curriculum import views
    from curriculum.models import CurriculumImportJob

    job = make_job(
        source_text="[página 1]\nfracciones",
        page_count=1,
    )

    def boom(chunk):
        raise TypeError("contrato roto a propósito")

    with patch.object(pipeline, "extract_pdf_pages", return_value=["página uno"]), \
         patch.object(pipeline, "identify_topics", side_effect=boom):
        views._run_import_job_stage(job.pk, "extract")

    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED
    assert "contrato roto" in job.error_message

    failures = [entry for entry in job.llm_trace if not entry["ok"]]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["stage"] == "extract"
    assert any("TypeError" in line for line in failure["errors"])
    assert "boom" in failure["errors"][0]  # la pila apunta al culpable real
