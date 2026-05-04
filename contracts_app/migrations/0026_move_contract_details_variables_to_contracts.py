from django.db import migrations


def move_contract_details_variables_to_contracts(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(
        source_section="experts",
        source_table="contract_details",
    ).update(source_section="contracts")


def move_contract_details_variables_to_experts(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(
        source_section="contracts",
        source_table="contract_details",
    ).update(source_section="experts")


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0025_seed_performer_facsimile_variable"),
    ]

    operations = [
        migrations.RunPython(
            move_contract_details_variables_to_contracts,
            move_contract_details_variables_to_experts,
        ),
    ]
