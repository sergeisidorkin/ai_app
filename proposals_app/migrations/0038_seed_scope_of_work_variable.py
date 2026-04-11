from django.db import migrations
from django.db.models import Max


def seed_scope_of_work_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="[[scope_of_work]]").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[scope_of_work]]",
        description="Состав оказываемых услуг",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_scope_of_work_variable(apps, schema_editor):
    # Safe rollback: avoid deleting a variable that may have existed before this migration.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0037_proposalregistration_service_editor_states"),
    ]

    operations = [
        migrations.RunPython(
            seed_scope_of_work_variable,
            remove_scope_of_work_variable,
        ),
    ]
