"""Issue #96: deterministic annex fast path for reviewable staging data."""

import json
import os
import hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import django
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
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
from curriculum.views import (  # noqa: E402
    _import_action_annex_fast_path,
    _import_action_extract,
    _run_import_job_stage,
)


pytestmark = pytest.mark.django_db


ANNEX_SOURCE = """[página 4]
Planeación Didáctica Semana 01
Proyecto: El uso de las vocales y la letra M
Contenido: Mis primeros pasos en la lectoescritura

[página 5]
Desarrollo de actividades
Asigne como tarea el anexo 1, anexo 2 y anexo 3.

[página 6]
ANEXO # 01
Busca el video en YouTube así:
Canción de las vocales
https://example.test/vocales-aula
La ______ jugando está.
La ______ comió y se fue.
La ______, la ______ y la ______ se fueron a la escuela como tú.
Escribe en los círculos las cinco vocales mostradas en el video.
Con ayuda, completa las frases de la canción escuchada y cántala.

[página 7]
ANEXO # 02
Aprendamos las vocales mayúsculas y minúsculas.
https://example.test/vocales-color
Según lo aprendido, colorea el dibujo de esta forma:
Vocal A -> verde
Vocal E -> amarillo
Vocal I -> rojo
Vocal O -> azul
Vocal U -> anaranjado

[página 8]
ANEXO # 03
Observa el video y relaciona cada grupo de vocales:
https://example.test/vocales-match
a, e, i, o, u
A, E, I, O, U
Vocales mayúsculas
Vocales minúsculas
Significa menor
Significa mayor
"""


def test_annex_fast_path_extracts_manifest_and_all_three_companions():
    result = pipeline.build_annex_fast_path(ANNEX_SOURCE)

    assert result is not None
    assert [item["number"] for item in result["manifest"]] == [1, 2, 3]
    assert [item["page"] for item in result["manifest"]] == [6, 7, 8]
    assert [item["source_url"] for item in result["manifest"]] == [
        "https://example.test/vocales-aula",
        "https://example.test/vocales-color",
        "https://example.test/vocales-match",
    ]
    assert [activity["annex"]["kind"] for activity in result["activities"]] == [
        "fill_blank",
        "color_mapping",
        "matching",
    ]
    assert all(activity["annex"]["source_pages"] == [page] for activity, page in zip(result["activities"], [6, 7, 8]))


def test_annex_companions_are_valid_current_package_proposals_and_count_is_one_entry_each():
    result = pipeline.build_annex_fast_path(ANNEX_SOURCE)

    assert len(result["activities"]) == 3
    for activity in result["activities"]:
        proposal = activity["proposal"]
        if activity["is_valid"]:
            assert proposal["questions"]
            assert all(sum(option["expected"] for option in question["value"]["options"]) == 1 for question in proposal["questions"])
            assert all(question["value"]["hints"] for question in proposal["questions"])
            assert all(option["text"] for question in proposal["questions"] for option in question["value"]["options"])

    fill_entry = result["activities"][0]
    fill = fill_entry["proposal"]
    assert "completar" in fill["objective"].lower()
    assert fill["questions"] == []
    assert fill_entry["is_valid"] is False
    assert "requires_human_answer_key" in fill_entry["issues"]
    assert fill_entry["annex"]["details"]["requires_human_answer_key"] is True
    assert fill_entry["annex"]["details"]["blanks"]

    colors = result["activities"][1]["proposal"]["questions"]
    assert len(colors) == 5
    expected_colors = {
        "A": "verde",
        "E": "amarillo",
        "I": "rojo",
        "O": "azul",
        "U": "anaranjado",
    }
    for question, vowel in zip(colors, "AEIOU"):
        expected = [option["text"] for option in question["value"]["options"] if option["expected"]]
        assert expected == [expected_colors[vowel]]

    matching = result["activities"][2]["proposal"]["questions"]
    assert len(matching) == 4
    expected_matching = [
        "Vocales minúsculas",
        "Vocales mayúsculas",
        "Significa menor",
        "Significa mayor",
    ]
    for question, expected_text in zip(matching, expected_matching):
        expected = [option["text"] for option in question["value"]["options"] if option["expected"]]
        assert expected == [expected_text]


def test_annex_fast_path_uses_source_text_not_filename_or_fixed_urls():
    source = ANNEX_SOURCE.replace("example.test", "otro-dominio.invalid")
    result = pipeline.build_annex_fast_path(source)

    assert result is not None
    assert all("otro-dominio.invalid" in item["source_url"] for item in result["manifest"])
    assert "example.test" not in json.dumps(result, ensure_ascii=False)


def test_annex_fast_path_falls_back_when_high_confidence_pattern_is_missing():
    source = """[página 1]\nPlaneación Didáctica\nANEXO # 01\nActividad libre sin estructura reconocible\n"""

    assert pipeline.build_annex_fast_path(source) is None


def test_extract_stage_bypasses_llm_and_persists_reviewable_annex_staging():
    teacher = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model().objects.create_user(
        username="annex-fast-path-teacher",
        is_staff=True,
    )
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("curriculum.pdf", b"%PDF-1.4"),
        created_by=teacher,
    )

    def extract_in_memory():
        # Mirrors CurriculumImportJob.extract_text: extraction updates the
        # object before the stage persists its result.
        job.source_text = ANNEX_SOURCE
        job.page_count = 8
        return []

    with patch.object(job, "extract_text", side_effect=extract_in_memory), patch.object(
        pipeline, "identify_topics", side_effect=AssertionError("fast path must bypass Stage B")
    ), patch.object(
        pipeline, "chat_json", side_effect=AssertionError("fast path must not call Ollama")
    ):
        _import_action_extract(job, pipeline)

    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    assert job.source_text.startswith("[página 4]")
    assert job.page_count == 8
    assert len(job.activities) == 3
    assert job.llm_trace == []
    assert job.activities[0]["proposal"]["questions"] == []
    assert all(entry["proposal"]["questions"] for entry in job.activities[1:])
    assert all(entry["annex"]["source_pages"] for entry in job.activities)
    assert any(entry["stage"] == "annex_fast_path" for entry in job.llm_log)


def _persisted_fast_job():
    teacher = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model().objects.create_user(
        username=f"annex-review-{__import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model().objects.count()}",
        is_staff=True,
    )
    result = pipeline.build_annex_fast_path(ANNEX_SOURCE)
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("source.pdf", b"%PDF-1.4 source"),
        created_by=teacher,
        source_text=ANNEX_SOURCE,
        page_count=8,
        topics=result["topics"],
        activities=result["activities"],
        status=CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED,
    )
    return teacher, job, result


@pytest.mark.usefixtures("legacy_import_routes")
def test_activity_review_renders_source_pages_urls_and_original_instruction():
    teacher, job, _result = _persisted_fast_job()
    client = Client()
    client.force_login(teacher)

    response = client.get(reverse("tutor-import-detail", args=[job.pk]))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Páginas fuente" in body
    assert "ANEXO # 02" in body
    assert "https://example.test/vocales-color" in body
    assert "Instrucción original" in body
    assert reverse("tutor-import-source-page", args=[job.pk, 7]) in body


def test_source_page_endpoint_is_owner_scoped_and_keeps_pdf_inline():
    teacher, job, _result = _persisted_fast_job()
    owner = Client()
    owner.force_login(teacher)

    response = owner.get(reverse("tutor-import-source-page", args=[job.pk, 4]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline;")

    outsider = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model().objects.create_user(
        username="annex-outsider",
        is_staff=True,
    )
    other = Client()
    other.force_login(outsider)
    denied = other.get(reverse("tutor-import-source-page", args=[job.pk, 4]))
    assert denied.status_code == 404
    assert owner.get(reverse("tutor-import-source-page", args=[job.pk, 99])).status_code == 404


@pytest.mark.usefixtures("legacy_import_routes")
def test_an_annex_without_answer_key_cannot_be_converted_but_other_companions_can():
    teacher, job, result = _persisted_fast_job()
    client = Client()
    client.force_login(teacher)

    response = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {
            "action": "convert_selected",
            "select": [entry["id"] for entry in result["activities"]],
        },
    )

    assert response.status_code == 200
    assert CurriculumPackage.objects.count() == 2
    assert not CurriculumPackage.objects.filter(title="ANEXO # 01").exists()
    color_package = CurriculumPackage.objects.get(title="ANEXO # 02")
    assert color_package.source_references[0]["source_pages"] == [7]
    assert color_package.source_references[0]["source_urls"] == ["https://example.test/vocales-color"]


def _editorial_reviewer(username="annex-editorial-reviewer"):
    reviewer = get_user_model().objects.create_user(
        username=username,
        password="test-password",
        is_staff=True,
    )
    reviewer.groups.add(Group.objects.get(name="EditorialReviewer"))
    reviewer.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="curriculum",
            content_type__model="curriculumpackage",
            codename__in=("add_curriculumpackage", "change_curriculumpackage"),
        ),
        Permission.objects.get(
            content_type__app_label="wagtailadmin", codename="access_admin"
        ),
    )
    return reviewer


def _portable_annex_pdf():
    """Always construct a synthetic PDF; never discover private local inputs."""

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    pages = [
        ["Planeación Didáctica Semana 01", "Proyecto: Vocales", "Contenido: Lectoescritura"],
        ["Desarrollo de actividades", "Conservar los anexos para revisión."],
        ["ANEXO # 01", "La ______ jugando está.", "La ______ comió y se fue.", "La ______, la ______ y la ______ se fueron.", "Escribe en los círculos las cinco vocales.", "https://fixture.invalid/a"],
        ["ANEXO # 02", "Vocal A -> verde", "Vocal E -> amarillo", "Vocal I -> rojo", "Vocal O -> azul", "Vocal U -> anaranjado", "https://fixture.invalid/b"],
        ["ANEXO # 03", "a, e, i, o, u", "A, E, I, O, U", "Vocales mayúsculas", "Vocales minúsculas", "Significa menor", "Significa mayor", "https://fixture.invalid/c"],
    ]
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        resources = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        })
        page[NameObject("/Resources")] = writer._add_object(resources)
        commands = []
        for line_number, line in enumerate(lines):
            encoded = line.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            commands.append(f"BT /F1 11 Tf 40 {760 - 20 * line_number} Td (".encode() + encoded + b") Tj ET")
        stream = DecodedStreamObject()
        stream.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _approve_and_publish(client, package, reviewer):
    revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    response = client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state.pk],
        ),
        {"comment": "Revisión editorial humana de anexos 2 y 3."},
    )
    assert response.status_code in (200, 302)
    snapshot = PublishedPackageSnapshot.objects.get(package=package)
    assert snapshot.source_pdf_sha256
    return snapshot


@pytest.mark.usefixtures("legacy_import_routes")
def test_real_upload_worker_review_convert_and_publish_preserves_annex_sources():
    reviewer = _editorial_reviewer()
    client = Client()
    client.force_login(reviewer)
    upload = client.post(
        reverse("tutor-import-upload"),
        {"pdf": SimpleUploadedFile("issue96.pdf", _portable_annex_pdf(), content_type="application/pdf")},
    )
    assert upload.status_code == 302
    job = CurriculumImportJob.objects.latest("pk")

    _run_import_job_stage(job.pk, "extract")
    job.refresh_from_db()
    assert job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    assert len(job.activities) == 3
    review = client.get(reverse("tutor-import-detail", args=[job.pk]))
    assert review.status_code == 200
    assert "Páginas fuente" in review.content.decode()

    converted = client.post(
        reverse("tutor-import-detail", args=[job.pk]),
        {
            "action": "convert_selected",
            "select": [entry["id"] for entry in job.activities[1:]],
        },
    )
    assert converted.status_code == 200
    packages = list(CurriculumPackage.objects.filter(created_by=reviewer).order_by("id"))
    assert len(packages) == 2
    assert {package.source_references[0]["number"] for package in packages} == {2, 3}
    assert all(package.source_pdf and package.source_pdf_sha256 for package in packages)

    snapshots = [_approve_and_publish(client, package, reviewer) for package in packages]
    for snapshot in snapshots:
        reference = snapshot.payload["source_references"][0]
        assert reference["source_pdf_sha256"] == snapshot.source_pdf_sha256
        assert reference["source_pages"]
        source_page = reference["source_pages"][0]
        response = client.get(reverse("tutor-package-source-page", args=[snapshot.pk, source_page]))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        served_pdf = b"".join(response.streaming_content)
        assert hashlib.sha256(served_pdf).hexdigest() == snapshot.source_pdf_sha256

    # The published route remains usable after the mutable import job is gone.
    original_pdf_hashes = []
    for snapshot in snapshots:
        with snapshot.source_pdf.open("rb") as source_pdf:
            original_pdf_hashes.append(hashlib.sha256(source_pdf.read()).hexdigest())
    job.pdf.delete(save=True)
    for snapshot, expected_hash in zip(snapshots, original_pdf_hashes):
        source_page = snapshot.payload["source_references"][0]["source_pages"][0]
        response = client.get(reverse("tutor-package-source-page", args=[snapshot.pk, source_page]))
        assert response.status_code == 200
        assert hashlib.sha256(b"".join(response.streaming_content)).hexdigest() == expected_hash

    tampered = snapshots[0]
    source_name = tampered.source_pdf.name
    default_storage.delete(source_name)
    default_storage.save(source_name, ContentFile(b"tampered source"))
    source_page = tampered.payload["source_references"][0]["source_pages"][0]
    assert client.get(
        reverse("tutor-package-source-page", args=[tampered.pk, source_page])
    ).status_code == 404

    outsider = get_user_model().objects.create_user(username="published-source-outsider", is_staff=True)
    denied = Client()
    denied.force_login(outsider)
    assert denied.get(
        reverse("tutor-package-source-page", args=[snapshots[0].pk, snapshots[0].payload["source_references"][0]["source_pages"][0]])
    ).status_code == 404


def test_annex_fast_path_cancellation_keeps_partial_staging():
    teacher, job, result = _persisted_fast_job()
    job.progress_stage = "extract"
    job.save(update_fields=["progress_stage"])
    original_save = job.save

    def save_and_cancel(*args, **kwargs):
        original_save(*args, **kwargs)
        if job.progress_done == 1:
            CurriculumImportJob.objects.filter(pk=job.pk).update(cancel_requested=True)

    with patch.object(job, "save", side_effect=save_and_cancel):
        _import_action_annex_fast_path(job, result)

    job.refresh_from_db()
    assert job.progress_stage == ""
    assert job.cancelled_at is not None
    assert len(job.activities) == 1


def test_annex_fast_path_rerun_is_idempotent_and_does_not_duplicate_entries():
    teacher, job, result = _persisted_fast_job()
    job.activities = []
    job.status = CurriculumImportJob.STATUS_UPLOADED
    job.save(update_fields=["activities", "status"])

    _import_action_annex_fast_path(job, result)
    first = list(job.activities)
    first_log = list(job.llm_log)
    _import_action_annex_fast_path(job, result)
    job.refresh_from_db()

    assert len(job.activities) == 3
    assert [entry["id"] for entry in job.activities] == ["annex-01", "annex-02", "annex-03"]
    assert job.activities == first
    assert job.llm_log == first_log
    assert sum(entry["stage"] == "annex_fast_path" for entry in job.llm_log) == 3
