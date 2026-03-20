from django.db import migrations
from django.db.models import Max


def seed_contract_price(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    if not ContractVariable.objects.filter(key="{{contract_price}}").exists():
        mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0
        ContractVariable.objects.create(
            key="{{contract_price}}",
            description="Сумма столбца «Согласовано» по выделенным строкам исполнителя",
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=mx_pos + 1,
        )


def remove_contract_price(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="{{contract_price}}").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0008_add_contractvariable_is_computed"),
    ]

    operations = [
        migrations.RunPython(seed_contract_price, remove_contract_price),
    ]
