from django.db import migrations
from django.db.models import Max


def seed_kopecks_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, desc in [
        ("{{avansplat_sum_kop}}", "Копейки авансового платежа (дробная часть avansplat_sum)"),
        ("{{finplat_sum_kop}}", "Копейки окончательного платежа (дробная часть finplat_sum)"),
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


def remove_kopecks_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(
        key__in=["{{avansplat_sum_kop}}", "{{finplat_sum_kop}}"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0010_seed_payment_variables"),
    ]

    operations = [
        migrations.RunPython(seed_kopecks_vars, remove_kopecks_vars),
    ]
