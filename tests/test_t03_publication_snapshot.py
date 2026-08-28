import hashlib
import importlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, migrations, transaction
from django.test import Client
from django.urls import reverse


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.models import CurriculumPackage, PublishedPackageSnapshot, WorkflowState


pytestmark = pytest.mark.django_db


def valid_package(owner=None):
    return CurriculumPackage.objects.create(
        title="Fracciones: partes de un todo",
        objective="Reconocer partes iguales de un todo.",
        micro_lesson="El denominador indica las partes iguales.",
        questions=[
            (
                "reactivo",
                {
                    "prompt": "¿Qué indica el denominador?",
                    "options": [
                        {
                            "position": 1,
                            "text": "Las partes iguales",
                            "expected": True,
                            "feedback": "Correcto.",
                        },
                        {
                            "position": 2,
                            "text": "El color",
                            "expected": False,
                            "feedback": "Revisa la microlección.",
                        },
                    ],
                    "hints": ["Observa el número de abajo."],
                },
            )
        ],
        final_explanation="El denominador cuenta las partes iguales.",
        created_by=owner,
    )


def editorial_reviewer():
    user = get_user_model().objects.create_user(
        username="editorial-reviewer",
        password="test-password",
        is_staff=True,
    )
    user.groups.add(Group.objects.get(name="EditorialReviewer"))
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="curriculum",
            content_type__model="curriculumpackage",
            codename__in=("add_curriculumpackage", "change_curriculumpackage"),
        ),
        Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        ),
    )
    return user


def incomplete_package(owner=None):
    return CurriculumPackage.objects.create(
        title="Paquete incompleto",
        created_by=owner,
    )


def test_publication_rejects_structurally_incomplete_package_before_creating_snapshot():
    reviewer = editorial_reviewer()
    package = incomplete_package(reviewer)
    assert package.structural_validation()["is_valid"] is False
    package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    client = Client()
    client.force_login(reviewer)

    response = client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state.pk],
        ),
        {"comment": "Intento de aprobar un paquete incompleto."},
        follow=True,
    )

    assert response.status_code == 200
    assert PublishedPackageSnapshot.objects.count() == 0
    task_state.refresh_from_db()
    assert task_state.status == task_state.STATUS_IN_PROGRESS
    workflow_state.refresh_from_db()
    assert workflow_state.status == workflow_state.STATUS_IN_PROGRESS
    shown_messages = [str(message) for message in get_messages(response.wsgi_request)]
    validation = package.structural_validation()
    for missing in validation["missing"]:
        assert any(missing in message for message in shown_messages)


def test_domain_publish_rejects_invalid_revision_even_with_recorded_human_approval():
    reviewer = editorial_reviewer()
    package = incomplete_package(reviewer)
    revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state

    # La aprobación humana se registra, pero la publicación debe seguir bloqueada.
    with pytest.raises(ValidationError, match="estructuralmente"):
        task_state.approve(user=reviewer, update=True)

    assert PublishedPackageSnapshot.objects.count() == 0
    task_state.refresh_from_db()
    assert task_state.status == task_state.STATUS_IN_PROGRESS


def test_structural_validation_blocks_stale_incomplete_revision_even_if_package_is_completed_later():
    reviewer = editorial_reviewer()
    package = incomplete_package(reviewer)
    stale_revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state

    # El paquete se completa después, pero la revisión aprobada sigue siendo inválida.
    package.objective = "Objetivo agregado tarde."
    package.save()
    package.save_revision(user=reviewer)

    # Se registra aprobación humana sobre la tarea de la revisión vieja e inválida.
    task_state.approve(user=reviewer, update=False)
    workflow_state.status = WorkflowState.STATUS_APPROVED
    workflow_state.save()

    with pytest.raises(ValidationError, match="estructuralmente"):
        stale_revision.publish(user=reviewer, skip_permission_checks=True)

    assert PublishedPackageSnapshot.objects.count() == 0


def test_publication_without_human_approval_is_rejected():
    reviewer = editorial_reviewer()
    package = valid_package(reviewer)
    revision = package.save_revision(user=reviewer)

    with pytest.raises(ValidationError, match="aprobación humana"):
        revision.publish(user=reviewer, skip_permission_checks=True)

    assert PublishedPackageSnapshot.objects.count() == 0


def test_publication_path_rejects_an_authenticated_user_outside_editorial_reviewer_group():
    unauthorized = get_user_model().objects.create_user(
        username="publisher-outside-review-group",
        password="test-password",
        is_staff=True,
    )
    unauthorized.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="curriculum",
            content_type__model="curriculumpackage",
            codename="change_curriculumpackage",
        )
    )
    package = valid_package(unauthorized)
    revision = package.save_revision(user=unauthorized)

    with pytest.raises(ValidationError, match="EditorialReviewer"):
        revision.publish(user=unauthorized, skip_permission_checks=True)

    assert PublishedPackageSnapshot.objects.count() == 0


def test_editorial_reviewer_approves_valid_revision_and_creates_snapshot():
    reviewer = editorial_reviewer()
    package = valid_package(reviewer)
    revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    action_url = reverse(
        package.snippet_viewset.get_url_name("workflow_action"),
        args=[package.pk, "approve", task_state.pk],
    )

    client = Client()
    client.force_login(reviewer)
    response = client.post(action_url, {"comment": "Aprobación humana."})

    assert response.status_code == 302
    snapshot = PublishedPackageSnapshot.objects.get(package=package)
    assert snapshot.version == 1
    assert snapshot.source_revision_id == revision.id
    assert snapshot.published_by_id == reviewer.id
    assert snapshot.payload["title"] == "Fracciones: partes de un todo"
    expected_fingerprint = hashlib.sha256(
        json.dumps(
            snapshot.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    assert snapshot.sha256 == expected_fingerprint


def test_correction_creates_a_new_auditable_snapshot_without_changing_snapshot_one():
    reviewer = editorial_reviewer()
    package = valid_package(reviewer)
    revision_1 = package.save_revision(user=reviewer)
    workflow_state_1 = package.get_workflow().start(package, user=reviewer)
    task_state_1 = workflow_state_1.current_task_state
    client = Client()
    client.force_login(reviewer)
    client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state_1.pk],
        ),
        {"comment": "Aprobación humana de la primera versión."},
    )
    snapshot_1 = PublishedPackageSnapshot.objects.get(package=package, version=1)

    package.refresh_from_db()
    package.micro_lesson = (
        "Corrección: el denominador indica cuántas partes iguales hay."
    )
    package.save()
    revision_2 = package.save_revision(user=reviewer)
    workflow_state_2 = package.get_workflow().start(package, user=reviewer)
    task_state_2 = workflow_state_2.current_task_state
    client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state_2.pk],
        ),
        {"comment": "Aprobación humana de la corrección."},
    )

    snapshot_1.refresh_from_db()
    snapshot_2 = PublishedPackageSnapshot.objects.get(package=package, version=2)

    assert snapshot_1.source_revision_id == revision_1.id
    assert snapshot_2.source_revision_id == revision_2.id
    assert snapshot_1.payload["micro_lesson"] == "El denominador indica las partes iguales."
    assert snapshot_2.payload["micro_lesson"] == (
        "Corrección: el denominador indica cuántas partes iguales hay."
    )
    assert snapshot_1.payload != snapshot_2.payload
    assert snapshot_1.sha256 != snapshot_2.sha256
    with pytest.raises(ValidationError, match="inmutable"):
        snapshot_1.save()


def test_authenticated_staff_without_editorial_reviewer_role_cannot_approve():
    reviewer = editorial_reviewer()
    unauthorized = get_user_model().objects.create_user(
        username="staff-without-review-role",
        password="test-password",
        is_staff=True,
    )
    unauthorized.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        ),
        *Permission.objects.filter(
            content_type__app_label="curriculum",
            content_type__model="curriculumpackage",
            codename="change_curriculumpackage",
        ),
    )
    package = valid_package(reviewer)
    package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    client = Client()
    client.force_login(unauthorized)

    response = client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state.pk],
        ),
        {"comment": "Intento no autorizado."},
    )

    assert response.status_code == 403
    assert PublishedPackageSnapshot.objects.count() == 0
    task_state.refresh_from_db()
    assert task_state.status == task_state.STATUS_IN_PROGRESS


def test_published_snapshot_rejects_mass_updates_and_deletes_at_database_boundary():
    reviewer = editorial_reviewer()
    package = valid_package(reviewer)
    revision = package.save_revision(user=reviewer)
    workflow_state = package.get_workflow().start(package, user=reviewer)
    task_state = workflow_state.current_task_state
    client = Client()
    client.force_login(reviewer)
    response = client.post(
        reverse(
            package.snippet_viewset.get_url_name("workflow_action"),
            args=[package.pk, "approve", task_state.pk],
        ),
        {"comment": "Aprobación para probar inmutabilidad."},
    )
    assert response.status_code == 302
    snapshot = PublishedPackageSnapshot.objects.get(
        package=package,
        source_revision=revision,
    )
    original_payload = snapshot.payload
    original_version = snapshot.version

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PublishedPackageSnapshot.objects.filter(pk=snapshot.pk).update(
                payload={"tampered": True}
            )
    snapshot.refresh_from_db()
    assert snapshot.payload == original_payload

    snapshot.version = original_version + 1
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PublishedPackageSnapshot.objects.bulk_update([snapshot], ["version"])
    snapshot.refresh_from_db()
    assert snapshot.version == original_version

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_publishedpackagesnapshot SET version = %s WHERE id = %s",
                    [original_version + 1, snapshot.pk],
                )
    snapshot.refresh_from_db()
    assert snapshot.version == original_version

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PublishedPackageSnapshot.objects.filter(pk=snapshot.pk).delete()
    assert PublishedPackageSnapshot.objects.filter(pk=snapshot.pk).exists()


def test_editorial_workflow_migration_has_a_non_destructive_reverse():
    migration_module = importlib.import_module(
        "curriculum.migrations.0004_editorial_review_workflow"
    )

    assert migration_module.Migration.operations[0].reverse_code is migrations.RunPython.noop


def test_snapshot_immutability_migration_keeps_triggers_on_reverse():
    migration_module = importlib.import_module(
        "curriculum.migrations.0006_snapshot_immutability_and_reviewer_permissions"
    )

    assert migration_module.Migration.operations[0].reverse_code is migrations.RunPython.noop
