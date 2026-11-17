from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0020_reliable_sort_pipeline"),
    ]

    # 24832 == core.cloud_paths.CLOUD_FILE_URL_MAX_LENGTH
    operations = [
        migrations.AlterField(
            model_name="projectworkspace",
            name="public_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=24832,
                verbose_name="Публичная ссылка",
            ),
        ),
        migrations.AlterField(
            model_name="checklistitemfolder",
            name="public_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=24832,
                verbose_name="Публичная ссылка",
            ),
        ),
        migrations.AlterField(
            model_name="sourcedatasectionfolder",
            name="public_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=24832,
                verbose_name="Публичная ссылка",
            ),
        ),
        migrations.AlterField(
            model_name="sourcedataitemfolder",
            name="public_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=24832,
                verbose_name="Публичная ссылка",
            ),
        ),
    ]
