"""Issue #86: group-level retention and the bounded pseudonymous register."""

import hashlib
import json
import os
import uuid

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomGroup,
    ClassroomSession,
    CurriculumPackage,
    CurriculumProgress,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
    PseudonymousSurveyResponse,
)
from helpers import tutor_client, tutor_client_for_sessions  # noqa: E402


pytestmark = pytest.mark.django_db


def published_snapshot(title="Actividad #86"):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {"title": title, "objective": "Objetivo", "questions": []}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=digest,
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username=f"publisher-{package.pk}"),
    )


def three_activity_roadmap(snapshot):
    return PublishedRoadmapSnapshot.objects.create(
        title="Tres actividades",
        version=1,
        payload={
            "title": "Tres actividades",
            "units": [{
                "id": "unit-1",
                "title": "Unidad",
                "lessons": [{
                    "id": "lesson-1",
                    "title": "Lección",
                    "activities": [
                        {"id": f"activity-{number}", "title": f"Actividad {number}", "package_snapshot_id": snapshot.pk}
                        for number in range(1, 4)
                    ],
                }],
            }],
        },
        sha256="ignored-by-model",
        published_by=get_user_model().objects.create_user(username=f"roadmap-{snapshot.pk}"),
    )


def result(session, participant_key, activity_id, state=PseudonymousResult.STATE_COMPLETED):
    return PseudonymousResult.objects.create(
        result_batch_id=session.result_batch_id,
        participant_key=participant_key,
        activity_id=activity_id,
        snapshot_id=session.snapshot_id,
        snapshot_version=session.snapshot.version,
        snapshot_sha256=session.snapshot.sha256,
        state=state,
        duration_seconds=20,
        responses=[],
        score=0,
        help_requests=[],
        technical_errors=[],
    )


def test_closing_roadmap_session_groups_two_participants_across_three_activities_without_nickname():
    snapshot = published_snapshot()
    roadmap = three_activity_roadmap(snapshot)
    session = ClassroomSession.prepare_from_snapshot(snapshot, 2, 2, roadmap_snapshot=roadmap)
    session.confirm()
    first = session.device_assignments.all()[0].reserve_turn("Apodo privado A")
    second = session.device_assignments.all()[1].reserve_turn("Apodo privado B")

    session.close()

    results = list(PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id))
    assert len(results) == 6
    assert {item.participant_key for item in results} == {first.participant_key, second.participant_key}
    assert {item.activity_id for item in results} == {"activity-1", "activity-2", "activity-3"}
    assert all(
        sum(item.participant_key == key for item in results) == 3
        for key in (first.participant_key, second.participant_key)
    )
    persisted = json.dumps(list(PseudonymousResult.objects.values()), default=str, ensure_ascii=False)
    assert "Apodo privado" not in persisted

    client = tutor_client_for_sessions(session)
    page = client.get(reverse("tutor-session-results", args=[session.pk]))
    assert page.status_code == 200
    assert "Registro individual seudónimo" in page.text
    assert str(first.participant_key) not in page.text
    assert str(first.participant_key)[:8] in page.text
    assert "Diagnóstico" not in page.text
    json_export = client.post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "json"}
    )
    csv_export = client.post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "csv"}
    )
    assert json_export.status_code == csv_export.status_code == 200
    for response in (json_export, csv_export):
        assert str(first.participant_key) not in response.text
        assert str(results[0].id) not in response.text
        assert "participant_label" in response.text


def test_group_aggregates_stay_with_the_selected_classroom_group():
    owner = get_user_model().objects.create_user(username="maestra", is_staff=True)
    other_owner = get_user_model().objects.create_user(username="otra", is_staff=True)
    snapshot = published_snapshot()
    group = ClassroomGroup.objects.create(name="6° A", created_by=owner)
    other_group = ClassroomGroup.objects.create(name="6° B", created_by=other_owner)
    first = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, classroom_group=group, teacher=owner
    )
    second = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, classroom_group=other_group, teacher=other_owner
    )
    first.close()
    second.close()
    group_result = result(first, uuid.uuid4(), "activity-1")
    group_result.help_requests = [{"kind": "hint"}]
    group_result.technical_errors = [{"message": "local"}]
    group_result.save(update_fields=["help_requests", "technical_errors"])
    result(second, uuid.uuid4(), "activity-1")
    PseudonymousSurveyResponse.objects.create(
        result_batch_id=first.result_batch_id,
        snapshot_id=snapshot.pk,
        snapshot_version=snapshot.version,
        rating=4,
    )

    client = Client()
    client.force_login(owner)
    page = client.get(reverse("tutor-group-results", args=[group.pk]))
    assert page.status_code == 200
    assert "6° A" in page.text
    assert "4.0 / 5" in page.text
    assert "Distribución de actividades" in page.text
    assert ">1</strong> ayudas solicitadas" in page.text
    assert ">1</strong> errores técnicos" in page.text
    assert snapshot.sha256[:8] in page.text
    assert client.get(reverse("tutor-group-results", args=[other_group.pk])).status_code == 404


def test_close_school_year_erases_only_group_results_and_surveys_preserving_curriculum_and_sessions():
    client = tutor_client("year-close-teacher")
    owner = get_user_model().objects.get(username="year-close-teacher")
    snapshot = published_snapshot()
    roadmap = three_activity_roadmap(snapshot)
    CurriculumProgress.confirm(
        roadmap_snapshot=roadmap,
        node_id="unit-1",
        status=CurriculumProgress.STATUS_WORKED,
        teacher=owner,
    )
    group = ClassroomGroup.objects.create(name="6° A", created_by=owner)
    session = ClassroomSession.prepare_from_snapshot(
        snapshot,
        1,
        1,
        roadmap_snapshot=roadmap,
        classroom_group=group,
        teacher=owner,
    )
    session.close()
    result(session, uuid.uuid4(), "activity-1")
    PseudonymousSurveyResponse.objects.create(
        result_batch_id=session.result_batch_id,
        snapshot_id=snapshot.pk,
        snapshot_version=snapshot.version,
        rating=5,
    )

    close_url = reverse("tutor-group-close-year", args=[group.pk])
    assert client.post(close_url).status_code == 400
    assert PseudonymousResult.objects.exists()
    assert PseudonymousSurveyResponse.objects.exists()
    assert client.post(close_url, {"confirm": "CERRAR"}).status_code == 302
    assert not PseudonymousResult.objects.exists()
    assert not PseudonymousSurveyResponse.objects.exists()
    assert CurriculumPackage.objects.filter(pk=snapshot.package_id).exists()
    assert PublishedPackageSnapshot.objects.filter(pk=snapshot.pk).exists()
    assert PublishedRoadmapSnapshot.objects.filter(pk=roadmap.pk).exists()
    assert CurriculumProgress.objects.filter(roadmap_snapshot=roadmap).exists()
    assert ClassroomSession.objects.filter(pk=session.pk, classroom_group=group).exists()


def test_new_group_routes_require_a_staff_teacher_and_close_year_is_post_only():
    owner = get_user_model().objects.create_user(username="route-owner", is_staff=True)
    group = ClassroomGroup.objects.create(name="6° A", created_by=owner)
    routes = [
        reverse("tutor-groups"),
        reverse("tutor-group-results", args=[group.pk]),
        reverse("tutor-group-close-year", args=[group.pk]),
    ]
    for route in routes:
        assert Client().get(route).status_code == 302

    non_staff = Client()
    non_staff.force_login(get_user_model().objects.create_user(username="not-staff-86"))
    for route in routes:
        assert non_staff.get(route).status_code == 403

    staff = Client()
    staff.force_login(owner)
    assert staff.get(reverse("tutor-group-close-year", args=[group.pk])).status_code == 405


def test_session_result_routes_reject_another_staff_teacher():
    owner = get_user_model().objects.create_user(username="session-owner", is_staff=True)
    other = get_user_model().objects.create_user(username="session-other", is_staff=True)
    snapshot = published_snapshot("Sesión privada")
    session = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1, teacher=owner)
    session.close()
    stored = result(session, uuid.uuid4(), "activity-1")
    other_client = Client()
    other_client.force_login(other)

    protected = [
        ("get", reverse("tutor-session-review", args=[session.pk])),
        ("get", reverse("tutor-session-results", args=[session.pk])),
        ("post", reverse("tutor-session-export", args=[session.pk]), {"format": "json"}),
        ("post", reverse("tutor-session-results-delete", args=[session.pk])),
        ("post", reverse("tutor-result-delete", args=[session.pk, stored.pk])),
    ]
    for method, url, *data in protected:
        assert getattr(other_client, method)(url, *(data or [])).status_code == 404

    assert other_client.get(reverse("tutor-results")).status_code == 200
    assert "Sesión privada" not in other_client.get(reverse("tutor-results")).text
