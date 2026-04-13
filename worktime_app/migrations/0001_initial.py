from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects_app", "0049_performer_work_hours"),
        ("users_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorktimeAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("executor_name", models.CharField(db_index=True, max_length=255, verbose_name="Исполнитель")),
                ("source_type", models.CharField(choices=[("performer_confirmation", "Подтверждение исполнителя"), ("project_manager", "Руководитель проекта"), ("direction_head_request", "Запрос руководителю направления")], default="performer_confirmation", max_length=40, verbose_name="Источник создания")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("employee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="worktime_assignments", to="users_app.employee", verbose_name="Сотрудник")),
                ("performer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="worktime_assignments", to="projects_app.performer", verbose_name="Строка исполнителя")),
                ("registration", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="worktime_assignments", to="projects_app.projectregistration", verbose_name="Проект")),
            ],
            options={
                "verbose_name": "Строка табеля",
                "verbose_name_plural": "Строки табеля",
                "ordering": ["executor_name", "registration__position", "registration__id", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("registration", "executor_name"), name="worktime_assignment_project_executor_unique"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorktimeEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("work_date", models.DateField(verbose_name="Дата")),
                ("hours", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(24)], verbose_name="Количество часов")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="worktime_app.worktimeassignment", verbose_name="Строка табеля")),
            ],
            options={
                "verbose_name": "Запись табеля",
                "verbose_name_plural": "Записи табеля",
                "ordering": ["work_date", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("assignment", "work_date"), name="worktime_entry_assignment_date_unique"),
                ],
            },
        ),
    ]
