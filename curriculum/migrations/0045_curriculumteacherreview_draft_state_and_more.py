from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0044_curriculumteacherreview")]
    operations = [
        migrations.AddField(model_name="curriculumteacherreview", name="draft_state", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="curriculumteacherreview", name="draft_epoch", field=models.PositiveIntegerField(default=0)),
    ]
