from django.db import migrations
from django.db.models import Max


def seed_tkp_preliminary_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{tkp_preliminary}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{tkp_preliminary}}",
        description="Предварительное ТКП на титуле",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_tkp_preliminary_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="{{tkp_preliminary}}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0033_proposalregistration_final_report_term_weeks"),
    ]

    operations = [
        migrations.RunPython(
            seed_tkp_preliminary_variable,
            remove_tkp_preliminary_variable,
        ),
    ]
