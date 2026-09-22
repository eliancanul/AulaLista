"""Level B support requests stay scoped and non-nominal."""

import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import ClassroomGroup, School, SupportRequest, TeacherAssignment  # noqa: E402


pytestmark = pytest.mark.django_db


def user(username):
    return get_user_model().objects.create_user(username=username, is_staff=True)


def scope():
    platform = get_user_model().objects.create_superuser("platform-support", "support@example.test", "test")
    director, teacher = user("director-support"), user("teacher-support")
    school = School.provision(name="Escuela apoyo", director=director, actor=platform)
    group = ClassroomGroup.objects.create(school=school, name="1 A", academic_year="2026-2027", modality="primary", grade=1, group_key="A", shift="matutino")
    TeacherAssignment.create_assignment(teacher=teacher, classroom_group=group, actor=director)
    return director, teacher, group


def test_teacher_creates_non_nominal_support_request_and_director_closes_it():
    director, teacher, group = scope()
    client = Client(); client.force_login(teacher)
    response = client.post(reverse("tutor-group-support-request", args=[group.pk]), {
        "category": "family_communication", "description": "Solicitar aviso general sobre el horario.", "target_date": "2026-09-10",
    })
    assert response.status_code == 302
    request = SupportRequest.objects.get()
    assert request.school == group.school and request.status == SupportRequest.STATUS_PENDING
    client.force_login(director)
    assert "Solicitar aviso general sobre el horario." in client.get(reverse("director-dashboard")).text
    response = client.post(reverse("director-support-request-update", args=[request.pk]), {"status": "resolved", "responsible_id": director.pk})
    request.refresh_from_db()
    assert response.status_code == 302 and request.closed_at is not None and request.responsible == director


def test_teacher_cannot_request_support_outside_an_active_assignment():
    _director, teacher, group = scope()
    foreign = ClassroomGroup.objects.create(school=group.school, name="1 B", academic_year="2026-2027", modality="primary", grade=1, group_key="B", shift="matutino")
    client = Client(); client.force_login(teacher)
    response = client.post(reverse("tutor-group-support-request", args=[foreign.pk]), {"category": "resources", "description": "Materiales", "target_date": "2026-09-10"})
    assert response.status_code == 404
