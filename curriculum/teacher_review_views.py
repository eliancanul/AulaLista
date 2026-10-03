"""Django-shell review: one answer box, local durable draft and source read-only."""
import uuid
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview
from curriculum.teacher_review import (
    CLAIM_TIMEOUT, MAX_ANSWER, MAX_QUESTIONS, ReviewError, advance_review, open_review,
    recover_stale_claim, resume_changed_dossier, submit_answer, unresolved,
    save_local_draft, discard_local_draft, local_drafts,
)
from curriculum.source_interpreter import derive_operational_queue
from curriculum.teacher_review_provider import provider_configuration_notice
from curriculum.views import teacher_required


def _draft_key(job):
    return f"teacher-review-draft-{job.pk}"


def _parse_draft_epoch(value):
    if not str(value).isascii() or not str(value).isdecimal() or str(value) != str(int(value)):
        raise ValueError()
    return int(value)


def _keep_draft(request, job, turn_id, text, mode):
    if not isinstance(text, str) or len(text) > MAX_ANSWER:
        return False
    review = CurriculumTeacherReview.objects.filter(job=job).first()
    if not review or not any(t["id"] == turn_id for t in review.state["turns"]):
        return False
    request.session[_draft_key(job)] = {"turn_id": turn_id, "text": text, "mode": mode}
    return True


@teacher_required
@require_http_methods(["GET", "POST"])
def teacher_review(request, job_id):
    job = get_object_or_404(CurriculumImportJob, pk=job_id, created_by=request.user)
    if request.method == "POST" and request.POST.get("action") == "reextract":
        from curriculum.views import tutor_import_interpretation
        return tutor_import_interpretation(request, job_id)
    if request.method == "POST":
        allowed = {"csrfmiddlewaretoken", "action", "expected_version", "expected_revision", "receipt", "turn_id", "answer", "draft_mode", "draft_epoch"}
        if any(k not in allowed or len(request.POST.getlist(k)) != 1 for k in request.POST):
            return HttpResponseBadRequest("El formulario contiene campos duplicados o no autorizados.")
        if request.POST.get("action") in ("save_draft", "discard_draft"):
            try:
                from curriculum.source_interpreter import parse_canonical_positive_int
                revision = parse_canonical_positive_int(request.POST.get("expected_revision"))
                epoch = _parse_draft_epoch(request.POST.get("draft_epoch", ""))
                if request.POST["action"] == "discard_draft":
                    discard_local_draft(job_id=job.pk, user=request.user,
                        expected_revision=revision, expected_epoch=epoch,
                        turn_id=request.POST.get("turn_id"))
                    request.session.pop(_draft_key(job), None)
                    return redirect("tutor-import-interpretation", job_id=job.pk)
                next_epoch = save_local_draft(job_id=job.pk, user=request.user,
                    expected_revision=revision, expected_epoch=epoch,
                    turn_id=request.POST.get("turn_id"), text=request.POST.get("answer", ""),
                    mode=request.POST.get("draft_mode", "answer"))
                request.session.pop(_draft_key(job), None)
                return JsonResponse({"saved": True, "kind": "local_draft", "draft_epoch": next_epoch})
            except (ValueError, TypeError):
                return JsonResponse({"saved": False, "error": "invalid_draft_version"}, status=400)
            except ReviewError as exc:
                return JsonResponse({"saved": False, "error": str(exc)}, status=exc.status)
    try:
        review = open_review(job)
    except ReviewError as exc:
        if request.method == "GET" and exc.status != 503:
            return redirect("tutor-import-wait", job_id=job.pk)
        return HttpResponse(str(exc), status=exc.status)
    error, saved_message, status = "", "", 200
    answer_saved = False
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("answer", "edit", "skip"):
            _keep_draft(request, job, request.POST.get("turn_id"), request.POST.get("answer", ""), action)
        try:
            from curriculum.source_interpreter import parse_canonical_positive_int
            revision = parse_canonical_positive_int(request.POST.get("expected_revision"))
            version = parse_canonical_positive_int(request.POST.get("expected_version"))
            if action in ("answer", "edit", "skip"):
                review, changed = submit_answer(
                    job_id=job.pk, user=request.user, expected_revision=revision,
                    expected_version=version,
                    expected_draft_epoch=_parse_draft_epoch(request.POST.get("draft_epoch", "")),
                    receipt=request.POST.get("receipt"),
                    turn_id=request.POST.get("turn_id"), answer=request.POST.get("answer", ""),
                    edit=action == "edit", skip=action == "skip")
                answer_saved = True
                request.session.pop(_draft_key(job), None)
                saved_message = "Respuesta guardada. Puedes salir y retomar aquí."
                if changed:
                    review = advance_review(job_id=job.pk, user=request.user,
                        expected_revision=review.revision, expected_version=review.dossier_version)
            elif action == "resume_changed":
                review = resume_changed_dossier(job_id=job.pk, user=request.user,
                    expected_revision=revision, expected_version=version)
                review = advance_review(job_id=job.pk, user=request.user,
                    expected_revision=review.revision, expected_version=review.dossier_version)
            elif action in ("continue", "retry_interrupted"):
                if action == "retry_interrupted":
                    review = recover_stale_claim(review, expected_revision=revision)
                    revision = review.revision
                    # Recover the claim before asking to resume a changed source.
                    if review.dossier_version != version:
                        return redirect("tutor-import-interpretation", job_id=job.pk)
                review = advance_review(job_id=job.pk, user=request.user,
                    expected_revision=revision, expected_version=version)
            else:
                raise ReviewError("Acción no reconocida.", 400)
        except ValueError:
            error, status = "Versión del formulario inválida. Tu borrador sigue en la caja.", 400
        except ReviewError as exc:
            error, status = str(exc), exc.status
            if answer_saved:
                error = "Tu respuesta ya está guardada. La siguiente consulta no pudo completarse: " + error
            else:
                error += " Tu borrador sigue en la caja; no hace falta copiarlo."
        if not error:
            return redirect("tutor-import-interpretation", job_id=job.pk)
    job.refresh_from_db()
    review.refresh_from_db()
    dossier = job.get_interpretation_dossier()
    queue = derive_operational_queue(dossier)
    state = review.state
    active = next((t for t in state["turns"] if t["answer"] is None), None) if state["status"] == "asking" else None
    edit_id = request.GET.get("edit", "")
    editing = next((t for t in state["turns"] if t["id"] == edit_id and t["answer"] is not None), None)
    drafts = local_drafts(review)
    selected = editing or active
    stored_draft = (drafts.get(selected["id"], {}) if selected
                    else next(reversed(drafts.values()), {}))
    session_draft = request.session.get(_draft_key(job), {})
    draft = (session_draft if session_draft and (not edit_id or session_draft.get("turn_id") == edit_id)
             else stored_draft)
    draft_turn = next((t for t in state["turns"] if t["id"] == draft.get("turn_id")), None)
    # A stale submission remains attached to its original question, never silently
    # moved into the next question. Re-saving an already answered turn is explicit edit.
    if draft_turn and (not edit_id or edit_id == draft_turn["id"]):
        if draft_turn["answer"] is not None:
            editing = draft_turn
        else:
            active = draft_turn
    form_turn = editing or active
    form_text = (draft["text"] if draft_turn and form_turn and draft_turn["id"] == form_turn["id"]
                 else editing["answer"] if editing else "")
    stale = review.dossier_version != dossier.version or review.source_sha256 != dossier.source_sha256
    display_turns = [{**t, "prior_source": t.get("answer_source_sha256") != dossier.source_sha256}
                     for t in state["turns"]]
    context = {"job": job, "dossier": dossier, "review": review, "state": state,
        "provider_notice": provider_configuration_notice(),
        "turns": display_turns, "active": active, "editing": editing, "form_turn": form_turn,
        "form_text": form_text, "has_draft": bool(draft_turn),
        "max_questions": MAX_QUESTIONS, "asked_count": len(state["turns"]),
        "unresolved": unresolved(dossier), "error": error, "saved_message": saved_message,
        "receipt": str(uuid.uuid4()), "stale": stale,
        "has_active_approval": job.is_approved,
        "can_approve": queue.requires_resolution_count == 0 and not review.generation_token
            and state["status"] in ("complete", "limited") and not stale,
        "pending_count": queue.pending_review_count,
        "interrupted": bool(review.generation_started_at and timezone.now() - review.generation_started_at >= CLAIM_TIMEOUT)}
    return render(request, "curriculum/tutor_teacher_review.html", context, status=status)
