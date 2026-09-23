from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0030_institutionalauditevent_school_teacherassignment_and_more")]
    operations = [
        migrations.AddField(model_name="curriculumimportjob", name="cancel_requested", field=models.BooleanField(default=False, editable=False)),
        migrations.AddField(model_name="curriculumimportjob", name="cancelled_at", field=models.DateTimeField(blank=True, editable=False, null=True)),
    ]
