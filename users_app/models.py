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
    patronymic = models.CharField("Отчество", max_length=150, blank=True, default="")
    phone = models.CharField("Телефон", max_length=50, blank=True, default="")
    employment = models.CharField("Трудоустройство", max_length=255, blank=True, default="")
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
