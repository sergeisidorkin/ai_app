from django.db import migrations
from django.db.models import Max


VARIABLES = [
    ("{{owner}}", "Владелец активов"),
    ("{{service_goal_genitive}}", "Цель оказания услуг в родительном падеже"),
    ("{{specialization}}", "Область специализации"),
    ("[[services]]", "Многоуровневый список: этапы, состав услуг"),
]


def seed_contract_additional_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    max_position = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, description in VARIABLES:
        variable = ContractVariable.objects.filter(key=key).first()
        if variable:
            variable.description = description
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
            continue

        max_position += 1
        ContractVariable.objects.create(
            key=key,
            description=description,
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=max_position,
        )


def remove_contract_additional_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key__in=[key for key, _description in VARIABLES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0035_alter_contractprojectregistration_status"),
    ]

    operations = [
        migrations.RunPython(
            seed_contract_additional_variables,
            remove_contract_additional_variables,
        ),
    ]
