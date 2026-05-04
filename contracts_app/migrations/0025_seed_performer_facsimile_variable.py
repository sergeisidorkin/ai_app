from django.db import migrations
from django.db.models import Max


def seed_performer_facsimile_variable(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    key = "[[facsimile_prfrm]]"
    description = "Подпись исполнителя"

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
        return

    max_position = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ContractVariable.objects.create(
        key=key,
        description=description,
        is_computed=True,
        source_section="",
        source_table="",
        source_column="",
        position=max_position + 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0024_seed_contract_image_variables"),
    ]

    operations = [
        migrations.RunPython(seed_performer_facsimile_variable, migrations.RunPython.noop),
    ]
