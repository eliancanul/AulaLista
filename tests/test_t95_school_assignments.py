"""Core institutional contract for issues #95 and #104."""

import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import (  # noqa: E402
    DIRECTOR_GROUP_NAME,
    InstitutionalAuditEvent,
    School,
)


pytestmark = pytest.mark.django_db


def staff_user(username, **kwargs):
    return get_user_model().objects.create_user(
        username=username,
        is_staff=True,
        **kwargs,
    )


def platform_administrator(username="platform-admin"):
    return get_user_model().objects.create_superuser(
        username=username,
        email=f"{username}@example.invalid",
        password="test-password",
    )


def test_school_requires_explicit_platform_admin_provisioning_and_creates_one_director():
    administrator = platform_administrator()
    director = staff_user("direccion")

    with pytest.raises(ValidationError, match="provisi"):
        School.objects.create(name="Escuela implícita", director=director)

    school = School.provision(
        name="Escuela Benito Juárez",
        modality=School.MODALITY_PRIMARY,
        director=director,
        actor=administrator,
    )

    assert School.configured() == school
    assert School.objects.count() == 1
    assert school.director == director
    assert director.groups.filter(name=DIRECTOR_GROUP_NAME).exists()
    assert get_user_model().objects.filter(
        is_active=True,
        groups__name=DIRECTOR_GROUP_NAME,
    ).count() == 1


def test_school_provisioning_is_authorized_and_audited_atomically():
    non_administrator = staff_user("tecnico-sin-rol")
    director = staff_user("direccion-auditada", first_name="María", last_name="Poot")

    with pytest.raises(ValidationError, match="PlatformAdministrator"):
        School.provision(
            name="Escuela sin autorización",
            director=director,
            actor=non_administrator,
        )
    assert not School.objects.exists()
    assert not InstitutionalAuditEvent.objects.exists()

    administrator = platform_administrator("admin-auditoria")
    school = School.provision(
        name="Escuela auditada",
        director=director,
        actor=administrator,
        source="manual",
    )

    event = InstitutionalAuditEvent.objects.get()
    assert event.school == school
    assert event.actor == administrator
    assert event.actor_display_name == "Cuenta institucional"
    assert event.actor_role == "PlatformAdministrator"
    assert event.action == "school_provisioned"
    assert event.previous_state == {}
    assert event.new_state == {
        "director": "María Poot",
        "modality": "primary",
        "school": "Escuela auditada",
    }
    assert event.source == "manual"


def test_platform_administrator_handoff_revokes_outgoing_director_and_preserves_history():
    administrator = platform_administrator("admin-handoff")
    outgoing = staff_user("direccion-saliente", first_name="Ana", last_name="May")
    incoming = staff_user("direccion-entrante", first_name="Luz", last_name="Pech")
    school = School.provision(
        name="Escuela de transición",
        director=outgoing,
        actor=administrator,
    )

    handed_off = school.handoff_director(
        incoming,
        actor=administrator,
        source="manual",
    )

    outgoing.refresh_from_db()
    incoming.refresh_from_db()
    assert handed_off.director == incoming
    assert outgoing.is_active is False
    assert not outgoing.groups.filter(name=DIRECTOR_GROUP_NAME).exists()
    assert incoming.is_active is True
    assert incoming.groups.filter(name=DIRECTOR_GROUP_NAME).exists()
    assert get_user_model().objects.filter(
        is_active=True,
        groups__name=DIRECTOR_GROUP_NAME,
    ).count() == 1
    event = InstitutionalAuditEvent.objects.get(action="director_handoff")
    assert event.previous_state == {"director": "Ana May"}
    assert event.new_state == {"director": "Luz Pech"}
    assert event.source == "manual"
