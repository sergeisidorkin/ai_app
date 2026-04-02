from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0016_proposalregistration_service_composition_mode_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="commercial_totals_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="Итоги коммерческого предложения"),
        ),
    ]
