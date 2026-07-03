from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0044_contract_project_registration_service_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contracttemplate",
            name="act_sample_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=512,
                verbose_name="Наименование образца акта",
            ),
        ),
        migrations.AddField(
            model_name="contracttemplate",
            name="act_version",
            field=models.CharField(
                blank=True,
                default="",
                max_length=128,
                verbose_name="Версия акта",
            ),
        ),
        migrations.AddField(
            model_name="contracttemplate",
            name="act_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to="contract_templates/",
                verbose_name="Файл акта",
            ),
        ),
    ]
