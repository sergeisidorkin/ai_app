from django.db import migrations
from django.db.models import Max


def seed_stage_terms_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    variable = ProposalVariable.objects.filter(key="[[stage_terms]]").first()
    defaults = {
        "description": "Сроки сдачи Предварительного и Итогового отчета по этапу",
        "is_computed": True,
        "source_section": "",
        "source_table": "",
        "source_column": "",
    }
    if variable:
        for field, value in defaults.items():
            setattr(variable, field, value)
        variable.save(update_fields=list(defaults))
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[stage_terms]]",
        position=max_position + 1,
        **defaults,
    )


def remove_stage_terms_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0051_seed_final_report_term_month_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_stage_terms_variable,
            remove_stage_terms_variable,
        ),
    ]
