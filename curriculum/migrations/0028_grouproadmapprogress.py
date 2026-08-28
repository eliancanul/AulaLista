from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0027_teacher_curriculum_ownership")]

    operations = [
        migrations.CreateModel(
            name="GroupRoadmapProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completed_activity_ids", models.JSONField(blank=True, default=list)),
                ("current_activity_id", models.CharField(blank=True, default="", max_length=160)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("roadmap_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="group_progress", to="curriculum.publishedroadmapsnapshot")),
                ("session", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="group_roadmap_progress", to="curriculum.classroomsession")),
            ],
        ),
    ]
