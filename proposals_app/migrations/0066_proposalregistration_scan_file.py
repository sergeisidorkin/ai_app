from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0065_proposalregistration_project_start_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="scan_file_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Наименование файла скана",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="scan_file_link",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Ссылка на скан",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="scan_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор скана в Nextcloud",
            ),
        ),
    ]
