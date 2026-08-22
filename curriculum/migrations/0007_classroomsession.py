from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0006_snapshot_immutability_and_reviewer_permissions"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomSession",
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
                    "status",
                    models.CharField(
                        choices=[("active", "Activa"), ("stopped", "Detenida")],
                        default="active",
                        max_length=16,
                        verbose_name="estado",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="iniciada en"),
                ),
                (
                    "stopped_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="detenida en",
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="classroom_sessions",
                        to="curriculum.publishedpackagesnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "ClassroomSession",
                "verbose_name_plural": "ClassroomSessions",
                "ordering": ["-started_at", "-id"],
            },
        ),
    ]
