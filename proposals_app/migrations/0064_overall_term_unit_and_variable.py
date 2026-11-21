from django.db import migrations, models
from django.db.models import Max


def rename_final_report_term_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    description = "Срок оказания услуг от получения исходных данных до сдачи Итогового отчёта"
    current = ProposalVariable.objects.filter(key="{{final_report_term_month}}").first()
    renamed = ProposalVariable.objects.filter(key="{{final_report_term}}").first()
    if current and renamed and current.pk != renamed.pk:
        current.delete()
        renamed.description = description
        renamed.is_computed = True
        renamed.save(update_fields=["description", "is_computed"])
        return
    variable = current or renamed
    if variable is None:
        max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
        ProposalVariable.objects.create(
            key="{{final_report_term}}",
            position=max_position + 1,
            description=description,
            is_computed=True,
        )
        return
    variable.key = "{{final_report_term}}"
    variable.description = description
    variable.is_computed = True
    variable.source_section = ""
    variable.source_table = ""
    variable.source_column = ""
    variable.save()


def restore_final_report_term_month_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    variable = ProposalVariable.objects.filter(key="{{final_report_term}}").first()
    if variable is None:
        return
    variable.key = "{{final_report_term_month}}"
    variable.description = "Срок оказания услуг от получения исходных данных до сдачи Итогового отчёта в месяцах"
    variable.save(update_fields=["key", "description"])


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0063_proposal_dispatch_letter"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="overall_term_unit",
            field=models.CharField(
                blank=True,
                choices=[("days", "дн."), ("weeks", "нед."), ("months", "мес.")],
                default="months",
                max_length=10,
                verbose_name="Единица общего срока",
            ),
        ),
        migrations.RunPython(
            rename_final_report_term_variable,
            restore_final_report_term_month_variable,
        ),
    ]
