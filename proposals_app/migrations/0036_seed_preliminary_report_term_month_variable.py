from django.db import migrations
from django.db.models import Max


def seed_preliminary_report_term_month_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{preliminary_report_term_month}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{preliminary_report_term_month}}",
        description="Срок оказания услуг от получения исходных данных до сдачи Предварительного отчёта в месяцах",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_preliminary_report_term_month_variable(apps, schema_editor):
    # Safe rollback: avoid deleting a variable that may have existed before this migration.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0035_seed_preliminary_payment_percentage_full_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_preliminary_report_term_month_variable,
            remove_preliminary_report_term_month_variable,
        ),
    ]
