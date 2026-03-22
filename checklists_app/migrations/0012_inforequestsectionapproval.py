import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0011_add_unique_constraints_to_source_data_folders"),
        ("projects_app", "0019_performer_info_approval_at_and_more"),
        ("policy_app", "0018_alter_typicalsection_executor_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InfoRequestSectionApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("approved_at", models.DateTimeField(verbose_name="Дата согласования")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="info_request_section_approvals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто согласовал",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="info_request_section_approvals",
                        to="projects_app.projectregistration",
                        verbose_name="Проект",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="info_request_approvals",
                        to="policy_app.typicalsection",
                        verbose_name="Типовой раздел",
                    ),
                ),
            ],
            options={
                "verbose_name": "Согласование раздела запроса",
                "verbose_name_plural": "Согласования разделов запросов",
                "unique_together": {("project", "section", "approved_by")},
            },
        ),
    ]
