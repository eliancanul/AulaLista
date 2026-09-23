"""Issues #95/#104: institutional HTTP authorization and safe projections."""

import csv
import hashlib
import io
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    ClassroomGroup,
    ClassroomSession,
    CurriculumPackage,
    InstitutionalAuditEvent,
    PublishedPackageSnapshot,
    School,
    TeacherAssignment,
)


pytestmark = pytest.mark.django_db


def user(username, *, name=None, staff=True, active=True, superuser=False):
    account = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@private.invalid",
        is_staff=staff,
        is_active=active,
        is_superuser=superuser,
    )
    if name:
        first, _, last = name.partition(" ")
        account.first_name = first
        account.last_name = last
        account.save(update_fields=["first_name", "last_name"])
    return account


def school_with_director(name="Escuela Norte"):
    director = user(f"director-{School.objects.count()}", name="Dirección Norte")
    if School.objects.exists():
        # Isolation fixture for #104. Production provisioning remains singleton;
        # this deliberately unreachable second scope proves fail-closed queries.
        school = School(name=name, director=director, is_configured=False)
        School.objects.bulk_create([school])
    else:
        platform = user(f"provisioner-{School.objects.count()}", superuser=True)
        school = School.provision(name=name, director=director, actor=platform)
    return school, director


def classroom(school, name="1 A"):
    return ClassroomGroup.objects.create(
        school=school,
        name=name,
        academic_year="2026-2027",
        modality=School.MODALITY_PRIMARY,
        grade=1,
        group_key=name,
        shift="matutino",
    )


def assign(school, group, teacher, director, **kwargs):
    return TeacherAssignment.create_assignment(
        teacher=teacher,
        classroom_group=group,
        actor=director,
        source="manual",
        **kwargs,
    )


def published_snapshot(owner, title="Actividad institucional"):
    package = CurriculumPackage.objects.create(title=title, created_by=owner)
    revision = package.save_revision(user=owner)
    payload = {"title": title, "objective": "Objetivo", "questions": []}
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
    )


def test_school_director_is_the_only_director_authority_source():
    school, director = school_with_director()
    legacy = user("legacy-director", name="Rol heredado")
    legacy.groups.add(Group.objects.get(name="Director"))
    platform = user("platform-admin", superuser=True)

    assert Client().get(reverse("director-dashboard")).status_code == 302
    for account in (legacy, platform):
        client = Client()
        client.force_login(account)
        assert client.get(reverse("director-dashboard")).status_code == 403

    client = Client()
    client.force_login(director)
    response = client.get(reverse("director-dashboard"))
    assert response.status_code == 200
    assert school.name in response.text


def test_director_dashboard_is_school_scoped_and_candidates_do_not_leak_accounts():
    school, director = school_with_director()
    group = classroom(school, "1 A")
    local_unassigned = user("local-candidate", name="María López")
    local_assigned = user("local-assigned", name="María López")
    assign(school, group, local_assigned, director, subject="Matemáticas")

    foreign_school, foreign_director = school_with_director("Escuela Sur")
    foreign_group = classroom(foreign_school, "1 A")
    foreign_teacher = user("foreign-teacher", name="María López")
    assign(foreign_school, foreign_group, foreign_teacher, foreign_director)
    inactive = user("inactive-teacher", name="Docente Inactiva", active=False)
    platform = user("technical-platform", name="Administrador Técnico", superuser=True)

    client = Client()
    client.force_login(director)
    response = client.get(reverse("director-dashboard"))
    body = response.text

    assert response.status_code == 200
    assert "Escuela Norte" in body
    assert "Escuela Sur" not in body
    assert "local-candidate" not in body
    assert local_unassigned.email not in body
    assert "foreign-teacher" not in body
    assert foreign_teacher.email not in body
    assert "Docente Inactiva" not in body
    assert "Administrador Técnico" not in body


def test_assignment_actions_preserve_zero_one_many_and_are_school_scoped_post_only():
    school, director = school_with_director()
    group = classroom(school)
    first = user("first-teacher", name="Primera Docente")
    second = user("second-teacher", name="Segunda Docente")

    client = Client()
    client.force_login(director)
    url = reverse("director-group-assign", args=[group.pk])
    first_response = client.post(
        url,
        {"teacher": first.pk, "function": "Titular", "subject": ""},
    )
    second_response = client.post(
        url,
        {"teacher": second.pk, "function": "Especialista", "subject": "Artes"},
    )

    assert first_response.status_code == second_response.status_code == 302
    active = TeacherAssignment.objects.filter(
        school=school,
        classroom_group=group,
        status=TeacherAssignment.STATUS_ACTIVE,
    )
    assert active.count() == 2
    assert active.get(teacher=first).function == "Titular"
    assert active.get(teacher=second).subject == "Artes"
    assert client.get(url).status_code == 405

    foreign_school, foreign_director = school_with_director("Escuela Sur")
    foreign_group = classroom(foreign_school, "1 B")
    assert client.post(
        reverse("director-group-assign", args=[foreign_group.pk]),
        {"teacher": first.pk},
    ).status_code == 404


def test_teacher_assignment_grants_and_revocation_removes_group_session_results_export_and_purge():
    school, director = school_with_director()
    group = classroom(school)
    teacher = user("assigned-teacher", name="Docente Adscrita")
    assignment = assign(school, group, teacher, director)
    snapshot = published_snapshot(teacher)
    session = ClassroomSession.objects.create(
        snapshot=snapshot,
        school=school,
        classroom_group=group,
        created_by=teacher,
        status=ClassroomSession.STATUS_ACTIVE,
    )
    session = session.close()

    client = Client()
    client.force_login(teacher)
    allowed = [
        ("get", reverse("tutor-group-results", args=[group.pk]), None),
        ("get", reverse("tutor-session-results", args=[session.pk]), None),
        ("post", reverse("tutor-session-export", args=[session.pk]), {"format": "json"}),
        ("post", reverse("tutor-group-close-year", args=[group.pk]), {"confirm": "CERRAR"}),
    ]
    for method, url, data in allowed:
        assert getattr(client, method)(url, data or {}).status_code in {200, 302}

    assignment.end(actor=director, source="manual")
    for method, url, data in allowed:
        assert getattr(client, method)(url, data or {}).status_code == 404


def test_legacy_owner_unresolved_session_remains_explicitly_fail_closed_compatible():
    teacher = user("legacy-staff", name="Personal Histórico")
    snapshot = published_snapshot(teacher)
    marked = ClassroomSession(
        snapshot=snapshot,
        created_by=None,
        legacy_owner_unresolved=True,
        status=ClassroomSession.STATUS_CLOSED,
    )
    unmarked = ClassroomSession(
        snapshot=snapshot,
        created_by=None,
        legacy_owner_unresolved=False,
        status=ClassroomSession.STATUS_CLOSED,
    )
    # These are historical rows, not new operational sessions: bypass the
    # runtime closure receipt guard exactly as a pre-existing migration does.
    ClassroomSession.objects.bulk_create([marked, unmarked])
    client = Client()
    client.force_login(teacher)

    assert client.get(reverse("tutor-session-results", args=[marked.pk])).status_code == 200
    assert client.get(reverse("tutor-session-results", args=[unmarked.pk])).status_code == 404


def test_institutional_exports_are_stable_formula_safe_and_identifier_free():
    school, director = school_with_director("=SUM(A1:A2)")
    group = classroom(school, "+1 A")
    teacher = user("secret-username", name="@Docente Visible")
    assignment = assign(
        school,
        group,
        teacher,
        director,
        function="-Titular",
        subject="=Matemáticas",
    )
    InstitutionalAuditEvent.record(
        school=school,
        actor=director,
        action="assignment_reviewed",
        object_type="TeacherAssignment",
        object_id=assignment.pk,
        classroom_group=group,
        previous_state={"status": "candidate", "teacher_id": teacher.pk},
        new_state={"status": "active", "teacher_id": teacher.pk},
        source="manual",
    )
    client = Client()
    client.force_login(director)
    url = reverse("director-export")

    assert client.get(url).status_code == 405
    json_first = client.post(url, {"format": "json"})
    json_second = client.post(url, {"format": "json"})
    csv_first = client.post(url, {"format": "csv"})
    csv_second = client.post(url, {"format": "csv"})
    assert json_first.status_code == csv_first.status_code == 200
    assert json_first.content == json_second.content
    assert csv_first.content == csv_second.content

    combined = json_first.text + csv_first.text
    forbidden = [
        "secret-username",
        teacher.email,
        "teacher_id",
        "group_id",
        "object_id",
        "participant_key",
    ]
    assert not [value for value in forbidden if value and value in combined]
    payload = json_first.json()
    assert payload["audit"][0]["previous"] == "Estado: candidate; docente: @Docente Visible"
    assert payload["audit"][0]["new"] == "Estado: active; docente: @Docente Visible"
    assert payload["audit"][0]["source"] == "manual"

    rows = list(csv.reader(io.StringIO(csv_first.text)))
    dangerous = ("=", "+", "-", "@")
    assert all(
        not cell.lstrip().startswith(dangerous)
        for row in rows[1:]
        for cell in row
        if cell
    )


def test_director_handoff_requires_platform_administrator_and_uses_core_atomic_api(monkeypatch):
    school, old_director = school_with_director()
    new_director = user("new-director", name="Dirección Nueva")
    ordinary_staff = user("ordinary-staff", name="Personal Ordinario")
    platform = user("platform", name="Administrador", superuser=True)
    called = []
    original = School.handoff_director

    def observed(self, new_director, *, actor, source="manual"):
        called.append((self.pk, new_director.pk, actor.pk, source))
        return original(self, new_director, actor=actor, source=source)

    monkeypatch.setattr(School, "handoff_director", observed)
    url = reverse("platform-director-handoff")
    for account in (old_director, ordinary_staff):
        client = Client()
        client.force_login(account)
        assert client.post(url, {"director": new_director.pk, "confirm": "CAMBIAR"}).status_code == 403

    client = Client()
    client.force_login(platform)
    assert client.get(url).status_code == 405
    response = client.post(url, {"director": new_director.pk, "confirm": "CAMBIAR"})
    assert response.status_code == 302
    assert called == [(school.pk, new_director.pk, platform.pk, "manual")]
    school.refresh_from_db()
    old_director.refresh_from_db()
    new_director.refresh_from_db()
    assert school.director == new_director
    assert old_director.is_active is False
    assert new_director.is_active is True
