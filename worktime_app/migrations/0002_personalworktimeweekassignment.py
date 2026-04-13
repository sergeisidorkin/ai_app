from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("worktime_app", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worktimeassignment",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("performer_confirmation", "Подтверждение исполнителя"),
                    ("project_manager", "Руководитель проекта"),
                    ("direction_head_request", "Запрос руководителю направления"),
                    ("manual_personal_week", "Личный табель по неделе"),
                ],
                default="performer_confirmation",
                max_length=40,
                verbose_name="Источник создания",
            ),
        ),
        migrations.CreateModel(
            name="PersonalWorktimeWeekAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField(verbose_name="Начало недели")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personal_week_links",
                        to="worktime_app.worktimeassignment",
                        verbose_name="Строка табеля",
                    ),
                ),
            ],
            options={
                "verbose_name": "Недельная строка личного табеля",
                "verbose_name_plural": "Недельные строки личного табеля",
                "ordering": ["week_start", "assignment__executor_name", "assignment__registration__id", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="personalworktimeweekassignment",
            constraint=models.UniqueConstraint(
                fields=("assignment", "week_start"),
                name="worktime_personal_week_assignment_unique",
            ),
        ),
    ]
