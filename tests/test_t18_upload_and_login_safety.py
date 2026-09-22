"""Issue #30 and #31: safe anonymous redirects and PDF filename sanitization."""

import os

import django
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import CurriculumImportJob, curriculum_import_pdf_path  # noqa: E402

pytestmark = pytest.mark.django_db


def test_anonymous_tutor_route_redirects_to_wagtail_login():
    """Issue #30: anonymous access to tutor/* must redirect to the real login."""

    client = Client()
    url = reverse("tutor-import-upload")
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"].startswith("/cms/login/")
    assert f"next={url}" in response["Location"]

    # Same contract for detail routes.
    detail_url = reverse("tutor-import-detail", args=[999])
    response = client.get(detail_url)
    assert response.status_code == 302
    assert response["Location"].startswith("/cms/login/")


def test_anonymous_login_then_next_returns_to_original_page():
    """Issue #30: after login the teacher lands on the originally requested page."""

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user_model.objects.create_user(
        username="redirect-tutor",
        password="test-password",
        is_staff=True,
    )
    client = Client()
    target = reverse("tutor-import-upload")
    response = client.get(target)
    login_url = response["Location"]
    assert client.get(login_url).status_code == 200

    assert client.login(username="redirect-tutor", password="test-password")
    response = client.get(target)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "raw_name",
    [
        "x" * 300,
        "a" * 200 + ".pdf.pdf",
        "Currícula SEM 1 — Primaria   Rural (2026) 📚🔥 .pdf",
        "plan<>:\"/\\|?*de%estudios\".pdf",
        "   ",
        "!!!",
    ],
)
def test_sanitized_pdf_names_always_safe(raw_name):
    path = curriculum_import_pdf_path(None, raw_name)
    stem = os.path.basename(path)
    assert path.startswith("curriculum_imports/")
    assert stem.endswith(".pdf")
    assert len(stem.encode("utf-8")) <= 255
    assert not any(ch in stem for ch in '<>:"/\\|?*')
    assert "\x00" not in stem


def test_sanitized_pdf_name_falls_back_when_empty():
    assert (
        curriculum_import_pdf_path(None, "!!!.pdf")
        == "curriculum_imports/curriculo.pdf"
    )


def test_upload_with_huge_name_saves_without_error():
    """Issue #31: a 300+ char name uploads fine; the teacher renames nothing."""

    from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

    pdf = SimpleUploadedFile(
        "C" * 300 + ".pdf",
        MINIMAL_VALID_PDF_BYTES,
        content_type="application/pdf",
    )
    response = tutor_client().post(reverse("tutor-import-upload"), {"pdf": pdf})
    assert response.status_code == 302

    job = CurriculumImportJob.objects.latest("id")
    stored = job.pdf.name
    assert stored.startswith("curriculum_imports/")
    assert os.path.basename(stored).endswith(".pdf")
    assert len(os.path.basename(stored).encode("utf-8")) <= 255


def test_tutor_import_form_get_contains_ux_copy_controls_and_aria():
    """Task 1: GET /tutor/imports/new/ contains required copy, controls, and ARIA attributes."""
    from bs4 import BeautifulSoup
    from helpers import tutor_client

    client = tutor_client("ux-upload-tester")
    resp = client.get(reverse("tutor-import-upload"))
    assert resp.status_code == 200

    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # 1. Exact prompt text in drop zone
    assert "Arrastra tu planeación aquí" in html
    prompt = soup.find(class_="drop-zone__prompt")
    assert prompt is not None
    assert prompt.get_text().strip() == "Arrastra tu planeación aquí"

    # 2. Clear "Elegir archivo" button operable via native label (no redundant role/tabindex)
    assert "Elegir archivo" in html
    file_label = soup.find("label", {"for": "id_pdf"})
    assert file_label is not None
    assert "Elegir archivo" in file_label.get_text()
    assert file_label.get("tabindex") is None, "Label should not duplicate native input tab stop"
    assert file_label.get("role") is None, "Label should not have redundant button role"

    # 3. Real file input functional without JS
    file_input = soup.find("input", {"id": "id_pdf", "name": "pdf"})
    assert file_input is not None
    assert file_input.get("type") == "file"
    assert "application/pdf" in file_input.get("accept")
    assert ".pdf" in file_input.get("accept")
    assert file_input.has_attr("required")

    # 4. Accessible drop zone and aria-live announcements
    drop_zone = soup.find(id="drop-zone")
    assert drop_zone is not None
    assert drop_zone.get("role") == "region"
    assert drop_zone.get("aria-label") == "Zona para arrastrar archivo de planeación"

    live_region = soup.find(id="selected-file-info")
    assert live_region is not None
    assert live_region.get("aria-live") == "polite"

    # 5. Status indicator is not purely color (contains explicit text)
    status_badge = soup.find(id="file-status-badge")
    assert status_badge is not None
    assert status_badge.get_text().strip() != ""
    assert "Sin archivo" in status_badge.get_text()

    # 6. Submit button
    submit_btn = soup.find(id="submit-button")
    assert submit_btn is not None
    assert submit_btn.get("type") == "submit"


def test_tutor_import_form_teacher_language_and_no_fake_limits():
    """Task 1 / B3: Uses teacher language, honest copy, and does not invent fake limits."""
    from helpers import tutor_client

    client = tutor_client("ux-copy-tester")
    resp = client.get(reverse("tutor-import-upload"))
    assert resp.status_code == 200

    html = resp.content.decode("utf-8")

    # Primary notice uses teacher language and explains honest outcome (Subir -> Organizando -> Revisar)
    notice = resp.content.decode("utf-8").split('<p class="notice-docente">')[1].split('</p>')[0].strip()

    # Separate semantic assertions: auto-start of organization, review step, and no auto-publish
    assert "empezará a organizar el proyecto, los datos y las clases" in notice
    assert "permitirá revisarlos" in notice
    assert "Nada se publica automáticamente" in notice

    # Strict check: NO obsolete manual copy ("podrás organizar")
    assert "podrás organizar" not in html.lower()
    assert "después de cargar tu planeación podrás organizar" not in html.lower()

    # Strict check: NO technical local-LLM / AI / model / version jargon in primary notice
    technical_jargon = [
        "modelo local", "inteligencia artificial", "modelo de ia", " ia ", "llm", "v0", "v1", "pipeline"
    ]
    for term in technical_jargon:
        assert term not in notice.lower(), f"Technical term '{term}' found in primary notice!"

    # Real backend requirements and example brief
    assert "Formato admitido" in html
    assert "PDF" in html or ".pdf" in html
    assert "Planeación didáctica o de proyecto" in html

    # Strict check: NO invented limits that the backend does not enforce
    fake_limits = [
        "10MB", "10 MB", "20MB", "20 MB", "50MB", "50 MB", "100MB", "100 MB",
        "máximo 10", "máximo 50", "límite de tamaño", "páginas máximas", "hasta 50 páginas",
    ]
    for limit in fake_limits:
        assert limit.lower() not in html.lower(), f"Invented limit '{limit}' found in template!"


def test_tutor_import_post_valid_and_invalid_semantics():
    """Task 1: Existing POST semantics preserved (valid redirects, invalid returns 400 without mutation)."""
    from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

    client = tutor_client("ux-post-tester")
    url = reverse("tutor-import-upload")

    initial_job_count = CurriculumImportJob.objects.count()

    # 1. Invalid POST: no file provided -> 400 with human message
    resp_empty = client.post(url, {})
    assert resp_empty.status_code == 400
    assert "Selecciona el PDF de la currícula." in resp_empty.content.decode("utf-8")
    assert 'role="alert"' in resp_empty.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == initial_job_count

    # 2. Invalid POST: non-PDF file -> 400 with human message
    txt_file = SimpleUploadedFile("planeacion.txt", b"plain text content", content_type="text/plain")
    resp_txt = client.post(url, {"pdf": txt_file})
    assert resp_txt.status_code == 400
    assert "El archivo debe ser un documento en formato PDF (.pdf)." in resp_txt.content.decode("utf-8")
    assert 'role="alert"' in resp_txt.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == initial_job_count

    # 3. Valid POST: valid PDF -> 302 redirect to wait, job created
    pdf_file = SimpleUploadedFile("mi_planeacion.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf")
    resp_valid = client.post(url, {"pdf": pdf_file})
    assert resp_valid.status_code in (302, 303)
    assert CurriculumImportJob.objects.count() == initial_job_count + 1

    latest_job = CurriculumImportJob.objects.latest("id")
    assert resp_valid["Location"] == reverse("tutor-import-wait", args=[latest_job.pk])
    assert latest_job.created_by.username == "ux-post-tester"


def test_tutor_import_post_b1_validation_matrix():
    """Task 1 / B1: Server validation matrix rejects corrupt/fake/empty/multiple files without creating jobs."""
    from pathlib import Path
    from django.utils.datastructures import MultiValueDict
    from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

    client = tutor_client("b1-matrix-tester")
    url = reverse("tutor-import-upload")

    # 1. Uppercase extension with valid PDF bytes passes
    start_count = CurriculumImportJob.objects.count()
    resp_upper = client.post(
        url,
        {"pdf": SimpleUploadedFile("plan.PDF", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf")},
    )
    assert resp_upper.status_code == 302
    assert CurriculumImportJob.objects.count() == start_count + 1

    # 2. Real C01 PDF passes cleanly
    c01_path = Path("output/pdf/prueba-issue-96-paginas-4-a-8.pdf")
    if c01_path.exists():
        start_count = CurriculumImportJob.objects.count()
        resp_c01 = client.post(
            url,
            {"pdf": SimpleUploadedFile("c01.pdf", c01_path.read_bytes(), content_type="application/pdf")},
        )
        assert resp_c01.status_code == 302
        assert CurriculumImportJob.objects.count() == start_count + 1

    # 3. Fake content type (text/plain) but valid PDF bytes passes
    start_count = CurriculumImportJob.objects.count()
    resp_typed_wrong = client.post(
        url,
        {"pdf": SimpleUploadedFile("typed-wrong.pdf", MINIMAL_VALID_PDF_BYTES, content_type="text/plain")},
    )
    assert resp_typed_wrong.status_code == 302
    assert CurriculumImportJob.objects.count() == start_count + 1

    # 4. Fake .pdf with non-PDF text bytes -> 400, 0 jobs created
    start_count = CurriculumImportJob.objects.count()
    resp_fake = client.post(
        url,
        {"pdf": SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")},
    )
    assert resp_fake.status_code == 400
    assert "El archivo no es un documento PDF válido" in resp_fake.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == start_count

    # 5. Empty .pdf -> 400, 0 jobs created
    resp_empty = client.post(
        url,
        {"pdf": SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")},
    )
    assert resp_empty.status_code == 400
    assert "El archivo seleccionado está vacío" in resp_empty.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == start_count

    # 6. Header-only non-parseable PDF stream -> 400, 0 jobs created
    resp_corrupt = client.post(
        url,
        {"pdf": SimpleUploadedFile("corrupt.pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3", content_type="application/pdf")},
    )
    assert resp_corrupt.status_code == 400
    assert "El archivo no es un documento PDF válido" in resp_corrupt.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == start_count

    # 7. Multiple files in same 'pdf' field -> 400, 0 jobs created
    resp_many = client.post(
        url,
        {
            "pdf": [
                SimpleUploadedFile("one.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
                SimpleUploadedFile("two.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
            ]
        },
    )
    assert resp_many.status_code == 400
    assert "Elige un solo archivo PDF" in resp_many.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == start_count

    # 8. Extra file in different field -> 400, 0 jobs created
    resp_extra = client.post(
        url,
        {
            "pdf": SimpleUploadedFile("one.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
            "extra": SimpleUploadedFile("two.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"),
        },
    )
    assert resp_extra.status_code == 400
    assert "Elige un solo archivo PDF" in resp_extra.content.decode("utf-8")
    assert CurriculumImportJob.objects.count() == start_count


def test_tutor_import_template_b2_fallback_and_b4_multiple_drop_and_a11y():
    """Task 1 / B2, B4: Template includes DataTransfer fallback, multiple drop rejection, and clean a11y."""
    from bs4 import BeautifulSoup
    from helpers import tutor_client

    client = tutor_client("ux-b2-b4-tester")
    resp = client.get(reverse("tutor-import-upload"))
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # B2: Template script handles fallback when DataTransfer fails
    assert "No pudimos añadir el archivo al soltarlo. Usa Elegir archivo." in html
    assert "assignmentSucceeded" in html

    # B4: Template script rejects empty drop (0 files) and cleans previous selection
    assert "No se encontró un archivo. Usa Elegir archivo." in html

    # B4: Template script rejects multiple dropped files explicitly
    assert "Elige un solo archivo PDF" in html
    assert "files.length > 1" in html

    # Extension check in JS requires .pdf
    assert "name.endsWith('.pdf')" in html
    assert ".toLowerCase()" in html

    # Native input overlay & keyboard accessibility
    file_input = soup.find("input", id="id_pdf")
    assert file_input is not None
    assert "file-input-native" in file_input.get("class", [])

    # No redundant custom keydown listeners on label
    label = soup.find("label", {"for": "id_pdf"})
    assert label is not None
    assert label.get("role") is None
    assert label.get("tabindex") is None


def test_tutor_import_form_no_js_and_keyboard_accessible():
    """Task 1: Form is fully operable without JavaScript and satisfies touch/focus accessibility."""
    from bs4 import BeautifulSoup
    from helpers import tutor_client

    client = tutor_client("ux-a11y-tester")
    resp = client.get(reverse("tutor-import-upload"))
    html = resp.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    form = soup.find("form", id="upload-form")
    assert form is not None
    assert form.get("method", "").lower() == "post"
    assert "multipart/form-data" in form.get("enctype", "").lower()
    csrf = form.find("input", {"name": "csrfmiddlewaretoken"})
    assert csrf is not None

    # CSS contains >= 44px min-height touch targets and focus-visible indicators
    assert "min-height: 44px" in html
    assert "focus-visible" in html
