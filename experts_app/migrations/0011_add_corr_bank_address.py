# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0010_change_self_employed_to_datefield"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofile",
            name="corr_bank_address",
            field=models.CharField(
                "Адрес банка-корреспондента", max_length=512, blank=True, default=""
            ),
        ),
    ]
