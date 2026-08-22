from django.db import migrations


TRIGGER_NAME = "curriculum_classroomsession_no_snapshot_update"
TABLE_NAME = "curriculum_classroomsession"


def protect_session_snapshot_on_sqlite(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return

    schema_editor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS {TRIGGER_NAME}
        BEFORE UPDATE OF snapshot_id ON {TABLE_NAME}
        BEGIN
            SELECT RAISE(ABORT, 'ClassroomSession snapshot is immutable');
        END;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0007_classroomsession"),
    ]

    operations = [
        migrations.RunPython(
            protect_session_snapshot_on_sqlite,
            migrations.RunPython.noop,
        ),
    ]
