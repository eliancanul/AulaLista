"""Issue #96: the authoring assistant updates incrementally without page reloads."""

import os
from datetime import timedelta
from unittest.mock import patch

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import CurriculumImportJob  # noqa: E402
from curriculum.views import _run_import_job_stage, _start_import_stage  # noqa: E402


pytestmark = pytest.mark.django_db


def owned_job(*, stage="activities", done=0, total=0):
    teacher = get_user_model().objects.create_user(
        username=f"maestra-estado-vivo-{get_user_model().objects.count() + 1}",
        is_staff=True,
    )
    client = Client()
    client.force_login(teacher)
    job = CurriculumImportJob.objects.create(
        pdf=SimpleUploadedFile("curricula.pdf", b"%PDF-1.4"),
        created_by=teacher,
        progress_stage=stage,
        progress_done=done,
        progress_total=total,
    )
    return teacher, client, job


def test_wait_page_polls_incrementally_without_full_page_refresh():
    _teacher, client, job = owned_job()

    response = client.get(reverse("tutor-import-wait", args=[job.pk]))

    assert response.status_code == 200
    assert '<meta http-equiv="refresh"' not in response.text
    assert reverse("tutor-import-status", args=[job.pk]) in response.text
    assert "curriculum/assistant_progress.js" in response.text
    assert 'id="assistant-progress-counter"' in response.text


@pytest.mark.parametrize(
    ("stage", "done", "total", "error", "expected"),
    [
        ("activities", 0, 0, "", "waiting"),
        ("activities", 0, 3, "", "working"),
        ("activities", 1, 3, "", "partial"),
        ("", 3, 3, "", "finished"),
        ("", 1, 3, "modelo desconectado", "error"),
    ],
)
def test_status_endpoint_distinguishes_each_teacher_facing_state(
    stage, done, total, error, expected
):
    _teacher, client, job = owned_job(stage=stage, done=done, total=total)
    job.error_message = error
    job.progress_started_at = timezone.now() - timedelta(seconds=3)
    job.save(update_fields=["error_message", "progress_started_at"])

    response = client.get(reverse("tutor-import-status", args=[job.pk]))

    assert response.status_code == 200
    assert response.json()["state"] == expected
    assert response.json()["started_at"] is not None
    assert "finished_at" in response.json()


def test_status_poll_releases_timeout_as_recoverable_error():
    _teacher, client, job = owned_job(stage="activities", done=1, total=3)
    job.progress_started_at = timezone.now() - timedelta(minutes=120)
    job.save(update_fields=["progress_started_at"])

    response = client.get(reverse("tutor-import-status", args=[job.pk]))
    job.refresh_from_db()

    assert response.json()["state"] == "error"
    assert "tardó demasiado" in response.json()["error"]
    assert job.progress_stage == ""
    assert job.progress_finished_at is not None


def test_worker_records_start_and_finish_without_losing_partial_state():
    _teacher, _client, job = owned_job(stage="activities", done=1, total=3)
    job.progress_started_at = timezone.now() - timedelta(seconds=2)
    job.save(update_fields=["progress_started_at"])

    with patch(
        "curriculum.views._import_action_generate_activities",
        side_effect=OSError("modelo desconectado"),
    ):
        _run_import_job_stage(job.pk, "activities")

    job.refresh_from_db()
    assert job.error_message == "modelo desconectado"
    assert job.progress_done == 1
    assert job.progress_started_at is not None
    assert job.progress_finished_at >= job.progress_started_at


def test_stale_request_cannot_start_a_duplicate_generation():
    _teacher, _client, job = owned_job(stage="")
    stale_job = CurriculumImportJob.objects.get(pk=job.pk)
    CurriculumImportJob.objects.filter(pk=job.pk).update(progress_stage="activities")

    with patch("curriculum.views._import_stage_runner") as runner_factory:
        response = _start_import_stage(None, stale_job, "activities")

    assert response.status_code == 302
    assert response["Location"] == reverse("tutor-import-wait", args=[job.pk])
    runner_factory.assert_not_called()
