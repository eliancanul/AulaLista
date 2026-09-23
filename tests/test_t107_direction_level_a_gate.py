"""Reproducible synthetic gate for issue #107; it makes no field-effect claim."""

import io

import pytest
from django.contrib.auth import get_user_model
from openpyxl import Workbook

from curriculum.institutional_import import apply_preview, workbook_preview
from curriculum.models import ClassroomGroup, School, TeacherAssignment


pytestmark = pytest.mark.django_db


def test_twenty_synthetic_classrooms_import_without_collision_or_implicit_identity():
    User = get_user_model()
    platform = User.objects.create_superuser("platform-gate", "gate@example.test", "test")
    director = User.objects.create_user("director-gate", is_staff=True)
    school = School.provision(name="Escuela sintética", director=director, actor=platform)
    teachers = []
    for number in range(20):
        teacher = User.objects.create_user(f"teacher-gate-{number}", is_staff=True, first_name="Docente", last_name=f"{number:02d}")
        teachers.append(teacher)
    book = Workbook()
    sheet = book.active
    sheet.append(["Escuela", "Ciclo escolar", "Modalidad", "Grado", "Grupo", "Turno", "Docente"])
    for number, teacher in enumerate(teachers, start=1):
        sheet.append([school.name, "2026-2027", "Primaria", (number - 1) % 6 + 1, f"G{number:02d}", "Matutino", teacher.get_full_name()])
    upload = io.BytesIO()
    book.save(upload)
    upload.name = "gate.xlsx"
    upload.seek(0)

    preview = workbook_preview(upload, school, teachers)
    assert len(preview["rows"]) == 20
    assert {row["status"] for row in preview["rows"]} == {"valid"}
    result = apply_preview(preview, school, director, {})

    assert result == {"created_groups": 20, "changed_groups": 0, "created_assignments": 20}
    assert ClassroomGroup.objects.filter(school=school).count() == 20
    assert TeacherAssignment.objects.filter(school=school).count() == 20
    assert all(group.school_id == school.pk for group in ClassroomGroup.objects.all())
