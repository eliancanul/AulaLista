"""Issue #85: teacher curriculum progress and student roadmap progress stay separate."""

import hashlib
import json
import os

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
    CurriculumProgress,
    PublishedPackageSnapshot,
    PublishedRoadmapSnapshot,
    StudentRoadmapProgress,
)
from helpers import tutor_client  # noqa: E402


pytestmark = pytest.mark.django_db


def _snapshot(title, version=1):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Practicar una respuesta.",
        "micro_lesson": "Una microlección fijada.",
        "questions": [
            {
                "type": "reactivo",
                "value": {
                    "prompt": "¿Cuál respuesta es correcta?",
                    "options": [
                        {"position": 1, "text": "Sí", "expected": True, "feedback": "Correcto."},
                        {"position": 2, "text": "No", "expected": False, "feedback": "Inténtalo de nuevo."},
                    ],
                    "hints": ["Busca la afirmación correcta."],
                },
            }
        ],
        "final_explanation": "Explicación fijada.",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=version,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(username=f"publisher-{title}-{version}"),
    )


def _roadmap(title="Camino", version=1, package_snapshot_id=None):
    activity = {"id": f"actividad-{version}", "title": "Practicar una respuesta"}
    if package_snapshot_id is not None:
        activity["package_snapshot_id"] = package_snapshot_id
    payload = {
        "title": title,
        "units": [
            {
                "id": "unidad-1",
                "title": "Unidad uno",
                "lessons": [
                    {
                        "id": "leccion-1",
                        "title": "Lección uno",
                        "activities": [activity],
                    }
                ],
            }
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedRoadmapSnapshot.objects.create(
        title=title,
        version=version,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        published_by=get_user_model().objects.create_user(username=f"roadmap-publisher-{title}-{version}"),
    )


def _session(package, roadmap, student_count=1, device_count=1):
    session = ClassroomSession.prepare_from_snapshot(
        package,
        student_count,
        device_count,
        roadmap_snapshot=roadmap,
    )
    session.confirm()
    return session


def _start(client, session, assignment, name="Luna"):
    return client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": name},
    )


def test_teacher_marks_topic_worked_without_student_activity_completion():
    package = _snapshot("Tema trabajado")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    teacher = tutor_client()

    response = teacher.post(
        reverse("tutor-roadmap-progress", args=[roadmap.pk]),
        {"node_id": "leccion-1", "status": "worked"},
    )

    assert response.status_code == 302
    progress = CurriculumProgress.objects.get(roadmap_snapshot=roadmap, node_id="leccion-1")
    assert progress.status == CurriculumProgress.STATUS_WORKED
    assert not StudentRoadmapProgress.objects.exists()


def test_student_completion_changes_only_the_pseudonymous_route():
    package = _snapshot("Separación")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    teacher = tutor_client(username="teacher-separation")
    teacher_user = get_user_model().objects.get(username="teacher-separation")
    CurriculumProgress.confirm(
        roadmap_snapshot=roadmap,
        node_id="leccion-1",
        status=CurriculumProgress.STATUS_CURRENT,
        teacher=teacher_user,
    )
    session = _session(package, roadmap)
    client = Client()
    assignment = session.device_assignments.get()
    assert _start(client, session, assignment).status_code == 302

    response = client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1},
    )

    student_progress = StudentRoadmapProgress.objects.get()
    teacher_progress = CurriculumProgress.objects.get()
    assert response.status_code == 200
    assert student_progress.completed_activity_ids == ["actividad-1"]
    assert teacher_progress.status == CurriculumProgress.STATUS_CURRENT
    assert "COMPLETADA" in response.text


def test_two_students_have_independent_pseudonymous_routes():
    package = _snapshot("Recorridos independientes")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    session = _session(package, roadmap, student_count=2, device_count=2)
    assignments = list(session.device_assignments.order_by("id"))
    first = Client()
    second = Client()
    assert _start(first, session, assignments[0], "Luna").status_code == 302
    assert _start(second, session, assignments[1], "Luna").status_code == 302

    first.post(reverse("student-question-answer", args=[session.pk, 0]), {"option_position": 1})

    progress = list(StudentRoadmapProgress.objects.order_by("created_at", "id"))
    assert len(progress) == 2
    assert progress[0].student_key != progress[1].student_key
    assert progress[0].completed_activity_ids == ["actividad-1"]
    assert progress[1].completed_activity_ids == []


def test_active_session_keeps_both_original_snapshots_after_correction():
    package = _snapshot("Corrección uno", version=1)
    roadmap_one = _roadmap("Camino uno", version=1, package_snapshot_id=package.pk)
    session = _session(package, roadmap_one)
    client = Client()
    assignment = session.device_assignments.get()
    assert _start(client, session, assignment).status_code == 302

    corrected_package = _snapshot("Corrección dos", version=2)
    roadmap_two = _roadmap("Camino dos", version=2, package_snapshot_id=corrected_package.pk)

    session.refresh_from_db()
    assert session.snapshot_id == package.pk
    assert session.roadmap_snapshot_id == roadmap_one.pk
    activity = client.get(reverse("student-activity", args=[session.pk]))
    assert "Corrección uno" in activity.text
    assert "Corrección dos" not in activity.text
    assert roadmap_two.pk != session.roadmap_snapshot_id
