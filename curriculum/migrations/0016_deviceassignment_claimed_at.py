from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("curriculum", "0015_t08_closure_receipt_and_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="deviceassignment",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="reclamada en",
            ),
        ),
    ]
