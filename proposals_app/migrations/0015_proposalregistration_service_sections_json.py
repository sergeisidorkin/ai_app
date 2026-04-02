from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0014_proposalregistration_proposal_project_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="service_sections_json",
            field=models.JSONField(blank=True, default=list, verbose_name="Состав услуг: разделы"),
        ),
    ]
