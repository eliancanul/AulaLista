import importlib
import uuid

import django.db.models.deletion
from django.db import migrations, models


CLOSURE_RECEIPT_UPDATE_GUARD = "curriculum_classroomsession_closure_receipt_guard"
CLOSED_ASSIGNMENT_REASSIGN_GUARD = "curriculum_deviceassignment_closed_reassign_guard"


def _drop_previous_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    importlib.import_module("curriculum.migrations.0014_t08_closed_guards").drop_runtime_guards(
        apps,
        schema_editor,
    )


def _recreate_previous_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    importlib.import_module(
        "curriculum.migrations.0014_t08_closed_guards"
    ).create_runtime_guards(apps, schema_editor)


def drop_runtime_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    _drop_previous_guards(apps, schema_editor)
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS {CLOSURE_RECEIPT_UPDATE_GUARD};"
    )
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS {CLOSED_ASSIGNMENT_REASSIGN_GUARD};"
    )


def create_runtime_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    _recreate_previous_guards(apps, schema_editor)
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CLOSURE_RECEIPT_UPDATE_GUARD}
        BEFORE UPDATE OF status, closed_at ON curriculum_classroomsession
        WHEN (
            NEW.status = 'closed'
            AND NOT EXISTS (
                SELECT 1
                FROM curriculum_classroomsessionclosure
                WHERE session_id = NEW.id
            )
        )
        OR (
            OLD.status = 'closed'
            AND (
                NEW.status != 'closed'
                OR NEW.closed_at IS NOT OLD.closed_at
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'Closed status requires an immutable closure receipt');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER {CLOSED_ASSIGNMENT_REASSIGN_GUARD}
        BEFORE UPDATE OF session_id ON curriculum_deviceassignment
        WHEN EXISTS (
            SELECT 1
            FROM curriculum_classroomsession
            WHERE id = NEW.session_id AND status = 'closed'
        )
        BEGIN
            SELECT RAISE(ABORT, 'DeviceAssignment cannot move to a closed session');
        END;
        """
    )


def backfill_result_batches(apps, schema_editor):
    Session = apps.get_model("curriculum", "ClassroomSession")
    Result = apps.get_model("curriculum", "PseudonymousResult")

    seen_session_batches = set()
    for session in Session.objects.order_by("pk"):
        if session.result_batch_id in seen_session_batches:
            new_batch_id = uuid.uuid4()
            while new_batch_id in seen_session_batches:
                new_batch_id = uuid.uuid4()
            Session.objects.filter(pk=session.pk).update(result_batch_id=new_batch_id)
            session.result_batch_id = new_batch_id
        seen_session_batches.add(session.result_batch_id)

    used_result_batches = set(seen_session_batches)
    for result in Result.objects.filter(result_batch_id__isnull=True).order_by("pk"):
        new_batch_id = uuid.uuid4()
        while new_batch_id in used_result_batches:
            new_batch_id = uuid.uuid4()
        Result.objects.filter(pk=result.pk).update(result_batch_id=new_batch_id)
        used_result_batches.add(new_batch_id)


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0014_t08_closed_guards")]

    operations = [
        migrations.RunPython(drop_runtime_guards, _recreate_previous_guards),
        migrations.CreateModel(
            name="ClassroomSessionClosure",
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
                    "closed_at",
                    models.DateTimeField(verbose_name="cerrada en"),
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
                        related_name="closure_receipt",
                        to="curriculum.classroomsession",
                    ),
                ),
            ],
            options={
                "verbose_name": "ClassroomSessionClosure",
                "verbose_name_plural": "ClassroomSessionClosures",
            },
        ),
        migrations.RunPython(backfill_result_batches, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="classroomsession",
            name="result_batch_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="lote opaco de resultados",
            ),
        ),
        migrations.AlterField(
            model_name="pseudonymousresult",
            name="result_batch_id",
            field=models.UUIDField(
                db_index=True,
                verbose_name="lote opaco de resultados",
            ),
        ),
        migrations.RunPython(create_runtime_guards, drop_runtime_guards),
    ]
