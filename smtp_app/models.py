from django.conf import settings
from django.db import models

from .security import decrypt_secret, encrypt_secret


class ExternalSMTPAccount(models.Model):
    class TestStatus(models.TextChoices):
        UNKNOWN = "unknown", "Не проверялось"
        OK = "ok", "Успешно"
        FAILED = "failed", "Ошибка"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_smtp_account",
    )
    label = models.CharField("Название подключения", max_length=120, default="Внешний SMTP")
    smtp_host = models.CharField("SMTP host", max_length=255)
    smtp_port = models.PositiveIntegerField("SMTP port", default=587)
    username = models.CharField("Логин", max_length=255)
    password_ciphertext = models.TextField("Зашифрованный пароль", blank=True, default="")
    use_tls = models.BooleanField("Использовать STARTTLS", default=True)
    use_ssl = models.BooleanField("Использовать SSL", default=False)
    skip_tls_verify = models.BooleanField("Не проверять TLS-сертификат", default=False)
    from_email = models.EmailField("Email отправителя")
    reply_to_email = models.EmailField("Reply-To", blank=True, default="")
    is_active = models.BooleanField("Подключение активно", default=True)
    use_for_notifications = models.BooleanField("Использовать для уведомлений", default=True)
    last_test_at = models.DateTimeField("Последняя проверка", null=True, blank=True)
    last_test_status = models.CharField(
        "Статус проверки",
        max_length=16,
        choices=TestStatus.choices,
        default=TestStatus.UNKNOWN,
    )
    last_test_error = models.TextField("Текст ошибки проверки", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Внешний SMTP-аккаунт"
        verbose_name_plural = "Внешние SMTP-аккаунты"

    def __str__(self):
        return f"{self.label} ({self.from_email})"

    @property
    def has_password(self) -> bool:
        return bool(self.password_ciphertext)

    def set_password(self, raw_password: str) -> None:
        self.password_ciphertext = encrypt_secret(raw_password)

    def get_password(self) -> str:
        return decrypt_secret(self.password_ciphertext)
