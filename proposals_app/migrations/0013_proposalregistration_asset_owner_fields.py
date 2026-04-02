from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0013_legalentityrecord"),
        ("proposals_app", "0012_proposalcommercialoffer_service_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Владелец активов"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_asset_owner_registrations",
                to="classifiers_app.oksmcountry",
                verbose_name="Страна владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_identifier",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Идентификатор владельца активов"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_matches_customer",
            field=models.BooleanField(default=True, verbose_name="Совпадает с Заказчиком"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_registration_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата регистрации владельца активов"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_registration_number",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Регистрационный номер владельца активов"),
        ),
    ]
