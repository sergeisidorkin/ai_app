from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0048_alter_contractprojectregistration_products"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="contract_end",
            field=models.DateField(blank=True, null=True, verbose_name="Окончание договора"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="contract_end_enabled",
            field=models.BooleanField(default=True, verbose_name="Окончание договора включено"),
        ),
    ]
