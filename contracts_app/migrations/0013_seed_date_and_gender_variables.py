from django.db import migrations
from django.db.models import Max


def seed_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, desc in [
        ("{{deadline_ru}}", "Дедлайн проекта в формате «дд месяц гггг г.»"),
        ("{{year}}", "Текущий год (гггг)"),
        ("{{day}}", "Текущий день (дд)"),
        ("{{month}}", "Текущий месяц на русском языке"),
        ("{{named}}", "«именуемый» / «именуемая» в зависимости от пола исполнителя"),
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


def remove_vars(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key__in=[
        "{{deadline_ru}}", "{{year}}", "{{day}}", "{{month}}", "{{named}}",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0012_seed_text_variables"),
    ]

    operations = [
        migrations.RunPython(seed_vars, remove_vars),
    ]
