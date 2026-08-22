import hashlib
import json
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
django.setup()

from curriculum.distribution import (  # noqa: E402
    CapacityOverflowError,
    DistributionInputError,
    calculate_distribution,
    ensure_capacity,
)
from curriculum.models import (  # noqa: E402
    ClassroomSession,
    ClassroomSessionConfirmation,
    CurriculumPackage,
    DeviceAssignment,
    PublishedPackageSnapshot,
)


pytestmark = pytest.mark.django_db


def published_snapshot(title="Paquete T06"):
    package = CurriculumPackage.objects.create(title=title)
    revision = package.save_revision()
    payload = {
        "title": title,
        "objective": "Distinguir una idea principal.",
        "micro_lesson": "Una idea principal organiza el sentido.",
        "questions": [],
        "final_explanation": "La idea principal organiza el sentido.",
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload=payload,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_revision=revision,
        published_by=get_user_model().objects.create_user(
            username=f"publisher-{title}",
        ),
    )


def test_distribution_is_balanced_exact_and_deterministic():
    first = calculate_distribution(8, 3)

    assert first == (3, 3, 2)
    assert sum(first) == 8
    assert max(first) - min(first) <= 1
    assert calculate_distribution(8, 3) == first


@pytest.mark.parametrize(
    ("students", "devices"),
    [
        (None, 2),
        (8, None),
        ("", "2"),
        ("ocho", "2"),
        ("8.0", "2"),
        (0, 1),
        (-1, 1),
        (8, 0),
        (8, -1),
        (2, 3),
    ],
)
def test_distribution_rejects_invalid_counts(students, devices):
    with pytest.raises(DistributionInputError):
        calculate_distribution(students, devices)


def test_capacity_guard_rejects_overflow_unless_explicitly_authorized():
    class Assignment:
        remaining_capacity = 2

    with pytest.raises(CapacityOverflowError):
        ensure_capacity(Assignment(), 3)

    reservation = ensure_capacity(Assignment(), 3, allow_overflow=True)

    assert reservation.overflow == 1
    assert reservation.remaining_capacity == 0


def test_tutor_reviews_local_opaque_device_queues_without_student_identity():
    snapshot = published_snapshot()
    client = Client()

    response = client.post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {
            "student_count": "8",
            "device_count": "3",
            "student_name": "Ana Identidad No Enviada",
        },
    )

    assert response.status_code == 302
    session = ClassroomSession.objects.get()
    assignments = list(session.device_assignments.order_by("id"))
    assert session.status == ClassroomSession.STATUS_PREPARED
    assert [assignment.assigned_capacity for assignment in assignments] == [3, 3, 2]
    assert all(assignment.local_identifier for assignment in assignments)
    assert "Ana Identidad No Enviada" not in client.get(
        reverse("tutor-session-review", args=[session.pk])
    ).text


def test_prepared_session_is_not_active_or_available_to_students():
    snapshot = published_snapshot()
    response = Client().post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {"student_count": "2", "device_count": "1"},
    )
    session = ClassroomSession.objects.get()

    assert response.status_code == 302
    assert session.status == ClassroomSession.STATUS_PREPARED
    assert Client().get(
        reverse("student-activity", args=[session.pk])
    ).status_code == 403


def test_tutor_confirmation_activates_once_and_keeps_snapshot_pinned():
    snapshot = published_snapshot()
    client = Client()
    prepare = client.post(
        reverse("tutor-session-prepare", args=[snapshot.pk]),
        {"student_count": "5", "device_count": "2"},
    )
    session = ClassroomSession.objects.get()
    assignment_count = DeviceAssignment.objects.filter(session=session).count()

    first_confirmation = client.post(
        reverse("tutor-session-confirm", args=[session.pk]),
    )
    session.refresh_from_db()
    confirmed_at = session.confirmed_at
    receipt = ClassroomSessionConfirmation.objects.get(session=session)
    second_confirmation = client.post(
        reverse("tutor-session-confirm", args=[session.pk]),
    )
    session.refresh_from_db()

    assert prepare.status_code == 302
    assert first_confirmation.status_code == 302
    assert second_confirmation.status_code == 302
    assert session.status == ClassroomSession.STATUS_ACTIVE
    assert confirmed_at is not None
    assert session.confirmed_at == confirmed_at
    assert receipt.confirmed_at == confirmed_at
    assert receipt.nonce
    assert ClassroomSessionConfirmation.objects.filter(session=session).count() == 1
    assert session.snapshot_id == snapshot.pk
    assert DeviceAssignment.objects.filter(session=session).count() == assignment_count
    assignment = session.device_assignments.order_by("id").first()
    client.post(
        reverse("student-turn-start", args=[session.pk, assignment.local_identifier]),
        {"display_name": "Luna"},
    )
    assert client.get(reverse("student-activity", args=[session.pk])).status_code == 200


def test_prepared_distribution_cannot_change_snapshot():
    first = published_snapshot("Primero")
    second = published_snapshot("Segundo")
    session = ClassroomSession.prepare_from_snapshot(first, 3, 2)

    session.snapshot = second
    with pytest.raises(ValidationError, match="fijado"):
        session.save()


def test_prepared_session_cannot_be_activated_by_direct_save():
    snapshot = published_snapshot()
    session = ClassroomSession.prepare_from_snapshot(snapshot, 3, 2)
    session.status = ClassroomSession.STATUS_ACTIVE

    with pytest.raises(ValidationError, match="confirmación explícita"):
        session.save()


def test_database_guards_reject_queryset_and_sql_activation_without_confirmation():
    snapshot = published_snapshot()
    session = ClassroomSession.prepare_from_snapshot(snapshot, 3, 2)

    session.status = ClassroomSession.STATUS_ACTIVE
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.bulk_update([session], ["status"])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.filter(pk=session.pk).update(
                status=ClassroomSession.STATUS_ACTIVE,
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.filter(pk=session.pk).update(
                status=ClassroomSession.STATUS_ACTIVE,
                confirmed_at=timezone.now(),
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE curriculum_classroomsession SET status = %s WHERE id = %s",
                    [ClassroomSession.STATUS_ACTIVE, session.pk],
                )

    session.refresh_from_db()
    assert session.status == ClassroomSession.STATUS_PREPARED
    assert session.confirmed_at is None


def test_database_guard_rejects_active_update_when_persisted_distribution_is_invalid():
    snapshot = published_snapshot()
    session = ClassroomSession.prepare_from_snapshot(snapshot, 3, 2)
    first_assignment = session.device_assignments.order_by("id").first()
    DeviceAssignment.objects.filter(pk=first_assignment.pk).update(
        assigned_capacity=3,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.filter(pk=session.pk).update(
                status=ClassroomSession.STATUS_ACTIVE,
                confirmed_at=timezone.now(),
            )


def test_database_guard_rejects_active_t06_insert_without_confirmation():
    snapshot = published_snapshot()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClassroomSession.objects.bulk_create(
                [
                    ClassroomSession(
                        snapshot=snapshot,
                        status=ClassroomSession.STATUS_ACTIVE,
                        student_count=3,
                        device_count=2,
                    )
                ]
            )
