from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalSMTPAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(default="Внешний SMTP", max_length=120, verbose_name="Название подключения")),
                ("smtp_host", models.CharField(max_length=255, verbose_name="SMTP host")),
                ("smtp_port", models.PositiveIntegerField(default=587, verbose_name="SMTP port")),
                ("username", models.CharField(max_length=255, verbose_name="Логин")),
                ("password_ciphertext", models.TextField(blank=True, default="", verbose_name="Зашифрованный пароль")),
                ("use_tls", models.BooleanField(default=True, verbose_name="Использовать STARTTLS")),
                ("use_ssl", models.BooleanField(default=False, verbose_name="Использовать SSL")),
                ("from_email", models.EmailField(max_length=254, verbose_name="Email отправителя")),
                ("reply_to_email", models.EmailField(blank=True, default="", max_length=254, verbose_name="Reply-To")),
                ("is_active", models.BooleanField(default=True, verbose_name="Подключение активно")),
                ("use_for_notifications", models.BooleanField(default=True, verbose_name="Использовать для уведомлений")),
                ("last_test_at", models.DateTimeField(blank=True, null=True, verbose_name="Последняя проверка")),
                (
                    "last_test_status",
                    models.CharField(
                        choices=[("unknown", "Не проверялось"), ("ok", "Успешно"), ("failed", "Ошибка")],
                        default="unknown",
                        max_length=16,
                        verbose_name="Статус проверки",
                    ),
                ),
                ("last_test_error", models.TextField(blank=True, default="", verbose_name="Текст ошибки проверки")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_smtp_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Внешний SMTP-аккаунт",
                "verbose_name_plural": "Внешние SMTP-аккаунты",
            },
        ),
    ]
