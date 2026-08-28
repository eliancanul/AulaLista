from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0028_grouproadmapprogress"),
    ]

    operations = [
        migrations.AddField(
            model_name="curriculumimportjob",
            name="progress_finished_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="fin de la etapa",
            ),
        ),
    ]
