from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0035_servicegoalreport_service_goal_genitive"),
    ]

    operations = [
        migrations.CreateModel(
            name="TypicalServiceTerm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "preliminary_report_months",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=6,
                        validators=[MinValueValidator(0)],
                        verbose_name="Срок подготовки Предварительного отчёта, мес.",
                    ),
                ),
                (
                    "final_report_weeks",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Срок подготовки Итогового отчёта, нед.",
                    ),
                ),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="typical_service_terms",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
            ],
            options={
                "verbose_name": "Типовой срок оказания услуг",
                "verbose_name_plural": "Типовые сроки оказания услуг",
                "ordering": ["position", "id"],
            },
        ),
    ]
