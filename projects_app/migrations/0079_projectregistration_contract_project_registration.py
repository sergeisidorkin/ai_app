import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0078_payment_request_performer_proxy"),
        ("contracts_app", "0035_alter_contractprojectregistration_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="contract_project_registration",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_project_registrations",
                to="contracts_app.contractprojectregistration",
                verbose_name="Договор ID",
            ),
        ),
    ]
