from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0013_proposalregistration_asset_owner_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="proposal_project_name",
            field=models.TextField(blank=True, default="", verbose_name="Наименование ТКП (проекта)"),
        ),
    ]
