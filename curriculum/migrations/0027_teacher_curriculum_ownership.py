from django.db import migrations, models
import django.db.models.deletion


def backfill_package_owners(apps, schema_editor):
    CurriculumPackage = apps.get_model("curriculum", "CurriculumPackage")
    PublishedPackageSnapshot = apps.get_model(
        "curriculum", "PublishedPackageSnapshot"
    )
    for package in CurriculumPackage.objects.filter(created_by__isnull=True):
        publisher_id = (
            PublishedPackageSnapshot.objects.filter(package_id=package.pk)
            .order_by("published_at", "id")
            .values_list("published_by_id", flat=True)
            .first()
        )
        if publisher_id is not None:
            package.created_by_id = publisher_id
            package.save(update_fields=["created_by"])


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0026_classroomsession_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="curriculumpackage",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="curriculum_packages",
                to="auth.user",
            ),
        ),
        migrations.AddField(
            model_name="curriculumimportjob",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="curriculum_import_jobs",
                to="auth.user",
            ),
        ),
        migrations.RunPython(
            backfill_package_owners,
            migrations.RunPython.noop,
        ),
    ]
