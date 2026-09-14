import io
import json
import os
from unittest.mock import patch

import django
import pytest
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
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


from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db

# Las etapas LLM corren en segundo plano por defecto (#32/#36); los
# tests de comportamiento sincrono piden modo inline explicito.
sync_stage = override_settings(AULALISTA_IMPORT_ASYNC=False)


from helpers import MINIMAL_VALID_PDF_BYTES


def pdf_upload(name="curricula.pdf"):
    return SimpleUploadedFile(
        name,
        MINIMAL_VALID_PDF_BYTES,
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


def test_qwen14b_is_default_in_settings_and_curriculum_import():
    expected_model = "qwen2.5:14b"

    assert django_settings.AULALISTA_LLM_MODEL == expected_model
    assert pipeline.DEFAULT_MODEL == expected_model
    with override_settings(AULALISTA_LLM_MODEL=""):
        assert pipeline.llm_model() == expected_model


def test_topic_identification_drops_administrative_and_project_containers():
    chunk = {"first_page": 1, "last_page": 1, "text": "[página 1] Planeación Didáctica Semana 01"}

    def transport(_request):
        return {
            "message": {
                "content": json.dumps(
                    {"temas": [
                        {"titulo": "Planeación Didáctica Semana 01", "pagina_inicio": 1, "pagina_fin": 1, "tipo": "tema"},
                        {"titulo": "Identificación General", "pagina_inicio": 1, "pagina_fin": 1, "tipo": "tema"},
                        {"titulo": "PROYECTO: MIS EMOCIONES Y YO", "pagina_inicio": 1, "pagina_fin": 1, "tipo": "tema"},
                        {"titulo": "Representación numérica", "pagina_inicio": 1, "pagina_fin": 1, "tipo": "tema"},
                    ]}
                )
            }
        }

    assert pipeline.identify_topics(chunk, transport=transport) == [
        {"titulo": "Representación numérica", "pagina_inicio": 1, "pagina_fin": 1}
    ]


def test_upload_creates_staging_job_without_touching_editorial_models():
    before_packages = CurriculumPackage.objects.count()
    client = tutor_client()
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


@sync_stage
def test_extract_action_identifies_topics_with_citations_and_no_packages():
    client = tutor_client()
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
            follow=True,
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


@sync_stage
def test_failed_stage_records_error_and_allows_retry():
    client = tutor_client()
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
            follow=True,
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
            follow=True,
        )

    assert second.status_code == 200
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_TOPICS_PROPOSED


@sync_stage
def test_confirm_topics_checkpoint_edits_then_proposes_subtopics():
    client = tutor_client()
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
                # El tema 1 se desmarca: un checkbox desmarcado nunca viaja
                # en el POST, así que su clave simplemente no se envía (#44).
                "topic_1": "Proporcionalidad",
                "start_1": "3",
                "end_1": "4",
            },
            follow=True,
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
    client = tutor_client()
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
            # keep_0_1 ausente: descartado por la persona docente (#44)
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


# --- Issue #33: tema central vs título de actividad -------------------------


def make_minimal_pdf(pages_text):
    """Build a small single-font PDF whose text pypdf can extract."""

    import io

    pages = []
    for lines in pages_text:
        escaped = [
            line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            for line in lines.split("\n")
        ]
        body = "0 -18 Td ".join(f"({line}) Tj " for line in escaped)
        content = f"BT /F1 12 Tf 72 720 Td {body}ET".encode("latin-1")
        pages.append(content)

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids ["]
    kids = []
    for index in range(len(pages)):
        kids.append(f"{4 + index * 2} 0 R".encode())
    objects[1] = objects[1] + b" ".join(kids) + b"] /Count %d >>" % len(pages)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_number = 4
    for content in pages:
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {page_number + 1} 0 R /Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        stream = b"stream\n" + content + b"\nendstream"
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\n" + stream
        )
        page_number += 2

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_at = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode())
    buffer.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    )
    return buffer.getvalue()


def typed_topics_transport(payload):
    def transport(request):
        return {"message": {"content": json.dumps(payload)}}

    return transport


def test_identify_topics_filters_activity_and_other_titles():
    chunk = {"text": "[página 1] contenido", "first_page": 1, "last_page": 1}
    transport = typed_topics_transport(
        {
            "temas": [
                {
                    "titulo": "Fracciones",
                    "pagina_inicio": 1,
                    "pagina_fin": 1,
                    "tipo": "tema",
                },
                {
                    "titulo": "Actividad: colorea las mitades",
                    "pagina_inicio": 1,
                    "pagina_fin": 1,
                    "tipo": "actividad",
                },
                {
                    "titulo": "Nota editorial",
                    "pagina_inicio": 1,
                    "pagina_fin": 1,
                    "tipo": "otro",
                },
                # Sin tipo explícito se conserva (compatibilidad).
                {"titulo": "Números enteros", "pagina_inicio": 1, "pagina_fin": 1},
            ]
        }
    )

    topics = pipeline.identify_topics(chunk, transport=transport)
    assert [topic["titulo"] for topic in topics] == [
        "Fracciones",
        "Números enteros",
    ]


def test_synthetic_pdf_detection_keeps_only_central_topics_with_citations():
    pdf_bytes = make_minimal_pdf(
        [
            "BLOQUE I FRACCIONES",
            "Actividad: suma con material concreto",
            "Ejercicio: colorea las mitades",
            "FRACCIONES CONTINUACION",
        ]
    )
    from curriculum.curriculum_import import chunk_pages, extract_pdf_pages

    pages = extract_pdf_pages(io.BytesIO(pdf_bytes))
    assert len(pages) == 4
    assert "FRACCIONES" in pages[0]
    assert "colorea las mitades" in pages[2]

    chunks = chunk_pages(pages)
    transport = typed_topics_transport(
        {
            "temas": [
                {
                    "titulo": "Fracciones",
                    "pagina_inicio": 1,
                    "pagina_fin": 4,
                    "tipo": "tema",
                },
                {
                    "titulo": "Actividad: suma con material concreto",
                    "pagina_inicio": 2,
                    "pagina_fin": 2,
                    "tipo": "actividad",
                },
                {
                    "titulo": "Ejercicio: colorea las mitades",
                    "pagina_inicio": 3,
                    "pagina_fin": 3,
                    "tipo": "actividad",
                },
            ]
        }
    )
    merged = consolidate_topics(
        [pipeline.identify_topics(chunk, transport=transport) for chunk in chunks]
    )

    # Sólo el tema central sobrevive, con sus citas de página correctas.
    assert len(merged) == 1
    fracciones = merged[0]
    assert fracciones["titulo"] == "Fracciones"
    assert fracciones["pagina_inicio"] == 1
    assert fracciones["pagina_fin"] == 4
