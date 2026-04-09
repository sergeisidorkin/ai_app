from django.db import migrations
from django.db.models import Max


def seed_owner_country_full_name_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{owner_country_full_name}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{owner_country_full_name}}",
        description="Наименование страны Владельца активов (полное)",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_owner_country_full_name_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="{{owner_country_full_name}}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0027_proposalvariable_is_computed_and_client_country"),
    ]

    operations = [
        migrations.RunPython(
            seed_owner_country_full_name_variable,
            remove_owner_country_full_name_variable,
        ),
    ]
