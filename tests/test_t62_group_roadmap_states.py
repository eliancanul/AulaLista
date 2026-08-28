from curriculum.roadmap import states_for_group_progress


def _payload():
    return {"units": [
        {"id": "u1", "lessons": [{"id": "l1", "activities": [{"id": "a1"}, {"id": "a2"}]}]},
        {"id": "u2", "lessons": [{"id": "l2", "activities": [{"id": "a3"}]}]},
    ]}


def test_group_states_follow_order_and_current_checkpoint():
    rows = states_for_group_progress(_payload(), [])
    assert [row["id"] for row in rows] == ["a1", "a2", "a3"]
    assert [row["state"] for row in rows] == ["ACTUAL", "DISPONIBLE", "BLOQUEADA"]


def test_current_takes_precedence_and_does_not_claim_activity_completion():
    rows = states_for_group_progress(_payload(), ["a1"], "a2")
    assert [row["state"] for row in rows] == ["COMPLETADA", "ACTUAL", "DISPONIBLE"]


def test_only_worked_checkpoint_starts_deterministic_navigation():
    rows = states_for_group_progress(_payload(), ["a1"])
    assert [row["state"] for row in rows] == ["COMPLETADA", "ACTUAL", "DISPONIBLE"]


def test_worked_unit_marks_only_one_representative_activity():
    rows = states_for_group_progress(_payload(), ["a1"])
    assert [row["state"] for row in rows] == ["COMPLETADA", "ACTUAL", "DISPONIBLE"]


# Integration contract: these use the real session, turn, snapshot and HTTP
# boundaries rather than testing the state helper in isolation.
import hashlib
import json
import os
from pathlib import Path
import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()
from curriculum.models import (  # noqa: E402
    ClassroomSession, CurriculumPackage, GroupRoadmapProgress,
    PublishedPackageSnapshot, PublishedRoadmapSnapshot, StudentRoadmapProgress,
)
from helpers import tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db


def _published(title, expected=True):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {"title": title, "objective": "Objetivo", "micro_lesson": "Lección",
               "questions": [{"value": {"prompt": "Elige", "options": [
                   {"position": 1, "text": "Sí", "expected": expected, "feedback": "Bien"},
                   {"position": 2, "text": "No", "expected": not expected, "feedback": "No"}], "hints": []}}]}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(package=package, version=1, payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(), source_revision=revision,
        published_by=get_user_model().objects.create_user(username=f"pub-{title}"))


def _multi_roadmap(first, second):
    payload = {"title": "Camino", "units": [{"id": "u1", "lessons": [{"id": "l1", "title": "L1", "activities": [{"id": "a1", "package_snapshot_id": first.pk}]}]}, {"id": "u2", "lessons": [{"id": "l2", "title": "L2", "activities": [{"id": "a2", "package_snapshot_id": second.pk}]}]}]}
    return PublishedRoadmapSnapshot.objects.create(title="Camino", version=1, payload=payload,
        sha256="x", published_by=get_user_model().objects.create_user(username="roadmap-pub"))


def _active(first, second):
    roadmap = _multi_roadmap(first, second)
    session = ClassroomSession.prepare_from_snapshot(first, 2, 2, roadmap_snapshot=roadmap)
    session.confirm()
    return session, roadmap


def _join(session, client, assignment):
    response = client.post(reverse("student-turn-start", args=[session.pk, assignment.local_identifier]), {"display_name": "VisibleName"})
    assert response.status_code == 302


def test_group_completion_rejects_stale_activity():
    first, second = _published("a1"), _published("a2")
    session, roadmap = _active(first, second)
    group = GroupRoadmapProgress.for_session(session)
    group.advance_to("a2")
    with pytest.raises(ValidationError):
        group.complete_activity("a1")
    assert group.refresh_from_db() is None and group.current_activity_id == "a2"


def test_two_turns_and_late_joiner_use_group_snapshot():
    first, second = _published("a1"), _published("a2")
    session, roadmap = _active(first, second)
    clients = [Client(), Client()]
    assignments = list(session.device_assignments.order_by("id"))
    _join(session, clients[0], assignments[0])
    completed = clients[0].post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1, "activity_id": "a1"},
    )
    assert completed.status_code == 200
    _join(session, clients[1], assignments[1])
    assert GroupRoadmapProgress.for_session(session).current_activity_id == "a2"
    assert StudentRoadmapProgress.objects.filter(session=session).count() == 2
    responses = [clients[0].get(reverse("student-activity", args=[session.pk])), clients[1].get(reverse("student-activity", args=[session.pk]))]
    assert all(response.status_code == 200 for response in responses)
    assert all(response.context["snapshot"].pk == second.pk for response in responses)
    assert all(response.context["item_activity_id"] == "a2" for response in responses)


def test_missing_and_stale_answer_cannot_advance_group():
    first, second = _published("a1"), _published("a2")
    session, _ = _active(first, second)
    client = Client()
    _join(session, client, session.device_assignments.order_by("id").first())
    answer_url = reverse("student-question-answer", args=[session.pk, 0])

    assert client.post(answer_url, {"option_position": 1}).status_code == 400
    assert GroupRoadmapProgress.for_session(session).current_activity_id == "a1"

    assert client.post(
        answer_url,
        {"option_position": 1, "activity_id": "a1"},
    ).status_code == 200
    assert GroupRoadmapProgress.for_session(session).current_activity_id == "a2"

    assert client.post(
        answer_url,
        {"option_position": 1, "activity_id": "a1"},
    ).status_code == 400
    progress = StudentRoadmapProgress.objects.get(session=session)
    assert "a2" not in progress.correct_question_indices
    assert GroupRoadmapProgress.for_session(session).current_activity_id == "a2"


def test_manual_lesson_advance_requires_teacher_post_csrf_and_only_forward():
    first, second = _published("a1"), _published("a2")
    session, roadmap = _active(first, second)
    teacher = tutor_client(username="advance-teacher")
    url = reverse("tutor-session-roadmap-advance", args=[session.pk])
    assert teacher.get(url).status_code == 405
    assert Client().post(url, {"lesson_id": "l2"}).status_code in (302, 403)

    nonstaff = Client()
    nonstaff.force_login(get_user_model().objects.create_user(username="not-staff"))
    assert nonstaff.post(url, {"lesson_id": "l2"}).status_code == 403

    csrf = Client(enforce_csrf_checks=True)
    user = get_user_model().objects.get(username="advance-teacher")
    csrf.force_login(user)
    assert csrf.post(url, {"lesson_id": "l2"}).status_code == 403
    active = csrf.get(reverse("tutor-session-active", args=[session.pk]))
    assert active.status_code == 200
    assert 'value="l2"' in active.text
    assert 'value="l1"' not in active.text
    csrf_token = csrf.cookies["csrftoken"].value
    assert csrf.post(
        url,
        {"lesson_id": "l2"},
        HTTP_X_CSRFTOKEN=csrf_token,
    ).status_code == 302
    assert GroupRoadmapProgress.for_session(session).current_activity_id == "a2"
    assert teacher.post(url, {"lesson_id": "l2"}).status_code == 400
    assert teacher.post(url, {"lesson_id": "l1"}).status_code == 400


def test_sessions_same_roadmap_are_isolated_and_complete_cannot_reopen():
    first, second = _published("a1"), _published("a2")
    roadmap = _multi_roadmap(first, second)
    one = ClassroomSession.prepare_from_snapshot(first, 1, 1, roadmap_snapshot=roadmap); one.confirm()
    two = ClassroomSession.prepare_from_snapshot(first, 1, 1, roadmap_snapshot=roadmap); two.confirm()
    GroupRoadmapProgress.for_session(one).complete_activity("a1")
    assert GroupRoadmapProgress.for_session(two).current_activity_id in ("", "a1")
    group = GroupRoadmapProgress.for_session(one); group.complete_activity("a2")
    with pytest.raises(ValidationError): group.advance_to("a1")
    assert one.roadmap_snapshot_id == two.roadmap_snapshot_id == roadmap.pk


def test_landing_is_group_only_private_local_and_accessible():
    first, second = _published("a1"), _published("a2")
    session, _ = _active(first, second)
    client = Client()
    _join(session, client, session.device_assignments.order_by("id").first())

    response = client.get(reverse("student-roadmap", args=[session.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    lowered = body.lower()
    for state in ("ACTUAL", "DISPONIBLE", "COMPLETADA", "BLOQUEADA"):
        assert state in body
    assert "AVANCE DEL GRUPO" in body
    assert "Demostración sintética" in body
    for forbidden in (
        "visiblename", "participant_key", "uuid", "mac", "roster",
        "participantes presentes", "http://", "https://",
    ):
        assert forbidden not in lowered

    css = Path("static/curriculum/aulalista.css").read_text()
    template = Path("templates/curriculum/student_roadmap.html").read_text()
    assert "@keyframes roadmap-completed" in css
    assert ".activity-row.state-completada" in css
    assert "prefers-reduced-motion" in css
    assert "max-width: 360px" in css
    assert "{% static 'curriculum/aulalista.css' %}" in template
    assert "http://" not in template and "https://" not in template


def test_landing_completion_comes_from_group_not_individual_turn():
    first, second = _published("a1"), _published("a2")
    session, _ = _active(first, second)
    client = Client()
    _join(session, client, session.device_assignments.order_by("id").first())
    individual = StudentRoadmapProgress.objects.get(session=session)
    assert individual.completed_activity_ids == []

    group = GroupRoadmapProgress.for_session(session)
    group.complete_activity("a1")
    group.complete_activity("a2")
    response = client.get(reverse("student-roadmap", args=[session.pk]))

    assert response.status_code == 200
    assert response.context["roadmap_completed"] is True
    assert "El grupo ha completado todas las actividades" in response.text
    individual.refresh_from_db()
    assert individual.completed_activity_ids == []
