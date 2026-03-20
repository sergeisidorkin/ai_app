from django.db import migrations
from django.db.models import Max


def seed_list_var(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    if not ContractVariable.objects.filter(key="[[actives_name]]").exists():
        mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0
        ContractVariable.objects.create(
            key="[[actives_name]]",
            description="Список наименований активов (маркированный список)",
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=mx_pos + 1,
        )


def remove_list_var(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="[[actives_name]]").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0013_seed_date_and_gender_variables"),
    ]

    operations = [
        migrations.RunPython(seed_list_var, remove_list_var),
    ]
