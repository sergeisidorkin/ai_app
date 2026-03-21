from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class NotificationQuerySet(models.QuerySet):
    def for_user(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(recipient=user)

    def pending_attention(self):
        return self.filter(Q(is_read=False) | Q(is_processed=False))


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        PROJECT_PARTICIPATION_CONFIRMATION = (
            "project_participation_confirmation",
            "Запрос подтверждения участия в проекте",
        )
        PROJECT_INFO_REQUEST_APPROVAL = (
            "project_info_request_approval",
            "Согласование запроса информации",
        )
        PROJECT_CONTRACT_CONCLUSION = (
            "project_contract_conclusion",
            "Отправлен проект договора",
        )

    class RelatedSection(models.TextChoices):
        NONE = "none", "Не указан"
        PROJECTS = "projects", "Проекты"
        CHECKLISTS = "checklists", "Чек-листы"
        CONTRACTS = "contracts", "Договоры"

    class ActionChoice(models.TextChoices):
        NONE = "", "Не выбрано"
        CONFIRMED = "confirmed", "Подтвердить участие"
        DECLINED = "declined", "Отклонить"
        APPROVED = "approved", "Согласовать запрос"

    notification_type = models.CharField(
        "Тип уведомления",
        max_length=64,
        choices=NotificationType.choices,
        db_index=True,
    )
    related_section = models.CharField(
        "Раздел",
        max_length=32,
        choices=RelatedSection.choices,
        default=RelatedSection.NONE,
        db_index=True,
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_notifications",
        verbose_name="Получатель",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sent_notifications",
        verbose_name="Автор отправки",
        null=True,
        blank=True,
    )
    read_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="read_notifications",
        verbose_name="Автор прочтения",
        null=True,
        blank=True,
    )
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="processed_notifications",
        verbose_name="Автор действия",
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Проект",
        null=True,
        blank=True,
    )
    title_text = models.CharField("Заголовок уведомления", max_length=500)
    content_text = models.TextField("Содержание уведомления", blank=True, default="")
    payload = models.JSONField("Данные уведомления", blank=True, default=dict)
    sent_at = models.DateTimeField("Дата отправки", default=timezone.now, db_index=True)
    deadline_at = models.DateTimeField("Срок действия", null=True, blank=True)
    read_at = models.DateTimeField("Дата прочтения", null=True, blank=True)
    action_at = models.DateTimeField("Дата действия", null=True, blank=True)
    is_read = models.BooleanField("Прочитано", default=False, db_index=True)
    is_processed = models.BooleanField("Обработано", default=False, db_index=True)
    action_choice = models.CharField(
        "Действие по уведомлению",
        max_length=20,
        choices=ActionChoice.choices,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-sent_at", "-id"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"

    def __str__(self):
        return self.title_text

    @property
    def requires_attention(self):
        return (not self.is_read) or (not self.is_processed)


class NotificationPerformerLink(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="performer_links",
        verbose_name="Уведомление",
    )
    performer = models.ForeignKey(
        "projects_app.Performer",
        on_delete=models.CASCADE,
        related_name="notification_links",
        verbose_name="Строка исполнителя",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Строка уведомления"
        verbose_name_plural = "Строки уведомлений"
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "performer"],
                name="notification_performer_unique",
            ),
        ]

    def __str__(self):
        return f"{self.notification_id} -> {self.performer_id}"
