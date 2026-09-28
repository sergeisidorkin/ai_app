from django.db import migrations, models


def set_skill_reasoning_off(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    ReportMacro.objects.filter(check_kind="skill", reasoning_effort="").update(
        reasoning_effort="off"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0111_report_remarks_notice_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="reasoning_effort",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="Уровень рассуждений",
            ),
        ),
        migrations.RunPython(set_skill_reasoning_off, migrations.RunPython.noop),
    ]
