from django.db import migrations


def update_deadline_ru_description(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="{{deadline_ru}}").update(
        description="Позднейший дедлайн разделов исполнителя из графика проекта в формате «дд месяц гггг г.»"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0027_contractreturncomment"),
    ]

    operations = [
        migrations.RunPython(update_deadline_ru_description, migrations.RunPython.noop),
    ]
