from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0049_reportstructure"),
        ("projects_app", "0083_full_report_upload"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportCheckRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "check_type",
                    models.CharField(
                        choices=[("skill", "Навык"), ("macro", "Макрос")],
                        db_index=True,
                        default="skill",
                        max_length=16,
                        verbose_name="Тип проверки",
                    ),
                ),
                ("check_value", models.CharField(max_length=255, verbose_name="Проверка")),
                ("model_id", models.CharField(blank=True, default="", max_length=255, verbose_name="Модель")),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_check_rules",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_check_rules",
                        to="policy_app.typicalsection",
                        verbose_name="Раздел",
                    ),
                ),
            ],
            options={
                "verbose_name": "Правило проверки отчёта",
                "verbose_name_plural": "Правила проверки отчётов",
                "ordering": ["position", "id"],
            },
        ),
    ]
