from django.db import migrations
from django.db.models import Max


def seed_actives_name_list_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="[[actives_name]]").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[actives_name]]",
        description="Список наименований активов",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_actives_name_list_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="[[actives_name]]").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0031_seed_service_goal_genitive_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_actives_name_list_variable,
            remove_actives_name_list_variable,
        ),
    ]
