from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0052_production_calendar_day_details"),
        ("contracts_app", "0049_contract_project_registration_contract_end"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="customer_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_customer_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор заказчика",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="asset_owner_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_asset_owner_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор владельца активов",
            ),
        ),
    ]
