from django.db import migrations


OLD_DESCRIPTION = "Многоуровневый список: активы, разделы, подразделы"
NEW_DESCRIPTION = "Многоуровневый список: этапы, активы, разделы, подразделы"


def update_chapters_name_description(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="[[chapters_name]]").update(
        description=NEW_DESCRIPTION,
    )


def revert_chapters_name_description(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="[[chapters_name]]").update(
        description=OLD_DESCRIPTION,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0028_update_deadline_ru_description"),
    ]

    operations = [
        migrations.RunPython(update_chapters_name_description, revert_chapters_name_description),
    ]
