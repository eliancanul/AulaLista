"""Issue #96: the authoring assistant updates incrementally without page reloads."""

import os
from datetime import timedelta
from unittest.mock import patch

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
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
    if error:
        job.interpretation_error_message = error
        job.interpretation_state = CurriculumImportJob.INTERPRETATION_STATE_FAILED
    job.progress_started_at = timezone.now() - timedelta(seconds=3)
    job.save()

    response = client.get(reverse("tutor-import-status", args=[job.pk]))

    assert response.status_code == 200
    assert response.json()["state"] == expected
    assert response.json()["started_at"] is not None
    assert "finished_at" in response.json()


def test_status_poll_releases_timeout_as_recoverable_error():
    """T2/B2: GET status is a pure read; stale stage is derived as 'delayed' without DB or session mutation."""
    _teacher, client, job = owned_job(stage="activities", done=1, total=3)
    job.progress_started_at = timezone.now() - timedelta(minutes=120)
    job.save(update_fields=["progress_started_at"])

    # Snapshot complete row byte/field-by-field and session BEFORE GET
    before_row = CurriculumImportJob.objects.filter(pk=job.pk).values().first()
    before_session = dict(client.session.items())

    # 1. First GET: returns delayed state with honest recoverable copy, not terminal error or ready
    response = client.get(reverse("tutor-import-status", args=[job.pk]))
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "delayed"
    assert data["label"] == "Está tardando más de lo esperado; aún puede terminar"
    assert data["stage"] == "activities"
    assert data["done"] == 1
    assert data["total"] == 3
    assert data["state"] not in ("error", "finished", "ready")

    # 2. Row is field-by-field identical AFTER GET: no claim release, no stage clearing, no timestamps overwritten
    job.refresh_from_db()
    after_row = CurriculumImportJob.objects.filter(pk=job.pk).values().first()
    assert after_row == before_row
    assert job.progress_stage == "activities"
    assert job.progress_done == 1
    assert job.progress_total == 3
    assert job.progress_finished_at is None
    assert job.interpretation_state == before_row["interpretation_state"]
    assert job.interpretation_claim_token == before_row["interpretation_claim_token"]
    assert job.interpretation_claimed_at == before_row["interpretation_claimed_at"]
    assert job.interpretation_error_message == before_row["interpretation_error_message"]

    # 3. Session is identical
    after_session = dict(client.session.items())
    assert after_session == before_session

    # 4. Repeated GET is strictly idempotent
    response2 = client.get(reverse("tutor-import-status", args=[job.pk]))
    assert response2.status_code == 200
    assert response2.json() == data
    job.refresh_from_db()
    assert CurriculumImportJob.objects.filter(pk=job.pk).values().first() == before_row
    assert dict(client.session.items()) == before_session


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


def test_persistent_sqlite_lock_finishes_stage_as_recoverable_error():
    _teacher, _client, job = owned_job(stage="activities")
    locked = OperationalError("database is locked")
    with patch(
        "curriculum.views._run_import_job_stage_once",
        side_effect=locked,
    ), patch("curriculum.views.time.sleep"):
        _run_import_job_stage(job.pk, "activities")

    job.refresh_from_db()
    assert job.progress_stage == ""
    assert job.progress_finished_at is not None
    assert job.status == CurriculumImportJob.STATUS_ACTIVITIES_PROPOSED
    assert "bloque" in job.error_message.lower()


def test_non_lock_operational_error_is_not_hidden_by_retry_wrapper():
    _teacher, _client, job = owned_job(stage="activities")
    with patch(
        "curriculum.views._run_import_job_stage_once",
        side_effect=OperationalError("disk I/O error"),
    ):
        with pytest.raises(OperationalError, match="disk I/O error"):
            _run_import_job_stage(job.pk, "activities")

    job.refresh_from_db()
    assert job.progress_stage == "activities"


def test_stale_request_cannot_start_a_duplicate_generation():
    _teacher, _client, job = owned_job(stage="")
    stale_job = CurriculumImportJob.objects.get(pk=job.pk)
    CurriculumImportJob.objects.filter(pk=job.pk).update(progress_stage="activities")

    with patch("curriculum.views._import_stage_runner") as runner_factory:
        response = _start_import_stage(None, stale_job, "activities")

    assert response.status_code == 302
    assert response["Location"] == reverse("tutor-import-wait", args=[job.pk])
    runner_factory.assert_not_called()


def test_teacher_cancels_running_help_without_deleting_staged_work():
    _teacher, client, job = owned_job(stage="activities", done=1, total=3)
    job.activities = [{"title": "Borrador conservado"}]
    job.save(update_fields=["activities"])

    response = client.post(reverse("tutor-import-cancel", args=[job.pk]))
    job.refresh_from_db()

    assert response.status_code == 302
    assert job.cancel_requested is True
    assert job.activities == [{"title": "Borrador conservado"}]
    _run_import_job_stage(job.pk, "activities")
    job.refresh_from_db()
    assert job.progress_stage == ""
    assert job.cancelled_at is not None
