from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0055_performer_contract_project_folder_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор проекта договора в Nextcloud",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_project_folder_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор папки проекта договора в Nextcloud",
            ),
        ),
    ]
