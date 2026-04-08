from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0023_proposalregistration_dispatch_recipient_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="transfer_to_contract_date",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Дата передачи для составления договора",
            ),
        ),
    ]
