from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def seed_reports_role(apps, schema_editor):
    Folder = apps.get_model("projects_app", "RegistrationWorkspaceFolder")
    by_user = {}
    for folder in Folder.objects.all().order_by("position", "id"):
        by_user.setdefault(folder.user_id, []).append(folder)
    for folders in by_user.values():
        if any(item.role == "reports" for item in folders):
            continue
        target = next((item for item in folders if item.name == "06 Отчеты"), None)
        if target is None:
            continue
        target.role = "reports"
        target.save(update_fields=["role"])


def unseed_reports_role(apps, schema_editor):
    Folder = apps.get_model("projects_app", "RegistrationWorkspaceFolder")
    Folder.objects.filter(role="reports", name="06 Отчеты").update(role="")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects_app", "0081_resequence_project_stages_by_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrationworkspacefolder",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", ""),
                    ("imc_id", "ИД IMC Montan"),
                    ("customer_id", "ИД Заказчика"),
                    ("reports", "Отчеты"),
                ],
                default="",
                max_length=32,
                verbose_name="Роль",
            ),
        ),
        migrations.CreateModel(
            name="PerformerReportUpload",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("executor", models.CharField(blank=True, default="", max_length=255, verbose_name="Исполнитель")),
                ("asset_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Актив")),
                ("is_all_sections", models.BooleanField(db_index=True, default=False, verbose_name="Все разделы")),
                ("file_name", models.CharField(blank=True, default="", max_length=500, verbose_name="Имя файла")),
                ("file_link", models.URLField(blank=True, default="", max_length=2000, verbose_name="Ссылка на файл")),
                ("cloud_path", models.CharField(blank=True, default="", max_length=2048, verbose_name="Путь в облаке")),
                ("uploaded_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата загрузки")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата отправки")),
                (
                    "performer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_uploads",
                        to="projects_app.performer",
                        verbose_name="Строка исполнителя",
                    ),
                ),
                (
                    "registration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_uploads",
                        to="projects_app.projectregistration",
                        verbose_name="Проект",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="performer_report_uploads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Загрузка отчёта исполнителя",
                "verbose_name_plural": "Загрузки отчётов исполнителей",
            },
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_all_sections", True)),
                fields=("registration", "executor", "asset_name"),
                name="uniq_report_upload_all_sections",
            ),
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_all_sections", False), ("performer__isnull", False)),
                fields=("performer",),
                name="uniq_report_upload_section",
            ),
        ),
        migrations.RunPython(seed_reports_role, unseed_reports_role),
    ]
