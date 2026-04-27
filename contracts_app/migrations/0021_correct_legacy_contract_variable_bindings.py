from django.db import migrations


CORRECTED_BINDINGS = {
    "{{short_name}}": {
        "description": "Фамилия И.О. исполнителя",
        "source_section": "contacts",
        "source_table": "persons",
        "source_column": "short_name",
    },
    "{{name}}": {
        "description": "Заказчик проекта",
        "source_section": "projects",
        "source_table": "registration",
        "source_column": "customer",
    },
    "{{country}}": {
        "description": "Полное наименование страны исполнителя по ОКСМ",
        "source_section": "classifiers",
        "source_table": "oksm_countries",
        "source_column": "full_name",
    },
}


def correct_legacy_contract_variable_bindings(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    for key, binding in CORRECTED_BINDINGS.items():
        ContractVariable.objects.filter(key=key, is_computed=False).update(**binding)


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0020_seed_project_registration_variables"),
    ]

    operations = [
        migrations.RunPython(correct_legacy_contract_variable_bindings, migrations.RunPython.noop),
    ]
