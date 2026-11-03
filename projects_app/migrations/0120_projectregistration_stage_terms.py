from django.db import migrations, models


def copy_contract_start_to_project_start(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    ProjectRegistration.objects.filter(
        project_start_date__isnull=True,
        contract_start__isnull=False,
    ).update(project_start_date=models.F("contract_start"))


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0119_registration_group_summary_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="project_start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата начала проекта"),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="stage_terms_json",
            field=models.JSONField(blank=True, default=list, verbose_name="Сроки этапов"),
        ),
        migrations.RunPython(copy_contract_start_to_project_start, migrations.RunPython.noop),
    ]
