"""Issue #100: worked-only group results and private roadmap control."""

import hashlib
import csv
import io
import json
import uuid

import django
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from wagtail.models import Revision
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomSession,
    CurriculumPackage,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
    ClassroomGroup,
    GroupRoadmapProgress,
)
from curriculum.views import _has_valid_result_response, _result_aggregate  # noqa: E402
from helpers import tutor_client_for_sessions  # noqa: E402


pytestmark = pytest.mark.django_db


def _snapshot(title="Actividad sintética", owner=None):
    owner = owner or get_user_model().objects.create_user(
        username=f"owner-{uuid.uuid4().hex[:8]}", is_staff=True
    )
    package = CurriculumPackage.objects.create(title=title, created_by=owner)
    revision = package.save_revision()
    payload = {"title": title, "questions": []}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=digest,
        source_revision=revision,
        published_by=owner,
    ), owner


def _result(session, participant, activity, *, state="completed", responses=None):
    snapshot = session.snapshot
    return PseudonymousResult.objects.create(
        result_batch_id=session.result_batch_id,
        participant_key=participant,
        activity_id=activity,
        snapshot_id=snapshot.pk,
        snapshot_version=snapshot.version,
        snapshot_sha256=snapshot.sha256,
        state=state,
        duration_seconds=20,
        responses=responses
        if responses is not None
        else [{"question_index": 0, "selected_position": 1, "is_correct": False}],
        score=0,
        help_requests=[],
        technical_errors=[],
    )


@pytest.mark.parametrize(
    "responses",
    [
        None,
        [],
        [None],
        [{}],
        [{"junk": None}],
        [{"question_index": 0, "selected_position": None, "is_correct": None}],
        [{"question_index": "0", "selected_position": 1, "is_correct": True}],
    ],
)
def test_only_canonical_response_payloads_count_as_worked(responses):
    result = type("Result", (), {"responses": responses})()
    assert _has_valid_result_response(result) is False


@pytest.mark.parametrize("is_correct", [True, False])
def test_canonical_correct_and_incorrect_responses_are_valid(is_correct):
    result = type(
        "Result",
        (),
        {
            "responses": [
                {
                    "question_index": 0,
                    "selected_position": 1,
                    "is_correct": is_correct,
                }
            ]
        },
    )()
    assert _has_valid_result_response(result) is True


def test_aggregate_ignores_empty_rows_and_deduplicates_activity_and_participant():
    snapshot, _ = _snapshot()
    session = ClassroomSession.prepare_from_snapshot(snapshot, 2, 2)
    session.close()
    participant = uuid.uuid4()
    _result(session, participant, "actividad-0")
    _result(session, participant, "actividad-0")
    _result(session, uuid.uuid4(), "actividad-0", state="abandoned", responses=[])
    _result(session, uuid.uuid4(), "actividad-0", responses=[{"junk": None}])
    aggregate = _result_aggregate(
        PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id),
        session=session,
    )
    assert aggregate["activities_worked"] == 1
    assert aggregate["participants"] == 1
    assert aggregate["activities_completed"] == 1
    assert aggregate["count"] == 1


def test_legacy_session_accepts_only_the_close_sentinel_activity_id():
    snapshot, _ = _snapshot("Actividad legacy")
    session = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1)
    session.close()
    sentinel = _result(session, uuid.uuid4(), "actividad-0")
    unknown = _result(session, uuid.uuid4(), "future/unknown")

    aggregate = _result_aggregate(
        [unknown, sentinel],
        session=session,
    )
    assert aggregate["count"] == 1
    assert aggregate["worked_activities"][0]["activity_id"] == "actividad-0"
    assert aggregate["worked_activities"][0]["activity_title"] == "Actividad legacy"

    # The grouped projection resolves the owning session from the result
    # batch, so the same fail-closed rule must apply without an explicit one.
    assert _result_aggregate([unknown, sentinel])["count"] == 1


def test_legacy_unknown_activity_is_excluded_from_review_and_exports():
    snapshot, _ = _snapshot("Actividad legacy visible")
    session = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1)
    session.close()
    sentinel = _result(session, uuid.uuid4(), "actividad-0")
    unknown = _result(session, uuid.uuid4(), "future/unknown")
    client = tutor_client_for_sessions(session)

    review = client.get(reverse("tutor-session-review", args=[session.pk]))
    assert review.status_code == 200
    assert len(review.context["individual_register"]) == 1

    exported_json = client.post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "json"}
    )
    assert [row["activity_title"] for row in exported_json.json()["results"]] == [
        "Actividad legacy visible"
    ]
    exported_csv = client.post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "csv"}
    )
    assert len(list(csv.DictReader(io.StringIO(exported_csv.content.decode())))) == 1


def test_aggregate_requires_roadmap_activity_and_response_scope_to_match():
    snapshot, owner = _snapshot("Actividad presentada")
    second_snapshot, _ = _snapshot("Actividad futura", owner=owner)
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Roadmap de alcance",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "Unidad segura",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "Lección segura",
                    "activities": [
                        {
                            "id": "a1",
                            "title": "Actividad presentada",
                            "package_snapshot_id": snapshot.pk,
                        },
                        {
                            "id": "a2",
                            "title": "Actividad futura",
                            "package_snapshot_id": second_snapshot.pk,
                        },
                    ],
                }],
            }],
        },
        sha256="roadmap-alcance",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    session.close()
    participant = uuid.uuid4()
    valid = _result(
        session,
        participant,
        "a1",
        responses=[{
            "question_index": 0,
            "selected_position": 1,
            "is_correct": True,
            "activity_id": "a1",
        }],
    )
    unknown = _result(
        session,
        uuid.uuid4(),
        "future",
        responses=[{
            "question_index": 0,
            "selected_position": 1,
            "is_correct": True,
            "activity_id": "future",
        }],
    )
    future_in_roadmap = _result(
        session,
        uuid.uuid4(),
        "a2",
        responses=[{
            "question_index": 0,
            "selected_position": 1,
            "is_correct": True,
            "activity_id": "a2",
        }],
    )
    future_in_roadmap.snapshot_id = second_snapshot.pk
    future_in_roadmap.snapshot_version = second_snapshot.version
    future_in_roadmap.snapshot_sha256 = second_snapshot.sha256
    future_in_roadmap.save(update_fields=["snapshot_id", "snapshot_version", "snapshot_sha256"])
    mismatch = _result(
        session,
        uuid.uuid4(),
        "a1",
        responses=[{
            "question_index": 0,
            "selected_position": 1,
            "is_correct": True,
            "activity_id": "future",
        }],
    )
    mismatch.snapshot_id = second_snapshot.pk
    mismatch.snapshot_version = second_snapshot.version
    mismatch.snapshot_sha256 = second_snapshot.sha256
    mismatch.save(update_fields=["snapshot_id", "snapshot_version", "snapshot_sha256"])
    wrong_snapshot_metadata = _result(session, uuid.uuid4(), "a1")
    wrong_snapshot_metadata.snapshot_version = 999
    wrong_snapshot_metadata.snapshot_sha256 = "f" * 64
    wrong_snapshot_metadata.save(update_fields=["snapshot_version", "snapshot_sha256"])

    aggregate = _result_aggregate(
        PseudonymousResult.objects.filter(result_batch_id=session.result_batch_id),
        session=session,
    )
    assert aggregate["count"] == 1
    assert aggregate["worked_activities"][0]["activity_id"] == "a1"
    assert aggregate["participants"] == 1

    # A result from another session cannot be smuggled into this projection.
    other_snapshot, other_owner = _snapshot("Otra actividad")
    other_session = ClassroomSession.prepare_from_snapshot(
        other_snapshot, 1, 1, teacher=other_owner
    )
    other_session.close()
    foreign_result = _result(other_session, uuid.uuid4(), "future")
    assert _result_aggregate(
        [foreign_result], session=session
    )["count"] == 0


def test_aggregate_export_keeps_human_activity_hierarchy_without_identifiers():
    snapshot, owner = _snapshot("Partes iguales")
    second_snapshot, _ = _snapshot("Denominadores", owner=owner)
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Roadmap exportable",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "Fracciones",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "Representación",
                    "activities": [
                        {"id": "a1", "title": "Partes iguales", "package_snapshot_id": snapshot.pk},
                        {"id": "a2", "title": "Denominadores", "package_snapshot_id": second_snapshot.pk},
                    ],
                }],
            }],
        },
        sha256="roadmap-exportable",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    group_progress = GroupRoadmapProgress.for_session(session)
    group_progress.complete_activity("a1")
    session.close()
    second = _result(session, uuid.uuid4(), "a2", responses=[{
        "question_index": 0, "selected_position": 1, "is_correct": False,
        "activity_id": "a2",
    }])
    first = _result(session, uuid.uuid4(), "a1", responses=[{
        "question_index": 0, "selected_position": 1, "is_correct": True,
        "activity_id": "a1",
    }])
    second.snapshot_id = second_snapshot.pk
    second.snapshot_version = second_snapshot.version
    second.snapshot_sha256 = second_snapshot.sha256
    second.save(update_fields=["snapshot_id", "snapshot_version", "snapshot_sha256"])

    response = tutor_client_for_sessions(session).post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "json"}
    )
    assert response.status_code == 200
    rows = response.json()["results"]
    assert [row["activity_title"] for row in rows] == [
        "Partes iguales",
        "Denominadores",
    ]
    assert {row["activity_title"] for row in rows} == {"Partes iguales", "Denominadores"}
    assert {row["unit_title"] for row in rows} == {"Fracciones"}
    assert {row["lesson_title"] for row in rows} == {"Representación"}
    assert all("activity_id" not in row and "snapshot_id" not in row for row in rows)
    csv_response = tutor_client_for_sessions(session).post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "csv"}
    )
    csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode())))
    assert [row["activity_title"] for row in csv_rows] == [
        "Partes iguales",
        "Denominadores",
    ]


def test_csv_export_neutralizes_formula_titles_and_preserves_csv_quoting():
    snapshot, owner = _snapshot("Paquete")
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Roadmap CSV",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "=unidad",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "@lección",
                    "activities": [
                        {"id": "a1", "title": "+actividad", "package_snapshot_id": snapshot.pk},
                        {"id": "a2", "title": "-peligro,\nsegunda línea", "package_snapshot_id": snapshot.pk},
                    ],
                }],
            }],
        },
        sha256="ignored",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    progress = GroupRoadmapProgress.for_session(session)
    progress.complete_activity("a1")
    progress.complete_activity("a2")
    session.close()
    _result(session, uuid.uuid4(), "a2")
    _result(session, uuid.uuid4(), "a1")

    response = tutor_client_for_sessions(session).post(
        reverse("tutor-session-export", args=[session.pk]), {"format": "csv"}
    )
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert [row["activity_title"] for row in rows] == [
        "'+actividad",
        "'-peligro,\nsegunda línea",
    ]
    assert rows[0]["unit_title"] == "'=unidad"
    assert rows[0]["lesson_title"] == "'@lección"


def test_published_roadmap_rejects_duplicate_activity_ids():
    snapshot, owner = _snapshot("Duplicado")
    with pytest.raises(ValidationError, match="IDs de actividad duplicados"):
        PublishedRoadmapSnapshot.objects.create(
            title="Roadmap ambiguo",
            version=1,
            payload={
                "units": [{
                    "id": "u1",
                    "lessons": [{
                        "id": "l1",
                        "activities": [
                            {"id": "same", "package_snapshot_id": snapshot.pk},
                            {"id": "same", "package_snapshot_id": snapshot.pk},
                        ],
                    }],
                }],
            },
            sha256="ignored",
            published_by=owner,
        )


def test_empty_results_use_exact_state_and_roadmap_action():
    snapshot, owner = _snapshot("Sin respuestas")
    roadmap = PublishedRoadmapSnapshot.publish(
        title="Camino sintético", package_snapshots=[snapshot], teacher=owner
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    session.close()
    response = tutor_client_for_sessions(session).get(
        reverse("tutor-session-results", args=[session.pk])
    )
    assert response.status_code == 200
    assert "Aún no hay actividades trabajadas" in response.text
    assert "Volver al Roadmap" in response.text
    assert "pending" not in response.text.lower()


def test_roadmap_advance_cannot_mutate_another_teachers_session():
    snapshot, owner = _snapshot("Roadmap de una maestra")
    roadmap = PublishedRoadmapSnapshot.publish(
        title="Camino privado", package_snapshots=[snapshot], teacher=owner
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    session.confirm()
    progress = GroupRoadmapProgress.for_session(session)
    before = (progress.current_activity_id, list(progress.completed_activity_ids))
    other = get_user_model().objects.create_user(
        username=f"other-{uuid.uuid4().hex[:8]}", is_staff=True
    )
    client = Client()
    client.force_login(other)
    valid_lesson_id = roadmap.payload["units"][0]["lessons"][0]["id"]
    response = client.post(
        reverse("tutor-session-roadmap-advance", args=[session.pk]),
        {"lesson_id": valid_lesson_id},
    )
    assert response.status_code == 404
    progress.refresh_from_db()
    assert (progress.current_activity_id, progress.completed_activity_ids) == before


def test_mixed_session_has_worked_default_and_secondary_no_participation_view():
    snapshot, owner = _snapshot("Mixta")
    second_snapshot, _ = _snapshot("Mixta 2", owner=owner)
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Camino mixto",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "Unidad",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "Lección",
                    "activities": [
                        {"id": "a1", "title": "Trabajada", "package_snapshot_id": snapshot.pk},
                        {
                            "id": "a2",
                            "title": "Sin respuesta",
                            "package_snapshot_id": second_snapshot.pk,
                        },
                    ],
                }],
            }]
        },
        sha256="mixta",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    progress = GroupRoadmapProgress.for_session(session)
    progress.complete_activity("a1")
    session.close()
    participant_key = uuid.uuid4()
    stored_result = _result(session, participant_key, "a1")
    client = tutor_client_for_sessions(session)
    worked = client.get(reverse("tutor-results"))
    assert "Trabajada" in worked.text
    assert "Sin respuesta" not in worked.text
    assert "Ver actividades sin participación" in worked.text
    # The session primary key is an authorization/routing key allowed by the
    # contract; participant/result UUIDs and snapshot hashes are not exposed.
    assert reverse("tutor-session-results", args=[session.pk]) in worked.text
    assert str(participant_key) not in worked.text
    assert reverse(
        "tutor-result-delete", args=[session.pk, stored_result.pk]
    ) not in worked.text
    assert snapshot.sha256 not in worked.text
    assert snapshot.sha256[:8] not in worked.text
    unworked = client.get(reverse("tutor-results") + "?vista=sin-participacion")
    assert "Sin respuesta" in unworked.text
    assert "Trabajada" not in unworked.text
    export = client.post(reverse("tutor-session-export", args=[session.pk]), {"format": "json"})
    assert export.status_code == 200
    assert {
        "participant_label",
        "activity_id",
        "snapshot_id",
        "snapshot_sha256",
    }.isdisjoint(export.json()["results"][0])
    assert "participant_label" not in export.text


def test_results_navigation_excludes_future_roadmap_activities():
    snapshot, owner = _snapshot("Actividad uno")
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Camino con futuras",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "Unidad",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "Lección",
                    "activities": [
                        {"id": "a1", "title": "Presentada", "package_snapshot_id": snapshot.pk},
                        {"id": "a2", "title": "Presentada sin respuesta", "package_snapshot_id": snapshot.pk},
                        {"id": "a3", "title": "Nunca lanzada", "package_snapshot_id": snapshot.pk},
                    ],
                }],
            }],
        },
        sha256="futuras",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    progress = GroupRoadmapProgress.for_session(session)
    # ``a1`` is the presented/current activity; ``a2`` and ``a3`` remain future.
    session.close()
    _result(session, uuid.uuid4(), "a1")

    client = tutor_client_for_sessions(session)
    default = client.get(reverse("tutor-session-results", args=[session.pk]))
    assert default.status_code == 200
    assert "Presentada" in default.text
    assert "Presentada sin respuesta" not in default.text
    assert "Nunca lanzada" not in default.text
    assert default.context["has_unworked_activities"] is False

    secondary = client.get(
        reverse("tutor-session-results", args=[session.pk])
        + "?vista=sin-participacion"
    )
    assert secondary.status_code == 200
    assert "<li>Presentada ·" not in secondary.text
    assert "Presentada sin respuesta" not in secondary.text
    assert "Nunca lanzada" not in secondary.text
    assert secondary.context["has_unworked_activities"] is False


def test_legacy_results_without_progress_fail_closed_for_same_snapshot_futures():
    snapshot, owner = _snapshot("Actividad uno legacy")
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Camino legacy con futuras",
        version=1,
        payload={
            "units": [{
                "id": "u1",
                "title": "Unidad",
                "lessons": [{
                    "id": "u1:l1",
                    "title": "Lección",
                    "activities": [
                        {"id": "a1", "title": "Trabajada", "package_snapshot_id": snapshot.pk},
                        {"id": "a2", "title": "Presentada sin respuesta", "package_snapshot_id": snapshot.pk},
                        {"id": "a3", "title": "Nunca lanzada", "package_snapshot_id": snapshot.pk},
                    ],
                }],
            }],
        },
        sha256="legacy-futuras",
        published_by=owner,
    )
    session = ClassroomSession.prepare_from_snapshot(
        snapshot, 1, 1, roadmap_snapshot=roadmap, teacher=owner
    )
    session.close()
    _result(session, uuid.uuid4(), "a1")
    _result(session, uuid.uuid4(), "a2", state="abandoned", responses=[])
    _result(session, uuid.uuid4(), "a3", state="abandoned", responses=[])

    client = tutor_client_for_sessions(session)
    default = client.get(reverse("tutor-session-results", args=[session.pk]))
    assert default.status_code == 200
    assert "Trabajada" in default.text
    assert "Presentada sin respuesta" not in default.text
    assert "Nunca lanzada" not in default.text
    assert default.context["has_unworked_activities"] is False

    secondary = client.get(
        reverse("tutor-session-results", args=[session.pk])
        + "?vista=sin-participacion"
    )
    assert secondary.status_code == 200
    assert "Presentada sin respuesta" not in secondary.text
    assert "Nunca lanzada" not in secondary.text
    assert secondary.context["has_unworked_activities"] is False


def test_results_demo_seed_is_idempotent_and_creates_owned_grouped_sessions():
    User = get_user_model()
    foreign = User.objects.create_user(username="foreign", is_staff=True, is_active=True)
    CurriculumPackage.objects.create(
        title="Fracciones · partes iguales", created_by=foreign, is_demo=True
    )
    call_command("seed_results_demo", username="seed-owner", stdout=None)
    teacher = User.objects.get(username="seed-owner")
    owned_packages = CurriculumPackage.objects.filter(created_by=teacher)
    owned_revisions_before = Revision.objects.filter(
        object_id__in=[str(pk) for pk in owned_packages.values_list("pk", flat=True)]
    ).count()
    groups_before = ClassroomGroup.objects.filter(created_by=teacher).count()
    sessions_before = ClassroomSession.objects.filter(created_by=teacher).count()
    call_command("seed_results_demo", username="seed-owner", stdout=None)
    owned_revisions_after = Revision.objects.filter(
        object_id__in=[str(pk) for pk in owned_packages.values_list("pk", flat=True)]
    ).count()
    assert owned_revisions_after == owned_revisions_before
    groups_after = ClassroomGroup.objects.filter(created_by=teacher).count()
    sessions_after = ClassroomSession.objects.filter(created_by=teacher).count()
    assert groups_before == groups_after
    assert sessions_before == sessions_after
    assert groups_after == 1
    assert sessions_after == 2
    assert ClassroomSession.objects.filter(
        created_by=teacher, classroom_group__created_by=teacher
    ).count() == 2
    assert CurriculumPackage.objects.filter(
        created_by=foreign, title="Fracciones · partes iguales"
    ).exists()


def test_results_demo_namespace_stays_stable_when_foreign_collision_appears_after_first_run():
    User = get_user_model()
    call_command("seed_results_demo", username="stable-seed-owner", stdout=None)
    teacher = User.objects.get(username="stable-seed-owner")
    owned_package_titles = set(
        CurriculumPackage.objects.filter(created_by=teacher).values_list("title", flat=True)
    )
    owned_roadmap = PublishedRoadmapSnapshot.objects.get(published_by=teacher)
    package_payloads = {
        package.title: PublishedPackageSnapshot.objects.get(package=package).payload
        for package in CurriculumPackage.objects.filter(created_by=teacher)
    }
    foreign = User.objects.create_user(username="late-foreign", is_staff=True)
    CurriculumPackage.objects.create(
        title="Fracciones · partes iguales", created_by=foreign, is_demo=True
    )
    PublishedRoadmapSnapshot.objects.create(
        title="Roadmap · Fracciones", version=1, payload={"units": []},
        sha256="foreign", published_by=foreign,
    )
    call_command("seed_results_demo", username="stable-seed-owner", stdout=None)
    assert CurriculumPackage.objects.filter(created_by=teacher).count() == 2
    assert PublishedRoadmapSnapshot.objects.filter(published_by=teacher).count() == 1
    assert ClassroomSession.objects.filter(created_by=teacher).count() == 2
    assert PseudonymousResult.objects.filter(
        result_batch_id__in=ClassroomSession.objects.filter(
            created_by=teacher
        ).values_list("result_batch_id", flat=True)
    ).count() == 2
    assert set(
        CurriculumPackage.objects.filter(created_by=teacher).values_list("title", flat=True)
    ) == owned_package_titles
    assert PublishedRoadmapSnapshot.objects.get(pk=owned_roadmap.pk).payload == owned_roadmap.payload
    for package in CurriculumPackage.objects.filter(created_by=teacher):
        assert package_payloads[package.title] == PublishedPackageSnapshot.objects.get(
            package=package
        ).payload
