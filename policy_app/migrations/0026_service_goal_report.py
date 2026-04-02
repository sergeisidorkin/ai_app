from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0025_create_group_lawyer"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceGoalReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_goal", models.TextField(blank=True, default="", verbose_name="Цели оказания услуг")),
                ("report_title", models.TextField(blank=True, default="", verbose_name="Название отчета")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_goal_reports",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
            ],
            options={
                "verbose_name": "Цель услуги и название отчета",
                "verbose_name_plural": "Цели услуг и названия отчетов",
                "ordering": ["product__short_name", "position", "id"],
            },
        ),
    ]
