from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0052_production_calendar_day_details"),
        ("projects_app", "0062_projectregistration_registration_region"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Владелец активов"),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_asset_owner_registrations",
                to="classifiers_app.oksmcountry",
                verbose_name="Страна владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_identifier",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_registration_number",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Регистрационный номер владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_region",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Регион владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_registration_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Дата регистрации владельца активов",
            ),
        ),
    ]
