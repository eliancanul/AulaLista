"""Issue #103: review-first XLSX import stays scoped, explicit, and idempotent."""

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from openpyxl import Workbook

from curriculum.institutional_import import apply_preview, workbook_preview
from curriculum.models import ClassroomGroup, InstitutionalAuditEvent, School, TeacherAssignment


pytestmark = pytest.mark.django_db


def user(name, full_name):
    account = get_user_model().objects.create_user(username=name, is_staff=True)
    account.first_name, account.last_name = full_name.split(" ", 1)
    account.save(update_fields=["first_name", "last_name"])
    return account


def workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(["Escuela", "Ciclo escolar", "Modalidad", "Grado", "Grupo", "Turno", "Docente", "Materia"])
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    output.name = "salones.xlsx"
    output.seek(0)
    return output


def setup_school():
    platform = get_user_model().objects.create_superuser("platform", "platform@example.test", "test")
    director = user("director", "Dirección Uno")
    school = School.provision(name="Escuela Uno", director=director, actor=platform)
    return school, director


def test_preview_does_not_write_and_stops_homonyms_and_foreign_school():
    school, _ = setup_school()
    first, second = user("ana-1", "Ana López"), user("ana-2", "Ana López")
    source = workbook([
        [school.name, "2026-2027", "Primaria", 1, "A", "Matutino", "Ana López", ""],
        ["Escuela Ajena", "2026-2027", "Primaria", 1, "B", "Matutino", "Ana López", ""],
    ])

    preview = workbook_preview(source, school, [first, second])

    assert [row["status"] for row in preview["rows"]] == ["ambiguous", "conflict"]
    assert not ClassroomGroup.objects.exists()
    assert not TeacherAssignment.objects.exists()


def test_confirmed_import_is_atomic_idempotent_and_auditable():
    school, director = setup_school()
    teacher = user("ana", "Ana López")
    preview = workbook_preview(workbook([
        [school.name, "2026-2027", "Primaria", 1, "A", "Matutino", "Ana López", "Matemáticas"],
    ]), school, [teacher])

    first = apply_preview(preview, school, director, {})
    second = apply_preview(preview, school, director, {})

    assert first == {"created_groups": 1, "changed_groups": 0, "created_assignments": 1}
    assert second == {"created_groups": 0, "changed_groups": 0, "created_assignments": 0}
    assert ClassroomGroup.objects.count() == TeacherAssignment.objects.count() == 1
    with pytest.raises(ValidationError, match="Fila"):
        apply_preview({"rows": [dict(preview["rows"][0], status="conflict", reason="Otra School")]}, school, director, {})
    assert InstitutionalAuditEvent.objects.filter(action="assignment_created", source="excel").exists()
