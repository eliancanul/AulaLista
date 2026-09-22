import importlib

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


MIGRATE_FROM = [("curriculum", "0029_curriculumimportjob_progress_finished_at")]
MIGRATE_TO = [
    (
        "curriculum",
        "0030_institutionalauditevent_school_teacherassignment_and_more",
    )
]


@pytest.fixture
def migration_executor():
    executor = MigrationExecutor(connection)
    executor.migrate(MIGRATE_FROM)
    old_apps = executor.loader.project_state(MIGRATE_FROM).apps
    yield executor, old_apps

    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
    sqlite_guards = importlib.import_module(
        "curriculum.migrations.0025_classroomgroup_and_pseudonymous_retention"
    )
    with connection.schema_editor() as schema_editor:
        sqlite_guards.drop_sqlite_guards(None, schema_editor)
        package_guards = importlib.import_module(
            "curriculum.migrations.0006_snapshot_immutability_and_reviewer_permissions"
        )
        for trigger_name in (
            package_guards.UPDATE_TRIGGER,
            package_guards.DELETE_TRIGGER,
        ):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")
    call_command("flush", verbosity=0, interactive=False)
    with connection.schema_editor() as schema_editor:
        sqlite_guards.recreate_sqlite_guards(None, schema_editor)


def _create_legacy_snapshot(apps, publisher):
    ContentType = apps.get_model("contenttypes", "ContentType")
    CurriculumPackage = apps.get_model("curriculum", "CurriculumPackage")
    PublishedPackageSnapshot = apps.get_model(
        "curriculum", "PublishedPackageSnapshot"
    )
    Revision = apps.get_model("wagtailcore", "Revision")

    content_type = ContentType.objects.get(
        app_label="curriculum",
        model="curriculumpackage",
    )
    package = CurriculumPackage.objects.create(
        title="Paquete legado",
        objective="Objetivo legado",
        micro_lesson="Microleccion legada",
        questions=[],
        final_explanation="Explicacion legada",
        validation_summary="Validacion legada",
        created_by=publisher,
    )
    revision = Revision.objects.create(
        created_at=timezone.now(),
        user=publisher,
        content={},
        object_id=str(package.pk),
        content_type=content_type,
        base_content_type=content_type,
        object_str=package.title,
    )
    return PublishedPackageSnapshot.objects.create(
        package=package,
        version=1,
        payload={},
        sha256="0" * 64,
        published_by=publisher,
        source_revision=revision,
    )


def _create_ambiguous_legacy_rows(apps):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    ClassroomGroup = apps.get_model("curriculum", "ClassroomGroup")
    ClassroomSession = apps.get_model("curriculum", "ClassroomSession")

    director_role, _ = Group.objects.get_or_create(name="Director")
    director_candidate = User.objects.create(
        username="legacy-director-candidate",
        first_name="Alex",
        last_name="Lopez",
        is_staff=True,
        is_active=True,
    )
    director_candidate.groups.add(director_role)
    teacher_a = User.objects.create(
        username="legacy-teacher-a",
        first_name="Pat",
        last_name="Diaz",
        is_staff=True,
        is_active=True,
    )
    teacher_b = User.objects.create(
        username="legacy-teacher-b",
        first_name="Pat",
        last_name="Diaz",
        is_staff=True,
        is_active=True,
    )
    snapshot = _create_legacy_snapshot(apps, director_candidate)

    classroom_a = ClassroomGroup.objects.create(
        name="1 A",
        created_by=teacher_a,
    )
    classroom_b = ClassroomGroup.objects.create(
        name="1 A",
        created_by=teacher_b,
    )
    session_a = ClassroomSession.objects.create(
        status="prepared",
        snapshot=snapshot,
        started_at=timezone.now(),
        student_count=2,
        device_count=1,
        classroom_group=classroom_a,
        created_by=teacher_a,
    )
    session_b = ClassroomSession.objects.create(
        status="prepared",
        snapshot=snapshot,
        started_at=timezone.now(),
        student_count=2,
        device_count=1,
        classroom_group=classroom_b,
        created_by=director_candidate,
    )
    return {
        "director_candidate_id": director_candidate.pk,
        "teacher_ids": (teacher_a.pk, teacher_b.pk),
        "classroom_ids": (classroom_a.pk, classroom_b.pk),
        "session_ids": (session_a.pk, session_b.pk),
        "snapshot_id": snapshot.pk,
    }


def _migrate_forward(executor):
    # MigrationExecutor caches applied migrations. Rebuild after the backward
    # setup step so 0030 is actually reapplied in this test process.
    executor.loader.build_graph()
    executor.migrate(MIGRATE_TO)
    return executor.loader.project_state(MIGRATE_TO).apps


@pytest.mark.django_db(transaction=True)
def test_0030_marks_legacy_school_scope_unresolved_without_inventing_authority(
    migration_executor,
):
    executor, old_apps = migration_executor
    legacy = _create_ambiguous_legacy_rows(old_apps)

    new_apps = _migrate_forward(executor)
    School = new_apps.get_model("curriculum", "School")
    TeacherAssignment = new_apps.get_model("curriculum", "TeacherAssignment")
    InstitutionalAuditEvent = new_apps.get_model(
        "curriculum", "InstitutionalAuditEvent"
    )
    ClassroomGroup = new_apps.get_model("curriculum", "ClassroomGroup")
    ClassroomSession = new_apps.get_model("curriculum", "ClassroomSession")

    assert School.objects.count() == 0
    assert TeacherAssignment.objects.count() == 0
    assert InstitutionalAuditEvent.objects.count() == 0

    classrooms = list(ClassroomGroup.objects.order_by("pk"))
    sessions = list(ClassroomSession.objects.order_by("pk"))
    assert [row.pk for row in classrooms] == list(legacy["classroom_ids"])
    assert [row.pk for row in sessions] == list(legacy["session_ids"])
    assert all(row.school_id is None for row in classrooms)
    assert all(row.school_id is None for row in sessions)
    assert all(row.director_id is None for row in classrooms)
    assert all(row.legacy_school_unresolved is True for row in classrooms)
    assert all(row.legacy_school_unresolved is True for row in sessions)


@pytest.mark.django_db(transaction=True)
def test_0030_preserves_legacy_relations_without_heuristic_identity_attribution(
    migration_executor,
):
    executor, old_apps = migration_executor
    legacy = _create_ambiguous_legacy_rows(old_apps)

    new_apps = _migrate_forward(executor)
    ClassroomGroup = new_apps.get_model("curriculum", "ClassroomGroup")
    ClassroomSession = new_apps.get_model("curriculum", "ClassroomSession")

    classrooms = list(ClassroomGroup.objects.order_by("pk"))
    sessions = list(ClassroomSession.objects.order_by("pk"))
    assert [row.name for row in classrooms] == ["1 A", "1 A"]
    assert [row.created_by_id for row in classrooms] == list(legacy["teacher_ids"])
    assert [row.classroom_group_id for row in sessions] == list(
        legacy["classroom_ids"]
    )
    assert [row.created_by_id for row in sessions] == [
        legacy["teacher_ids"][0],
        legacy["director_candidate_id"],
    ]
    assert [row.snapshot_id for row in sessions] == [
        legacy["snapshot_id"],
        legacy["snapshot_id"],
    ]
    assert all(row.academic_year == "" for row in classrooms)
    assert all(row.modality == "" for row in classrooms)
    assert all(row.grade is None for row in classrooms)
    assert all(row.group_key == "" for row in classrooms)
    assert all(row.shift == "" for row in classrooms)


@pytest.mark.django_db(transaction=True)
def test_0030_round_trip_preserves_reversible_legacy_rows_and_relations(
    migration_executor,
):
    executor, old_apps = migration_executor
    legacy = _create_ambiguous_legacy_rows(old_apps)
    _migrate_forward(executor)

    executor.migrate(MIGRATE_FROM)
    restored_apps = executor.loader.project_state(MIGRATE_FROM).apps
    ClassroomGroup = restored_apps.get_model("curriculum", "ClassroomGroup")
    ClassroomSession = restored_apps.get_model("curriculum", "ClassroomSession")

    classrooms = list(ClassroomGroup.objects.order_by("pk"))
    sessions = list(ClassroomSession.objects.order_by("pk"))
    assert [row.pk for row in classrooms] == list(legacy["classroom_ids"])
    assert [row.name for row in classrooms] == ["1 A", "1 A"]
    assert [row.created_by_id for row in classrooms] == list(legacy["teacher_ids"])
    assert [row.pk for row in sessions] == list(legacy["session_ids"])
    assert [row.classroom_group_id for row in sessions] == list(
        legacy["classroom_ids"]
    )
    assert [row.created_by_id for row in sessions] == [
        legacy["teacher_ids"][0],
        legacy["director_candidate_id"],
    ]
    assert [row.snapshot_id for row in sessions] == [
        legacy["snapshot_id"],
        legacy["snapshot_id"],
    ]
