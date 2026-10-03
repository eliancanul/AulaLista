from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0043_curriculumsourceblob_check_curriculum_source_blob_content_size_gt_0_and_more")]
    operations = [migrations.CreateModel(
        name="CurriculumTeacherReview",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("revision", models.PositiveIntegerField(default=1)),
            ("dossier_version", models.PositiveIntegerField()),
            ("source_sha256", models.CharField(max_length=64)),
            ("state", models.JSONField(default=dict)),
            ("generation_token", models.UUIDField(blank=True, editable=False, null=True)),
            ("generation_started_at", models.DateTimeField(blank=True, editable=False, null=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("job", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="teacher_review", to="curriculum.curriculumimportjob")),
        ],
    )]
