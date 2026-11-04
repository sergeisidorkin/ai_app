from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0052_production_calendar_day_details"),
        ("projects_app", "0128_sync_tpgr_google_drive_footnotes"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="customer_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_customer_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор заказчика",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_asset_owner_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор владельца активов",
            ),
        ),
    ]
