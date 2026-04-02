from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0017_proposalregistration_commercial_totals_json"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="status",
            field=models.CharField(
                choices=[("preliminary", "Предварительное"), ("final", "Итоговое")],
                db_index=True,
                default="final",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
    ]
