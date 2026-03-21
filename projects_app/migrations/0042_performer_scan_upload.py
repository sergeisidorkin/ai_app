from django.db import migrations, models


def clear_text_scan_values(apps, schema_editor):
    Performer = apps.get_model("projects_app", "Performer")
    Performer.objects.exclude(contract_employee_scan="").update(contract_employee_scan="")


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0041_performer_contract_employee_scan_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_disk_folder",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Папка проекта на Яндекс.Диске",
            ),
        ),
        migrations.RunPython(clear_text_scan_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="performer",
            name="contract_employee_scan",
            field=models.FileField(
                blank=True,
                default="",
                upload_to="contract_employee_scans/",
                verbose_name="Скан с подписью сотрудника",
            ),
        ),
    ]
