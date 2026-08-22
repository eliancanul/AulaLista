import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThanOrEqual


CAPACITY_GUARD = "curriculum_studentturn_capacity_guard"
CAPACITY_DECREMENT = "curriculum_studentturn_capacity_decrement"
CAPACITY_UPDATE_GUARD = "curriculum_studentturn_capacity_update_guard"
SESSION_STATE_GUARD = "curriculum_studentturn_session_state_guard"
STATUS_INSERT_GUARD = "curriculum_studentturn_status_insert_guard"
ACTIVE_NAME_INSERT_GUARD = "curriculum_studentturn_active_name_insert_guard"
ACTIVE_NAME_UPDATE_GUARD = "curriculum_studentturn_active_name_update_guard"
ASSIGNMENT_GUARD = "curriculum_studentturn_assignment_immutable"
STATUS_GUARD = "curriculum_studentturn_status_transition"
COMPLETED_STATE_GUARD = "curriculum_studentturn_completed_state"

# SQLite has no portable trim-set syntax across all supported versions. Start
# with trim(NEW.display_name), map the five ASCII control whitespace characters
# to spaces, and trim again. This mirrors Python's boundary normalization for
# spaces, tabs, LF, CR, VT, and FF; it makes no Unicode-whitespace promise.
NORMALIZED_NAME_SQL = """trim(
    replace(
        replace(
            replace(
                replace(
                    replace(trim(NEW.display_name), char(9), ' '),
                    char(10), ' '
                ),
                char(13), ' '
            ),
            char(11), ' '
        ),
        char(12), ' '
    )
)"""


def drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    for trigger_name in (
        CAPACITY_GUARD,
        CAPACITY_DECREMENT,
        CAPACITY_UPDATE_GUARD,
        SESSION_STATE_GUARD,
        STATUS_INSERT_GUARD,
        ACTIVE_NAME_INSERT_GUARD,
        ACTIVE_NAME_UPDATE_GUARD,
        ASSIGNMENT_GUARD,
        STATUS_GUARD,
        COMPLETED_STATE_GUARD,
    ):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")


def create_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    drop_guards(apps, schema_editor)
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CAPACITY_GUARD}
        BEFORE INSERT ON curriculum_studentturn
        WHEN NEW.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM curriculum_deviceassignment
              WHERE id = NEW.assignment_id
                AND remaining_capacity > 0
          )
        BEGIN
            SELECT RAISE(ABORT, 'StudentTurn capacity exhausted');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CAPACITY_DECREMENT}
        AFTER INSERT ON curriculum_studentturn
        WHEN NEW.status = 'active'
        BEGIN
            UPDATE curriculum_deviceassignment
            SET remaining_capacity = remaining_capacity - 1
            WHERE id = NEW.assignment_id;
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CAPACITY_UPDATE_GUARD}
        BEFORE UPDATE OF remaining_capacity ON curriculum_deviceassignment
        WHEN NEW.remaining_capacity > OLD.remaining_capacity
        BEGIN
            SELECT RAISE(ABORT, 'DeviceAssignment capacity cannot increase');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {STATUS_INSERT_GUARD}
        BEFORE INSERT ON curriculum_studentturn
        WHEN NEW.status != 'active'
        BEGIN
            SELECT RAISE(ABORT, 'StudentTurn must start active');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {SESSION_STATE_GUARD}
        BEFORE INSERT ON curriculum_studentturn
        WHEN NEW.status = 'active'
          AND NOT EXISTS (
              SELECT 1
              FROM curriculum_deviceassignment AS assignment
              JOIN curriculum_classroomsession AS session
                ON session.id = assignment.session_id
              WHERE assignment.id = NEW.assignment_id
                AND session.status = 'active'
          )
        BEGIN
            SELECT RAISE(ABORT, 'StudentTurn requires an active ClassroomSession');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {ACTIVE_NAME_INSERT_GUARD}
        BEFORE INSERT ON curriculum_studentturn
        WHEN NEW.status = 'active'
          AND (
              length({NORMALIZED_NAME_SQL}) < 1
              OR length({NORMALIZED_NAME_SQL}) > 80
          )
        BEGIN
            SELECT RAISE(ABORT, 'Active StudentTurn name is invalid');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {ACTIVE_NAME_UPDATE_GUARD}
        BEFORE UPDATE ON curriculum_studentturn
        WHEN NEW.status = 'active'
          AND (
              length({NORMALIZED_NAME_SQL}) < 1
              OR length({NORMALIZED_NAME_SQL}) > 80
          )
        BEGIN
            SELECT RAISE(ABORT, 'Active StudentTurn name is invalid');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {ASSIGNMENT_GUARD}
        BEFORE UPDATE OF assignment_id ON curriculum_studentturn
        WHEN OLD.assignment_id != NEW.assignment_id
        BEGIN
            SELECT RAISE(ABORT, 'StudentTurn assignment is immutable');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {STATUS_GUARD}
        BEFORE UPDATE OF status ON curriculum_studentturn
        WHEN NOT (
            (OLD.status = 'active' AND NEW.status IN ('active', 'completed'))
            OR (OLD.status = 'completed' AND NEW.status = 'completed')
        )
        BEGIN
            SELECT RAISE(ABORT, 'StudentTurn status transition is invalid');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {COMPLETED_STATE_GUARD}
        BEFORE UPDATE OF status, display_name, completed_at ON curriculum_studentturn
        WHEN NEW.status = 'completed'
          AND (
              NEW.display_name != ''
              OR NEW.completed_at IS NULL
              OR NOT EXISTS (
                  SELECT 1
                  FROM curriculum_deviceassignment AS assignment
                  JOIN curriculum_classroomsession AS session
                    ON session.id = assignment.session_id
                  WHERE assignment.id = NEW.assignment_id
                    AND session.status = 'active'
              )
          )
        BEGIN
            SELECT RAISE(ABORT, 'Completed StudentTurn requires cleared name and timestamp');
        END;
        """
    )


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0009_t06_preparation")]

    operations = [
        migrations.CreateModel(
            name="StudentTurn",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        blank=True,
                        max_length=80,
                        verbose_name="apodo local",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Activo"), ("completed", "Completado")],
                        default="active",
                        max_length=16,
                        verbose_name="estado",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="iniciado en"),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="completado en",
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_turns",
                        to="curriculum.deviceassignment",
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at", "-id"],
                "verbose_name": "StudentTurn",
                "verbose_name_plural": "StudentTurns",
            },
        ),
        migrations.AddConstraint(
            model_name="studentturn",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["active", "completed"]),
                name="student_turn_status_allowed",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentturn",
            constraint=models.CheckConstraint(
                condition=Q(status="completed")
                | (Q(status="active") & ~Q(display_name="")),
                name="student_turn_active_name_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentturn",
            constraint=models.CheckConstraint(
                condition=Q(status="completed")
                | (
                    Q(status="active")
                    & GreaterThanOrEqual(Length(Trim("display_name")), 1)
                ),
                name="student_turn_active_name_length",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentturn",
            constraint=models.UniqueConstraint(
                condition=Q(status="active"),
                fields=("assignment",),
                name="unique_active_student_turn_per_assignment",
            ),
        ),
        migrations.RunPython(create_guards, drop_guards),
    ]
