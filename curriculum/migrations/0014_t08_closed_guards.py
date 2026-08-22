import importlib

from django.db import migrations


CLOSED_STATUS_UPDATE_GUARD = "curriculum_classroomsession_closed_terminal_guard"
CLOSED_ASSIGNMENT_INSERT_GUARD = "curriculum_deviceassignment_closed_insert_guard"


def _drop_previous_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    importlib.import_module("curriculum.migrations.0012_t08_close_session").drop_runtime_guards(
        apps,
        schema_editor,
    )


def _recreate_previous_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    importlib.import_module(
        "curriculum.migrations.0012_t08_close_session"
    ).recreate_runtime_guards(apps, schema_editor)


def drop_runtime_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    _drop_previous_guards(apps, schema_editor)
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS {CLOSED_STATUS_UPDATE_GUARD};"
    )
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS {CLOSED_ASSIGNMENT_INSERT_GUARD};"
    )


def create_runtime_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    _recreate_previous_guards(apps, schema_editor)
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CLOSED_STATUS_UPDATE_GUARD}
        BEFORE UPDATE OF status ON curriculum_classroomsession
        WHEN OLD.status = 'closed' AND NEW.status != 'closed'
        BEGIN
            SELECT RAISE(ABORT, 'Closed ClassroomSession is terminal');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CLOSED_ASSIGNMENT_INSERT_GUARD}
        BEFORE INSERT ON curriculum_deviceassignment
        WHEN EXISTS (
            SELECT 1
            FROM curriculum_classroomsession
            WHERE id = NEW.session_id AND status = 'closed'
        )
        BEGIN
            SELECT RAISE(ABORT, 'Closed ClassroomSession rejects DeviceAssignment');
        END;
        """
    )


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0013_t08_result_batches")]

    operations = [
        migrations.RunPython(drop_runtime_guards, create_runtime_guards),
        migrations.RunPython(create_runtime_guards, drop_runtime_guards),
    ]
