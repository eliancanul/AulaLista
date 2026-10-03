import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from curriculum.models import CurriculumImportApproval, CurriculumImportJob
from helpers import MINIMAL_VALID_PDF_BYTES


pytestmark = pytest.mark.django_db

READ_ROUTES = (
    "tutor-import-detail",
    "tutor-import-interpretation",
    "tutor-import-wait",
    "tutor-import-status",
    "tutor-import-log-md",
    "tutor-import-log-json",
    "tutor-import-source-page",
)
WRITE_ROUTES = (
    "tutor-import-interpretation",
    "tutor-import-cancel",
    "tutor-import-retry",
    "tutor-import-approve",
)


@pytest.fixture
def owned_job():
    owner = get_user_model().objects.create_user("s18-owner", is_staff=True)
    return CurriculumImportJob.objects.create(
        created_by=owner,
        pdf=SimpleUploadedFile("s18-private.pdf", MINIMAL_VALID_PDF_BYTES),
        error_message="S18_CONTENIDO_PRIVADO_SINTETICO",
    )


def route_url(route, job):
    args = [job.pk, 1] if route == "tutor-import-source-page" else [job.pk]
    return reverse(route, args=args)


@pytest.mark.parametrize("route", READ_ROUTES)
@pytest.mark.parametrize("identity", ["anonymous", "other_teacher", "non_teacher"])
def test_s18_document_reads_do_not_cross_identity(owned_job, route, identity):
    client = Client()
    if identity != "anonymous":
        other = get_user_model().objects.create_user(
            "s18-other", is_staff=identity == "other_teacher"
        )
        client.force_login(other)
    response = client.get(route_url(route, owned_job))
    expected = {"anonymous": 302, "other_teacher": 404, "non_teacher": 403}
    assert response.status_code == expected[identity]
    assert b"S18_CONTENIDO_PRIVADO_SINTETICO" not in response.content
    if identity == "anonymous":
        assert response["Location"].startswith("/cms/login/?next=")


@pytest.mark.parametrize("route", WRITE_ROUTES)
def test_s18_cross_owner_writes_do_not_mutate(owned_job, route):
    other = get_user_model().objects.create_user("s18-other", is_staff=True)
    client = Client()
    client.force_login(other)
    before = CurriculumImportJob.objects.filter(pk=owned_job.pk).values().get()
    response = client.post(route_url(route, owned_job), {
        "action": "save_corrections", "expected_version": "1",
        "confirm_approval": "1", "created_by": str(other.pk),
    })
    assert response.status_code == 404
    assert CurriculumImportJob.objects.filter(pk=owned_job.pk).values().get() == before
    assert not CurriculumImportApproval.objects.exists()


@pytest.mark.parametrize("route", WRITE_ROUTES + ("tutor-import-upload",))
def test_s18_owner_write_requires_csrf(owned_job, route):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owned_job.created_by)
    before = CurriculumImportJob.objects.filter(pk=owned_job.pk).values().get()
    url = reverse(route) if route == "tutor-import-upload" else route_url(route, owned_job)
    assert client.post(url, {"action": "save_corrections"}).status_code == 403
    assert CurriculumImportJob.objects.filter(pk=owned_job.pk).values().get() == before
    assert not CurriculumImportApproval.objects.exists()


@pytest.mark.parametrize("case", ["fake", "empty", "corrupt", "multiple", "oversize"])
def test_s18_rejected_upload_creates_no_job(owned_job, settings, case):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owned_job.created_by)
    url = reverse("tutor-import-upload")
    assert client.get(url).status_code == 200
    data = {"pdf": SimpleUploadedFile("s18.pdf", {
        "fake": b"<script>document.cookie</script>",
        "empty": b"", "corrupt": b"%PDF-1.4\n",
    }.get(case, MINIMAL_VALID_PDF_BYTES), content_type="application/pdf")}
    if case == "multiple":
        data["extra"] = SimpleUploadedFile("extra.pdf", MINIMAL_VALID_PDF_BYTES)
    if case == "oversize":
        settings.CURRICULUM_MAX_UPLOAD_SIZE_BYTES = len(MINIMAL_VALID_PDF_BYTES) - 1
    before = CurriculumImportJob.objects.count()
    response = client.post(url, data, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 400
    assert CurriculumImportJob.objects.count() == before


def test_s18_owner_can_read_status_and_pdf(owned_job):
    client = Client()
    client.force_login(owned_job.created_by)
    assert client.get(route_url("tutor-import-status", owned_job)).status_code == 200
    response = client.get(route_url("tutor-import-source-page", owned_job))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    response.close()


def test_s18_valid_upload_binds_session_owner_and_requires_human_approval(owned_job, settings):
    settings.CURRICULUM_MAX_UPLOAD_SIZE_BYTES = len(MINIMAL_VALID_PDF_BYTES)
    other = get_user_model().objects.create_user("s18-spoofed-owner", is_staff=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(owned_job.created_by)
    url = reverse("tutor-import-upload")
    assert client.get(url).status_code == 200
    response = client.post(url, {
        "pdf": SimpleUploadedFile("s18-valid.pdf", MINIMAL_VALID_PDF_BYTES),
        "created_by": str(other.pk), "approved": "true",
    }, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 302
    created = CurriculumImportJob.objects.latest("pk")
    assert created.pk != owned_job.pk
    assert created.created_by_id == owned_job.created_by_id
    assert not created.is_approved
    assert not CurriculumImportApproval.objects.exists()


def test_s18_valid_csrf_token_does_not_accept_foreign_origin(owned_job):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owned_job.created_by)
    assert client.get(reverse("tutor-import-upload")).status_code == 200
    response = client.post(route_url("tutor-import-cancel", owned_job), {},
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        HTTP_ORIGIN="https://s18-untrusted.invalid",
    )
    assert response.status_code == 403
    owned_job.refresh_from_db()
    assert not owned_job.cancel_requested
