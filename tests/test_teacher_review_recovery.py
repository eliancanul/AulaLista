"""Synthetic regressions for discarded receipts and pending answer corrections."""
import pytest
from test_teacher_review import ready_job, start, save, advance, _job_with_annex, _ask_annex, _apply_last_only
pytestmark = pytest.mark.django_db


class OutputWithReceipt(dict):
    provider_receipt = {"provider": "synthetic-test-double", "execution_status": "completed", "reconciled_usage": {"total_tokens": 17}}


def test_application_semantic_rejection_keeps_completed_transport_receipt(ready_job):
    _, user, job = _job_with_annex(ready_job)
    review = save(start(job, user, _ask_annex), user, "99")
    review = advance(review, user, lambda context: OutputWithReceipt(_apply_last_only(context)))
    assert review.state["error"] == "invalid_annex_page"
    assert review.state["turns"][0]["answer"] == "99"
    assert review.generation_token is None
    assert review.state["events"][-1].get("provider_receipt") == OutputWithReceipt.provider_receipt


def test_provider_receipt_survives_concurrent_dossier_edit(ready_job):
    from curriculum.models import CurriculumImportJob
    from curriculum.source_interpreter import resolve
    from curriculum.teacher_review import ReviewError
    from test_teacher_review import ask_first, apply_and_next
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "Preserved human answer")
    def concurrent_edit(context):
        fresh = CurriculumImportJob.objects.get(pk=job.pk)
        dossier = resolve(fresh.get_interpretation_dossier(), {"general_fields": {"metodologia": "Independent correction"}}, actor=user.username, pdf_source=fresh.pdf)
        fresh.save_interpretation_dossier(dossier)
        return OutputWithReceipt(apply_and_next(context))
    with pytest.raises(ReviewError):
        advance(review, user, concurrent_edit)
    review.refresh_from_db()
    assert review.generation_token is None
    assert review.state["turns"][0]["answer"] == "Preserved human answer"
    assert review.state["events"][-1].get("provider_receipt") == OutputWithReceipt.provider_receipt


def test_late_result_after_explicit_claim_recovery_keeps_old_completed_receipt(ready_job):
    from datetime import timedelta
    from django.utils import timezone
    from curriculum.models import CurriculumTeacherReview
    from curriculum.teacher_review import ReviewError, recover_stale_claim
    from test_teacher_review import ask_first
    _, user, job = ready_job
    captured = {}
    def recovered_during_request(context):
        current = CurriculumTeacherReview.objects.get(job_id=job.pk)
        current.generation_started_at = timezone.now() - timedelta(minutes=11)
        current.save(update_fields=["generation_started_at"])
        recovered = recover_stale_claim(current, expected_revision=current.revision)
        successor = advance(recovered, user, ask_first)
        captured["successor_question"] = successor.state["turns"][0]
        return OutputWithReceipt(ask_first(context))
    with pytest.raises(ReviewError):
        start(job, user, recovered_during_request)
    current = CurriculumTeacherReview.objects.get(job_id=job.pk)
    assert len(current.state["turns"]) == 1
    assert current.state["turns"][0] == captured["successor_question"]
    assert any(event.get("provider_receipt") == OutputWithReceipt.provider_receipt for event in current.state["events"])


def test_source_change_after_completion_keeps_receipt_without_applying(ready_job):
    from curriculum.teacher_review import ReviewError
    from test_teacher_review import ask_first
    _, user, job = ready_job
    def source_changes(context):
        with job.pdf.open("ab") as stream:
            stream.write(b"\n% synthetic source changed mid-request")
        return OutputWithReceipt(ask_first(context))
    with pytest.raises(ReviewError):
        start(job, user, source_changes)
    review = job.teacher_review
    review.refresh_from_db()
    assert review.state["turns"] == []
    assert review.generation_token is None
    assert review.state["events"][-1].get("provider_receipt") == OutputWithReceipt.provider_receipt


def test_pre_application_validation_rejection_already_keeps_receipt(ready_job):
    _, user, job = ready_job
    review = start(job, user, lambda _: OutputWithReceipt({"question": "Invalid target", "targets": ["not-real"], "answer_updates": []}))
    assert review.state["error"] == "invalid_targets"
    assert review.state["events"][-1].get("provider_receipt") == OutputWithReceipt.provider_receipt


@pytest.mark.parametrize("answer,skip,expect_call", [
    ("latest explicit correction", False, True),
    ("No sé", False, False),
    ("", True, False),
])
@pytest.mark.parametrize("legacy_format", [False, True])
def test_latest_teacher_edit_is_processed_even_if_independent_dossier_is_complete(ready_job, answer, skip, expect_call, legacy_format):
    import uuid
    from curriculum.source_interpreter import resolve
    from curriculum.teacher_review import resume_changed_dossier, submit_answer, unresolved
    from test_teacher_review import ask_first
    _, user, job = ready_job
    dossier = job.get_interpretation_dossier()
    dossier = resolve(dossier, {"general_fields": {
        name: "Confirmed human datum" if name != "campos_formativos" else ["Lenguajes"]
        for name in dossier.general_fields if name != "proposito"}}, actor=user.username, pdf_source=job.pdf)
    for session in dossier.sessions:
        dossier = resolve(dossier, {"session_id": session.session_id, "session_fields": {
            name: "Confirmed human datum" for name in session.fields}}, actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    review = advance(save(start(job, user, ask_first), user, "first answer"), user, _apply_last_only)
    assert review.state["status"] == "complete"
    if legacy_format:
        for turn in review.state["turns"]:
            turn.pop("pending_processing", None)
        review.save(update_fields=["state"])
        # A completed pre-flag answer must not be processed again on resume,
        # even though its existing targets remain eligible for that answer.
        review = resume_changed_dossier(job_id=job.pk, user=user, expected_revision=review.revision, expected_version=review.dossier_version)
        review = advance(review, user, lambda _: pytest.fail("Already processed legacy answer"))
    job.refresh_from_db()
    dossier = resolve(job.get_interpretation_dossier(), {"general_fields": {"proposito": "independent second value"}}, actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    review = resume_changed_dossier(job_id=job.pk, user=user, expected_revision=review.revision, expected_version=dossier.version)
    review = advance(review, user, lambda _: pytest.fail("Already resolved before answer edit"))
    turn = review.state["turns"][0]
    review, _ = submit_answer(job_id=job.pk, user=user, expected_revision=review.revision, expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()), turn_id=turn["id"], answer=answer, edit=True, skip=skip)
    if legacy_format:
        for turn in review.state["turns"]:
            turn.pop("pending_processing", None)
        review.save(update_fields=["state"])
    calls = []
    def apply_latest(context):
        calls.append(context)
        assert context["questions_remaining"] == 0
        assert context["missing_fields"] == []
        return _apply_last_only(context)
    review = advance(review, user, apply_latest)
    job.refresh_from_db()
    assert not unresolved(job.get_interpretation_dossier())
    assert review.state["turns"][0]["answer"] == answer
    assert bool(calls) is expect_call
    expected_value = answer if expect_call else "independent second value"
    assert job.get_interpretation_dossier().general_fields["proposito"].value == expected_value
    assert len(review.state["turns"]) == 1
    assert review.state["status"] == "complete"
    assert review.state["turns"][0]["pending_processing"] is False
    advance(review, user, lambda _: pytest.fail("Reload must not process the completed edit again"))


@pytest.mark.parametrize("recover_after_append", [False, True])
def test_late_result_keeps_successor_in_flight_claim_intact(ready_job, recover_after_append):
    import copy
    from datetime import timedelta
    from django.utils import timezone
    from curriculum.models import CurriculumTeacherReview
    from curriculum.teacher_review import ReviewError, recover_stale_claim
    from test_teacher_review import ask_first
    _, user, job = ready_job
    active = {}

    class SimulatedProcessInterruption(BaseException):
        """Leave an independently committed claim active without a real process."""

    def pause_successor(context):
        successor = CurriculumTeacherReview.objects.get(job_id=job.pk)
        successor.generation_started_at = timezone.now() - timedelta(minutes=11)
        successor.save(update_fields=["generation_started_at"])
        active["instance"] = successor
        active.update(revision=successor.revision, token=successor.generation_token,
                      started_at=successor.generation_started_at,
                      state=copy.deepcopy(successor.state), dossier_version=successor.dossier_version,
                      draft_epoch=successor.draft_epoch)
        raise SimulatedProcessInterruption()

    def recovered_during_request(context):
        current = CurriculumTeacherReview.objects.get(job_id=job.pk)
        current.generation_started_at = timezone.now() - timedelta(minutes=11)
        current.save(update_fields=["generation_started_at"])
        recovered = recover_stale_claim(current, expected_revision=current.revision)
        try:
            advance(recovered, user, pause_successor)
        except SimulatedProcessInterruption:
            pass
        return OutputWithReceipt(ask_first(context))

    with pytest.raises(ReviewError):
        start(job, user, recovered_during_request)
    current = CurriculumTeacherReview.objects.get(job_id=job.pk)
    assert active["token"] is not None
    assert current.generation_token == active["token"]
    assert current.revision == active["revision"]
    assert current.generation_started_at == active["started_at"]
    assert current.dossier_version == active["dossier_version"]
    assert current.draft_epoch == active["draft_epoch"]
    assert {k: v for k, v in current.state.items() if k != "events"} == {k: v for k, v in active["state"].items() if k != "events"}
    assert current.state["events"][:-1] == active["state"]["events"]
    assert current.state["events"][-1].get("provider_receipt") == OutputWithReceipt.provider_receipt

    if recover_after_append:
        recovered = recover_stale_claim(active["instance"], expected_revision=active["revision"])
        assert recovered.generation_token is None
        assert recovered.state["events"][:-1] == current.state["events"]
        assert recovered.state["events"][-2]["provider_receipt"] == OutputWithReceipt.provider_receipt
