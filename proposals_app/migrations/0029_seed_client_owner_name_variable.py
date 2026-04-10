from django.db import migrations
from django.db.models import Max


def seed_client_owner_name_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{client_owner_name}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{client_owner_name}}",
        description="Наименование заказчика и владельца активов на титуле",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_client_owner_name_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="{{client_owner_name}}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0028_seed_owner_country_full_name_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_client_owner_name_variable,
            remove_client_owner_name_variable,
        ),
    ]
