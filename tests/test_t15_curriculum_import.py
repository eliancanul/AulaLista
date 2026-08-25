import json
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
from curriculum.curriculum_import import (  # noqa: E402
    ImportPipelineError,
    chunk_pages,
    consolidate_topics,
)


pytestmark = pytest.mark.django_db


def pdf_upload(name="curricula.pdf"):
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4 fake bytes for staging tests",
        content_type="application/pdf",
    )


def ok_chat(payload):
    def transport(request):
        return {"message": {"content": json.dumps(payload)}}

    return transport


def fail_times(failures, payload):
    calls = {"n": 0}

    def transport(request):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise OSError("ollama down")
        return {"message": {"content": json.dumps(payload)}}

    return transport


def upload_job(client):
    response = client.post(
        reverse("tutor-import-upload"),
        {"pdf": pdf_upload()},
    )
    assert response.status_code == 302
    return CurriculumImportJob.objects.get()


def test_upload_creates_staging_job_without_touching_editorial_models():
    before_packages = CurriculumPackage.objects.count()
    client = Client()
    job = upload_job(client)

    assert job.status == CurriculumImportJob.STATUS_UPLOADED
    assert job.pdf.name.startswith("curriculum_imports/")
    assert CurriculumPackage.objects.count() == before_packages
    assert PublishedPackageSnapshot.objects.count() == 0


def test_chunk_pages_tags_every_page_and_respects_limits():
    pages = ["texto uno", "texto dos", "texto tres"]
    chunks = chunk_pages(pages, max_chars=10000)

    assert len(chunks) == 1
    assert "[página 1]" in chunks[0]["text"]
    assert chunks[0]["last_page"] == 3

    long_page = "x" * 3000
    split = chunk_pages([long_page, long_page], max_chars=4000)
    assert len(split) >= 2


def test_consolidate_topics_deduplicates_by_title_and_widens_citations():
    merged = consolidate_topics(
        [
            [
                {"titulo": "Fracciones", "pagina_inicio": 1, "pagina_fin": 2},
                {"titulo": "Números enteros", "pagina_inicio": 2, "pagina_fin": 3},
            ],
            [
                {"titulo": "fracciones", "pagina_inicio": 4, "pagina_fin": 6},
            ],
        ]
    )

    assert len(merged) == 2
    fracciones = next(t for t in merged if "Fracciones" in t["titulo"])
    assert fracciones["pagina_inicio"] == 1
    assert fracciones["pagina_fin"] == 6


def test_chat_json_retries_until_schema_valid_response():
    prompt = "prueba"
    result = pipeline.chat_json(
        prompt,
        pipeline.TOPIC_SCHEMA,
        transport=ok_chat({"temas": [{"titulo": "Tema válido"}]}),
    )
    assert result["temas"][0]["titulo"] == "Tema válido"

    resilient = fail_times(2, {"temas": []})
    retried = pipeline.chat_json(prompt, pipeline.TOPIC_SCHEMA, transport=resilient)
    assert retried["temas"] == []

    always_down = fail_times(99, {})
    with pytest.raises(ImportPipelineError, match="no produjo una propuesta válida"):
        pipeline.chat_json(prompt, pipeline.TOPIC_SCHEMA, transport=always_down)


def test_extract_action_identifies_topics_with_citations_and_no_packages():
    client = Client()
    job = upload_job(client)

    pages = ["Bloque de fracciones", "Suma de fracciones y ejemplos"]

    def fake_identify(chunk):
        return [
            {
                "titulo": "Fracciones",
                "pagina_inicio": chunk["first_page"],
                "pagina_fin": chunk["last_page"],
            }
        ]

    with patch.object(pipeline, "extract_pdf_pages", return_value=pages), patch.object(
        pipeline, "identify_topics", side_effect=fake_identify
    ):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "extract"},
        )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_TOPICS_PROPOSED
    assert job.page_count == 2
    assert "[página 1]" in job.source_text
    assert job.topics == [
        {
            "titulo": "Fracciones",
            "pagina_inicio": 1,
            "pagina_fin": 2,
            "subtemas": [],
        }
    ]
    assert job.llm_log[0]["stage"] == "identify_topics"
    assert CurriculumPackage.objects.count() == 0
    assert PublishedPackageSnapshot.objects.count() == 0


def test_failed_stage_records_error_and_allows_retry():
    client = Client()
    job = upload_job(client)

    with patch.object(
        pipeline,
        "extract_pdf_pages",
        return_value=["contenido"],
    ), patch.object(
        pipeline,
        "identify_topics",
        side_effect=ImportPipelineError("modelo sin respuesta"),
    ):
        first = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "extract"},
        )

    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_FAILED
    assert "modelo sin respuesta" in job.error_message

    with patch.object(
        pipeline, "extract_pdf_pages", return_value=["contenido"]
    ), patch.object(pipeline, "identify_topics", return_value=[]):
        second = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {"action": "extract"},
        )

    assert second.status_code == 200
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_TOPICS_PROPOSED


def test_confirm_topics_checkpoint_edits_then_proposes_subtopics():
    client = Client()
    job = upload_job(client)
    with patch.object(
        pipeline, "extract_pdf_pages", return_value=["página uno", "página dos"]
    ):
        job.extract_text()
    job.topics = [
        {"titulo": "Fracciones", "pagina_inicio": 1, "pagina_fin": 2, "subtemas": []},
        {"titulo": "Proporcionalidad", "pagina_inicio": 3, "pagina_fin": 4, "subtemas": []},
    ]
    job.status = CurriculumImportJob.STATUS_TOPICS_PROPOSED
    job.save()

    def fake_subtopics(title, context):
        return {"subtemas": [f"{title} básico"], "actividades_sugeridas": 2}

    with patch.object(pipeline, "propose_subtopics", side_effect=fake_subtopics):
        response = client.post(
            reverse("tutor-import-detail", args=[job.pk]),
            {
                "action": "confirm_topics",
                "topic_0": "Fracciones propias e impropias",
                "start_0": "1",
                "end_0": "2",
                "keep_0": "on",
                # El tema 1 se desmarca y no debe llegar al modelo ni al resultado.
                "topic_1": "Proporcionalidad",
                "start_1": "3",
                "end_1": "4",
                "keep_1": "off",
            },
        )

    job.refresh_from_db()
    assert response.status_code == 200
    assert job.status == CurriculumImportJob.STATUS_SUBTOPICS_PROPOSED
    assert [topic["titulo"] for topic in job.topics] == [
        "Fracciones propias e impropias"
    ]
    assert job.topics[0]["subtemas"] == [
        {"titulo": "Fracciones propias e impropias básico", "actividades_sugeridas": 2}
    ]
    assert any(entry["stage"] == "propose_subtopics" for entry in job.llm_log)
    assert CurriculumPackage.objects.count() == 0


def test_confirm_subtopics_completes_hierarchy_without_creating_packages():
    client = Client()
    job = upload_job(client)
    job.topics = [
        {
            "titulo": "Fracciones",
            "pagina_inicio": 1,
            "pagina_fin": 2,
            "subtemas": [
                {"titulo": "Suma", "actividades_sugeridas": 1},
                {"titulo": "Resta", "actividades_sugeridas": 2},
            ],
        }
    ]
    job.status = CurriculumImportJob.STATUS_SUBTOPICS_PROPOSED
    job.save()

    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {
            "action": "confirm_subtopics",
            "heading_0": "Fracciones",
            "start_0": "1",
            "end_0": "2",
            "keep_topic_0": "on",
            "topic_0_sub_0": "Suma de fracciones",
            "keep_0_0": "on",
            "acts_0_0": "1",
            "topic_0_sub_1": "Resta de fracciones",
            "keep_0_1": "off",  # descartado por la persona docente
            "acts_0_1": "2",
        },
    )

    job.refresh_from_db()
    assert response.status_code == 200
    assert job.status == CurriculumImportJob.STATUS_COMPLETED
    assert len(job.topics) == 1
    assert job.topics[0]["subtemas"] == [
        {"titulo": "Suma de fracciones", "actividades_sugeridas": 1}
    ]
    assert CurriculumPackage.objects.count() == 0
    assert PublishedPackageSnapshot.objects.count() == 0
