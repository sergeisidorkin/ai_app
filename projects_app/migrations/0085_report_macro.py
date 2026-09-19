from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0084_report_check_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="check_error",
            field=models.TextField(blank=True, default="", verbose_name="Ошибка проверки"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_finding_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Замечаний"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_status",
            field=models.CharField(
                blank=True,
                choices=[("", "—"), ("running", "Проверяется"), ("done", "Проверено"), ("error", "Ошибка")],
                db_index=True,
                default="",
                max_length=16,
                verbose_name="Статус проверки",
            ),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="checked_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата проверки"),
        ),
        migrations.CreateModel(
            name="ReportMacro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("description", models.CharField(blank=True, default="", max_length=500, verbose_name="Описание")),
                ("code", models.TextField(verbose_name="Код")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
            ],
            options={
                "verbose_name": "Макрос проверки отчёта",
                "verbose_name_plural": "Макросы проверки отчётов",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddField(
            model_name="reportcheckrule",
            name="macros",
            field=models.ManyToManyField(
                blank=True,
                related_name="check_rules",
                to="projects_app.reportmacro",
                verbose_name="Макросы",
            ),
        ),
    ]
