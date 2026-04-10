from django.db import migrations
from django.db.models import Max


def seed_service_goal_genitive_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{service_goal_genitive}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{service_goal_genitive}}",
        description="Цель оказания услуг в родительном падеже",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_service_goal_genitive_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="{{service_goal_genitive}}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0030_seed_service_type_short_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_service_goal_genitive_variable,
            remove_service_goal_genitive_variable,
        ),
    ]
