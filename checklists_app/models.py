import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta

_PREVIOUS_STATUS_UNSET = object()

class ChecklistItem(models.Model):
    class ItemType(models.TextChoices):
        BASIC = "basic", "Основной"
        ADDITIONAL = "additional", "Дополнительный"

    project = models.ForeignKey(
        "projects_app.ProjectRegistration", on_delete=models.CASCADE, related_name="checklist_items"
    )
    section = models.ForeignKey(
        "policy_app.TypicalSection", on_delete=models.CASCADE, related_name="checklist_items"
    )
    code = models.CharField("Код", max_length=50)
    number = models.PositiveIntegerField("№")
    short_name = models.CharField("Краткое наименование", max_length=120, blank=True, default="")
    name = models.TextField("Наименование запроса")
    position = models.PositiveIntegerField(default=1)
    item_type = models.CharField(
        "Тип запроса", max_length=16,
        choices=ItemType.choices, default=ItemType.BASIC,
    )
    additional_date = models.DateField("Дата доп. запроса", null=True, blank=True)
    additional_number = models.PositiveIntegerField("№ доп. запроса", null=True, blank=True)
    source_request_item = models.ForeignKey(
        "requests_app.RequestItem", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="derived_checklist_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Пункт чек-листа"
        verbose_name_plural = "Пункты чек-листа"

    def __str__(self):
        return f"{self.code} {self.number:02d} — {self.short_name or self.name[:40]}"


class ChecklistStatus(models.Model):
    class Status(models.TextChoices):
        PROVIDED = "provided", "Предоставлено"
        PARTIAL = "partial", "Предоставлено частично"
        MISSING = "missing", "Не предоставлено"
        NOT_REQUIRED = "na", "Не требуется"

    checklist_item = models.ForeignKey(
        ChecklistItem, null=True, blank=True, on_delete=models.CASCADE, related_name="statuses"
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
        unique_together = (("checklist_item", "legal_entity"),)
        verbose_name = "Статус запроса"
        verbose_name_plural = "Статусы запросов"

    def save(self, *args, **kwargs):
        previous_status = kwargs.pop("previous_status", _PREVIOUS_STATUS_UNSET)
        if self.pk:
            previous = previous_status
            if previous is _PREVIOUS_STATUS_UNSET:
                previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous != self.status and (previous is not None or self.status != self.Status.MISSING):
                self.status_changed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.checklist_item_id} / {self.legal_entity_id} — {self.get_status_display()}"


class ChecklistStatusHistory(models.Model):
    checklist_status = models.ForeignKey(
        ChecklistStatus, related_name="history", on_delete=models.CASCADE
    )
    checklist_item = models.ForeignKey(ChecklistItem, null=True, blank=True, on_delete=models.CASCADE, related_name="status_history")
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
        return f"{self.checklist_item_id}/{self.legal_entity_id}: {self.new_status}"


class ChecklistRequestNote(models.Model):
    checklist_item = models.ForeignKey(
        ChecklistItem, null=True, blank=True, on_delete=models.CASCADE, related_name="notes"
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
        unique_together = (("checklist_item", "project", "section", "asset_name"),)
        verbose_name = "Комментарий для запроса"
        verbose_name_plural = "Комментарии для запросов"

    def __str__(self):
        return f"{self.project_id}/{self.asset_name}/{self.section_id}/{self.checklist_item_id}"


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
        ep = getattr(self.author, "employee_profile", None)
        if ep and ep.full_name:
            return ep.full_name
        return self.author.get_full_name() or self.author.username


_PREVIOUS_CUSTOMER_STATUS_UNSET = object()


class ChecklistCustomerStatus(models.Model):
    class Status(models.TextChoices):
        NOT_TRANSFERRED = "not_transferred", "Не передано"
        PARTIAL_TRANSFER = "partial_transfer", "Передано частично"
        TRANSFERRED = "transferred", "Передано все"
        NO_DATA = "no_data", "Нет данных"

    checklist_item = models.ForeignKey(
        ChecklistItem, on_delete=models.CASCADE, related_name="customer_statuses"
    )
    legal_entity = models.ForeignKey(
        "projects_app.LegalEntity", on_delete=models.CASCADE, related_name="checklist_customer_statuses"
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NOT_TRANSFERRED)
    status_changed_at = models.DateTimeField("Дата изменения статуса", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="checklist_customer_statuses",
    )

    class Meta:
        unique_together = (("checklist_item", "legal_entity"),)
        verbose_name = "Статус заказчика"
        verbose_name_plural = "Статусы заказчика"

    def save(self, *args, **kwargs):
        previous_status = kwargs.pop("previous_status", _PREVIOUS_CUSTOMER_STATUS_UNSET)
        if self.pk:
            previous = previous_status
            if previous is _PREVIOUS_CUSTOMER_STATUS_UNSET:
                previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous != self.status and (previous is not None or self.status != self.Status.NOT_TRANSFERRED):
                self.status_changed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.checklist_item_id} / {self.legal_entity_id} — {self.get_status_display()}"


class ChecklistCustomerStatusHistory(models.Model):
    customer_status = models.ForeignKey(
        ChecklistCustomerStatus, related_name="history", on_delete=models.CASCADE
    )
    checklist_item = models.ForeignKey(
        ChecklistItem, null=True, blank=True, on_delete=models.CASCADE, related_name="customer_status_history"
    )
    legal_entity = models.ForeignKey("projects_app.LegalEntity", on_delete=models.CASCADE)
    previous_status = models.CharField(
        max_length=32, choices=ChecklistCustomerStatus.Status.choices, blank=True
    )
    new_status = models.CharField(max_length=32, choices=ChecklistCustomerStatus.Status.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="checklist_customer_status_history",
    )

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "История статуса заказчика"
        verbose_name_plural = "История статусов заказчика"

    def __str__(self):
        return f"{self.checklist_item_id}/{self.legal_entity_id}: {self.new_status}"


def _default_expiry():
    return timezone.now() + timedelta(days=183)


def _generate_token():
    return secrets.token_urlsafe(48)


class SharedChecklistLink(models.Model):
    class Permission(models.TextChoices):
        VIEW = "view", "Доступен просмотр"
        EDIT = "edit", "Доступно редактирование"

    project = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="shared_checklist_links",
    )
    token = models.CharField(max_length=128, unique=True, default=_generate_token, db_index=True)
    permission = models.CharField(
        max_length=16,
        choices=Permission.choices,
        default=Permission.EDIT,
    )
    expires_at = models.DateTimeField("Дата прекращения действия", default=_default_expiry)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_checklist_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Публичная ссылка на чек-лист"
        verbose_name_plural = "Публичные ссылки на чек-листы"

    def __str__(self):
        return f"SharedLink:{self.project_id}:{self.token[:12]}…"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_active(self):
        return not self.is_expired

    @property
    def can_edit(self):
        return self.permission == self.Permission.EDIT and self.is_active


class ProjectWorkspace(models.Model):
    """Корневая папка рабочего пространства проекта на Яндекс.Диске."""
    project = models.OneToOneField(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="yadisk_workspace",
    )
    disk_path = models.CharField("Путь на диске", max_length=2048)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_workspaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Рабочее пространство проекта"
        verbose_name_plural = "Рабочие пространства проектов"

    def __str__(self):
        return f"Workspace:{self.project_id}:{self.disk_path[:60]}"


class SourceDataWorkspace(models.Model):
    """Корневая папка пространства исходных данных проекта на Яндекс.Диске."""
    project = models.OneToOneField(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="source_data_workspace",
    )
    disk_path = models.CharField("Путь на диске", max_length=2048)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_source_data_workspaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Пространство исходных данных"
        verbose_name_plural = "Пространства исходных данных"

    def __str__(self):
        return f"SourceDataWS:{self.project_id}:{self.disk_path[:60]}"


class ChecklistItemFolder(models.Model):
    """Связь пункта чек-листа с папкой на Яндекс.Диске."""
    checklist_item = models.OneToOneField(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name="yadisk_folder",
    )
    project = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="yadisk_folders",
    )
    disk_path = models.CharField("Путь на диске", max_length=2048)
    public_url = models.URLField("Публичная ссылка", blank=True, default="")
    file_count = models.PositiveIntegerField("Кол-во файлов", default=0)
    last_upload_at = models.DateTimeField("Последняя загрузка", null=True, blank=True)
    synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Папка пункта чек-листа"
        verbose_name_plural = "Папки пунктов чек-листа"

    def __str__(self):
        return f"Folder:{self.checklist_item_id}:{self.disk_path[:60]}"


class SourceDataSectionFolder(models.Model):
    """Папка типового раздела в пространстве исходных данных на Яндекс.Диске."""
    project = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="source_data_section_folders",
    )
    section = models.ForeignKey(
        "policy_app.TypicalSection",
        on_delete=models.CASCADE,
        related_name="source_data_folders",
    )
    asset_name = models.CharField("Наименование актива", max_length=255, blank=True, default="")
    disk_path = models.CharField("Путь на диске", max_length=2048)
    public_url = models.URLField("Публичная ссылка", blank=True, default="")
    file_count = models.PositiveIntegerField("Кол-во файлов", default=0)
    last_upload_at = models.DateTimeField("Последняя загрузка", null=True, blank=True)
    synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Папка раздела исходных данных"
        verbose_name_plural = "Папки разделов исходных данных"

    def __str__(self):
        return f"SectionFolder:{self.project_id}:{self.section_id}:{self.disk_path[:60]}"


class SourceDataItemFolder(models.Model):
    """Папка пункта чек-листа в пространстве исходных данных на Яндекс.Диске.
    В отличие от ChecklistItemFolder допускает несколько записей для одного
    пункта (при наличии нескольких активов в проекте)."""
    project = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="source_data_item_folders",
    )
    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name="source_data_folders",
    )
    asset_name = models.CharField("Наименование актива", max_length=255, blank=True, default="")
    disk_path = models.CharField("Путь на диске", max_length=2048)
    public_url = models.URLField("Публичная ссылка", blank=True, default="")
    file_count = models.PositiveIntegerField("Кол-во файлов", default=0)
    last_upload_at = models.DateTimeField("Последняя загрузка", null=True, blank=True)
    synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Папка запроса исходных данных"
        verbose_name_plural = "Папки запросов исходных данных"

    def __str__(self):
        return f"ItemFolder:{self.project_id}:{self.checklist_item_id}:{self.disk_path[:60]}"