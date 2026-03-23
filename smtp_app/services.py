from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone

from .models import ExternalSMTPAccount


class SMTPServiceError(RuntimeError):
    """Raised when an external SMTP account cannot be used."""


def build_smtp_connection(account: ExternalSMTPAccount):
    if not account.is_active:
        raise SMTPServiceError("SMTP-подключение отключено.")

    password = account.get_password()
    if not password:
        raise SMTPServiceError("Для SMTP-подключения не сохранён пароль.")

    return get_connection(
        backend="smtp_app.backends.ExternalSMTPEmailBackend",
        host=account.smtp_host,
        port=account.smtp_port,
        username=account.username,
        password=password,
        use_tls=account.use_tls,
        use_ssl=account.use_ssl,
        skip_tls_verify=account.skip_tls_verify,
        timeout=getattr(settings, "EMAIL_TIMEOUT", 10),
    )


def update_test_status(account: ExternalSMTPAccount, *, ok: bool, error: str = "") -> None:
    account.last_test_at = timezone.now()
    account.last_test_status = (
        ExternalSMTPAccount.TestStatus.OK
        if ok
        else ExternalSMTPAccount.TestStatus.FAILED
    )
    account.last_test_error = error or ""
    if not account.pk:
        return
    account.save(update_fields=["last_test_at", "last_test_status", "last_test_error", "updated_at"])


def test_smtp_connection(account: ExternalSMTPAccount) -> dict:
    try:
        connection = build_smtp_connection(account)
        opened = connection.open()
        if not opened:
            raise SMTPServiceError("SMTP-сервер не подтвердил открытие соединения.")
        connection.close()
    except Exception as exc:
        update_test_status(account, ok=False, error=str(exc))
        return {"ok": False, "error": str(exc)}

    update_test_status(account, ok=True)
    return {"ok": True, "error": ""}


test_smtp_connection.__test__ = False


def send_test_email(account: ExternalSMTPAccount, to_email: str) -> dict:
    recipient_email = (to_email or "").strip()
    if not recipient_email:
        raise SMTPServiceError("Не указан email для тестового письма.")

    connection = build_smtp_connection(account)
    message = EmailMultiAlternatives(
        subject="Тест SMTP-подключения — IMC Montan AI",
        body=(
            "Это тестовое письмо подтверждает, что внешний SMTP-аккаунт "
            "успешно подключён к IMC Montan AI."
        ),
        from_email=account.from_email,
        to=[recipient_email],
        reply_to=[account.reply_to_email] if account.reply_to_email else None,
        connection=connection,
    )
    try:
        sent_count = message.send(fail_silently=False)
    except Exception as exc:
        update_test_status(account, ok=False, error=str(exc))
        raise SMTPServiceError(f"Не удалось отправить тестовое письмо: {exc}") from exc

    if sent_count != 1:
        update_test_status(
            account,
            ok=False,
            error="Почтовый backend не подтвердил отправку тестового письма.",
        )
        raise SMTPServiceError("Почтовый backend не подтвердил отправку тестового письма.")

    update_test_status(account, ok=True)
    return {"ok": True, "recipient_email": recipient_email}


def get_user_notification_email_options(user) -> dict:
    if not getattr(user, "is_authenticated", False):
        return {}

    account = getattr(user, "external_smtp_account", None)
    if not account or not account.is_active or not account.use_for_notifications:
        return {}

    return {
        "connection": build_smtp_connection(account),
        "from_email": account.from_email,
        "reply_to": [account.reply_to_email] if account.reply_to_email else None,
    }
