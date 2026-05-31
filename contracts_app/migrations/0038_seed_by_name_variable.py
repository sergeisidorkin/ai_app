from django.db import migrations
from django.db.models import Max


KEY = "{{by_name}}"
DESCRIPTION = "Вставка « по заказу {{name}}» при расхождении Заказчика и Владельца активов"


def seed_by_name_variable(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    variable = ContractVariable.objects.filter(key=KEY).first()
    if variable:
        variable.description = DESCRIPTION
        variable.is_computed = True
        variable.source_section = ""
        variable.source_table = ""
        variable.source_column = ""
        variable.save(
            update_fields=[
                "description",
                "is_computed",
                "source_section",
                "source_table",
                "source_column",
            ]
        )
        return

    max_position = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ContractVariable.objects.create(
        key=KEY,
        description=DESCRIPTION,
        is_computed=True,
        source_section="",
        source_table="",
        source_column="",
        position=max_position + 1,
    )


def remove_by_name_variable(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key=KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0037_allow_duplicate_contract_project_products"),
    ]

    operations = [
        migrations.RunPython(seed_by_name_variable, remove_by_name_variable),
    ]
