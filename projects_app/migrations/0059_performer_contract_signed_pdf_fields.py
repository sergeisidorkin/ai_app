from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0058_performer_contract_group_member"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_signed_pdf_file",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Подписанный договор",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_signed_pdf_link",
            field=models.URLField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Ссылка на подписанный договор",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_signed_pdf_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор подписанного договора в Nextcloud",
            ),
        ),
    ]
