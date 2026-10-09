"""Same-document HTTP acceptance, with a generated PDF and declared Pi double.

This does not launch Pi, read credentials, or evaluate a model. Unlike the
separate already-complete approval fixture, every approved field starts with
the actual upload/parser and changes only through the public one-box forms.
"""
import copy
import hashlib

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
import pytest

from curriculum.models import (
    ClassroomSession, CurriculumImportJob, CurriculumPackage,
    CurriculumTeacherReview, PublishedPackageSnapshot,
)
from curriculum.pi_review_provider import PiReply
from curriculum.source_interpreter import derive_operational_queue
from curriculum.teacher_review_provider import ReviewProviderError
from helpers import tutor_client
from test_t15_curriculum_import import make_minimal_pdf

pytestmark = pytest.mark.django_db


def test_uploaded_pdf_clarifications_reopen_and_human_approval_same_job(settings, monkeypatch, tmp_path):
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER = "pi_luna"
    settings.AULALISTA_PI_LIVE_ENABLED = False
    settings.AULALISTA_LUNA_LIVE_ENABLED = False
    settings.AULALISTA_GEMINI_LIVE_ENABLED = False
    settings.AULALISTA_PI_ATTEMPT_DIR = str(tmp_path / "no-real-attempts")
    client = tutor_client("same-document-teacher")
    teacher = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    pdf = make_minimal_pdf([
        "Proyecto: Lectura sintetica\nGrado: 3ro\nSESION 1: Primera lectura\n"
        "Inicio: Observar el texto.\nCierre: Compartir una idea.\nUsar Anexo 1.",
        "SESION 2: Segunda lectura\nInicio: Recuperar ideas.\n"
        "Desarrollo: Comparar dos frases.\nANEXO 1\nLAMINA SINTETICA DE ACEPTACION",
    ])
    contexts = []
    fail_once = [True]
    values = {
        "campos_formativos": "Lenguajes",
        "proposito": "Comparar relatos de la comunidad.",
        "finalidad": "Compartir una lectura con el grupo.",
        "desarrollo": "Leer dos relatos y comparar sus personajes.",
        "cierre": "Escribir una conclusion y compartirla.",
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Same-document acceptance must never call a real transport")

    def declared_pi_double(provider, context):
        # Selection/constructor are production; only this explicitly fake call
        # is replaced. False is mandatory even when the process environment
        # happens to have a real runtime configured.
        assert provider.live_enabled is False
        contexts.append(copy.deepcopy(context))
        saved = CurriculumTeacherReview.objects.get(job=job)
        assert saved.generation_token is not None
        for turn in context["turns"]:
            persisted = next(t for t in saved.state["turns"] if t["id"] == turn["id"])
            assert persisted["answer"] == turn["answer"]
            assert persisted["answer_history"] == turn["answer_history"]
        # A failure after saving an answer must leave that exact answer durable.
        if len(context["turns"]) == 2 and context["turns"][-1]["answer"] is not None and fail_once[0]:
            fail_once[0] = False
            raise ReviewProviderError("synthetic_provider_unavailable")
        by_id = {t["target_id"]: t for t in context["all_targets"]}
        updates = []
        for turn in context["turns"]:
            if turn["answer"] is None or turn["skipped"]:
                continue
            for target_id in turn["eligible_targets"]:
                quote = values[by_id[target_id]["field_name"]]
                assert quote in turn["answer"]
                updates.append({"turn_id": turn["id"], "target_id": target_id, "quote": quote})
        applied = {u["target_id"] for u in updates}
        missing = [t for t in context["missing_fields"]
                   if t["priority_state"] == "requires_resolution" and t["target_id"] not in applied]
        if missing:
            first = missing[0]
            focus = next(group for group in context["question_policy"]["groups"]
                         if first["target_id"] in group["target_ids"])
            group = [t for t in missing if t["target_id"] in focus["target_ids"]]
            question = "Pregunta de prueba, datos de " + (first["session_id"] or "la planeacion") + ": "
            question += ", ".join(t["human_label"] for t in group)
        else:
            question, group = None, []
        return PiReply({"question": question, "targets": [t["target_id"] for t in group],
                        "answer_updates": updates},
                       {"test_double": True, "live_inference": False, "call": len(contexts)})

    monkeypatch.setattr("curriculum.pi_review_provider.PiLunaProvider.__call__", declared_pi_double)
    monkeypatch.setattr("curriculum.pi_review_provider.PiLunaProvider._identity", forbidden)
    monkeypatch.setattr("curriculum.luna_review_provider.LunaCodexCliProvider.__call__", forbidden)
    monkeypatch.setattr("curriculum.gemini_review_provider.GeminiHighAgyProvider.__call__", forbidden)
    monkeypatch.setattr("curriculum.curriculum_import.chat_json", forbidden)
    response = client.post(reverse("tutor-import-upload"), {
        "pdf": SimpleUploadedFile("same-document-synthetic.pdf", pdf, content_type="application/pdf")})
    assert response.status_code == 302
    job = CurriculumImportJob.objects.get(created_by=teacher)
    assert job.has_valid_ready_dossier()
    initial = job.get_interpretation_dossier()
    assert len(initial.sessions) == 2
    assert derive_operational_queue(initial).requires_resolution_count == 5
    assert not contexts and not job.is_approved
    original = copy.deepcopy(job.interpretation_dossier)
    url = reverse("tutor-import-interpretation", args=[job.pk])

    def page():
        before = len(contexts)
        response = client.get(url)
        assert response.status_code == 200
        assert len(contexts) == before, "GET/reopening must not generate a question"
        return BeautifulSoup(response.content, "html.parser")

    def post(action, answer=None):
        soup = page()
        button = soup.find("button", attrs={"value": action})
        assert button is not None, soup.get_text()
        form = button.find_parent("form")
        data = {i["name"]: i.get("value", "") for i in form.find_all("input")}
        data["action"] = action
        if answer is not None:
            data["answer"] = answer
        return client.post(url, data)

    assert post("continue").status_code == 302
    for index in range(4):
        job.refresh_from_db()
        review = CurriculumTeacherReview.objects.get(job=job)
        assert review.state["status"] == "asking", review.state
        turn = review.state["turns"][-1]
        by_id = {t["target_id"]: t for t in contexts[-1]["all_targets"]}
        answer = "  " + "\n".join(
            f"{by_id[target]['human_label']}: {values[by_id[target]['field_name']]}"
            for target in turn["targets"]) + "\n"
        soup = page()
        assert len(soup.find_all("textarea")) == 1
        form = soup.find("form", id="teacher-answer-form")
        data = {i["name"]: i.get("value", "") for i in form.find_all("input")}
        assert client.post(url, {**data, "action": "save_draft", "answer": answer}).status_code == 200
        # New authenticated session, not just refresh of the same browser state.
        client = Client()
        client.force_login(teacher)
        assert page().textarea.get_text() == answer
        assert post("answer", answer).status_code == 302
        review.refresh_from_db()
        assert review.state["turns"][index]["answer"] == answer
        assert review.state["turns"][index]["answer_history"][-1]["answer"] == answer
        assert not review.draft_state
        assert not job.approvals.exists()
        if index == 1:
            assert review.state["error"] == "synthetic_provider_unavailable"
            assert review.state["status"] == "pending"
            assert not review.generation_token
            before = len(contexts)
            page()
            assert len(contexts) == before
            assert post("continue").status_code == 302

    job.refresh_from_db()
    review = CurriculumTeacherReview.objects.get(job=job)
    final = job.get_interpretation_dossier()
    queue = derive_operational_queue(final)
    assert queue.requires_resolution_count == 0
    assert review.state["status"] == "limited"  # Optional/source confirmations stay explicit.
    assert len(review.state["turns"]) == 4 <= 6
    assert final.source_sha256 == hashlib.sha256(pdf).hexdigest()
    assert final.sessions[0].fields["inicio"].to_dict() == original["sessions"][0]["fields"]["inicio"]
    assert final.sessions[0].fields["desarrollo"].value == values["desarrollo"]
    assert final.sessions[1].fields["cierre"].value == values["cierre"]
    assert final.general_fields["proposito"].origin == "teacher_entered"
    assert not final.general_fields["proposito"].evidence
    assert final.sessions[0].annex_references[0].confirmed_page is None
    for context in contexts:
        assert len(context["dossier"]["sessions"]) == 2
        source = context["source_document"]
        assert source["source_sha256"] == final.source_sha256 and source["page_count"] == 2
        assert "LAMINA SINTETICA DE ACEPTACION" in source["pages"][1]["text"]
        assert source["ocr_performed"] is False
    assert all(e["provider_receipt"]["live_inference"] is False
               for e in review.state["events"] if e["kind"] == "provider_result")

    approval = page().find("form", class_="review-approval")
    assert approval is not None
    approval_url = approval["action"]
    data = {i["name"]: i.get("value", "") for i in approval.find_all("input")}
    # A populated form is not approval. Explicit confirmation is still required.
    assert client.post(approval_url, {k: v for k, v in data.items() if k != "confirm_approval"}).status_code == 400
    assert client.post(approval_url, {**data, "expected_version": final.version - 1}).status_code == 409
    assert not job.approvals.exists()
    assert client.post(approval_url, data).status_code == 302
    job.refresh_from_db()
    assert job.is_approved and job.approvals.count() == 1
    assert client.post(approval_url, data).status_code == 302
    assert job.approvals.count() == 1
    assert "aprobación docente vigente" in page().get_text()
    assert CurriculumImportJob.objects.count() == 1
    assert CurriculumPackage.objects.count() == 1
    assert PublishedPackageSnapshot.objects.count() == ClassroomSession.objects.count() == 0
    assert not (tmp_path / "no-real-attempts").exists()
