"""Issue #84: the teacher UI is one protected, navigable classroom workflow."""

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
    ClassroomSession,
    CurriculumPackage,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    PseudonymousResult,
)
from helpers import tutor_client  # noqa: E402

pytestmark = pytest.mark.django_db


def published_snapshot(title="Actividad UI"):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Practicar una idea.",
        "micro_lesson": "Una explicación breve.",
        "questions": [],
    }
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


def published_roadmap(snapshot):
    return PublishedRoadmapSnapshot.objects.create(
        title="Camino del grupo",
        version=1,
        payload={
            "title": "Camino del grupo",
            "units": [{
                "id": "unit-1",
                "title": "Unidad 1",
                "lessons": [{
                    "id": "lesson-1",
                    "title": "Lección 1",
                    "activities": [{
                        "id": "activity-1",
                        "title": snapshot.payload["title"],
                        "package_snapshot_id": snapshot.pk,
                    }],
                }],
            }],
        },
        sha256="ignored-by-model",
        published_by=get_user_model().objects.create_user(username="roadmap-editor"),
    )


def test_new_teacher_surfaces_require_staff_login():
    routes = [
        reverse("tutor-home"),
        reverse("tutor-curriculum"),
        reverse("tutor-results"),
        reverse("tutor-package-detail", args=[1]),
        reverse("tutor-session-results", args=[1]),
    ]
    for route in routes:
        response = Client().get(route)
        assert response.status_code == 302
        assert "/cms/login/" in response["Location"]

    user = get_user_model().objects.create_user(username="not-staff")
    client = Client()
    client.force_login(user)
    assert client.get(reverse("tutor-results")).status_code == 403


def test_teacher_navigation_reaches_published_activity_and_prepare():
    snapshot = published_snapshot()
    roadmap = published_roadmap(snapshot)
    client = tutor_client()

    home = client.get(reverse("tutor-home"))
    assert home.status_code == 200
    assert reverse("tutor-roadmaps") in home.text
    assert reverse("tutor-curriculum") in home.text
    assert reverse("tutor-results") in home.text

    curriculum = client.get(reverse("tutor-curriculum"))
    assert "Actividad UI" in curriculum.text
    activity = client.get(reverse("tutor-package-detail", args=[snapshot.pk]))
    assert activity.status_code == 200
    assert "Practicar una idea." in activity.text
    assert reverse("tutor-session-prepare", args=[snapshot.pk]) in activity.text

    progress = client.get(reverse("tutor-roadmap-progress", args=[roadmap.pk]))
    assert progress.status_code == 200
    assert "Ver actividad publicada" in progress.text
    assert 'name="node_id" value="activity-1"' in progress.text
    assert reverse("tutor-package-detail", args=[snapshot.pk]) in progress.text


def test_group_results_show_required_metrics_and_privacy_empty_state():
    snapshot = published_snapshot("Actividad con resultados")
    session = ClassroomSession.prepare_from_snapshot(snapshot, 2, 1)
    session.close()
    PseudonymousResult.objects.create(
        result_batch_id=session.result_batch_id,
        participant_key=uuid.uuid4(),
        snapshot_id=snapshot.pk,
        snapshot_version=snapshot.version,
        snapshot_sha256=snapshot.sha256,
        state=PseudonymousResult.STATE_COMPLETED,
        duration_seconds=40,
        responses=[],
        score=1,
        help_requests=[{"kind": "hint"}],
        technical_errors=[],
    )
    PseudonymousResult.objects.create(
        result_batch_id=session.result_batch_id,
        participant_key=uuid.uuid4(),
        snapshot_id=snapshot.pk,
        snapshot_version=snapshot.version,
        snapshot_sha256=snapshot.sha256,
        state=PseudonymousResult.STATE_ABANDONED,
        duration_seconds=20,
        responses=[],
        score=0,
        help_requests=[],
        technical_errors=[{"message": "local"}],
    )

    client = tutor_client()
    listing = client.get(reverse("tutor-results"))
    detail = client.get(reverse("tutor-session-results", args=[session.pk]))
    for response in (listing, detail):
        assert response.status_code == 200
        assert "2 participantes" in response.text
        assert "1 actividades completadas" in response.text
        assert "60" in response.text
        assert "Luna" not in response.text
        assert str(PseudonymousResult.objects.first().id) not in response.text
    assert "Registro individual seudónimo" in detail.text
    assert "versión 1" in detail.text
    assert snapshot.sha256[:8] in detail.text


def test_empty_group_results_are_explicit():
    snapshot = published_snapshot("Sin resultados")
    session = ClassroomSession.prepare_from_snapshot(snapshot, 1, 1)
    session.close()
    response = tutor_client().get(reverse("tutor-session-results", args=[session.pk]))
    assert response.status_code == 200
    assert "no tiene resultados agregados" in response.text
    assert "Registro individual seudónimo" in response.text
