import hashlib
import json
import os
import re

import django
import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import ClassroomSession, CurriculumPackage, PublishedPackageSnapshot


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_practice_cache():
    cache.clear()
    yield
    cache.clear()


def hidden_capability(response, name):
    matches = re.findall(
        rf'name="{name}" value="([^"]+)"',
        response.text,
    )
    assert matches, f"No se emitió la capacidad {name}."
    return matches[-1]


def published_snapshot(
    *,
    title="Práctica determinista",
    final_explanation="La idea principal organiza el sentido del texto.",
):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": "Una idea principal organiza el sentido del texto.",
        "questions": [
            {
                "type": "reactivo",
                "value": {
                    "prompt": "¿Cuál opción corresponde?",
                    "options": [
                        {
                            "position": 1,
                            "text": "La idea principal",
                            "expected": True,
                            "feedback": "Elegiste la idea principal.",
                        },
                        {
                            "position": 2,
                            "text": "Un detalle secundario",
                            "expected": False,
                            "feedback": "Elegiste un detalle secundario.",
                        },
                    ],
                    "hints": [
                        "Busca la afirmación que organiza el sentido del texto.",
                        "Después, distingue los detalles que la apoyan.",
                    ],
                },
            }
        ],
        "final_explanation": final_explanation,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    snapshot = PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username=f"publisher-{title}"),
    )
    return snapshot


def active_student_session(snapshot, client):
    session = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1)
    session.confirm()
    assignment = session.device_assignments.get()
    response = client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    assert response.status_code == 302
    return session


def test_student_can_submit_a_response_and_see_a_deterministic_result():
    snapshot = published_snapshot()
    client = Client()
    session = active_student_session(snapshot, client)

    response = client.post(
        reverse(
            "student-question-answer",
            args=[session.pk, 0],
        ),
        {"option_position": 1},
    )

    assert response.status_code == 200
    assert "Respuesta correcta" in response.text
    assert "Puntuación: 1" in response.text
    assert "Elegiste la idea principal." in response.text


def test_activity_does_not_reveal_expected_answer_before_response():
    snapshot = published_snapshot()
    client = Client()
    session = active_student_session(snapshot, client)

    response = client.get(
        reverse("student-activity", args=[session.pk]),
    )

    assert response.status_code == 200
    assert response.text.index("1. La idea principal") < response.text.index(
        "2. Un detalle secundario"
    )
    assert "expected" not in response.text
    assert "Respuesta correcta" not in response.text
    assert "La idea principal organiza el sentido del texto." not in response.text


def test_same_wrong_response_has_the_same_score_and_selected_option_feedback():
    snapshot = published_snapshot()
    client = Client()
    session = active_student_session(snapshot, client)
    answer_url = reverse("student-question-answer", args=[session.pk, 0])

    first_response = client.post(answer_url, {"option_position": 2})
    second_response = client.post(answer_url, {"option_position": 2})

    assert first_response.status_code == 200
    assert first_response.context["practice_result"] == second_response.context[
        "practice_result"
    ]
    assert "Respuesta incorrecta" in first_response.text
    assert "Puntuación: 0" in first_response.text
    assert "Elegiste un detalle secundario." in first_response.text


def test_regulated_assistance_returns_ordered_snapshot_hints_without_changing_score():
    snapshot = published_snapshot()
    client = Client()
    session = active_student_session(snapshot, client)
    assistance_url = reverse("student-question-assistance", args=[session.pk, 0])
    session_rows_before = Session.objects.count()

    activity = client.get(reverse("student-activity", args=[session.pk]))
    initial_hint_capability = hidden_capability(activity, "hint_capability")
    repeated_initial_activity = client.get(
        reverse("student-activity", args=[session.pk])
    )
    assert hidden_capability(repeated_initial_activity, "hint_capability") == (
        initial_hint_capability
    )
    tampered_hint = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": initial_hint_capability[:-1]
            + ("a" if initial_hint_capability[-1] != "a" else "b"),
        },
    )
    hint_one_without_capability = client.post(
        assistance_url,
        {"kind": "hint", "hint_index": 1},
    )
    hint_one_with_initial_capability = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 1,
            "hint_capability": initial_hint_capability,
        },
    )
    wrong_answer = client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 2},
    )
    first_hint = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": initial_hint_capability,
        },
    )
    next_hint_capability = hidden_capability(first_hint, "hint_capability")
    replayed_first_hint = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 0,
            "hint_capability": initial_hint_capability,
        },
    )
    reopened_activity = client.get(reverse("student-activity", args=[session.pk]))
    answer_after_first_hint = client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 2},
    )
    activity_after_answer = client.get(reverse("student-activity", args=[session.pk]))
    second_hint = client.post(
        assistance_url,
        {
            "kind": "hint",
            "hint_index": 1,
            "hint_capability": next_hint_capability,
        },
    )
    repeated_answer = client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 2},
    )

    assert first_hint.status_code == 200
    assert tampered_hint.status_code == 400
    assert hint_one_without_capability.status_code == 400
    assert hint_one_with_initial_capability.status_code == 400
    assert replayed_first_hint.status_code == 400
    assert 'name="hint_index" value="0"' not in reopened_activity.text
    assert answer_after_first_hint.status_code == 200
    assert 'name="hint_index" value="0"' not in activity_after_answer.text
    assert 'name="hint_index" value="1"' in activity_after_answer.text
    assert "Busca la afirmación que organiza el sentido del texto." in first_hint.text
    assert "Después, distingue los detalles que la apoyan." not in first_hint.text
    assert '"expected"' not in first_hint.text
    assert "La ayuda no modifica la puntuación." in first_hint.text
    assert first_hint.context["assistance"].score_impact == 0

    assert second_hint.status_code == 200
    assert "Después, distingue los detalles que la apoyan." in second_hint.text
    assert "Busca la afirmación que organiza el sentido del texto." not in second_hint.text
    assert second_hint.context["assistance"].hint_index == 1
    assert second_hint.context["assistance"].next_hint_index is None
    assert "Solicitar pista" not in second_hint.text
    assert "Solicitar siguiente pista" not in second_hint.text

    assert wrong_answer.context["practice_result"] == repeated_answer.context[
        "practice_result"
    ]
    assert Session.objects.count() == session_rows_before
    assert not any(
        key.startswith("aulalista.practice") for key in client.session.keys()
    )


def test_final_explanation_is_snapshot_assistance_only_after_response():
    snapshot = published_snapshot(
        final_explanation="La explicación final autorizada vive en este snapshot."
    )
    answered_client = Client()
    session = active_student_session(snapshot, answered_client)
    assistance_url = reverse("student-question-assistance", args=[session.pk, 0])

    forged_client = Client()
    before_response = forged_client.post(
        assistance_url,
        {"kind": "explanation", "answer_submitted": "1"},
    )

    answer_response = answered_client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    )
    after_response = answered_client.post(
        assistance_url,
        {
            "kind": "explanation",
            "explanation_capability": hidden_capability(
                answer_response,
                "explanation_capability",
            ),
        },
    )

    assert before_response.status_code == 403
    assert "La explicación final autorizada vive en este snapshot." not in before_response.text
    assert "La explicación final autorizada vive en este snapshot." not in answer_response.text
    assert after_response.status_code == 200
    assert "La explicación final autorizada vive en este snapshot." in after_response.text
    assert after_response.context["assistance"].score_impact == 0
