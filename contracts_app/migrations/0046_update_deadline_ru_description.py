from django.db import migrations


OLD_DESCRIPTION = "Позднейший дедлайн разделов исполнителя из графика проекта в формате «дд месяц гггг г.»"
NEW_DESCRIPTION = "Дедлайн из реестра проектов в формате «дд месяц гггг г.»"


def update_deadline_ru_description(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="{{deadline_ru}}").update(
        description=NEW_DESCRIPTION,
    )


def revert_deadline_ru_description(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="{{deadline_ru}}").update(
        description=OLD_DESCRIPTION,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0045_contracttemplate_act_fields"),
    ]

    operations = [
        migrations.RunPython(update_deadline_ru_description, revert_deadline_ru_description),
    ]
