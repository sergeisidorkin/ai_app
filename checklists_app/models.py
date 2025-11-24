from django.conf import settings
from django.db import models
from django.utils import timezone

class ChecklistStatus(models.Model):
    class Status(models.TextChoices):
        PROVIDED = "provided", "Предоставлено"
        PARTIAL = "partial", "Предоставлено частично"
        MISSING = "missing", "Не предоставлено"
        NOT_REQUIRED = "na", "Не требуется"

    request_item = models.ForeignKey(
        "requests_app.RequestItem", on_delete=models.CASCADE, related_name="checklist_statuses"
    )
    legal_entity = models.ForeignKey(
        "projects_app.LegalEntity", on_delete=models.CASCADE, related_name="checklist_statuses"
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.MISSING)
    status_changed_at = models.DateTimeField("Дата изменения статуса", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_statuses"
    )

    class Meta:
        unique_together = (("request_item", "legal_entity"),)
        verbose_name = "Статус запроса"
        verbose_name_plural = "Статусы запросов"

    def save(self, *args, **kwargs):
        refresh_timestamp = False
        if not self.status_changed_at:
            refresh_timestamp = True
        elif self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            refresh_timestamp = previous != self.status
        if refresh_timestamp:
            self.status_changed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_item_id} / {self.legal_entity_id} — {self.get_status_display()}"

class ChecklistStatusHistory(models.Model):
    checklist_status = models.ForeignKey(
        ChecklistStatus, related_name="history", on_delete=models.CASCADE
    )
    request_item = models.ForeignKey("requests_app.RequestItem", on_delete=models.CASCADE)
    legal_entity = models.ForeignKey("projects_app.LegalEntity", on_delete=models.CASCADE)
    previous_status = models.CharField(
        max_length=32, choices=ChecklistStatus.Status.choices, blank=True
    )
    new_status = models.CharField(max_length=32, choices=ChecklistStatus.Status.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_status_history"
    )

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "История статуса"
        verbose_name_plural = "История статусов"

    def __str__(self):
        return f"{self.request_item_id}/{self.legal_entity_id}: {self.new_status}"

class ChecklistRequestNote(models.Model):
    request_item = models.ForeignKey(
        "requests_app.RequestItem", on_delete=models.CASCADE, related_name="checklist_notes"
    )
    project = models.ForeignKey(
        "projects_app.ProjectRegistration", on_delete=models.CASCADE, related_name="checklist_notes"
    )
    section = models.ForeignKey(
        "policy_app.TypicalSection", on_delete=models.CASCADE, related_name="checklist_notes"
    )
    asset_name = models.CharField("Актив", max_length=255, blank=True, default="")
    imc_comment = models.TextField("Комментарий IMC Montan", blank=True, default="")
    customer_comment = models.TextField("Комментарий Заказчика", blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_notes"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("request_item", "project", "section", "asset_name"),)
        verbose_name = "Комментарий для запроса"
        verbose_name_plural = "Комментарии для запросов"

    def __str__(self):
        return f"{self.project_id}/{self.asset_name}/{self.section_id}/{self.request_item_id}"


class ChecklistCommentHistory(models.Model):
    class Field(models.TextChoices):
        IMC = "imc_comment", "Комментарий IMC Montan"
        CUSTOMER = "customer_comment", "Комментарий Заказчика"

    note = models.ForeignKey(
        ChecklistRequestNote,
        on_delete=models.CASCADE,
        related_name="comment_history",
    )
    field = models.CharField(max_length=32, choices=Field.choices)
    text = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checklist_comment_history",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "История комментариев"
        verbose_name_plural = "Истории комментариев"

    def __str__(self):
        return f"{self.note_id}:{self.field}"

    @property
    def author_label(self) -> str:
        if not self.author:
            return "—"