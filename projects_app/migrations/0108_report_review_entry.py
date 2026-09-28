from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0107_report_review_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="step_revision",
            field=models.BooleanField(default=False, verbose_name="Файл шага проверки"),
        ),
        migrations.CreateModel(
            name="ReportReviewEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("step", models.CharField(blank=True, default="", max_length=8, verbose_name="Шаг")),
                ("phase", models.CharField(blank=True, default="", max_length=8, verbose_name="Фаза")),
                ("settled", models.BooleanField(default=False, verbose_name="Шаг закрыт файлом")),
                ("review_file_name", models.CharField(blank=True, default="", max_length=500, verbose_name="Имя файла замечаний")),
                ("review_file_link", models.URLField(blank=True, default="", max_length=2000, verbose_name="Ссылка на файл замечаний")),
                ("review_cloud_path", models.CharField(blank=True, default="", max_length=2048, verbose_name="Путь файла замечаний")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата статуса")),
                ("basis_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="next_entries", to="projects_app.reportreviewentry", verbose_name="Файл предыдущего шага")),
                ("upload", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_entries", to="projects_app.performerreportupload", verbose_name="Файл")),
            ],
            options={
                "verbose_name": "Строка шага проверки",
                "verbose_name_plural": "Строки шагов проверки",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
