from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects_app", "0018_performer_employee"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("project_participation_confirmation", "Запрос подтверждения участия в проекте"),
                        ],
                        db_index=True,
                        max_length=64,
                        verbose_name="Тип уведомления",
                    ),
                ),
                (
                    "related_section",
                    models.CharField(
                        choices=[("none", "Не указан"), ("projects", "Проекты")],
                        db_index=True,
                        default="none",
                        max_length=32,
                        verbose_name="Раздел",
                    ),
                ),
                ("title_text", models.CharField(max_length=500, verbose_name="Заголовок уведомления")),
                ("content_text", models.TextField(blank=True, default="", verbose_name="Содержание уведомления")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Данные уведомления")),
                ("sent_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="Дата отправки")),
                ("deadline_at", models.DateTimeField(blank=True, null=True, verbose_name="Срок действия")),
                ("read_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата прочтения")),
                ("action_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата действия")),
                ("is_read", models.BooleanField(db_index=True, default=False, verbose_name="Прочитано")),
                ("is_processed", models.BooleanField(db_index=True, default=False, verbose_name="Обработано")),
                (
                    "action_choice",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "Не выбрано"),
                            ("confirmed", "Подтвердить участие"),
                            ("declined", "Отклонить"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Действие по уведомлению",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "action_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор действия",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="projects_app.projectregistration",
                        verbose_name="Проект",
                    ),
                ),
                (
                    "read_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="read_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор прочтения",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="received_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Получатель",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор отправки",
                    ),
                ),
            ],
            options={
                "verbose_name": "Уведомление",
                "verbose_name_plural": "Уведомления",
                "ordering": ["-sent_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="NotificationPerformerLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="performer_links",
                        to="notifications_app.notification",
                        verbose_name="Уведомление",
                    ),
                ),
                (
                    "performer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_links",
                        to="projects_app.performer",
                        verbose_name="Строка исполнителя",
                    ),
                ),
            ],
            options={
                "verbose_name": "Строка уведомления",
                "verbose_name_plural": "Строки уведомлений",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="notificationperformerlink",
            constraint=models.UniqueConstraint(fields=("notification", "performer"), name="notification_performer_unique"),
        ),
    ]
