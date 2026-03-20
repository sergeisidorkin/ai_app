from django.db import migrations
from django.db.models import Max


def seed_text_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, desc in [
        ("{{contract_price_text}}", "Сумма контракта прописью"),
        ("{{avansplat_sum_text}}", "Сумма авансового платежа прописью"),
        ("{{avansplat_sum_kop_text}}", "Копейки авансового платежа прописью"),
        ("{{finplat_sum_text}}", "Сумма окончательного платежа прописью"),
        ("{{finplat_sum_kop_text}}", "Копейки окончательного платежа прописью"),
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


def remove_text_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key__in=[
        "{{contract_price_text}}",
        "{{avansplat_sum_text}}",
        "{{avansplat_sum_kop_text}}",
        "{{finplat_sum_text}}",
        "{{finplat_sum_kop_text}}",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0011_seed_kopecks_variables"),
    ]

    operations = [
        migrations.RunPython(seed_text_vars, remove_text_vars),
    ]
