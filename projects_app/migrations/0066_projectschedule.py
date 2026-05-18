from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0065_projectregistration_evaluation_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("row_number", models.CharField(blank=True, max_length=50, verbose_name="№")),
                ("task", models.CharField(blank=True, max_length=255, verbose_name="Задача")),
                ("start_date", models.DateField(blank=True, null=True, verbose_name="Начало")),
                ("end_date", models.DateField(blank=True, null=True, verbose_name="Окончание")),
                ("specialty", models.CharField(blank=True, max_length=255, verbose_name="Специальность")),
                ("executor", models.CharField(blank=True, max_length=255, verbose_name="Исполнитель")),
                ("deadline", models.DateField(blank=True, null=True, verbose_name="Дедлайн")),
                ("constraint", models.CharField(blank=True, max_length=255, verbose_name="Ограничение")),
                (
                    "duration",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Длительность",
                    ),
                ),
                (
                    "duration_star",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Длительность*",
                    ),
                ),
                ("predecessors", models.CharField(blank=True, max_length=255, verbose_name="Предшественники")),
                (
                    "progress",
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                        verbose_name="Прогресс",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule_items",
                        to="projects_app.projectregistration",
                        verbose_name="Проект",
                    ),
                ),
            ],
            options={
                "verbose_name": "График проекта",
                "verbose_name_plural": "График проекта",
                "ordering": ["project__position", "position", "id"],
            },
        ),
    ]
