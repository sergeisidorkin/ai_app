from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0027_alter_service_goal_report_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="TypicalServiceComposition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_composition", models.TextField(blank=True, default="", verbose_name="Состав услуг")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="typical_service_compositions",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="typical_service_compositions",
                        to="policy_app.typicalsection",
                        verbose_name="Раздел (услуга)",
                    ),
                ),
            ],
            options={
                "verbose_name": "Типовой состав услуг",
                "verbose_name_plural": "Типовой состав услуг",
                "ordering": ["position", "id"],
            },
        ),
    ]
