from django.db import migrations
from django.db.models import Max


IMAGE_VARIABLES = [
    ("[[seal]]", "Печать организации"),
    ("[[facsimile_imcm]]", "Подпись руководителя организации"),
]


def seed_contract_image_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    max_position = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, description in IMAGE_VARIABLES:
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


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0023_contracttemplate_products"),
    ]

    operations = [
        migrations.RunPython(seed_contract_image_variables, migrations.RunPython.noop),
    ]
