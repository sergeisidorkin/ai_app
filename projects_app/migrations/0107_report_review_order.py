from django.db import migrations, models

import projects_app.models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0106_report_check_pipeline"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="project_coordinator",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Координатор проекта"),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="project_coordinator_prs_id",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="ID-PRS координатора проекта"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="review_step",
            field=models.CharField(blank=True, default="", max_length=8, verbose_name="Шаг проверки"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="review_phase",
            field=models.CharField(blank=True, default="", max_length=8, verbose_name="Фаза шага"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="status_changed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата статуса"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="review_file_name",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="Имя файла замечаний"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="review_file_link",
            field=models.URLField(blank=True, default="", max_length=2000, verbose_name="Ссылка на файл замечаний"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="review_cloud_path",
            field=models.CharField(blank=True, default="", max_length=2048, verbose_name="Путь файла замечаний"),
        ),
        migrations.AddField(
            model_name="reportcheckrule",
            name="review_order",
            field=models.JSONField(
                blank=True,
                default=projects_app.models.default_report_review_order,
                verbose_name="Порядок",
            ),
        ),
    ]
