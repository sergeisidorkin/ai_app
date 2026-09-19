from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0086_report_check_full_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="check_file_name",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="Имя файла проверки"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_file_link",
            field=models.URLField(blank=True, default="", max_length=2000, verbose_name="Ссылка на файл проверки"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_cloud_path",
            field=models.CharField(blank=True, default="", max_length=2048, verbose_name="Путь файла проверки"),
        ),
    ]
