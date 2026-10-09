"""Offline functional tests. Providers below are explicit doubles, not model evaluations."""
import copy
import hashlib
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview
from curriculum.source_interpreter import (
    AnnexReference, ImportDossier, InterpretedField, SessionPlan, SessionActivity,
    ORIGIN_TEACHER_ENTERED, STATUS_MISSING, REQUIRED_GENERAL_FIELDS, REQUIRED_SESSION_FIELDS, resolve,
)
from curriculum.teacher_review import (
    ReviewError, advance_review, open_review, submit_answer, targets, unresolved,
    recover_stale_claim,
)
from curriculum.teacher_review_provider import ReviewProviderError, get_review_provider
from helpers import MINIMAL_VALID_PDF_BYTES, tutor_client

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready_job():
    client = tutor_client()
    user = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    sha = hashlib.sha256(MINIMAL_VALID_PDF_BYTES).hexdigest()
    general = {name: InterpretedField(name, "", status=STATUS_MISSING) for name in sorted(REQUIRED_GENERAL_FIELDS | {"metodologia", "escenario_proyecto", "grado", "duracion_proyecto"})}
    general["proyecto"] = InterpretedField("proyecto", "", status=STATUS_MISSING)
    sessions = [SessionPlan(f"session-{n}", n, f"Sesión sintética {n}", pages=[1],
        fields={name: InterpretedField(name, "", status=STATUS_MISSING)
                for name in [*sorted(REQUIRED_SESSION_FIELDS), "materiales", "evaluacion", "contexto_ejecucion"]},
        activities=[SessionActivity(f"activity-{n}-1"), SessionActivity(f"activity-{n}-2")]) for n in (1, 2)]
    dossier = ImportDossier(source_sha256=sha, source_name="sintetico.pdf", page_count=1,
        general_fields=general, sessions=sessions, selection={"session_id": "session-1", "session_number": 1})
    job = CurriculumImportJob.objects.create(created_by=user,
        pdf=SimpleUploadedFile("sintetico.pdf", MINIMAL_VALID_PDF_BYTES, content_type="application/pdf"))
    dossier = resolve(dossier, {"general_fields": {"proyecto": "Planeación sintética"}}, actor=user.username, pdf_source=job.pdf)
    from curriculum.verification import verify_curriculum_dossier
    report = verify_curriculum_dossier(dossier, MINIMAL_VALID_PDF_BYTES)
    assert report.blocked_count == 0, [i for i in report.items if i["status"] == "blocked"]
    assert job.save_interpretation_dossier(dossier) == "ready"
    assert job.has_valid_ready_dossier()
    return client, user, job


def start(job, user, provider):
    review = open_review(job)
    return advance_review(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, provider=provider)


def ask_first(context):
    target = next(t for t in context["missing_fields"] if t["field_name"] == "proposito")
    return {"question": f"¿Qué indicas para {target['human_label']}?", "targets": [target["target_id"]], "answer_updates": []}


def save(review, user, answer="  Una respuesta humana literal.\n", **kwargs):
    turn = next(t for t in review.state["turns"] if t["answer"] is None)
    return submit_answer(job_id=review.job_id, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()), turn_id=turn["id"], answer=answer, **kwargs)[0]


def advance(review, user, provider):
    return advance_review(job_id=review.job_id, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, provider=provider)


def apply_and_next(context):
    answered = [t for t in context["turns"] if t["answer"] is not None and not t["skipped"]]
    turn = answered[-1]
    update = {"turn_id": turn["id"], "target_id": turn["targets"][0], "quote": turn["answer"]}
    next_target = next(t for t in context["missing_fields"] if t["target_id"] != update["target_id"])
    return {"question": f"Ahora que indicaste {turn['answer'].strip()}, ¿qué falta en {next_target['human_label']}?",
            "targets": [next_target["target_id"]], "answer_updates": [update]}


def test_full_dossier_and_accumulated_answers_in_adaptive_context(ready_job):
    _, user, job = ready_job
    review = start(job, user, ask_first)
    original = copy.deepcopy(job.interpretation_dossier)
    review = save(review, user)
    captured = []
    def provider(context):
        captured.append(context)
        return apply_and_next(context)
    review = advance(review, user, provider)
    context = captured[0]
    assert len(context["dossier"]["sessions"]) == 2
    assert all(len(s["activities"]) == 2 for s in context["dossier"]["sessions"])
    assert context["dossier"]["sessions"] == original["sessions"]
    assert context["turns"][0]["answer"] == "  Una respuesta humana literal.\n"
    assert "Una respuesta humana literal." in review.state["turns"][1]["question"]
    job.refresh_from_db()
    item = targets(job.get_interpretation_dossier())[review.state["turns"][0]["targets"][0]]
    field = job.get_interpretation_dossier().general_fields[item.field_name]
    assert field.origin == "teacher_entered" and field.review == "corrected"
    assert field.evidence == [] and field.original_value == ""
    assert job.interpretation_dossier["sessions"] == original["sessions"]
    assert not job.is_approved


def test_answer_survives_provider_failure_refresh_and_retry(ready_job):
    client, user, job = ready_job
    review = save(start(job, user, ask_first), user)
    version = review.dossier_version
    def failing(_):
        raise ReviewProviderError("network_unavailable")
    review = advance(review, user, failing)
    assert review.state["turns"][0]["answer"] == "  Una respuesta humana literal.\n"
    assert review.state["status"] == "pending" and review.generation_token is None
    response = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
    assert response.status_code == 200
    assert "Una respuesta humana literal." in response.content.decode()
    review = advance(review, user, apply_and_next)
    assert len(review.state["turns"]) == 2
    assert review.dossier_version > version


def test_get_resumes_persisted_question_without_provider_call(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    monkeypatch.setattr("curriculum.teacher_review.get_review_provider", lambda: pytest.fail("GET must not call provider"))
    for _ in range(2):
        response = client.get(reverse("tutor-import-interpretation", args=[job.pk]))
        assert response.status_code == 200
        assert response.content.count(b'<textarea') == 1
        assert review.state["turns"][0]["question"].encode() in response.content
    review.refresh_from_db()
    assert len(review.state["turns"]) == 1


def test_duplicate_submission_is_idempotent_even_with_old_versions(ready_job):
    _, user, job = ready_job
    review = start(job, user, ask_first)
    kwargs = dict(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()),
        turn_id=review.state["turns"][0]["id"], answer="literal")
    review, changed = submit_answer(**kwargs)
    first_revision, first_version = review.revision, review.dossier_version
    second, changed_again = submit_answer(**kwargs)
    assert changed and not changed_again
    assert second.revision == first_revision and second.dossier_version == first_version
    assert len(second.state["turns"][0]["answer_history"]) == 1
    with pytest.raises(ReviewError):
        submit_answer(**{**kwargs, "answer": "different"})


def test_version_conflict_keeps_first_answer_and_unsaved_text_visible(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    old = dict(expected_revision=review.revision, expected_version=review.dossier_version, draft_epoch=review.draft_epoch)
    turn_id = review.state["turns"][0]["id"]
    review = save(review, user, "first")
    response = client.post(reverse("tutor-import-interpretation", args=[job.pk]),
        {"action": "answer", **old, "receipt": str(uuid.uuid4()), "turn_id": turn_id, "answer": "second unsaved"})
    assert response.status_code == 409
    assert "second unsaved" in response.content.decode()
    review.refresh_from_db()
    assert review.state["turns"][0]["answer"] == "first"


def test_edit_retains_history_and_reverts_only_own_old_data(ready_job):
    _, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "old explicit value"), user, apply_and_next)
    turn = review.state["turns"][0]
    review, _ = submit_answer(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()),
        turn_id=turn["id"], answer="new explicit value", edit=True)
    assert [v["answer"] for v in review.state["turns"][0]["answer_history"]] == ["old explicit value", "new explicit value"]
    job.refresh_from_db()
    item = targets(job.get_interpretation_dossier())[turn["targets"][0]]
    assert job.get_interpretation_dossier().general_fields[item.field_name].value == ""
    pending_question = review.state["turns"][1]["question"]
    def correction_only(context):
        output = apply_and_next(context)
        output.update(question=None, targets=[])
        return output
    review = advance(review, user, correction_only)
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields[item.field_name].value == "new explicit value"
    assert len(review.state["turns"]) == 2
    assert review.state["turns"][1]["question"] == pending_question
    assert review.state["status"] == "asking"


def test_backend_maximum_six_and_no_seventh_provider_question(ready_job):
    _, user, job = ready_job
    def question(context):
        n = len(context["turns"])
        if n == 6:
            return {"question": None, "targets": [], "answer_updates": []}
        target = context["missing_fields"][n]
        return {"question": f"Pregunta adaptativa sintética {n + 1}", "targets": [target["target_id"]], "answer_updates": []}
    review = start(job, user, question)
    for _ in range(6):
        review = save(review, user, "", skip=True)
        review = advance(review, user, question)
    assert len(review.state["turns"]) == 6
    assert review.state["status"] == "needs_input"
    assert len(unresolved(job.get_interpretation_dossier())) > 0
    review = advance(review, user, lambda _: pytest.fail("terminal state must not call provider"))
    assert len(review.state["turns"]) == 6


def test_seventh_question_is_rejected_and_sixth_answer_retained(ready_job):
    _, user, job = ready_job
    review = start(job, user, ask_first)
    for _ in range(5):
        review = advance(save(review, user, "", skip=True), user, ask_first)
    review = save(review, user, "sixth literal answer")
    review = advance(review, user, ask_first)
    assert len(review.state["turns"]) == 6
    assert review.state["turns"][-1]["answer"] == "sixth literal answer"
    assert review.state["error"] == "question_limit"


def test_finishes_early_when_resolved(ready_job):
    _, user, job = ready_job
    dossier = job.get_interpretation_dossier()
    dossier = resolve(dossier, {"general_fields": {
        name: "Confirmado por humano" if name != "campos_formativos" else ["Lenguajes"]
        for name in dossier.general_fields}}, actor=user.username, pdf_source=job.pdf)
    for session in dossier.sessions:
        dossier = resolve(dossier, {"session_id": session.session_id, "session_fields": {
            name: "Confirmado por humano" for name in session.fields}}, actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    assert not unresolved(dossier), unresolved(dossier)
    review = start(job, user, lambda _: pytest.fail("all data resolved; no model needed"))
    assert review.state["status"] == "complete" and review.state["turns"] == []


@pytest.mark.parametrize("bad", ["invented", "paraphrased", ""])
def test_unsupported_values_are_rejected_without_dossier_mutation(ready_job, bad):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "literal answer")
    job.refresh_from_db()
    before = copy.deepcopy(job.interpretation_dossier)
    def provider(context):
        turn = context["turns"][0]
        return {"question": None, "targets": [], "answer_updates": [
            {"turn_id": turn["id"], "target_id": turn["targets"][0], "quote": bad}]}
    review = advance(review, user, provider)
    job.refresh_from_db()
    assert job.interpretation_dossier == before
    assert review.state["error"] == "unsupported_human_value"


def test_provider_cannot_change_another_unasked_session(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user)
    def provider(context):
        turn = context["turns"][0]
        unasked = next(t for t in context["all_targets"] if t["session_id"] == "session-2")
        return {"question": None, "targets": [], "answer_updates": [
            {"turn_id": turn["id"], "target_id": unasked["target_id"], "quote": turn["answer"]}]}
    review = advance(review, user, provider)
    assert review.state["error"] == "unsupported_human_value"


def test_missing_provider_is_honest_and_does_not_enable_ollama(ready_job, settings, monkeypatch):
    client, user, job = ready_job
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER = ""
    monkeypatch.setattr("curriculum.curriculum_import.chat_json", lambda *a, **k: pytest.fail("No implicit Ollama"))
    review = open_review(job)
    review = advance_review(job_id=job.pk, user=user, expected_revision=review.revision,
                            expected_version=review.dossier_version)
    assert review.state["error"] == "provider_not_configured"
    assert review.state["turns"] == []
    html = client.get(reverse("tutor-import-interpretation", args=[job.pk])).content.decode()
    assert "Todavía no hay preguntas generadas por un modelo real" in html


def test_claim_prevents_duplicate_generation_and_explicit_recovery(ready_job):
    _, user, job = ready_job
    review = open_review(job)
    CurriculumTeacherReview.objects.filter(pk=review.pk).update(
        generation_token=uuid.uuid4(), generation_started_at=timezone.now())
    review.refresh_from_db()
    with pytest.raises(ReviewError):
        advance(review, user, lambda _: pytest.fail("must not call provider twice"))
    with pytest.raises(ReviewError):
        recover_stale_claim(review, expected_revision=review.revision)
    CurriculumTeacherReview.objects.filter(pk=review.pk).update(generation_started_at=timezone.now() - timedelta(minutes=11))
    review.refresh_from_db()
    review = recover_stale_claim(review, expected_revision=review.revision)
    assert review.generation_token is None and review.state["status"] == "pending"
    assert len(start(job, user, ask_first).state["turns"]) == 1


def test_source_tamper_blocks_answers_and_provider(ready_job):
    _, user, job = ready_job
    review = start(job, user, ask_first)
    with job.pdf.open("wb") as stream:
        stream.write(MINIMAL_VALID_PDF_BYTES + b"\n%changed")
    with pytest.raises(ReviewError):
        save(review, user)
    with pytest.raises(ReviewError):
        advance(review, user, lambda _: pytest.fail("tampered source must never be sent"))


def test_external_dossier_change_fails_closed_without_losing_history(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user)
    job.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    dossier.version += 1
    job.save_interpretation_dossier(dossier)
    with pytest.raises(ReviewError):
        advance(review, user, ask_first)
    review.refresh_from_db()
    assert review.state["turns"][0]["answer"] is not None


def test_auth_ownership_csrf_and_escaping(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, lambda c: {"question": "<script>bad()</script> ¿Qué falta?", "targets": [c["missing_fields"][0]["target_id"]], "answer_updates": []})
    url = reverse("tutor-import-interpretation", args=[job.pk])
    html = client.get(url).content.decode()
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html and "<script>bad()</script>" not in html
    assert Client().get(url).status_code == 302
    other = tutor_client()
    assert other.get(url).status_code == 404
    assert other.post(url, {"action": "continue"}).status_code == 404
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    response = strict.get(url)
    assert strict.post(url, {"action": "continue"}).status_code == 403
    monkeypatch.setattr("curriculum.teacher_review.get_review_provider", lambda: ask_first)
    turn = review.state["turns"][0]
    response = strict.post(url, {"csrfmiddlewaretoken": strict.cookies["csrftoken"].value,
        "action": "answer", "expected_version": review.dossier_version,
        "expected_revision": review.revision, "draft_epoch": review.draft_epoch, "receipt": str(uuid.uuid4()),
        "turn_id": turn["id"], "answer": "CSRF-valid literal"})
    assert response.status_code == 302


def test_double_scalar_form_input_rejected(ready_job):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    response = client.post(reverse("tutor-import-interpretation", args=[job.pk]),
                           {"action": ["continue", "answer"]})
    assert response.status_code == 400


def test_vue_entry_and_old_detail_reach_django_shell(ready_job):
    client, user, job = ready_job
    assert client.get(reverse("sprint-shell")).url == reverse("tutor-curriculum")
    start(job, user, ask_first)
    response = client.get(reverse("tutor-import-detail", args=[job.pk]))
    assert response.status_code == 200 and b'teacher-answer-form' in response.content
    assert b'Vue' not in response.content


def test_provider_cannot_forge_human_origin_flags(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "literal human answer")
    job.refresh_from_db()
    before = copy.deepcopy(job.interpretation_dossier)
    def malicious(context):
        return {"question": None, "targets": [], "answer_updates": [],
                "general_fields": {"proposito": {"value": "invented", "origin": "teacher_entered"}}}
    review = advance(review, user, malicious)
    assert review.state["error"] == "invalid_output"
    job.refresh_from_db()
    assert job.interpretation_dossier == before


def test_verifier_blocks_human_label_without_correction_audit(ready_job):
    _, user, job = ready_job
    from curriculum.verification import verify_curriculum_dossier
    dossier = job.get_interpretation_dossier()
    field = dossier.general_fields["proposito"]
    field.value, field.origin, field.review, field.status = "invented", "teacher_entered", "corrected", "supported"
    report = verify_curriculum_dossier(dossier, MINIMAL_VALID_PDF_BYTES)
    assert any(i["status"] == "blocked" and i["details"].get("reason") == "missing_human_correction_audit" for i in report.items)


def test_human_correction_still_checks_retained_pdf_citation_integrity(ready_job):
    _, user, job = ready_job
    from curriculum.verification import verify_curriculum_dossier
    from curriculum.source_interpreter import SourceReference
    dossier = resolve(job.get_interpretation_dossier(), {"general_fields": {"proposito": "Explicit human value"}},
                      actor=user.username, pdf_source=job.pdf)
    assert verify_curriculum_dossier(dossier, MINIMAL_VALID_PDF_BYTES).blocked_count == 0
    dossier.general_fields["proposito"].evidence = [SourceReference("a" * 64, 1, excerpt="false physical citation")]
    report = verify_curriculum_dossier(dossier, MINIMAL_VALID_PDF_BYTES)
    assert report.blocked_count > 0
    assert any(i["status"] == "blocked" and i["item_id"].startswith("gen_proposito_ev_") for i in report.items)


def test_skip_or_unknown_never_becomes_invented_value(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "No sé")
    def provider(context):
        turn = context["turns"][0]
        return {"question": None, "targets": [], "answer_updates": [
            {"turn_id": turn["id"], "target_id": turn["targets"][0], "quote": "No sé"}]}
    review = advance(review, user, provider)
    assert review.state["error"] == "unsupported_human_value"
    assert review.state["turns"][0]["answer"] == "No sé"


def test_explicit_resume_after_external_edit_preserves_answers_and_budget(ready_job):
    _, user, job = ready_job
    from curriculum.teacher_review import resume_changed_dossier
    review = save(start(job, user, ask_first), user, "stored original answer")
    job.refresh_from_db()
    dossier = resolve(job.get_interpretation_dossier(), {"general_fields": {"metodologia": "Nueva decisión docente"}},
                      actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    review = resume_changed_dossier(job_id=job.pk, user=user, expected_revision=review.revision,
                                    expected_version=dossier.version)
    assert len(review.state["turns"]) == 1
    assert review.state["turns"][0]["answer"] == "stored original answer"
    assert review.dossier_version == dossier.version
    review = advance(review, user, apply_and_next)
    assert len(review.state["turns"]) == 2


def test_provider_result_after_concurrent_edit_is_discarded(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "stored answer")
    def interleaved(context):
        fresh = CurriculumImportJob.objects.get(pk=job.pk)
        dossier = resolve(fresh.get_interpretation_dossier(), {"general_fields": {"metodologia": "Concurrent human decision"}},
                          actor=user.username, pdf_source=fresh.pdf)
        fresh.save_interpretation_dossier(dossier)
        return apply_and_next(context)
    with pytest.raises(ReviewError):
        advance(review, user, interleaved)
    review.refresh_from_db()
    job.refresh_from_db()
    assert review.state["turns"][0]["answer"] == "stored answer"
    assert review.generation_token is None
    assert job.get_interpretation_dossier().general_fields["metodologia"].value == "Concurrent human decision"
    assert job.get_interpretation_dossier().general_fields["proposito"].value == ""


def test_apply_several_literal_human_fields_in_one_question(ready_job):
    _, user, job = ready_job
    def grouped(context):
        chosen = [i["target_id"] for i in context["missing_fields"] if i["scope"] == "general" and i["field_name"] in ("proposito", "finalidad")]
        return {"question": "¿Cuál es el propósito y la finalidad?", "targets": chosen, "answer_updates": []}
    review = save(start(job, user, grouped), user, "Propósito: explorar. Finalidad: colaborar.")
    def apply(context):
        turn = context["turns"][0]
        mapped = {i["field_name"]: i["target_id"] for i in context["all_targets"] if i["scope"] == "general"}
        return {"question": None, "targets": [], "answer_updates": [
            {"turn_id": turn["id"], "target_id": mapped["proposito"], "quote": "explorar"},
            {"turn_id": turn["id"], "target_id": mapped["finalidad"], "quote": "colaborar"}]}
    review = advance(review, user, apply)
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields["proposito"].value == "explorar"
    assert job.get_interpretation_dossier().general_fields["finalidad"].value == "colaborar"
    assert len(review.state["turns"]) == 1
    assert review.state["status"] == "needs_input"


def test_edit_cannot_create_uncounted_replacement_question(ready_job):
    _, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "old value"), user, apply_and_next)
    turn = review.state["turns"][0]
    pending_question = review.state["turns"][1]["question"]
    review, _ = submit_answer(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()),
        turn_id=turn["id"], answer="corrected value", edit=True)
    review = advance(review, user, apply_and_next)
    assert review.state["error"] == "question_limit"
    assert len(review.state["turns"]) == 2
    assert review.state["turns"][1]["question"] == pending_question
    assert review.state["turns"][0]["answer"] == "corrected value"


def _job_with_annex(ready_job):
    client, user, job = ready_job
    dossier = job.get_interpretation_dossier()
    dossier.sessions[1].annex_references.append(AnnexReference(
        "1", "Anexo sintético sin texto digital verificable", status="missing",
        reference_id="annex-session-2"))
    dossier.version += 1
    assert job.save_interpretation_dossier(dossier) == "ready"
    return client, user, job


def _ask_annex(context):
    target = next(t for t in context["missing_fields"] if t["scope"] == "annex")
    return {"question": "¿En qué página física está el anexo de la sesión 2?",
            "targets": [target["target_id"]], "answer_updates": []}


def _apply_last_only(context):
    turn = next(t for t in reversed(context["turns"]) if t["answer"] is not None)
    return {"question": None, "targets": [], "answer_updates": [
        {"turn_id": turn["id"], "target_id": turn["targets"][0], "quote": turn["answer"]}]}


def test_full_annex_provenance_is_preserved_and_sent_with_all_sessions(ready_job):
    _, user, job = _job_with_annex(ready_job)
    original = copy.deepcopy(job.interpretation_dossier["sessions"])
    seen = []
    def provider(context):
        seen.append(context)
        return ask_first(context)
    review = save(start(job, user, provider), user, "Explicit purpose")
    review = advance(review, user, apply_and_next)
    assert seen[0]["dossier"]["sessions"] == original
    assert seen[0]["dossier"]["sessions"][1]["annex_references"][0]["reference_id"] == "annex-session-2"
    job.refresh_from_db()
    assert job.interpretation_dossier["sessions"] == original


def test_human_annex_page_does_not_invent_verifiable_pdf_evidence(ready_job):
    _, user, job = _job_with_annex(ready_job)
    review = advance(save(start(job, user, _ask_annex), user, "1"), user, _apply_last_only)
    assert not review.state["error"]
    job.refresh_from_db()
    ref = job.get_interpretation_dossier().sessions[1].annex_references[0]
    assert ref.confirmed_page == 1
    assert ref.review == "pending"  # Blank synthetic PDF cannot demonstrate the sheet.
    assert not any(e.role == "teacher_selected_source_page" for e in ref.evidence)
    assert not job.is_approved


def test_invalid_annex_page_retains_answer_and_original_mapping(ready_job):
    _, user, job = _job_with_annex(ready_job)
    review = advance(save(start(job, user, _ask_annex), user, "99"), user, _apply_last_only)
    assert review.state["error"] == "invalid_annex_page"
    assert review.state["turns"][0]["answer"] == "99"
    job.refresh_from_db()
    assert job.get_interpretation_dossier().sessions[1].annex_references[0].confirmed_page is None


def test_edit_annex_removes_own_old_mapping_even_when_next_provider_fails(ready_job):
    _, user, job = _job_with_annex(ready_job)
    review = advance(save(start(job, user, _ask_annex), user, "1"), user, _apply_last_only)
    turn = review.state["turns"][0]
    review, _ = submit_answer(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()),
        turn_id=turn["id"], answer="No lo sé", edit=True)
    review = advance(review, user, lambda _: (_ for _ in ()).throw(ReviewProviderError("network_unavailable")))
    job.refresh_from_db()
    assert job.get_interpretation_dossier().sessions[1].annex_references[0].confirmed_page is None
    assert [a["answer"] for a in review.state["turns"][0]["answer_history"]] == ["1", "No lo sé"]


def test_missing_absent_field_is_added_and_edit_can_restore_absence(ready_job):
    _, user, job = ready_job
    dossier = job.get_interpretation_dossier()
    dossier.general_fields.pop("proposito")
    dossier.version += 1
    job.save_interpretation_dossier(dossier)
    def ask_absent(context):
        item = next(t for t in context["missing_fields"] if t["field_name"] == "proposito")
        return {"question": "¿Qué propósito tiene la actividad?", "targets": [item["target_id"]], "answer_updates": []}
    review = advance(save(start(job, user, ask_absent), user, "Comparar relatos"), user, _apply_last_only)
    assert not review.state["error"]
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields["proposito"].value == "Comparar relatos"
    turn = review.state["turns"][0]
    review, _ = submit_answer(job_id=job.pk, user=user, expected_revision=review.revision,
        expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch, receipt=str(uuid.uuid4()),
        turn_id=turn["id"], answer="No sé", edit=True)
    job.refresh_from_db()
    assert "proposito" not in job.get_interpretation_dossier().general_fields
    assert review.state["turns"][0]["answer"] == "No sé"


def test_active_review_routes_do_not_expose_retired_handlers(ready_job):
    from django.urls import resolve, Resolver404
    from curriculum.teacher_review_views import teacher_review
    _, _, job = ready_job
    for name in ("tutor-import-detail", "tutor-import-interpretation"):
        assert resolve(reverse(name, args=[job.pk])).func is teacher_review
    with pytest.raises(Resolver404):
        resolve(f"/_test_legacy/tutor/imports/{job.pk}/")


@pytest.mark.parametrize("action", [
    "extract", "confirm_topics", "confirm_subtopics", "generate_activities",
    "convert_selected", "remove_activity", "add_missing_activities", "postpone_queue_item",
])
def test_active_review_rejects_retired_actions_without_side_effects(ready_job, monkeypatch, action):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    before_state = copy.deepcopy(review.state)
    job.refresh_from_db()
    before_dossier = copy.deepcopy(job.interpretation_dossier)
    monkeypatch.setattr("curriculum.teacher_review.get_review_provider",
                        lambda: pytest.fail("A retired action must not call a provider"))
    response = client.post(reverse("tutor-import-detail", args=[job.pk]), {
        "action": action, "expected_revision": review.revision,
        "expected_version": review.dossier_version, "draft_epoch": review.draft_epoch,
    })
    assert response.status_code == 400
    review.refresh_from_db()
    job.refresh_from_db()
    assert review.state == before_state
    assert job.interpretation_dossier == before_dossier
    assert not job.is_approved
