from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0036_seed_contract_additional_variables"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="contractprojectregistrationproduct",
            unique_together=set(),
        ),
    ]
