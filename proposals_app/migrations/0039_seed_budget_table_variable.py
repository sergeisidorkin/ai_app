from django.db import migrations
from django.db.models import Max


def seed_budget_table_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="[[budget_table]]").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[budget_table]]",
        description="Расчёт вознаграждения за оказание услуг",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_budget_table_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0038_seed_scope_of_work_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_budget_table_variable,
            remove_budget_table_variable,
        ),
    ]
