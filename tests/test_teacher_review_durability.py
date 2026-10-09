"""Synthetic-only regressions for acknowledged drafts across tabs and turns."""
import uuid

import pytest
from bs4 import BeautifulSoup
from django.test import Client
from django.urls import reverse

from curriculum.teacher_review import local_drafts, submit_answer
from test_teacher_review import ready_job, start, save, advance, ask_first, apply_and_next

pytestmark = pytest.mark.django_db


def form_data(response):
    form = BeautifulSoup(response.content, "html.parser").find("form", id="teacher-answer-form")
    return {field["name"]: field.get("value", "") for field in form.find_all("input")}


@pytest.mark.parametrize("action", ["answer", "skip", "edit"])
def test_stale_answer_form_preserves_newer_acknowledged_draft(ready_job, monkeypatch, action):
    client, user, job = ready_job
    review = start(job, user, ask_first)
    if action == "edit":
        review = advance(save(review, user, "original answer"), user, apply_and_next)
    turn = review.state["turns"][0]
    before_answer = turn["answer"]
    url = reverse("tutor-import-interpretation", args=[job.pk])
    edit_url = url + (f'?edit={turn["id"]}' if action == "edit" else "")
    old_form = form_data(client.get(edit_url))
    other = Client()
    other.force_login(user)
    saved = other.post(url, {**old_form, "action": "save_draft",
                            "answer": "newer acknowledged draft"})
    assert saved.status_code == 200
    monkeypatch.setattr("curriculum.teacher_review.get_review_provider",
                        lambda: pytest.fail("A draft conflict must never query a provider"))
    response = client.post(url, {**old_form, "action": action, "answer": "older local answer"})
    assert response.status_code == 409
    assert "older local answer" in response.content.decode()
    review.refresh_from_db()
    job.refresh_from_db()
    assert local_drafts(review)[turn["id"]]["text"] == "newer acknowledged draft"
    assert review.state["turns"][0]["answer"] == before_answer
    assert review.dossier_version == int(old_form["expected_version"])
    assert "older local answer" in client.get(url).content.decode()
    assert "newer acknowledged draft" in other.get(edit_url).content.decode()


@pytest.mark.parametrize("finish", ["discard", "submit"])
def test_edit_draft_keeps_pending_turn_draft(ready_job, finish):
    client, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "original value"), user, apply_and_next)
    first, pending = review.state["turns"]
    url = reverse("tutor-import-interpretation", args=[job.pk])
    pending_data = form_data(client.get(url))
    assert client.post(url, {**pending_data, "action": "save_draft", "answer": "pending answer draft"}).status_code == 200
    edit_url = f'{url}?edit={first["id"]}'
    edit_data = form_data(client.get(edit_url))
    assert client.post(url, {**edit_data, "action": "save_draft", "answer": "unsent correction"}).status_code == 200
    page = BeautifulSoup(client.get(url).content, "html.parser")
    assert page.find("textarea").text == "pending answer draft"
    assert form_data(client.get(url))["turn_id"] == pending["id"]
    assert "unsent correction" in client.get(edit_url).content.decode()
    if finish == "discard":
        data = form_data(client.get(edit_url))
        response = client.post(url, {**data, "action": "discard_draft"})
        assert response.status_code == 302
    else:
        review.refresh_from_db()
        submit_answer(job_id=job.pk, user=user, expected_revision=review.revision,
                      expected_version=review.dossier_version, expected_draft_epoch=review.draft_epoch,
                      receipt=str(uuid.uuid4()), turn_id=first["id"], answer="saved correction", edit=True)
    review.refresh_from_db()
    assert first["id"] not in local_drafts(review)
    assert local_drafts(review)[pending["id"]]["text"] == "pending answer draft"
    assert BeautifulSoup(client.get(url).content, "html.parser").find("textarea").text == "pending answer draft"


def test_original_flat_draft_is_preserved_when_another_turn_is_edited(ready_job):
    client, user, job = ready_job
    review = advance(save(start(job, user, ask_first), user, "original value"), user, apply_and_next)
    first, pending = review.state["turns"]
    review.draft_state = {"turn_id": pending["id"], "text": "legacy acknowledged draft", "mode": "answer"}
    review.save(update_fields=["draft_state"])
    url = reverse("tutor-import-interpretation", args=[job.pk])
    edit_data = form_data(client.get(f'{url}?edit={first["id"]}'))
    assert client.post(url, {**edit_data, "action": "save_draft", "answer": "new edit draft"}).status_code == 200
    review.refresh_from_db()
    assert local_drafts(review)[pending["id"]]["text"] == "legacy acknowledged draft"
    assert local_drafts(review)[first["id"]]["text"] == "new edit draft"
