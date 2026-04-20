import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    person_record = models.ForeignKey(
        "contacts_app.PersonRecord",
        on_delete=models.SET_NULL,
        related_name="employee_links",
        null=True,
        blank=True,
    )
    managed_email_record = models.OneToOneField(
        "contacts_app.EmailRecord",
        on_delete=models.SET_NULL,
        related_name="employee_email_link",
        null=True,
        blank=True,
    )
    managed_position_record = models.OneToOneField(
        "contacts_app.PositionRecord",
        on_delete=models.SET_NULL,
        related_name="employee_position_link",
        null=True,
        blank=True,
    )
    patronymic = models.CharField("Отчество", max_length=150, blank=True, default="")
    employment = models.CharField("Трудоустройство", max_length=255, blank=True, default="")
    department = models.ForeignKey(
        "group_app.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Подразделение",
    )
    organization = models.CharField("Организация", max_length=255, blank=True, default="")
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    avatar = models.ImageField("Фото профиля", upload_to="avatars/", blank=True, default="")
    role = models.CharField("Роль", max_length=255, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

    def __str__(self):
        return f"{self.user.last_name} {self.user.first_name}".strip() or self.user.username

    @property
    def formatted_prs_id(self):
        return self.person_record.formatted_id if self.person_record_id else ""

    def _ordered_phone_records(self):
        if not self.person_record_id:
            return []
        person = self.person_record
        prefetched = getattr(person, "_prefetched_objects_cache", {}).get("phones")
        if prefetched is not None:
            return [phone for phone in prefetched if phone.is_active]
        return list(person.phones.filter(is_active=True).order_by("position", "id"))

    @staticmethod
    def _format_phone_record(phone):
        if not phone or not phone.phone_number:
            return ""
        parts = []
        if phone.code:
            parts.append(phone.code)
        parts.append(phone.phone_number)
        if phone.extension:
            parts.append(f"доб. {phone.extension}")
        return " ".join(part for part in parts if part).strip()

    @property
    def primary_phone_record(self):
        for phone in self._ordered_phone_records():
            if phone.is_primary:
                return phone
        return None

    @property
    def primary_phone_display(self):
        return self._format_phone_record(self.primary_phone_record)

    @property
    def secondary_phone_record(self):
        phones = self._ordered_phone_records()
        primary_phone = self.primary_phone_record
        if not phones or primary_phone is None:
            return None
        primary_found = False
        for phone in phones:
            if not primary_found:
                primary_found = phone.pk == primary_phone.pk
                continue
            if not phone.is_primary:
                return phone
        return None

    @property
    def secondary_phone_display(self):
        return self._format_phone_record(self.secondary_phone_record)


class PendingRegistration(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_registration",
    )
    token = models.CharField("URL-токен", max_length=64, unique=True, db_index=True)
    code = models.CharField("Код подтверждения", max_length=6)
    attempts = models.PositiveSmallIntegerField("Попытки", default=0)
    last_sent_at = models.DateTimeField("Последняя отправка", auto_now_add=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Ожидающая регистрация"
        verbose_name_plural = "Ожидающие регистрации"

    def __str__(self):
        return f"{self.user.email} ({self.token[:8]}…)"

    @staticmethod
    def generate_token():
        return secrets.token_hex(32)

    @staticmethod
    def generate_code():
        return str(secrets.randbelow(900000) + 100000)

    def is_expired(self):
        ttl = getattr(settings, "EMAIL_VERIFICATION_CODE_TTL", 1800)
        return (timezone.now() - self.created_at).total_seconds() > ttl

    def can_resend(self):
        return (timezone.now() - self.last_sent_at).total_seconds() >= 60
