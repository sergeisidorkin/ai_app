from django.db import migrations
from django.db.models import Max


def seed_computed_variables(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0

    for key, description in [
        ("{{year}}", "Текущий год (гггг)"),
        ("{{day}}", "Текущий день (дд)"),
        ("{{month}}", "Текущий месяц на русском языке"),
    ]:
        if ProposalVariable.objects.filter(key=key).exists():
            continue
        max_position += 1
        ProposalVariable.objects.create(
            key=key,
            description=description,
            position=max_position,
            source_section="",
            source_table="",
            source_column="",
        )


def remove_computed_variables(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(
        key__in=["{{year}}", "{{day}}", "{{month}}"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0025_proposalregistration_regions"),
    ]

    operations = [
        migrations.RunPython(
            seed_computed_variables,
            remove_computed_variables,
        ),
    ]
