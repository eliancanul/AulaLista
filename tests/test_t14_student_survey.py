import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
    PseudonymousResult,
    PseudonymousSurveyResponse,
    StudentTurn,
)
from curriculum.survey import (  # noqa: E402
    STUDENT_SURVEY_QUESTIONS,
    SurveyContractError,
    survey_aggregate,
    validate_survey_answers,
)


from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db


def published_snapshot(title="Paquete T14"):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": "Una idea principal organiza el sentido.",
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
                            "text": "Un detalle",
                            "expected": False,
                            "feedback": "Elegiste un detalle.",
                        },
                    ],
                    "hints": ["Busca la afirmación que organiza el sentido."],
                },
            }
        ],
        "final_explanation": "La idea principal organiza el sentido.",
    }
    import hashlib

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{title}-{package.pk}",
        ),
    )


def active_session():
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 1, 1)
    session.confirm()
    return session


def bound_client(session):
    """A client that joined the session and owns a device assignment."""

    import uuid as uuid_module

    client = Client()
    join = client.post(reverse("student-session-join", args=[session.pk]))
    assert join.status_code == 302
    # .../devices/<local_identifier>/turn/start/
    local_identifier = join["Location"].rstrip("/").split("/")[-3]
    assignment = session.device_assignments.get(
        local_identifier=uuid_module.UUID(local_identifier),
    )
    return client, assignment


def valid_post_data(**overrides):
    data = {
        "claridad": "Sí",
        "pistas": "Más o menos",
        "mas_actividades": "Sí",
        "comentario": "Me gustó la actividad.",
    }
    data.update(overrides)
    return data


def test_validate_survey_answers_normalizes_and_rejects_invalid():
    answers = validate_survey_answers(valid_post_data())
    assert answers == [
        {"question_id": "claridad", "choice": "Sí"},
        {"question_id": "pistas", "choice": "Más o menos"},
        {"question_id": "mas_actividades", "choice": "Sí"},
        {"question_id": "comentario", "text": "Me gustó la actividad."},
    ]

    with pytest.raises(SurveyContractError, match="clara"):
        validate_survey_answers(valid_post_data(claridad=""))
    with pytest.raises(SurveyContractError, match="no es una opción válida"):
        validate_survey_answers(valid_post_data(pistas="Tal vez"))


def test_survey_flow_stores_pseudonymous_response_once_per_device():
    cache.clear()
    session = active_session()
    client, _assignment = bound_client(session)
    url = reverse("student-session-survey", args=[session.pk])

    get_page = client.get(url)
    assert get_page.status_code == 200
    for question in STUDENT_SURVEY_QUESTIONS:
        assert question["prompt"] in get_page.text

    submitted = client.post(url, valid_post_data())
    assert submitted.status_code == 200
    response = PseudonymousSurveyResponse.objects.get()
    assert response.result_batch_id == session.result_batch_id
    assert response.snapshot_id == session.snapshot_id
    assert response.snapshot_version == session.snapshot.version
    assert len(response.answers) == len(STUDENT_SURVEY_QUESTIONS)

    duplicate = client.post(url, valid_post_data())
    assert duplicate.status_code == 400
    assert PseudonymousSurveyResponse.objects.count() == 1


def test_second_device_can_answer_independently_and_no_identity_is_linked():
    cache.clear()
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 2)
    session.confirm()
    url = reverse("student-session-survey", args=[session.pk])
    first, assignment_one = bound_client(session)
    second, assignment_two = bound_client(session)

    first.post(url, valid_post_data(comentario="Primera opinión"))
    second.post(url, valid_post_data(comentario="Segunda opinión"))

    assert PseudonymousSurveyResponse.objects.count() == 2
    stored = json.dumps(
        list(PseudonymousSurveyResponse.objects.values("answers")),
        ensure_ascii=False,
    )
    assert "Luna" not in stored
    assert str(assignment_one.local_identifier) not in stored
    assert str(assignment_two.local_identifier) not in stored
    assert not any(
        field.name in {"turn", "assignment", "device", "display_name"}
        for field in PseudonymousSurveyResponse._meta.fields
    )


def test_survey_requires_active_session_and_device_binding():
    session = active_session()
    url = reverse("student-session-survey", args=[session.pk])

    anonymous = Client().get(url)
    assert anonymous.status_code == 403

    client, _assignment = bound_client(session)
    assert Client().post(url, valid_post_data()).status_code == 403

    session.close()
    after_close = client.post(url, valid_post_data())
    assert after_close.status_code == 403


def test_close_preserves_survey_responses_without_temporal_relations():
    cache.clear()
    session = active_session()
    client, assignment = bound_client(session)
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    client.post(reverse("student-turn-ready", args=[session.pk]))
    client.post(
        reverse("student-session-survey", args=[session.pk]),
        valid_post_data(),
    )

    session.close()

    assert not StudentTurn.objects.exists()
    assert not DeviceAssignment.objects.exists()
    assert PseudonymousResult.objects.filter(
        result_batch_id=session.result_batch_id
    ).exists()
    surveys = PseudonymousSurveyResponse.objects.filter(
        result_batch_id=session.result_batch_id,
    )
    assert surveys.count() == 1
    assert surveys.get().answers[0]["choice"] == "Sí"


def test_teacher_review_shows_survey_aggregate_and_export_includes_it():
    cache.clear()
    session = ClassroomSession.prepare_from_snapshot(published_snapshot(), 2, 2)
    session.confirm()
    url = reverse("student-session-survey", args=[session.pk])
    first, _a = bound_client(session)
    second, _b = bound_client(session)
    first.post(url, valid_post_data(comentario="Más reactivos visuales"))
    second.post(url, valid_post_data(mas_actividades="No", comentario=""))

    review = tutor_client().get(reverse("tutor-session-review", args=[session.pk]))
    assert review.status_code == 200
    assert 'data-survey-aggregate' in review.text
    assert "Encuesta de los alumnos (2 respuestas)" in review.text
    assert "Más reactivos visuales" in review.text

    session.close()
    export = tutor_client().post(reverse("tutor-session-export", args=[session.pk]),
        {"format": "json"},
    )
    assert export.status_code == 200
    payload = json.loads(export.text)
    assert payload["survey"]["response_count"] == 2
    assert payload["survey"]["totals"]["mas_actividades"] == {"Sí": 1, "Más o menos": 0, "No": 1}
    assert payload["survey"]["open_texts"] == ["Más reactivos visuales"]


def test_deleting_all_results_also_deletes_their_surveys_but_individual_results_do_not():
    cache.clear()
    session = active_session()
    client, assignment = bound_client(session)
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    client.post(reverse("student-turn-ready", args=[session.pk]))
    client.post(
        reverse("student-session-survey", args=[session.pk]),
        valid_post_data(),
    )
    session.close()

    result = PseudonymousResult.objects.get()
    individual = tutor_client().post(
        reverse(
            "tutor-result-delete",
            args=[session.pk, result.pk],
        ),
    )
    assert individual.status_code == 200
    assert PseudonymousSurveyResponse.objects.count() == 1

    delete_all = tutor_client().post(reverse("tutor-session-results-delete", args=[session.pk]),
    )
    assert delete_all.status_code == 200
    body = delete_all.json()
    assert body["surveys_deleted"] == 1
    assert not PseudonymousSurveyResponse.objects.exists()
