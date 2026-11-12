import re
from email.utils import make_msgid, parseaddr
from html import unescape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags


class EmailDeliveryError(RuntimeError):
    """Controlled email-delivery error for notification channels."""


def _message_id_domain(from_email: str) -> str | None:
    address = parseaddr(str(from_email or "").strip())[1]
    if "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip().strip(">")
    return domain or None


def looks_like_html(content: str) -> bool:
    return bool(str(content or "").lstrip().startswith("<"))


def build_plain_text_body(content: str) -> str:
    value = str(content or "")
    if not value:
        return ""

    if not looks_like_html(value):
        return value.strip()

    normalized = re.sub(r"(?i)<br\s*/?>", "\n", value)
    normalized = re.sub(r"(?i)</(p|div|li|tr|h[1-6])\s*>", "\n", normalized)
    normalized = re.sub(r"(?i)</(ul|ol|table|section|article)\s*>", "\n\n", normalized)

    plain = strip_tags(normalized)
    plain = unescape(plain)
    plain = plain.replace("\r\n", "\n").replace("\r", "\n")
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


def _clean_email_list(values) -> list[str]:
    cleaned = []
    seen = set()
    for value in values or []:
        address = str(value or "").strip()
        key = address.casefold()
        if not address or key in seen:
            continue
        seen.add(key)
        cleaned.append(address)
    return cleaned


def send_notification_email(
    *,
    recipient,
    subject: str,
    content: str,
    from_email: str | None = None,
    connection=None,
    reply_to: list[str] | None = None,
    attachments: list[tuple[str, bytes] | tuple[str, bytes, str]] | None = None,
    to_emails: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict:
    clean_to = _clean_email_list(to_emails)
    recipient_email = (getattr(recipient, "email", "") or "").strip()
    if not clean_to and recipient_email:
        clean_to = [recipient_email]
    if not clean_to:
        raise EmailDeliveryError("У получателя не указан email.")
    to_keys = {address.casefold() for address in clean_to}
    clean_bcc = [
        address for address in _clean_email_list(bcc)
        if address.casefold() not in to_keys
    ]

    clean_subject = str(subject or "").strip()
    if not clean_subject:
        raise EmailDeliveryError("Не указан заголовок письма.")

    clean_content = str(content or "").strip()
    if not clean_content:
        raise EmailDeliveryError("Не указано содержание письма.")

    text_body = build_plain_text_body(clean_content)
    effective_from_email = from_email or settings.DEFAULT_FROM_EMAIL
    message = EmailMultiAlternatives(
        subject=clean_subject,
        body=text_body,
        from_email=effective_from_email,
        to=clean_to,
        bcc=clean_bcc or None,
        reply_to=reply_to,
        connection=connection,
        headers={
            "Message-ID": make_msgid(domain=_message_id_domain(effective_from_email)),
        },
    )
    if looks_like_html(clean_content):
        message.attach_alternative(clean_content, "text/html")
    for attachment in attachments or []:
        if len(attachment) == 2:
            filename, file_content = attachment
            mimetype = None
        else:
            filename, file_content, mimetype = attachment
        message.attach(filename, file_content, mimetype)

    try:
        sent_count = message.send(fail_silently=False)
    except Exception as exc:  # pragma: no cover - concrete backend errors vary
        raise EmailDeliveryError(f"Не удалось отправить письмо: {exc}") from exc

    if sent_count != 1:
        raise EmailDeliveryError("Почтовый backend не подтвердил отправку письма.")

    return {
        "recipient_email": clean_to[0],
        "to": clean_to,
        "bcc": clean_bcc,
        "subject": clean_subject,
        "is_html": looks_like_html(clean_content),
    }
