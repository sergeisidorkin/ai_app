import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0012_inforequestsectionapproval"),
        ("projects_app", "0019_performer_info_approval_at_and_more"),
        ("policy_app", "0018_alter_typicalsection_executor_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="checklistitem",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Дата удаления"),
        ),
        migrations.AddField(
            model_name="checklistitem",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="deleted_checklist_items",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Кто удалил",
            ),
        ),
        migrations.AlterModelOptions(
            name="checklistitem",
            options={
                "base_manager_name": "all_objects",
                "default_manager_name": "objects",
                "ordering": ["position", "id"],
                "verbose_name": "Пункт чек-листа",
                "verbose_name_plural": "Пункты чек-листа",
            },
        ),
        migrations.AddIndex(
            model_name="checklistitem",
            index=models.Index(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=["project", "section", "position", "id"],
                name="chk_item_active_order_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="checklistitem",
            index=models.Index(
                fields=["project", "section", "deleted_at"],
                name="chk_item_deleted_lookup_idx",
            ),
        ),
        migrations.CreateModel(
            name="ChecklistItemAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("created", "Создан"),
                            ("updated", "Изменён"),
                            ("soft_deleted", "Удалён"),
                            ("restored", "Восстановлен"),
                            ("batch_edit", "Массовое редактирование"),
                        ],
                        max_length=32,
                        verbose_name="Действие",
                    ),
                ),
                ("snapshot", models.JSONField(blank=True, default=dict, verbose_name="Снимок строки")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="Метаданные")),
                ("change_batch_id", models.UUIDField(blank=True, db_index=True, null=True, verbose_name="ID пакета изменений")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата события")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="checklist_item_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
                (
                    "checklist_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="checklists_app.checklistitem",
                        verbose_name="Пункт чек-листа",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_item_audit_logs",
                        to="projects_app.projectregistration",
                        verbose_name="Проект",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="checklist_item_audit_logs",
                        to="policy_app.typicalsection",
                        verbose_name="Раздел",
                    ),
                ),
            ],
            options={
                "verbose_name": "Аудит пункта чек-листа",
                "verbose_name_plural": "Аудит пунктов чек-листа",
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["project", "-created_at"], name="chk_audit_project_time_idx"),
                    models.Index(fields=["checklist_item", "-created_at"], name="chk_audit_item_time_idx"),
                    models.Index(fields=["action", "-created_at"], name="chk_audit_action_time_idx"),
                ],
            },
        ),
    ]
