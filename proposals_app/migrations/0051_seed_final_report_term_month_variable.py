from django.db import migrations
from django.db.models import Max


def seed_final_report_term_month_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    variable = ProposalVariable.objects.filter(key="{{final_report_term_month}}").first()
    defaults = {
        "description": "Срок оказания услуг от получения исходных данных до сдачи Итогового отчёта в месяцах",
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
        key="{{final_report_term_month}}",
        position=max_position + 1,
        **defaults,
    )


def remove_final_report_term_month_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0050_seed_product_name_list_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_final_report_term_month_variable,
            remove_final_report_term_month_variable,
        ),
    ]
