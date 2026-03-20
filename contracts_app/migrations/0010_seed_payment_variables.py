from django.db import migrations
from django.db.models import Max


def seed_payment_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, desc in [
        ("{{avansplat_sum}}", "Сумма авансового платежа (contract_price × Аванс%)"),
        ("{{finplat_sum}}", "Сумма окончательного платежа (contract_price − avansplat_sum)"),
    ]:
        if not ContractVariable.objects.filter(key=key).exists():
            mx_pos += 1
            ContractVariable.objects.create(
                key=key,
                description=desc,
                is_computed=True,
                source_section="",
                source_table="",
                source_column="",
                position=mx_pos,
            )


def remove_payment_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(
        key__in=["{{avansplat_sum}}", "{{finplat_sum}}"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0009_seed_contract_price_variable"),
    ]

    operations = [
        migrations.RunPython(seed_payment_vars, remove_payment_vars),
    ]
