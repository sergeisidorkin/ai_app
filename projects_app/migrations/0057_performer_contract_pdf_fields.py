from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0056_performer_contract_nextcloud_file_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_pdf_file",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Файл договора PDF",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_pdf_link",
            field=models.URLField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Ссылка на PDF договора",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_pdf_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор PDF договора в Nextcloud",
            ),
        ),
    ]
