from django.db import migrations
from django.db.models import Max


PROJECT_VARIABLES = [
    ("{{short_name}}", "Краткое имя продукта проекта", "short_name"),
    ("{{name}}", "Название проекта", "name"),
    ("{{country}}", "Страна проекта", "country"),
]


def seed_project_registration_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, description, source_column in PROJECT_VARIABLES:
        obj = ContractVariable.objects.filter(key=key).first()
        if obj is None:
            mx_pos += 1
            ContractVariable.objects.create(
                key=key,
                description=description,
                is_computed=False,
                source_section="projects",
                source_table="registration",
                source_column=source_column,
                position=mx_pos,
            )
            continue

        if not obj.is_computed:
            obj.description = obj.description or description
            obj.source_section = "projects"
            obj.source_table = "registration"
            obj.source_column = source_column
            obj.save(update_fields=[
                "description",
                "source_section",
                "source_table",
                "source_column",
            ])


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0019_bind_contract_details_variables"),
    ]

    operations = [
        migrations.RunPython(seed_project_registration_variables, migrations.RunPython.noop),
    ]
