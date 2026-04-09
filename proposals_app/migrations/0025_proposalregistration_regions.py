from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0024_proposalregistration_transfer_to_contract_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион владельца активов"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="registration_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион"),
        ),
    ]
