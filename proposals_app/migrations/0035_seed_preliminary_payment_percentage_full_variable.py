from django.db import migrations
from django.db.models import Max


def seed_preliminary_payment_percentage_full_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{preliminary_payment_percentage_full}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{preliminary_payment_percentage_full}}",
        description="Размер оплаты Предварительного отчёта в процентах (с учетом предоплаты)",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_preliminary_payment_percentage_full_variable(apps, schema_editor):
    # Safe rollback: avoid deleting a variable that may have existed before this migration.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0034_seed_tkp_preliminary_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_preliminary_payment_percentage_full_variable,
            remove_preliminary_payment_percentage_full_variable,
        ),
    ]
