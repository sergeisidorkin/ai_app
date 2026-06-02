from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0038_seed_by_name_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="contract_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата договора"),
        ),
    ]
