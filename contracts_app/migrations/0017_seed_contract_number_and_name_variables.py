from django.db import migrations
from django.db.models import Max


def seed_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    if not ContractVariable.objects.filter(key="{{number_of_contract}}").exists():
        mx_pos += 1
        ContractVariable.objects.create(
            key="{{number_of_contract}}",
            description="Номер договора (автоматически генерируется)",
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=mx_pos,
        )

    if not ContractVariable.objects.filter(key="{{contract_name}}").exists():
        mx_pos += 1
        ContractVariable.objects.create(
            key="{{contract_name}}",
            description="Предмет договора (по продукту исполнителя)",
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=mx_pos,
        )


def remove_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(
        key__in=["{{number_of_contract}}", "{{contract_name}}"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0016_contractsubject"),
    ]

    operations = [
        migrations.RunPython(seed_vars, remove_vars),
    ]
