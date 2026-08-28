"""Issue #85: teacher curriculum progress and student roadmap progress stay separate."""

import hashlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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


def _snapshot(title, version=1, question_count=1, owner=None):
    publisher = owner or get_user_model().objects.create_user(
        username=f"publisher-{title}-{version}"
    )
    package = CurriculumPackage.objects.create(title=title, created_by=publisher)
    revision = package.save_revision(user=publisher)
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
    if question_count > 1:
        payload["questions"] = [
            {
                **payload["questions"][0],
                "value": {
                    **payload["questions"][0]["value"],
                    "prompt": f"¿Cuál respuesta es correcta ({index})?",
                },
            }
            for index in range(question_count)
        ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=version,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        source_revision=revision,
        published_by=publisher,
    )


def _roadmap(title="Camino", version=1, package_snapshot_id=None, owner=None):
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
    return PublishedRoadmapSnapshot.objects.create(
        title=title,
        version=version,
        payload=payload,
        sha256="the-model-computes-this",
        published_by=owner or get_user_model().objects.create_user(
            username=f"roadmap-publisher-{title}-{version}"
        ),
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
    teacher = tutor_client()
    teacher_user = get_user_model().objects.get(pk=teacher.session["_auth_user_id"])
    package = _snapshot("Tema trabajado", owner=teacher_user)
    roadmap = _roadmap(package_snapshot_id=package.pk, owner=teacher_user)

    response = teacher.post(
        reverse("tutor-roadmap-progress", args=[roadmap.pk]),
        {"node_id": "leccion-1", "status": "worked"},
    )

    assert response.status_code == 302
    progress = CurriculumProgress.objects.get(roadmap_snapshot=roadmap, node_id="leccion-1")
    assert progress.status == CurriculumProgress.STATUS_WORKED
    assert not StudentRoadmapProgress.objects.exists()


def test_student_completion_changes_only_the_pseudonymous_route():
    teacher = tutor_client(username="teacher-separation")
    teacher_user = get_user_model().objects.get(username="teacher-separation")
    package = _snapshot("Separación", owner=teacher_user)
    roadmap = _roadmap(package_snapshot_id=package.pk, owner=teacher_user)
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
        {"option_position": 1, "activity_id": "actividad-1"},
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

    first.post(reverse("student-question-answer", args=[session.pk, 0]), {"option_position": 1, "activity_id": "actividad-1"})

    progress = list(StudentRoadmapProgress.objects.order_by("created_at", "id"))
    assert len(progress) == 2
    assert progress[0].student_key != progress[1].student_key
    assert progress[0].completed_activity_ids == ["actividad-1"]
    assert progress[1].completed_activity_ids == []


def test_roadmap_traverses_three_activities_backed_by_different_package_snapshots():
    packages = [_snapshot(f"Actividad de ruta {index}") for index in range(1, 4)]
    payload = {
        "title": "Ruta de tres actividades",
        "units": [
            {
                "id": f"unidad-{index}",
                "title": f"Unidad {index}",
                "lessons": [
                    {
                        "id": f"unidad-{index}:leccion-1",
                        "title": "Lección",
                        "activities": [
                            {
                                "id": f"u{index}:l0:a0",
                                "title": package.payload["title"],
                                "package_snapshot_id": package.pk,
                            }
                        ],
                    }
                ],
            }
            for index, package in enumerate(packages)
        ],
    }
    roadmap = PublishedRoadmapSnapshot.objects.create(
        title="Ruta de tres actividades",
        version=1,
        payload=payload,
        sha256="the-model-computes-this",
        published_by=get_user_model().objects.create_user(username="roadmap-three-publisher"),
    )
    session = _session(packages[0], roadmap)
    client = Client()
    assignment = session.device_assignments.get()
    assert _start(client, session, assignment).status_code == 302

    progress = StudentRoadmapProgress.objects.get()
    assert [item["state"] for item in progress.roadmap_states()] == [
        "ACTUAL",
        "DISPONIBLE",
        "BLOQUEADA",
    ]
    for index, package in enumerate(packages):
        response = client.post(
            reverse("student-question-answer", args=[session.pk, 0]),
            {"option_position": 1, "activity_id": f"u{index}:l0:a0"},
        )
        assert response.status_code == 200
        progress.refresh_from_db()
        assert progress.completed_activity_ids == [
            f"u{completed_index}:l0:a0" for completed_index in range(index + 1)
        ]
        if index < len(packages) - 1:
            states = [item["state"] for item in progress.roadmap_states()]
            assert states[index + 1] == "ACTUAL"
            if index + 2 < len(packages):
                assert states[index + 2] == "DISPONIBLE"


def test_teacher_can_publish_roadmap_and_prepare_session_from_it():
    teacher = tutor_client(username="roadmap-publisher-teacher")
    teacher_user = get_user_model().objects.get(username="roadmap-publisher-teacher")
    first = _snapshot("Publicable uno", owner=teacher_user)
    second = _snapshot("Publicable dos", owner=teacher_user)

    response = teacher.post(
        reverse("tutor-roadmaps"),
        {
            "title": "Camino publicado por maestra",
            "package_snapshot_ids": [str(first.pk), str(second.pk)],
        },
    )

    assert response.status_code == 302
    roadmap = PublishedRoadmapSnapshot.objects.get(title="Camino publicado por maestra")
    expected_hash = hashlib.sha256(
        json.dumps(roadmap.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert roadmap.sha256 == expected_hash
    assert str(roadmap.pk) in teacher.get(reverse("tutor-roadmaps")).text

    prepared = teacher.post(
        reverse("tutor-session-prepare", args=[first.pk]),
        {"student_count": "1", "device_count": "1", "roadmap_snapshot_id": roadmap.pk},
    )
    assert prepared.status_code == 302
    session = ClassroomSession.objects.order_by("-id").first()
    assert session.roadmap_snapshot_id == roadmap.pk


def test_reassigning_session_roadmap_snapshot_is_rejected():
    package = _snapshot("Roadmap fijo")
    first = _roadmap("Camino fijo uno", package_snapshot_id=package.pk)
    second = _roadmap("Camino fijo dos", version=2, package_snapshot_id=package.pk)
    session = _session(package, first)
    session.roadmap_snapshot = second
    with pytest.raises(ValidationError, match="fijado"):
        session.save()


def test_student_cannot_reach_teacher_roadmap_progress():
    package = _snapshot("Frontera docente")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    anonymous = Client()
    assert anonymous.get(reverse("tutor-roadmap-progress", args=[roadmap.pk])).status_code in {302, 403}
    student = get_user_model().objects.create_user(username="student-not-teacher")
    student_client = Client()
    student_client.force_login(student)
    assert student_client.get(reverse("tutor-roadmap-progress", args=[roadmap.pk])).status_code == 403


def test_closing_session_deletes_student_roadmap_progress():
    package = _snapshot("Borrado temporal")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    session = _session(package, roadmap)
    client = Client()
    _start(client, session, session.device_assignments.get())
    assert StudentRoadmapProgress.objects.exists()

    session.close()

    assert not StudentRoadmapProgress.objects.exists()


def test_published_roadmap_snapshot_is_immutable():
    package = _snapshot("Roadmap inmutable")
    roadmap = _roadmap(package_snapshot_id=package.pk)
    roadmap.title = "alterado"
    with pytest.raises(ValidationError, match="inmutable"):
        roadmap.save()
    with pytest.raises(ValidationError, match="inmutable"):
        roadmap.delete()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PublishedRoadmapSnapshot.objects.filter(pk=roadmap.pk).update(title="alterado")


def test_curriculum_progress_rejects_node_outside_roadmap():
    teacher = get_user_model().objects.create_user(username="node-validator", is_staff=True)
    package = _snapshot("Nodo validado", owner=teacher)
    roadmap = _roadmap(package_snapshot_id=package.pk, owner=teacher)
    with pytest.raises(ValidationError, match="pertenece"):
        CurriculumProgress.confirm(
            roadmap_snapshot=roadmap,
            node_id="no-existe",
            status=CurriculumProgress.STATUS_WORKED,
            teacher=teacher,
        )


def test_correct_answers_survive_ephemeral_summary_eviction():
    package = _snapshot("Persistencia de respuestas", question_count=2)
    roadmap = _roadmap(package_snapshot_id=package.pk)
    session = _session(package, roadmap)
    client = Client()
    _start(client, session, session.device_assignments.get())

    client.post(
        reverse("student-question-answer", args=[session.pk, 0]),
        {"option_position": 1, "activity_id": "actividad-1"},
    )
    from django.core.cache import cache
    from curriculum.ephemeral import ephemeral_session_summary_key
    cache.delete(ephemeral_session_summary_key(session.pk))
    client.post(
        reverse("student-question-answer", args=[session.pk, 1]),
        {"option_position": 1, "activity_id": "actividad-1"},
    )

    progress = StudentRoadmapProgress.objects.get()
    assert progress.completed_activity_ids == ["actividad-1"]


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
