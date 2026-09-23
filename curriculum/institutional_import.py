"""Deterministic, review-first import of institutional classroom workbooks."""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata

from openpyxl import load_workbook
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from curriculum.models import ClassroomGroup, School, TeacherAssignment


HEADER_ALIASES = {
    "school": {"escuela", "school"},
    "academic_year": {"ciclo", "ciclo escolar", "academic year"},
    "modality": {"modalidad", "modality"},
    "grade": {"grado", "grade"},
    "group_key": {"grupo", "clave de grupo", "group", "group key"},
    "name": {"salon", "salón", "etiqueta", "nombre", "classroom"},
    "shift": {"turno", "shift"},
    "teacher": {"docente", "maestra", "maestro", "teacher"},
    "subject": {"materia", "subject"},
    "function": {"funcion", "función", "rol", "function"},
}

MODALITY_VALUES = {
    "primaria": School.MODALITY_PRIMARY,
    "primary": School.MODALITY_PRIMARY,
    "secundaria general": School.MODALITY_SECONDARY_GENERAL,
    "secondary general": School.MODALITY_SECONDARY_GENERAL,
    "secundaria tecnica": School.MODALITY_SECONDARY_TECHNICAL,
    "secondary technical": School.MODALITY_SECONDARY_TECHNICAL,
    "telesecundaria": School.MODALITY_TELESECUNDARIA,
}


def _text(value):
    return str(value or "").strip()


def _key(value):
    return " ".join(
        unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode().lower().split()
    )


def _headers(values):
    result = {}
    for index, value in enumerate(values):
        normalized = _key(value)
        for field, aliases in HEADER_ALIASES.items():
            if normalized in {_key(alias) for alias in aliases}:
                result.setdefault(field, index)
    return result


def _cell(values, headers, field):
    index = headers.get(field)
    return _text(values[index]) if index is not None and index < len(values) else ""


def workbook_preview(upload, school, teachers):
    """Parse a workbook without any database write or implicit matching."""

    contents = upload.read()
    if not contents:
        raise ValidationError("El archivo está vacío.")
    try:
        workbook = load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    except Exception as error:  # openpyxl exposes several format exceptions.
        raise ValidationError("Selecciona un archivo .xlsx legible.") from error
    sheet = workbook.active
    values = list(sheet.iter_rows(values_only=True))
    if not values:
        raise ValidationError("El archivo no contiene encabezados.")
    headers = _headers(values[0])
    required = {"academic_year", "modality", "grade", "group_key", "shift", "teacher"}
    missing_headers = sorted(required - set(headers))
    if missing_headers:
        raise ValidationError("Faltan encabezados: " + ", ".join(missing_headers) + ".")

    people = {}
    for teacher in teachers:
        people.setdefault(_key(teacher.get_full_name()), []).append(
            {"id": teacher.pk, "label": teacher.get_full_name().strip() or "Cuenta docente"}
        )
    rows, identities = [], set()
    for row_number, values_row in enumerate(values[1:], start=2):
        if not any(_text(value) for value in values_row):
            continue
        row = {field: _cell(values_row, headers, field) for field in HEADER_ALIASES}
        row["row_number"] = row_number
        row["name"] = row["name"] or row["group_key"]
        row["school"] = row["school"] or school.name
        row["modality"] = MODALITY_VALUES.get(_key(row["modality"]), row["modality"])
        row["candidates"] = people.get(_key(row["teacher"]), [])
        row["status"] = "valid"
        row["reason"] = "Lista para confirmar"
        if _key(row["school"]) != _key(school.name):
            row["status"], row["reason"] = "conflict", "La fila corresponde a otra School"
        elif not all(row[field] for field in ("academic_year", "modality", "grade", "group_key", "shift", "teacher")):
            row["status"], row["reason"] = "missing", "Falta un dato institucional obligatorio"
        elif row["modality"] not in dict(School.MODALITY_CHOICES):
            row["status"], row["reason"] = "invalid", "Modalidad no autorizada"
        else:
            try:
                row["grade"] = int(row["grade"])
                maximum = 6 if row["modality"] == School.MODALITY_PRIMARY else 3
                if not 1 <= row["grade"] <= maximum:
                    raise ValueError
            except (TypeError, ValueError):
                row["status"], row["reason"] = "invalid", "El grado no corresponde a la modalidad"
            identity = (row["academic_year"], row["modality"], row["grade"], row["group_key"], row["shift"])
            if identity in identities and row["status"] == "valid":
                row["status"], row["reason"] = "duplicate", "Identidad de salón repetida en el archivo"
            identities.add(identity)
            if row["status"] == "valid" and not row["candidates"]:
                row["status"], row["reason"] = "conflict", "No hay una cuenta docente activa con coincidencia exacta"
            elif row["status"] == "valid" and len(row["candidates"]) > 1:
                row["status"], row["reason"] = "ambiguous", "Hay homónimos: Dirección debe confirmar una cuenta"
        rows.append(row)
    return {"sha256": hashlib.sha256(contents).hexdigest(), "rows": rows}


def apply_preview(preview, school, actor, selected_teachers):
    """Apply an already-reviewed preview in one transaction; repetitions are no-ops."""

    created_groups = changed_groups = created_assignments = 0
    for row in preview["rows"]:
        if row["status"] not in {"valid", "ambiguous"}:
            raise ValidationError(f"Fila {row['row_number']}: {row['reason']}.")
        candidates = {candidate["id"] for candidate in row["candidates"]}
        teacher_id = selected_teachers.get(str(row["row_number"]))
        if row["status"] == "valid" and len(candidates) == 1:
            teacher_id = next(iter(candidates))
        if teacher_id not in candidates:
            raise ValidationError(f"Fila {row['row_number']}: confirma una cuenta docente para el homónimo.")
        group, group_created = ClassroomGroup.objects.get_or_create(
            school=school,
            academic_year=row["academic_year"], modality=row["modality"],
            grade=row["grade"], group_key=row["group_key"], shift=row["shift"],
            defaults={"name": row["name"]},
        )
        if group_created:
            created_groups += 1
        elif group.name != row["name"]:
            group.name = row["name"]
            group.save(update_fields=["name"])
            changed_groups += 1
        duplicate = TeacherAssignment.objects.filter(
            school=school, classroom_group=group, teacher_id=teacher_id,
            function=row["function"], subject=row["subject"], status=TeacherAssignment.STATUS_ACTIVE,
        ).exists()
        if not duplicate:
            TeacherAssignment.create_assignment(
                teacher=get_user_model().objects.get(pk=teacher_id),
                classroom_group=group, actor=actor, source="excel",
                function=row["function"], subject=row["subject"],
            )
            created_assignments += 1
    return {"created_groups": created_groups, "changed_groups": changed_groups, "created_assignments": created_assignments}
