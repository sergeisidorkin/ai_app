from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0043_performer_scan_document_and_upload_datetime"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_employee_scan_link",
            field=models.URLField(
                "Ссылка на скан сотрудника",
                max_length=500,
                blank=True,
                default="",
            ),
        ),
    ]
