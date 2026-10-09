"""Gemini transport contracts with explicit doubles. No network/inference here."""
import copy
import hashlib
import json
from pathlib import Path
import uuid
from datetime import timedelta

import pytest
from django.db import OperationalError
from django.urls import reverse
from django.utils import timezone

from curriculum.gemini_review_provider import (
    GeminiHighAgyProvider, GeminiAttemptUnknown, VERIFIED_MODEL, VERIFIED_VERSION,
)
from curriculum.models import CurriculumTeacherReview
from curriculum.source_interpreter import resolve, SourceReference
from curriculum.teacher_review import ReviewError, resume_changed_dossier
from curriculum.teacher_review_provider import ReviewProviderError
from test_teacher_review import ready_job, start, save, advance, ask_first, apply_and_next, _apply_last_only
from helpers import MINIMAL_VALID_PDF_BYTES

pytestmark = pytest.mark.django_db
CLI_ROOT = Path(__file__).resolve().parents[2] / "agy_cli"


@pytest.fixture(autouse=True)
def fake_runtime_identity(tmp_path, monkeypatch):
    # Portable offline profile: never executes this invented launcher, and never
    # depends on a developer machine's installation/authentication.
    global CLI_ROOT
    CLI_ROOT = tmp_path / "fake_cli"
    agent = CLI_ROOT / "workspace/.agents/agents/structure-only/agent.md"
    agent.parent.mkdir(parents=True)
    launcher = CLI_ROOT / "run-agy-repro-v1"
    launcher.write_text("offline double; not executable")
    agent.write_text("offline tools-free profile double")
    monkeypatch.setattr("curriculum.gemini_review_provider.VERIFIED_LAUNCHER_SHA", hashlib.sha256(launcher.read_bytes()).hexdigest())
    monkeypatch.setattr("curriculum.gemini_review_provider.VERIFIED_AGENT_SHA", hashlib.sha256(agent.read_bytes()).hexdigest())


def _metadata(argv):
    return VERIFIED_VERSION if argv[-1] == "--version" else f"{VERIFIED_MODEL}\tGemini 3.8 Flash (High)\n"


def _adapter(tmp_path, capture, **extra):
    return GeminiHighAgyProvider(launcher=CLI_ROOT / "run-agy-repro-v1",
        agent_file=CLI_ROOT / "workspace/.agents/agents/structure-only/agent.md",
        attempt_root=tmp_path / "attempts", live_authorized=True,
        metadata=_metadata, capture=capture, **extra)


def _receipt(eligible=True):
    usage = {"input_tokens": 300, "output_tokens": 20, "thinking_tokens": 15, "cache_read_tokens": 0, "total_tokens": 320}
    return {"response_eligible_for_interpretation": eligible, "execution_status": "completed" if eligible else "incomplete",
        "accounting_status": "reconciled" if eligible else "unresolved", "usage_complete": eligible,
        "reported_result_usage_exact": usage, "reconciled_usage_exact": usage if eligible else None,
        "response_sha256": "a" * 64, "guard_reasons": []}


def test_gemini_high_exact_model_effort_full_context_and_exclusive_receipt(ready_job, tmp_path):
    _, user, job = ready_job
    seen = []
    def capture(argv, directory, limits, **kwargs):
        assert argv[argv.index("--model") + 1] == VERIFIED_MODEL
        assert argv[argv.index("--effort") + 1] == "high"
        assert "--dangerously-skip-permissions" not in argv
        assert "--continue" not in argv and "--conversation" not in argv
        assert (directory / "admission.json").exists()
        admission = json.loads((directory / "admission.json").read_text())
        assert admission["max_attempts"] == 1
        assert admission["max_attempts_scope"] == "wrapper_process_launches"
        request = json.loads((directory / "request.ndjson").read_text())
        prompt = request["message"]["content"]
        from curriculum.teacher_review_context import restore_provider_context
        encoded = json.loads(prompt.split("\nDATOS:\n", 1)[1])
        assert "missing_fields" not in encoded
        assert "missing_target_ids" in encoded
        assert "registro completo de all_targets" in prompt
        context = restore_provider_context(encoded)
        assert len(context["dossier"]["sessions"]) == 2
        assert all(len(s["activities"]) == 2 for s in context["dossier"]["sessions"])
        assert not any("Planeación sintética" in a for a in argv)
        assert kwargs["detector"]({"event": "init", "init": {"model": VERIFIED_MODEL, "agent": "structure-only", "tools": []}}) == ([], [])
        seen.append(directory)
        return _receipt(), json.dumps(ask_first(context)).encode()
    review = start(job, user, _adapter(tmp_path, capture))
    assert len(seen) == 1 and len(review.state["turns"]) == 1
    assert (seen[0] / "receipt.json").exists()
    receipt = review.state["events"][-1]["provider_receipt"]
    assert receipt["model"] == VERIFIED_MODEL and receipt["effort"] == "high"
    assert receipt["reconciled_usage"]["total_tokens"] == 320
    assert receipt["automatic_retries"] == 0
    assert receipt["automatic_retries_scope"] == "wrapper_process_relaunches"
    assert receipt["transport_internal_retries"] is None
    assert receipt["provider_dispatch_count"] is None


def test_live_disabled_never_checks_auth_or_spawns(tmp_path):
    provider = _adapter(tmp_path, lambda *a, **k: pytest.fail("No inference"))
    provider.live_authorized = False
    provider.metadata = lambda *a: pytest.fail("No metadata call needed")
    with pytest.raises(ReviewProviderError, match="gemini_live_not_enabled"):
        provider({})
    assert not provider.attempt_root.exists()


@pytest.mark.parametrize("model", ["gemini-3.8-flash-low", "gemini-3.1-pro-high", "frontier-runtime"])
def test_unverified_model_never_falls_back_or_spawns(tmp_path, model):
    provider = _adapter(tmp_path, lambda *a, **k: pytest.fail("No inference"), model=model)
    with pytest.raises(ReviewProviderError, match="gemini_exact_model_not_verified"):
        provider({})


def test_unknown_attempt_blocks_all_automatic_or_manual_retries(ready_job, tmp_path):
    _, user, job = ready_job
    calls = []
    def capture(argv, directory, limits, **kwargs):
        calls.append(1)
        kwargs["detector"]({"event": "init", "init": {"model": VERIFIED_MODEL, "agent": "structure-only", "tools": []}})
        return _receipt(False), None
    provider = _adapter(tmp_path, capture)
    review = start(job, user, provider)
    assert review.state["error"] == "gemini_attempt_unknown"
    assert (provider.attempt_root / "STOP_UNKNOWN.json").exists()
    with pytest.raises(ReviewError):
        advance(review, user, provider)
    with pytest.raises(ReviewProviderError, match="gemini_prior_attempt_unknown"):
        provider({})
    assert calls == [1]


def test_missing_identity_never_accepts_a_clean_looking_response(ready_job, tmp_path):
    _, user, job = ready_job
    def capture(*args, **kwargs):
        return _receipt(), b'{"question":null,"targets":[],"answer_updates":[]}'
    review = start(job, user, _adapter(tmp_path, capture))
    assert review.state["error"] == "gemini_attempt_unknown"
    assert review.state["turns"] == []


def test_mutated_runtime_profile_is_rejected_before_inference(tmp_path):
    bad_agent = tmp_path / "agent.md"
    bad_agent.write_text("tools: [run_command]")
    provider = _adapter(tmp_path, lambda *a, **k: pytest.fail("No inference"))
    provider.agent_file = bad_agent
    with pytest.raises(ReviewProviderError, match="gemini_runtime_identity_changed"):
        provider({})


def test_oversize_full_context_is_not_truncated_or_sent(tmp_path):
    provider = _adapter(tmp_path, lambda *a, **k: pytest.fail("No inference"))
    with pytest.raises(ReviewProviderError, match="gemini_full_context_too_large"):
        provider({"dossier": "x" * (4 * 1024 * 1024),
                  "all_targets": [], "missing_fields": []})
    assert not provider.attempt_root.exists()


def test_draft_stays_in_same_box_after_conflict_and_refresh(ready_job):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    prior_version, prior_revision = review.dossier_version, review.revision
    turn = review.state["turns"][0]
    review = save(review, user, "another window's answer")
    url = reverse("tutor-import-interpretation", args=[job.pk])
    response = client.post(url, {"action": "answer", "expected_version": prior_version,
        "expected_revision": prior_revision, "draft_epoch": 0, "receipt": str(uuid.uuid4()), "turn_id": turn["id"], "answer": "my exact draft\n"})
    assert response.status_code == 409
    from bs4 import BeautifulSoup
    for response in [response, client.get(url)]:
        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all("textarea")) == 1
        assert soup.find("textarea").text == "my exact draft\n"
        assert soup.find("input", {"name": "turn_id"})["value"] == turn["id"]
        assert soup.find("input", {"name": "draft_mode"})["value"] == "edit"
        assert "Cópialo" not in soup.text


def test_local_draft_autosave_does_not_enter_provider_context_or_answer_history(ready_job):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state["turns"][0]
    url = reverse("tutor-import-interpretation", args=[job.pk])
    response = client.post(url, {"action": "save_draft", "turn_id": turn["id"], "answer": "draft only", "draft_mode": "answer", "expected_revision": review.revision, "draft_epoch": review.draft_epoch})
    assert response.json() == {"saved": True, "kind": "local_draft", "draft_epoch": 1}
    review.refresh_from_db()
    assert review.state["turns"][0]["answer"] is None
    assert review.state["turns"][0]["answer_history"] == []
    assert "draft only" in client.get(url).content.decode()
    other = __import__("helpers").tutor_client()
    assert other.post(url, {"action": "save_draft", "turn_id": turn["id"], "answer": "bad"}).status_code == 404


def test_old_source_answers_require_new_human_confirmation(ready_job):
    _, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "first source answer"), user, _apply_last_only)
    job.refresh_from_db()
    dossier = copy.deepcopy(job.get_interpretation_dossier())
    new_source = MINIMAL_VALID_PDF_BYTES + b"\n% source changed"
    with job.pdf.open("wb") as stream:
        stream.write(new_source)
    dossier.source_sha256 = hashlib.sha256(new_source).hexdigest()
    dossier.version += 1
    dossier.general_fields["proposito"].value = ""
    dossier.general_fields["proposito"].status = "missing"
    dossier.general_fields["proposito"].review = "pending"
    assert job.save_interpretation_dossier(dossier) == "ready"
    review = resume_changed_dossier(job_id=job.pk, user=user, expected_revision=review.revision, expected_version=dossier.version)
    review = advance(review, user, _apply_last_only)
    assert review.state["error"] == "unsupported_human_value"
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields["proposito"].value == ""


def test_independent_newer_correction_cannot_be_overwritten_by_old_quote(ready_job):
    _, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "old explicit value"), user, _apply_last_only)
    job.refresh_from_db()
    dossier = resolve(job.get_interpretation_dossier(), {"general_fields": {"proposito": "newest independent human value"}}, actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    review = resume_changed_dossier(job_id=job.pk, user=user, expected_revision=review.revision, expected_version=dossier.version)
    def old_fragment(context):
        output = _apply_last_only(context)
        output["answer_updates"][0]["quote"] = "old"
        return output
    review = advance(review, user, old_fragment)
    job.refresh_from_db()
    assert review.state["error"] == "unsupported_human_value"
    assert job.get_interpretation_dossier().general_fields["proposito"].value == "newest independent human value"


def test_unknown_answer_fragment_does_not_resolve_a_missing_field(ready_job):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, "No tengo ese dato")
    def fragment(context):
        output = _apply_last_only(context)
        output["answer_updates"][0]["quote"] = "ese dato"
        return output
    review = advance(review, user, fragment)
    assert review.state["error"] == "unsupported_human_value"
    job.refresh_from_db()
    assert job.get_interpretation_dossier().general_fields["proposito"].value == ""


def test_stale_interrupted_claim_has_recovery_before_resume(ready_job):
    client, user, job = ready_job
    review = save(start(job, user, ask_first), user, "literal")
    CurriculumTeacherReview.objects.filter(pk=review.pk).update(generation_token=uuid.uuid4(), generation_started_at=timezone.now() - timedelta(minutes=11))
    job.refresh_from_db()
    dossier = resolve(job.get_interpretation_dossier(), {"general_fields": {"metodologia": "new method"}}, actor=user.username, pdf_source=job.pdf)
    job.save_interpretation_dossier(dossier)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    html = client.get(url).content.decode()
    assert 'value="retry_interrupted"' in html
    assert 'value="resume_changed"' not in html
    review.refresh_from_db()
    response = client.post(url, {"action": "retry_interrupted", "expected_revision": review.revision, "expected_version": dossier.version})
    assert response.status_code == 302
    assert 'value="resume_changed"' in client.get(url).content.decode()


def test_db_busy_is_recoverable_not_500(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    def busy(*args, **kwargs):
        raise OperationalError("database table is locked")
    monkeypatch.setattr("curriculum.teacher_review._bump_answer", busy)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    response = client.post(url, {"action": "answer", "expected_revision": review.revision,
        "expected_version": review.dossier_version, "draft_epoch": review.draft_epoch, "receipt": str(uuid.uuid4()),
        "turn_id": review.state["turns"][0]["id"], "answer": "busy draft retained"})
    assert response.status_code == 503
    assert "busy draft retained" in response.content.decode()
    review.refresh_from_db()
    assert review.state["turns"][0]["answer"] is None


def test_full_review_exposes_activity_titles_and_physical_provenance(ready_job):
    client, user, job = ready_job
    dossier = job.get_interpretation_dossier()
    activity = dossier.sessions[1].activities[0]
    activity.title = "Título visible de actividad sin descripción"
    activity.evidence = [SourceReference(dossier.source_sha256, 1, excerpt="Fragmento de procedencia sintético")]
    dossier.version += 1
    assert job.save_interpretation_dossier(dossier) == "ready"
    html = client.get(reverse("tutor-import-interpretation", args=[job.pk])).content.decode()
    assert "Título visible de actividad sin descripción" in html
    assert "Fragmento de procedencia sintético" in html
    assert "Página física 1" in html
    assert reverse("tutor-import-source-page", args=[job.pk, 1]) in html


def test_advance_failure_after_save_is_not_reported_as_unsaved_draft(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    def interrupted(*args, **kwargs):
        raise ReviewError("Fuente actualizada durante la consulta")
    monkeypatch.setattr("curriculum.teacher_review_views.advance_review", interrupted)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    response = client.post(url, {"action": "answer", "expected_revision": review.revision,
        "expected_version": review.dossier_version, "draft_epoch": review.draft_epoch, "receipt": str(uuid.uuid4()),
        "turn_id": review.state["turns"][0]["id"], "answer": "saved literal answer"})
    assert response.status_code == 409
    html = response.content.decode()
    assert "Tu respuesta ya está guardada" in html
    assert "todavía no se ha aplicado como respuesta" not in html
    review.refresh_from_db()
    assert review.state["turns"][0]["answer"] == "saved literal answer"


def test_synthetic_upload_reaches_one_box_with_exact_full_dossier(ready_job, monkeypatch):
    client, user, _ = ready_job
    from django.core.files.uploadedfile import SimpleUploadedFile
    from curriculum.models import CurriculumImportJob
    from test_t15_curriculum_import import make_minimal_pdf
    monkeypatch.setattr("curriculum.curriculum_import.chat_json", lambda *a, **k: pytest.fail("Upload must not start local Ollama"))
    data = make_minimal_pdf(["Proyecto: Exploración sintética\nSesión 1\nInicio: observar. Desarrollo: comparar. Cierre: comentar.",
                             "Sesión 2\nInicio: recordar. Desarrollo: clasificar. Cierre: compartir."])
    response = client.post(reverse("tutor-import-upload"), {"pdf": SimpleUploadedFile("upload-sintetico.pdf", data, content_type="application/pdf")})
    assert response.status_code == 302
    job = CurriculumImportJob.objects.latest("pk")
    assert job.has_valid_ready_dossier()
    assert job.interpretation_dossier["page_count"] == 2
    original = copy.deepcopy(job.interpretation_dossier)
    captured = []
    def provider(context):
        captured.append(context)
        target = context["missing_fields"][0]["target_id"]
        return {"question": "Pregunta de double sobre los datos faltantes", "targets": [target], "answer_updates": []}
    start(job, user, provider)
    assert captured[0]["dossier"] == original
    html = client.get(reverse("tutor-import-interpretation", args=[job.pk])).content
    assert html.count(b'<textarea') == 1


def _draft_payload(review, turn_id, text, epoch=0):
    return {"action": "save_draft", "expected_revision": review.revision,
        "draft_epoch": epoch, "turn_id": turn_id, "answer": text, "draft_mode": "answer"}


def test_late_autosave_cannot_reopen_a_successfully_answered_turn(ready_job, monkeypatch):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state["turns"][0]
    stale_draft = _draft_payload(review, turn["id"], "old typing")
    monkeypatch.setattr("curriculum.teacher_review.get_review_provider", lambda: apply_and_next)
    url = reverse("tutor-import-interpretation", args=[job.pk])
    response = client.post(url, {"action": "answer", "expected_revision": review.revision,
        "expected_version": review.dossier_version, "draft_epoch": 0,
        "receipt": str(uuid.uuid4()), "turn_id": turn["id"], "answer": "saved answer"})
    assert response.status_code == 302
    assert client.post(url, stale_draft).status_code == 409
    review.refresh_from_db()
    assert review.draft_state == {}
    html = client.get(url).content.decode()
    assert "Corregir respuesta" not in html
    assert "old typing" not in html
    assert review.state["turns"][1]["question"] in html


def test_late_autosave_after_discard_cannot_resurrect_draft(ready_job):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state["turns"][0]
    url = reverse("tutor-import-interpretation", args=[job.pk])
    payload = _draft_payload(review, turn["id"], "first draft")
    assert client.post(url, payload).json()["draft_epoch"] == 1
    stale_draft = _draft_payload(review, turn["id"], "late draft", 1)
    assert client.post(url, {"action": "discard_draft", "expected_revision": review.revision, "draft_epoch": 1, "turn_id": turn["id"]}).status_code == 302
    assert client.post(url, stale_draft).status_code == 409
    review.refresh_from_db()
    assert review.draft_state == {}
    assert "late draft" not in client.get(url).content.decode()


def test_reordered_autosaves_cannot_overwrite_newer_draft(ready_job):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    turn = review.state["turns"][0]
    url = reverse("tutor-import-interpretation", args=[job.pk])
    assert client.post(url, _draft_payload(review, turn["id"], "newer text", 0)).status_code == 200
    assert client.post(url, _draft_payload(review, turn["id"], "older text", 0)).status_code == 409
    review.refresh_from_db()
    assert review.draft_state["drafts"][turn["id"]]["text"] == "newer text"
    assert "newer text" in client.get(url).content.decode()
    assert "older text" not in client.get(url).content.decode()


@pytest.mark.parametrize("answer", ["No tengo ese dato todavía", "Por ahora no cuento con la información", "Tal vez sea posible", "Creo que no lo puedo confirmar"])
def test_uncertain_answer_never_yields_supported_fragment(ready_job, answer):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, answer)
    def fragment(context):
        output = _apply_last_only(context)
        output["answer_updates"][0]["quote"] = answer.split()[1]
        return output
    review = advance(review, user, fragment)
    assert review.state["error"] == "unsupported_human_value"
    assert review.state["turns"][0]["answer"] == answer
    job.refresh_from_db()
    field = job.get_interpretation_dossier().general_fields["proposito"]
    assert field.value == "" and field.status == "missing"


def test_stream_receipt_never_infers_internal_retry_or_dispatch_count():
    from curriculum.agy_transport.audit import audit_streams
    receipt = audit_streams(b'', b'', {"spawned": False, "transmission_status": "not_started"})
    assert receipt["automatic_retries"] == 0
    assert receipt["automatic_retries_scope"] == "wrapper_process_relaunches"
    assert receipt["transport_internal_retries"] is None
    assert receipt["provider_dispatch_count"] is None
    assert receipt["consumption_status"] == "unknown"
