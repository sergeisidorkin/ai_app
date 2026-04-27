from django.db import migrations
from django.db.models import Max


def seed_payment_schedule_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="[[payment_schedule]]").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[payment_schedule]]",
        description="График оплаты",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_payment_schedule_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0044_alter_proposalregistration_status"),
    ]

    operations = [
        migrations.RunPython(
            seed_payment_schedule_variable,
            remove_payment_schedule_variable,
        ),
    ]
