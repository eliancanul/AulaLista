import uuid

import django.db.models.deletion
from django.db import migrations, models


SNAPSHOT_TRIGGER = "curriculum_classroomsession_no_snapshot_update"
T06_INSERT_TRIGGER = "curriculum_classroomsession_t06_requires_confirmation_insert"
T06_UPDATE_TRIGGER = "curriculum_classroomsession_t06_requires_confirmation_update"
RECEIPT_TABLE = "curriculum_classroomsessionconfirmation"


def drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    for trigger_name in (
        SNAPSHOT_TRIGGER,
        T06_INSERT_TRIGGER,
        T06_UPDATE_TRIGGER,
    ):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")


def _create_snapshot_guard(schema_editor):
    schema_editor.execute(
        f"""
        CREATE TRIGGER {SNAPSHOT_TRIGGER}
        BEFORE UPDATE OF snapshot_id ON curriculum_classroomsession
        BEGIN
            SELECT RAISE(ABORT, 'ClassroomSession snapshot is immutable');
        END;
        """
    )


def _create_t06_confirmation_guards(schema_editor):
    invalid_distribution = f"""
          NEW.student_count IS NULL
          OR NEW.device_count IS NULL
          OR NEW.confirmed_at IS NULL
          OR NOT EXISTS (
              SELECT 1 FROM {RECEIPT_TABLE}
              WHERE session_id = NEW.id AND confirmed_at = NEW.confirmed_at
          )
          OR (
              SELECT COUNT(*) FROM curriculum_deviceassignment
              WHERE session_id = NEW.id
          ) != NEW.device_count
          OR COALESCE((
              SELECT SUM(assigned_capacity)
              FROM curriculum_deviceassignment
              WHERE session_id = NEW.id
          ), 0) != NEW.student_count
          OR (
              SELECT MAX(assigned_capacity) - MIN(assigned_capacity)
              FROM curriculum_deviceassignment
              WHERE session_id = NEW.id
          ) > 1
          OR EXISTS (
              SELECT 1 FROM curriculum_deviceassignment
              WHERE session_id = NEW.id
                AND (
                    assigned_capacity <= 0
                    OR remaining_capacity < 0
                    OR remaining_capacity > assigned_capacity
                )
          )
    """
    schema_editor.execute(
        f"""
        CREATE TRIGGER {T06_INSERT_TRIGGER}
        BEFORE INSERT ON curriculum_classroomsession
        WHEN NEW.status = 'active'
          AND (NEW.student_count IS NOT NULL OR NEW.device_count IS NOT NULL)
          AND ({invalid_distribution})
        BEGIN
            SELECT RAISE(ABORT, 'T06 ClassroomSession requires receipt and valid distribution');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {T06_UPDATE_TRIGGER}
        BEFORE UPDATE OF status, confirmed_at, student_count, device_count
            ON curriculum_classroomsession
        WHEN NEW.status = 'active'
          AND (
              OLD.status = 'prepared'
              OR NEW.student_count IS NOT NULL
              OR NEW.device_count IS NOT NULL
          )
          AND ({invalid_distribution})
        BEGIN
            SELECT RAISE(ABORT, 'T06 ClassroomSession requires receipt and valid distribution');
        END;
        """
    )


def recreate_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    drop_guards(apps, schema_editor)
    _create_snapshot_guard(schema_editor)
    _create_t06_confirmation_guards(schema_editor)


def restore_guards_after_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    drop_guards(apps, schema_editor)
    _create_snapshot_guard(schema_editor)


def forward_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0008_fix_classroomsession_snapshot"),
    ]

    operations = [
        migrations.RunPython(
            forward_noop,
            restore_guards_after_reverse,
        ),
        migrations.AddField(
            model_name="classroomsession",
            name="student_count",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="estudiantes indicados",
            ),
        ),
        migrations.AddField(
            model_name="classroomsession",
            name="device_count",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="dispositivos indicados",
            ),
        ),
        migrations.AddField(
            model_name="classroomsession",
            name="confirmed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="confirmada en",
            ),
        ),
        migrations.AlterField(
            model_name="classroomsession",
            name="status",
            field=models.CharField(
                choices=[
                    ("prepared", "Preparada"),
                    ("active", "Activa"),
                    ("stopped", "Detenida"),
                ],
                default="active",
                max_length=16,
                verbose_name="estado",
            ),
        ),
        migrations.CreateModel(
            name="DeviceAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "local_identifier",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                (
                    "assigned_capacity",
                    models.PositiveIntegerField(verbose_name="capacidad asignada"),
                ),
                (
                    "remaining_capacity",
                    models.PositiveIntegerField(verbose_name="capacidad restante"),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_assignments",
                        to="curriculum.classroomsession",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ClassroomSessionConfirmation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "confirmed_at",
                    models.DateTimeField(verbose_name="confirmada en"),
                ),
                (
                    "nonce",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="confirmation_receipt",
                        to="curriculum.classroomsession",
                    ),
                ),
            ],
            options={
                "verbose_name": "ClassroomSessionConfirmation",
                "verbose_name_plural": "ClassroomSessionConfirmations",
            },
        ),
        migrations.AddConstraint(
            model_name="classroomsession",
            constraint=models.CheckConstraint(
                condition=models.Q(student_count__isnull=True)
                | models.Q(student_count__gt=0),
                name="session_student_count_positive_or_null",
            ),
        ),
        migrations.AddConstraint(
            model_name="classroomsession",
            constraint=models.CheckConstraint(
                condition=models.Q(device_count__isnull=True)
                | models.Q(device_count__gt=0),
                name="session_device_count_positive_or_null",
            ),
        ),
        migrations.AddConstraint(
            model_name="classroomsession",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(student_count__isnull=True, device_count__isnull=True)
                    | models.Q(
                        student_count__isnull=False,
                        device_count__isnull=False,
                        student_count__gte=models.F("device_count"),
                    )
                ),
                name="session_device_count_not_above_students",
            ),
        ),
        migrations.AddConstraint(
            model_name="deviceassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(assigned_capacity__gt=0),
                name="device_assignment_capacity_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="deviceassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(remaining_capacity__gte=0),
                name="device_assignment_remaining_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="deviceassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    remaining_capacity__lte=models.F("assigned_capacity")
                ),
                name="device_assignment_remaining_within_capacity",
            ),
        ),
        migrations.AddConstraint(
            model_name="deviceassignment",
            constraint=models.UniqueConstraint(
                fields=("session", "local_identifier"),
                name="unique_session_local_device_identifier",
            ),
        ),
        migrations.RunPython(
            recreate_guards,
            drop_guards,
        ),
    ]
