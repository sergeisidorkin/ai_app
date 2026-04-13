import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import requests
from django.conf import settings

from core.cloud_storage import (
    CloudStorageNotReadyError,
    download_file as cloud_download_file,
    get_any_connected_service_user,
    is_nextcloud_primary,
)
from letters_app.services import get_effective_template, render_subject, render_template
from notifications_app.email_delivery import EmailDeliveryError, send_notification_email
from notifications_app.services import (
    DELIVERY_CHANNEL_CONNECTED_EMAIL,
    DELIVERY_CHANNEL_LABELS,
    DELIVERY_CHANNEL_SYSTEM_EMAIL,
)
from smtp_app.services import get_user_notification_email_options

logger = logging.getLogger(__name__)

# CI can import this module through either `proposals_app.services` or
# `ai_app.proposals_app.services`. Keep both names bound to the same module
# object so patch() targets stay stable.
sys.modules.setdefault("proposals_app.services", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.services", sys.modules[__name__])

PROPOSAL_SENDING_TEMPLATE_TYPE = "proposal_sending"
PROPOSAL_SENDING_DEFAULT_SUBJECT = "Технико-коммерческое предложение IMC Montan {{tkp_id}}"
PROPOSAL_SENDING_DEFAULT_BODY = "<p>Направляем проект ТКП {{tkp_id}}</p>"
SUPPORTED_PROPOSAL_DELIVERY_CHANNELS = (
    DELIVERY_CHANNEL_SYSTEM_EMAIL,
    DELIVERY_CHANNEL_CONNECTED_EMAIL,
)
PROPOSAL_DELIVERY_CHANNEL_ALIASES = {
    "email": DELIVERY_CHANNEL_SYSTEM_EMAIL,
}


def _proposal_system_from_email() -> str | None:
    value = str(getattr(settings, "PROPOSAL_SYSTEM_FROM_EMAIL", "") or "").strip()
    return value or None


def normalize_proposal_delivery_channels(delivery_channels):
    requested = {
        PROPOSAL_DELIVERY_CHANNEL_ALIASES.get(str(value).strip(), str(value).strip())
        for value in (delivery_channels or [])
        if str(value).strip()
    }
    if not requested:
        raise ValueError("Выберите хотя бы один способ отправки.")

    invalid = requested - set(SUPPORTED_PROPOSAL_DELIVERY_CHANNELS)
    if invalid:
        invalid_list = ", ".join(sorted(invalid))
        raise ValueError(f"Переданы неподдерживаемые каналы доставки: {invalid_list}.")

    return tuple(channel for channel in SUPPORTED_PROPOSAL_DELIVERY_CHANNELS if channel in requested)


def _empty_channel_summary(*, delivery_channel, email_requested=False):
    return {
        "channel": delivery_channel,
        "channel_label": DELIVERY_CHANNEL_LABELS.get(delivery_channel, delivery_channel),
        "requested": email_requested,
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "errors": [],
    }


def _proposal_type_label(proposal):
    proposal_type = getattr(proposal, "type", None)
    if not proposal_type:
        return ""
    return (getattr(proposal_type, "short_name", "") or str(proposal_type)).strip()


def build_proposal_tkp_id(proposal):
    parts = [
        (getattr(proposal, "short_uid", "") or "").strip(),
        _proposal_type_label(proposal),
        (getattr(proposal, "name", "") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _build_proposal_email(proposal, *, sender):
    tkp_id = build_proposal_tkp_id(proposal)
    template_vars = {"tkp_id": tkp_id}
    subject = render_subject(PROPOSAL_SENDING_DEFAULT_SUBJECT, template_vars)
    content = render_template(PROPOSAL_SENDING_DEFAULT_BODY, template_vars)

    tpl = get_effective_template(PROPOSAL_SENDING_TEMPLATE_TYPE, sender)
    if tpl:
        if tpl.subject_template:
            subject = render_subject(tpl.subject_template, template_vars)
        if tpl.body_html:
            content = render_template(tpl.body_html, template_vars)

    return {
        "tkp_id": tkp_id,
        "subject": subject,
        "content": content,
    }


def _get_proposal_attachment_cloud_user(user):
    if is_nextcloud_primary():
        return user or SimpleNamespace(username="nextcloud-system")

    from yandexdisk_app.models import YandexDiskAccount

    if user is not None and YandexDiskAccount.objects.filter(user=user, access_token__gt="").exists():
        return user
    try:
        return get_any_connected_service_user()
    except CloudStorageNotReadyError as exc:
        raise EmailDeliveryError(str(exc)) from exc


def _load_proposal_pdf_attachment(proposal, *, sender):
    pdf_name = str(getattr(proposal, "pdf_file_name", "") or "").strip()
    raw_link = str(getattr(proposal, "pdf_file_link", "") or "").strip()
    if not pdf_name or not raw_link:
        raise EmailDeliveryError("Для ТКП не указан PDF-файл для вложения.")

    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()
    if media_url and raw_link.startswith(media_url):
        relative_path = raw_link[len(media_url):].lstrip("/")
        local_media_path = Path(settings.MEDIA_ROOT) / relative_path
        if not local_media_path.exists():
            raise EmailDeliveryError("Локальная копия PDF-файла ТКП для вложения не найдена.")
        pdf_bytes = local_media_path.read_bytes()
    elif raw_link.startswith(("http://", "https://")):
        try:
            response = requests.get(raw_link, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise EmailDeliveryError(f"Не удалось скачать PDF-файл ТКП для вложения: {exc}") from exc
        pdf_bytes = response.content or b""
    else:
        cloud_user = _get_proposal_attachment_cloud_user(sender)
        if not cloud_user:
            raise EmailDeliveryError("Не найден пользователь с подключенным облачным хранилищем для чтения PDF.")
        _mime_type, pdf_bytes = cloud_download_file(cloud_user, raw_link)

    if not pdf_bytes:
        raise EmailDeliveryError("PDF-файл ТКП для вложения пустой или недоступен.")
    return (pdf_name, pdf_bytes, "application/pdf")


def _append_error(aggregate, *, channel, recipient_label, error_message):
    error_payload = {
        "recipient": recipient_label,
        "error": error_message,
        "channel": channel,
        "channel_label": DELIVERY_CHANNEL_LABELS.get(channel, channel),
    }
    aggregate["failed"] += 1
    aggregate["errors"].append(error_payload)
    channel_summary = aggregate["channels"][channel]
    channel_summary["failed"] += 1
    channel_summary["errors"].append(error_payload)


def send_proposal_dispatch_emails(*, proposals, sender, delivery_channels):
    delivery_channels = normalize_proposal_delivery_channels(delivery_channels)
    proposals = list(proposals)

    system_email_requested = DELIVERY_CHANNEL_SYSTEM_EMAIL in delivery_channels
    connected_email_requested = DELIVERY_CHANNEL_CONNECTED_EMAIL in delivery_channels
    connected_delivery_options = {}
    connected_delivery_error = ""

    if connected_email_requested:
        try:
            connected_delivery_options = get_user_notification_email_options(sender)
        except Exception as exc:  # pragma: no cover - backend-specific resolution errors vary
            logger.warning(
                "Failed to resolve external SMTP options for %s: %s",
                getattr(sender, "username", sender),
                exc,
            )
        if not connected_delivery_options:
            connected_delivery_error = "У отправителя не настроен активный внешний SMTP-аккаунт."

    email_delivery = {
        "requested": system_email_requested or connected_email_requested,
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "errors": [],
        "channels": {
            DELIVERY_CHANNEL_SYSTEM_EMAIL: _empty_channel_summary(
                delivery_channel=DELIVERY_CHANNEL_SYSTEM_EMAIL,
                email_requested=system_email_requested,
            ),
            DELIVERY_CHANNEL_CONNECTED_EMAIL: _empty_channel_summary(
                delivery_channel=DELIVERY_CHANNEL_CONNECTED_EMAIL,
                email_requested=connected_email_requested,
            ),
        },
    }
    sent_proposal_ids = []

    for proposal in proposals:
        message_payload = _build_proposal_email(proposal, sender=sender)
        recipient_email = (getattr(proposal, "contact_email", "") or "").strip()
        recipient_label = f"{message_payload['tkp_id']} -> {recipient_email or 'без email'}"
        recipient = SimpleNamespace(email=recipient_email)
        proposal_sent = False
        try:
            attachments = [_load_proposal_pdf_attachment(proposal, sender=sender)]
        except EmailDeliveryError as exc:
            for channel in delivery_channels:
                email_delivery["attempted"] += 1
                channel_summary = email_delivery["channels"][channel]
                channel_summary["attempted"] += 1
                _append_error(
                    email_delivery,
                    channel=channel,
                    recipient_label=recipient_label,
                    error_message=str(exc),
                )
            continue

        for channel in delivery_channels:
            email_delivery["attempted"] += 1
            channel_summary = email_delivery["channels"][channel]
            channel_summary["attempted"] += 1
            try:
                if not recipient_email:
                    raise EmailDeliveryError("У получателя не указан email.")

                delivery_options = {}
                if channel == DELIVERY_CHANNEL_CONNECTED_EMAIL:
                    if connected_delivery_error:
                        raise EmailDeliveryError(connected_delivery_error)
                    delivery_options = connected_delivery_options
                elif channel == DELIVERY_CHANNEL_SYSTEM_EMAIL:
                    delivery_options = {
                        "from_email": _proposal_system_from_email(),
                    }

                send_notification_email(
                    recipient=recipient,
                    subject=message_payload["subject"],
                    content=message_payload["content"],
                    from_email=delivery_options.get("from_email"),
                    connection=delivery_options.get("connection"),
                    reply_to=delivery_options.get("reply_to"),
                    attachments=attachments,
                )
                email_delivery["sent"] += 1
                channel_summary["sent"] += 1
                proposal_sent = True
            except EmailDeliveryError as exc:
                _append_error(
                    email_delivery,
                    channel=channel,
                    recipient_label=recipient_label,
                    error_message=str(exc),
                )

        if proposal_sent:
            sent_proposal_ids.append(proposal.pk)

    return {
        "delivery_channels": delivery_channels,
        "email_delivery": email_delivery,
        "sent_proposal_ids": sent_proposal_ids,
    }
