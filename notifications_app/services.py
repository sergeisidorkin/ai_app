from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone

from projects_app.models import Performer

from .models import Notification, NotificationPerformerLink


def _user_full_name(user):
    parts = [
        (getattr(user, "first_name", "") or "").strip(),
        getattr(getattr(user, "employee_profile", None), "patronymic", "").strip(),
    ]
    full = " ".join(part for part in parts if part).strip()
    return full or (getattr(user, "get_full_name", lambda: "")() or "").strip() or user.username


def _display_amount(value):
    if value in (None, ""):
        value = Decimal("0")
    return f"{Decimal(value):,.2f}".replace(",", " ").replace(".", ",")


def _display_project_type(project):
    product = getattr(project, "type", None)
    if not product:
        return "—"
    return product.display_name or product.name_ru or product.name_en or product.short_name or "—"


def _service_line(performer):
    asset_name = (performer.asset_name or "").strip()
    section_label = (
        getattr(performer.typical_section, "name_ru", "") or
        getattr(performer.typical_section, "short_name_ru", "") or
        ""
    ).strip()
    if asset_name and section_label:
        return f"{asset_name}: {section_label}"
    if asset_name:
        return asset_name
    if section_label:
        return section_label
    return "Без детализации"


def build_notification_counters(user):
    if not getattr(user, "is_authenticated", False):
        return {
            "total": 0,
            "sections": {},
        }

    qs = Notification.objects.for_user(user).pending_attention()
    total = qs.count()
    sections = {
        row["related_section"]: row["count"]
        for row in qs.values("related_section").order_by().annotate(count=Count("id"))
    }
    return {"total": total, "sections": sections}


def get_notification_queryset_for_user(user):
    link_qs = (
        NotificationPerformerLink.objects
        .select_related(
            "performer",
            "performer__registration",
            "performer__registration__type",
            "performer__typical_section",
        )
        .order_by("position", "id")
    )
    return (
        Notification.objects.for_user(user)
        .select_related("project", "project__type", "recipient", "sender", "read_by", "action_by")
        .prefetch_related(Prefetch("performer_links", queryset=link_qs))
    )


def _build_participation_payload(*, recipient, project, performers, request_sent_at, deadline_at, duration_hours):
    services = [_service_line(performer) for performer in performers]
    agreed_amount = sum((performer.agreed_amount or Decimal("0")) for performer in performers)
    project_label_parts = [project.short_uid]
    if project.type_id:
        project_label_parts.append(project.type.short_name or str(project.type))
    if project.name:
        project_label_parts.append(project.name)
    project_label = " ".join(part for part in project_label_parts if part)
    recipient_name = _user_full_name(recipient)
    project_manager = (project.project_manager or "—").strip() or "—"
    deadline_label = project.deadline.strftime("%d.%m.%Y") if project.deadline else "—"
    deadline_at_label = timezone.localtime(deadline_at).strftime("%H:%M %d.%m.%Y") if deadline_at else "—"
    sent_at_label = timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M")
    title_text = f"Запрос подтверждения участия в проекте {project_label}".strip()
    content_lines = [
        f"Добрый день, {recipient_name}!",
        "",
        f"Приглашаем вас принять участие в новом проекте IMC Montan Group — {project_label}.",
        f"Руководитель проекта: {project_manager}.",
        f"Срок завершения проекта: {deadline_label}.",
        f"Тип проекта: {_display_project_type(project)}.",
        "Предлагаемый состав услуг (разделов):",
    ]
    for service in services:
        content_lines.append(f"- {service}")
    content_lines.extend(
        [
            f"Предлагаемая оплата услуг: {_display_amount(agreed_amount)}.",
            (
                "Принять решение об участии в проекте, кликнув на кнопку "
                f"«Подтвердить участие» или «Отклонить», необходимо в течение {duration_hours} "
                f"часов с момента отправки данного сообщения — до {deadline_at_label}."
            ),
            "",
            "С уважением,",
            "IMC Montan AI",
        ]
    )
    payload = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "project_manager": project_manager,
        "project_deadline_display": deadline_label,
        "project_type_display": _display_project_type(project),
        "services": services,
        "agreed_amount_display": _display_amount(agreed_amount),
        "duration_hours": duration_hours,
        "request_sent_at_display": sent_at_label,
        "deadline_at_display": deadline_at_label,
    }
    return title_text, "\n".join(content_lines).strip(), payload


@transaction.atomic
def create_participation_notifications(*, performers, sender, request_sent_at, deadline_at, duration_hours):
    performers = list(performers)
    missing_employee = [performer for performer in performers if not performer.employee_id]
    if missing_employee:
        names = ", ".join(sorted({(performer.executor or f"#{performer.pk}").strip() for performer in missing_employee}))
        raise ValueError(f"Для части строк не найден сотрудник-получатель: {names}.")

    grouped = defaultdict(list)
    for performer in performers:
        grouped[(performer.registration_id, performer.employee_id)].append(performer)

    created = []
    for (_registration_id, _employee_id), grouped_performers in grouped.items():
        first = grouped_performers[0]
        recipient = first.employee.user
        project = first.registration
        title_text, content_text, payload = _build_participation_payload(
            recipient=recipient,
            project=project,
            performers=grouped_performers,
            request_sent_at=request_sent_at,
            deadline_at=deadline_at,
            duration_hours=duration_hours,
        )
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            related_section=Notification.RelatedSection.PROJECTS,
            recipient=recipient,
            sender=sender,
            project=project,
            title_text=title_text,
            content_text=content_text,
            payload=payload,
            sent_at=request_sent_at,
            deadline_at=deadline_at,
            is_read=False,
            is_processed=False,
        )
        NotificationPerformerLink.objects.bulk_create(
            [
                NotificationPerformerLink(
                    notification=notification,
                    performer=performer,
                    position=index,
                )
                for index, performer in enumerate(grouped_performers, start=1)
            ]
        )
        created.append(notification)
    return created


@transaction.atomic
def mark_notification_as_read(notification, actor):
    if notification.is_read:
        return notification
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.read_by = actor
    notification.save(update_fields=["is_read", "read_at", "read_by", "updated_at"])
    return notification


@transaction.atomic
def process_participation_notification(notification, actor, action_choice):
    if notification.notification_type != Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION:
        raise ValueError("Этот тип уведомления не поддерживает обработку действия.")
    if action_choice not in {
        Notification.ActionChoice.CONFIRMED,
        Notification.ActionChoice.DECLINED,
    }:
        raise ValueError("Передано неизвестное действие.")
    if notification.is_processed:
        return notification

    now = timezone.now()
    response_value = Performer.ParticipationResponse.CONFIRMED
    if action_choice == Notification.ActionChoice.DECLINED:
        response_value = Performer.ParticipationResponse.DECLINED

    performer_ids = list(notification.performer_links.values_list("performer_id", flat=True))
    Performer.objects.filter(pk__in=performer_ids).update(
        participation_response=response_value,
        participation_response_at=now,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now
        notification.read_by = actor
    notification.is_processed = True
    notification.action_at = now
    notification.action_by = actor
    notification.action_choice = action_choice
    notification.save(
        update_fields=[
            "is_read",
            "read_at",
            "read_by",
            "is_processed",
            "action_at",
            "action_by",
            "action_choice",
            "updated_at",
        ]
    )
    return notification


def serialize_notification_cards(notifications):
    pending_notifications = [item for item in notifications if item.requires_attention]
    pending_numbers = {item.pk: len(pending_notifications) - index for index, item in enumerate(pending_notifications)}

    cards = []
    for notification in notifications:
        payload = notification.payload or {}
        cards.append(
            {
                "notification": notification,
                "marker_number": pending_numbers.get(notification.pk),
                "services": payload.get("services") or [],
                "request_sent_at_display": payload.get("request_sent_at_display") or timezone.localtime(notification.sent_at).strftime("%d.%m.%Y %H:%M"),
                "deadline_at_display": payload.get("deadline_at_display") or (
                    timezone.localtime(notification.deadline_at).strftime("%H:%M %d.%m.%Y") if notification.deadline_at else "—"
                ),
                "project_label": payload.get("project_label") or notification.title_text,
                "project_manager": payload.get("project_manager") or "—",
                "project_deadline_display": payload.get("project_deadline_display") or "—",
                "project_type_display": payload.get("project_type_display") or "—",
                "agreed_amount_display": payload.get("agreed_amount_display") or "0,00",
                "duration_hours": payload.get("duration_hours") or 0,
                "recipient_name": payload.get("recipient_name") or _user_full_name(notification.recipient),
            }
        )
    return cards
