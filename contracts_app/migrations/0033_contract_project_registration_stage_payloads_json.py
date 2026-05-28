from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0032_contract_project_registration_contract_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="stage_payloads_json",
            field=models.JSONField(blank=True, default=list, verbose_name="Данные этапов договора"),
        ),
    ]
