import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from html import escape as html_escape

from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone

from policy_app.models import DEPARTMENT_HEAD_GROUP as DEPARTMENT_HEAD_ROLE
from projects_app.models import Performer

from .email_delivery import EmailDeliveryError, send_notification_email
from .models import Notification, NotificationPerformerLink

logger = logging.getLogger(__name__)

DELIVERY_CHANNEL_SYSTEM = "system"
DELIVERY_CHANNEL_SYSTEM_EMAIL = "system_email"
DELIVERY_CHANNEL_CONNECTED_EMAIL = "connected_email"
DELIVERY_CHANNEL_ALIASES = {
    "email": DELIVERY_CHANNEL_SYSTEM_EMAIL,
}
DELIVERY_CHANNEL_LABELS = {
    DELIVERY_CHANNEL_SYSTEM: "Системные уведомления",
    DELIVERY_CHANNEL_SYSTEM_EMAIL: "Системная электронная почта",
    DELIVERY_CHANNEL_CONNECTED_EMAIL: "Подключенная электронная почта",
}
SUPPORTED_DELIVERY_CHANNELS = (
    DELIVERY_CHANNEL_SYSTEM,
    DELIVERY_CHANNEL_SYSTEM_EMAIL,
    DELIVERY_CHANNEL_CONNECTED_EMAIL,
)


def normalize_delivery_channels(delivery_channels):
    requested = {
        DELIVERY_CHANNEL_ALIASES.get(str(value).strip(), str(value).strip())
        for value in (delivery_channels or [])
        if str(value).strip()
    }
    if not requested:
        requested = {DELIVERY_CHANNEL_SYSTEM}

    invalid = requested - set(SUPPORTED_DELIVERY_CHANNELS)
    if invalid:
        invalid_list = ", ".join(sorted(invalid))
        raise ValueError(f"Переданы неподдерживаемые каналы доставки: {invalid_list}.")

    return tuple(channel for channel in SUPPORTED_DELIVERY_CHANNELS if channel in requested)


def _deliver_notification_email_jobs(email_jobs, *, delivery_channel, email_requested=False):
    summary = {
        "channel": delivery_channel,
        "channel_label": DELIVERY_CHANNEL_LABELS.get(delivery_channel, delivery_channel),
        "requested": email_requested,
        "attempted": len(email_jobs),
        "sent": 0,
        "failed": 0,
        "errors": [],
    }
    if not email_jobs:
        return summary

    for job in email_jobs:
        recipient = job["recipient"]
        sender = job.get("sender")
        recipient_label = (
            (getattr(recipient, "email", "") or "").strip()
            or (getattr(recipient, "username", "") or "").strip()
            or f"user:{getattr(recipient, 'pk', 'unknown')}"
        )
        try:
            delivery_options = {}
            if delivery_channel == DELIVERY_CHANNEL_CONNECTED_EMAIL:
                if sender is None:
                    raise EmailDeliveryError("Не удалось определить отправителя для подключенной почты.")
                try:
                    from smtp_app.services import get_user_notification_email_options

                    delivery_options = get_user_notification_email_options(sender)
                except Exception as exc:
                    logger.warning(
                        "Failed to resolve external SMTP options for %s: %s",
                        getattr(sender, "username", sender),
                        exc,
                    )
                if not delivery_options:
                    raise EmailDeliveryError("У отправителя не настроен активный внешний SMTP-аккаунт.")
            send_notification_email(
                recipient=recipient,
                subject=job["subject"],
                content=job["content"],
                from_email=delivery_options.get("from_email"),
                connection=delivery_options.get("connection"),
                reply_to=delivery_options.get("reply_to"),
            )
            summary["sent"] += 1
        except EmailDeliveryError as exc:
            summary["failed"] += 1
            summary["errors"].append(
                {
                    "recipient": recipient_label,
                    "error": str(exc),
                    "channel": delivery_channel,
                    "channel_label": DELIVERY_CHANNEL_LABELS.get(delivery_channel, delivery_channel),
                }
            )
            logger.warning(
                "Failed to send %s notification email to %s: %s",
                delivery_channel,
                recipient_label,
                exc,
            )

    return summary


def _empty_email_delivery_summary(*, delivery_channel, email_requested=False, attempted=0):
    return {
        "channel": delivery_channel,
        "channel_label": DELIVERY_CHANNEL_LABELS.get(delivery_channel, delivery_channel),
        "requested": email_requested,
        "attempted": attempted,
        "sent": 0,
        "failed": 0,
        "errors": [],
    }


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


def _project_label_identifier(project):
    short_uid = (getattr(project, "short_uid", "") or "").strip()
    if len(short_uid) >= 7:
        return f"{project.formatted_number}{short_uid[-3:]}"
    return f"{project.formatted_number}{project.group_order_number}{project.group_alpha2}"


def _project_label(project):
    project_label_parts = [_project_label_identifier(project)]
    if project.type_short_display:
        project_label_parts.append(project.type_short_display)
    if project.name:
        project_label_parts.append(project.name)
    return " ".join(part for part in project_label_parts if part)


def _unique_project_labels(projects):
    labels = []
    seen = set()
    for project in projects:
        if not project:
            continue
        label = _project_label(project)
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def _join_unique(values, default="—"):
    items = []
    seen = set()
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            items.append(value)
            seen.add(value)
    return ", ".join(items) if items else default


def _product_stage_lines(projects):
    items = []
    seen = set()
    for project in projects:
        if not project:
            continue
        stage = int(getattr(project, "agreement_sequence", 0) or 1)
        products = project.ordered_products()
        if not products:
            key = (project.pk, stage, getattr(project, "type_short_display", ""))
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "stage": stage,
                    "project_id": project.pk or 0,
                    "line": f"Этап {stage}: {project.type_short_display or '—'} {_display_project_type(project)}".strip(),
                }
            )
            continue
        for index, product in enumerate(products):
            short_name = (getattr(product, "short_name", "") or "").strip()
            display_name = (getattr(product, "display_name", "") or "").strip()
            key = (project.pk, stage, getattr(product, "pk", None), index)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "stage": stage,
                    "project_id": project.pk or 0,
                    "line": f"Этап {stage}: {short_name} {display_name}".strip(),
                }
            )
    items.sort(key=lambda item: (item["stage"], item["project_id"], item["line"]))
    return [item["line"] for item in items]


def _project_stage(project):
    return int(getattr(project, "agreement_sequence", 0) or 1)


def _ordered_projects(projects):
    return sorted(
        [project for project in projects if project],
        key=lambda project: (_project_stage(project), project.pk or 0),
    )


def _combined_project_label(projects, fallback_project=None):
    ordered = _ordered_projects(projects)
    if not ordered:
        return _project_label(fallback_project) if fallback_project else ""
    if len(ordered) == 1:
        return _project_label(ordered[0])

    identifiers = []
    types = []
    names = []
    for project in ordered:
        identifier = _project_label_identifier(project)
        if identifier and identifier not in identifiers:
            identifiers.append(identifier)
        project_type = (getattr(project, "type_short_display", "") or "").strip()
        if project_type and project_type not in types:
            types.append(project_type)
        name = (getattr(project, "name", "") or "").strip()
        if name and name not in names:
            names.append(name)

    label_parts = []
    if identifiers:
        label_parts.append(identifiers[0] if len(identifiers) == 1 else "; ".join(identifiers))
    if types:
        label_parts.append("-".join(types))
    if names:
        label_parts.append(names[0] if len(names) == 1 else "; ".join(names))
    return " ".join(label_parts)


def _formatted_date(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    raw = str(value).strip()
    if not raw:
        return ""
    for candidate in (raw[:10], raw):
        try:
            return datetime.fromisoformat(candidate).date().strftime("%d.%m.%Y")
        except ValueError:
            pass
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date().strftime("%d.%m.%Y")
        except ValueError:
            pass
    return raw


def _date_sort_value(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for candidate in (raw[:10], raw):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _project_manager_display(projects):
    stage_managers = []
    for project in _ordered_projects(projects):
        manager = _short_fio(getattr(project, "project_manager", "")) or "—"
        stage_managers.append((_project_stage(project), manager))
    if not stage_managers:
        return "—", "—"
    unique_managers = {manager for _stage, manager in stage_managers}
    if len(unique_managers) == 1:
        manager = stage_managers[0][1]
        return manager, html_escape(manager)
    lines = [f"Этап {stage}: {manager}" for stage, manager in stage_managers]
    return "\n".join(lines), _service_list_html(lines)


def _stage_lines_display(lines):
    lines = [line for line in lines if line]
    if not lines:
        return "—", "—"
    text_value = "\n".join(f"- {line}" for line in lines)
    html_value = "<ul>" + "".join(f"<li>{html_escape(line)}</li>" for line in lines) + "</ul>"
    return text_value, html_value


def _product_stage_line(project):
    lines = _product_stage_lines([project])
    return lines[0] if lines else f"Этап {_project_stage(project)}: —"


def _service_list_html(lines):
    items = [line for line in lines if line]
    if not items:
        items = ["Без детализации"]
    return "<ul>" + "".join(f"<li>{html_escape(item)}</li>" for item in items) + "</ul>"


def _services_list_html(projects, performers):
    ordered_projects = _ordered_projects(projects)
    if len(ordered_projects) <= 1:
        return _service_list_html(_service_line(performer) for performer in performers)

    performers_by_project = defaultdict(list)
    for performer in performers:
        if getattr(performer, "registration_id", None):
            performers_by_project[performer.registration_id].append(performer)

    parts = []
    for project in ordered_projects:
        project_performers = performers_by_project.get(project.pk, [])
        if not project_performers:
            continue
        parts.append(f"<p>{html_escape(_product_stage_line(project))}</p>")
        parts.append(_service_list_html(_service_line(performer) for performer in project_performers))
    return "".join(parts) if parts else _service_list_html(_service_line(performer) for performer in performers)


def _gantt_task_deadline_values(project, performers):
    payload = getattr(project, "gantt_data", None)
    tasks = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return []

    performer_ids = {str(p.pk) for p in performers if getattr(p, "pk", None)}
    exact_values = [
        task.get("deadline")
        for task in tasks
        if isinstance(task, dict) and str(task.get("performer_id") or "") in performer_ids and task.get("deadline")
    ]
    if exact_values:
        return exact_values

    section_ids = {str(p.typical_section_id) for p in performers if getattr(p, "typical_section_id", None)}
    work_item_ids = {str(p.work_item_id) for p in performers if getattr(p, "work_item_id", None)}
    asset_names = {(p.asset_name or "").strip() for p in performers if (p.asset_name or "").strip()}
    values = []
    for task in tasks:
        if not isinstance(task, dict) or not task.get("deadline"):
            continue
        if str(task.get("typical_section_id") or "") not in section_ids:
            continue
        task_work_item = str(task.get("work_volume_id") or "")
        task_asset = (task.get("asset_name") or "").strip()
        if work_item_ids and task_work_item in work_item_ids:
            values.append(task.get("deadline"))
        elif asset_names and task_asset in asset_names:
            values.append(task.get("deadline"))
    return values


def _latest_deadline_for_project(project, performers):
    values = _gantt_task_deadline_values(project, performers)
    dated_values = [(sort_value, value) for value in values if (sort_value := _date_sort_value(value))]
    if dated_values:
        _sort_value, raw_value = max(dated_values, key=lambda item: item[0])
        return _formatted_date(raw_value)
    return _formatted_date(getattr(project, "deadline", None)) or "—"


def _project_deadline_display(projects, performers):
    performers_by_project = defaultdict(list)
    for performer in performers:
        if getattr(performer, "registration_id", None):
            performers_by_project[performer.registration_id].append(performer)

    ordered = _ordered_projects(projects)
    if not ordered:
        return "—", "—"
    if len(ordered) == 1:
        deadline = _latest_deadline_for_project(ordered[0], performers_by_project.get(ordered[0].pk, []))
        return deadline, html_escape(deadline)

    lines = [
        f"Этап {_project_stage(project)}: {_latest_deadline_for_project(project, performers_by_project.get(project.pk, []))}"
        for project in ordered
    ]
    return "\n".join(lines), _service_list_html(lines)


def _service_line(performer, *, include_project=False):
    asset_name = (performer.asset_name or "").strip()
    section_label = (
        getattr(performer.typical_section, "name_ru", "") or
        getattr(performer.typical_section, "short_name_ru", "") or
        ""
    ).strip()
    if asset_name and section_label:
        line = f"{asset_name}: {section_label}"
    elif asset_name:
        line = asset_name
    elif section_label:
        line = section_label
    else:
        line = "Без детализации"
    if include_project and getattr(performer, "registration", None):
        return f"{performer.registration.short_uid}: {line}"
    return line


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
            "performer__employee",
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


def _build_participation_payload(*, recipient, project, performers, request_sent_at, deadline_at, duration_hours, sender=None, template_type="participation_confirmation"):
    projects = []
    seen_project_ids = set()
    for performer in performers:
        performer_project = getattr(performer, "registration", None)
        if not performer_project or performer_project.pk in seen_project_ids:
            continue
        projects.append(performer_project)
        seen_project_ids.add(performer_project.pk)
    if not projects and project:
        projects = [project]
    project_labels = _unique_project_labels(projects)
    services = [_service_line(performer) for performer in performers]
    agreed_amount = sum((performer.agreed_amount or Decimal("0")) for performer in performers)
    project_label = _combined_project_label(projects, project)
    recipient_name = _user_full_name(recipient)
    project_manager, project_manager_html = _project_manager_display(projects)
    deadline_label, deadline_label_html = _project_deadline_display(projects, performers)
    project_type_display = _join_unique(
        getattr(p, "type_short_display", "") or _display_project_type(p)
        for p in projects
    )
    project_stage_lines = _product_stage_lines(projects)
    project_stages_display, project_stages_html = _stage_lines_display(project_stage_lines)
    project_number = ""
    project_numbers = {
        getattr(p, "formatted_number", "")
        for p in projects
        if getattr(p, "formatted_number", "")
    }
    if len(project_numbers) == 1:
        project_number = next(iter(project_numbers))
    deadline_at_label = timezone.localtime(deadline_at).strftime("%H:%M %d.%m.%Y") if deadline_at else "—"
    sent_at_label = timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M")
    title_text = f"Запрос подтверждения участия в проекте {project_label}".strip()

    services_html = _services_list_html(projects, performers)

    currency_code = ""
    for p in performers:
        if p.currency:
            currency_code = p.currency.code_alpha or ""
            break

    template_vars = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "project_manager": project_manager,
        "project_manager_html": project_manager_html,
        "project_deadline": deadline_label,
        "project_deadline_html": deadline_label_html,
        "project_stages": project_stages_html,
        # Backward compatibility for existing user templates that still use {project_type}.
        "project_type": project_type_display,
        "services_list": services_html,
        "agreed_amount": _display_amount(agreed_amount),
        "currency_code": currency_code,
        "duration_hours": str(duration_hours),
        "deadline_at": deadline_at_label,
    }

    content_text = None
    try:
        from letters_app.services import get_effective_template, render_template, render_subject
        tpl = get_effective_template(template_type, sender)
        if tpl:
            content_text = render_template(
                tpl.body_html,
                {
                    **template_vars,
                    "project_manager": project_manager_html,
                    "project_deadline": deadline_label_html,
                },
                safe_keys={"services_list", "project_stages", "project_manager", "project_deadline"},
            )
            if tpl.subject_template:
                title_text = render_subject(tpl.subject_template, template_vars)
    except Exception:
        logger.debug("letters_app template lookup failed, using fallback", exc_info=True)

    if content_text is None:
        content_lines = [
            f"Добрый день, {recipient_name}!",
            "",
            f"Приглашаем вас принять участие в новом проекте IMC Montan Group — {project_label}.",
            f"Руководитель проекта: {project_manager}.",
            f"Срок завершения проекта: {deadline_label}.",
            "Этапы проекта и продукты:",
            project_stages_display,
            "Предлагаемый состав услуг (разделов):",
        ]
        for service in services:
            content_lines.append(f"- {service}")
        content_lines.extend(
            [
                f"Предлагаемая оплата услуг: {_display_amount(agreed_amount)} {currency_code}".strip() + ".",
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
        content_text = "\n".join(content_lines).strip()

    payload = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "project_ids": [p.pk for p in projects if p],
        "project_labels": project_labels,
        "project_number": project_number,
        "project_types": [
            getattr(p, "type_short_display", "") or _display_project_type(p)
            for p in projects
        ],
        "project_stages": project_stage_lines,
        "project_stages_display": project_stages_display,
        "project_manager": project_manager,
        "project_deadline_display": deadline_label,
        "project_type_display": project_type_display,
        "services": services,
        "agreed_amount_display": _display_amount(agreed_amount),
        "duration_hours": duration_hours,
        "request_sent_at_display": sent_at_label,
        "deadline_at_display": deadline_at_label,
        "letter_template_type": template_type,
    }
    return title_text, content_text, payload


def create_participation_notifications(
    *,
    performers,
    sender,
    request_sent_at,
    deadline_at,
    duration_hours,
    delivery_channels=None,
):
    delivery_channels = normalize_delivery_channels(delivery_channels)
    performers = list(performers)
    missing_employee = [performer for performer in performers if not performer.employee_id]
    if missing_employee:
        names = ", ".join(sorted({(performer.executor or f"#{performer.pk}").strip() for performer in missing_employee}))
        raise ValueError(f"Для части строк не найден сотрудник-получатель: {names}.")

    grouped = defaultdict(list)
    for performer in performers:
        if performer.participation_batch_id:
            key = ("participation_batch", performer.participation_batch_id, performer.employee_id)
        else:
            key = ("registration", performer.registration_id, performer.employee_id)
        grouped[key].append(performer)

    created = []
    system_email_jobs = []
    connected_email_jobs = []
    should_create_notifications = DELIVERY_CHANNEL_SYSTEM in delivery_channels
    with transaction.atomic():
        for _group_key, grouped_performers in grouped.items():
            grouped_performers = sorted(
                grouped_performers,
                key=lambda p: (
                    p.registration.number if p.registration_id else 0,
                    p.registration_id or 0,
                    p.asset_name or "",
                    p.position or 0,
                    p.pk,
                ),
            )
            first = grouped_performers[0]
            recipient = first.employee.user
            project = first.registration
            employee_role = getattr(first.employee, "role", "") or ""
            template_type = (
                "direction_confirmation"
                if employee_role == DEPARTMENT_HEAD_ROLE
                else "participation_confirmation"
            )
            title_text, content_text, payload = _build_participation_payload(
                recipient=recipient,
                project=project,
                performers=grouped_performers,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
                sender=sender,
                template_type=template_type,
            )
            if should_create_notifications:
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
            if DELIVERY_CHANNEL_SYSTEM_EMAIL in delivery_channels:
                system_email_jobs.append(
                    {
                        "recipient": recipient,
                        "subject": title_text,
                        "content": content_text,
                        "sender": sender,
                    }
                )
            if DELIVERY_CHANNEL_CONNECTED_EMAIL in delivery_channels:
                connected_email_jobs.append(
                    {
                        "recipient": recipient,
                        "subject": title_text,
                        "content": content_text,
                        "sender": sender,
                    }
                )

    system_email_requested = DELIVERY_CHANNEL_SYSTEM_EMAIL in delivery_channels
    connected_email_requested = DELIVERY_CHANNEL_CONNECTED_EMAIL in delivery_channels
    email_delivery = {
        "requested": system_email_requested or connected_email_requested,
        "attempted": len(system_email_jobs) + len(connected_email_jobs),
        "sent": 0,
        "failed": 0,
        "errors": [],
        "channels": {
            DELIVERY_CHANNEL_SYSTEM_EMAIL: _empty_email_delivery_summary(
                delivery_channel=DELIVERY_CHANNEL_SYSTEM_EMAIL,
                email_requested=system_email_requested,
                attempted=len(system_email_jobs),
            ),
            DELIVERY_CHANNEL_CONNECTED_EMAIL: _empty_email_delivery_summary(
                delivery_channel=DELIVERY_CHANNEL_CONNECTED_EMAIL,
                email_requested=connected_email_requested,
                attempted=len(connected_email_jobs),
            ),
        },
    }
    if system_email_jobs:
        transaction.on_commit(
            lambda: _update_email_delivery_summary(
                aggregate=email_delivery,
                channel_summary=email_delivery["channels"][DELIVERY_CHANNEL_SYSTEM_EMAIL],
                delivered_summary=_deliver_notification_email_jobs(
                    system_email_jobs,
                    delivery_channel=DELIVERY_CHANNEL_SYSTEM_EMAIL,
                    email_requested=system_email_requested,
                ),
            )
        )
    if connected_email_jobs:
        transaction.on_commit(
            lambda: _update_email_delivery_summary(
                aggregate=email_delivery,
                channel_summary=email_delivery["channels"][DELIVERY_CHANNEL_CONNECTED_EMAIL],
                delivered_summary=_deliver_notification_email_jobs(
                    connected_email_jobs,
                    delivery_channel=DELIVERY_CHANNEL_CONNECTED_EMAIL,
                    email_requested=connected_email_requested,
                )
            )
        )
    return {
        "notifications": created,
        "delivery_channels": delivery_channels,
        "email_delivery": email_delivery,
    }


def _update_email_delivery_summary(*, aggregate, channel_summary, delivered_summary):
    channel_summary.update(delivered_summary)
    aggregate["sent"] += delivered_summary["sent"]
    aggregate["failed"] += delivered_summary["failed"]
    aggregate["errors"].extend(delivered_summary["errors"])


@transaction.atomic
def mark_notification_as_read(notification, actor):
    if notification.is_read:
        return notification
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.read_by = actor
    update_fields = ["is_read", "read_at", "read_by", "updated_at"]
    auto_process_types = {
        Notification.NotificationType.EMPLOYEE_SCAN_SENT,
    }
    if notification.notification_type in auto_process_types and not notification.is_processed:
        notification.is_processed = True
        notification.action_at = notification.read_at
        update_fields += ["is_processed", "action_at"]
    notification.save(update_fields=update_fields)
    return notification


@transaction.atomic
def complete_contract_notifications_for_performers(*, performer_ids, actor):
    performer_ids = [int(value) for value in performer_ids or []]
    if not performer_ids or not getattr(actor, "is_authenticated", False):
        return 0

    notification_ids = (
        NotificationPerformerLink.objects
        .filter(
            performer_id__in=performer_ids,
            notification__recipient=actor,
            notification__notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION,
        )
        .values_list("notification_id", flat=True)
        .distinct()
    )
    notifications = (
        Notification.objects
        .filter(pk__in=notification_ids, recipient=actor)
        .exclude(is_read=True, is_processed=True)
    )

    now = timezone.now()
    completed = 0
    for notification in notifications:
        update_fields = []
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = now
            notification.read_by = actor
            update_fields += ["is_read", "read_at", "read_by"]
        if not notification.is_processed:
            notification.is_processed = True
            notification.action_at = now
            notification.action_by = actor
            update_fields += ["is_processed", "action_at", "action_by"]
        if update_fields:
            notification.save(update_fields=[*update_fields, "updated_at"])
            completed += 1
    return completed


def check_direction_notifications_completion(performer_ids):
    """Auto-complete direction_confirmation notifications where all linked performers are confirmed."""
    if not performer_ids:
        return
    candidate_notification_ids = set(
        NotificationPerformerLink.objects
        .filter(
            performer_id__in=performer_ids,
            notification__is_processed=False,
            notification__notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
        )
        .values_list("notification_id", flat=True)
    )
    for nid in candidate_notification_ids:
        notification = Notification.objects.get(pk=nid)
        if (notification.payload or {}).get("letter_template_type") != "direction_confirmation":
            continue
        all_ids = list(
            notification.performer_links.values_list("performer_id", flat=True)
        )
        all_done = not Performer.objects.filter(pk__in=all_ids).exclude(
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        ).exists()
        if all_done:
            now = timezone.now()
            notification.is_processed = True
            notification.action_at = notification.action_at or now
            notification.save(update_fields=["is_processed", "action_at", "updated_at"])


def _grant_nextcloud_workspace_access_for_confirmed_performers(performer_ids):
    from core.cloud_storage import is_nextcloud_primary

    if not is_nextcloud_primary():
        return 0

    from nextcloud_app.api import NextcloudApiError
    from nextcloud_app.workspace import grant_project_workspace_editor_access_for_performers

    try:
        return grant_project_workspace_editor_access_for_performers(performer_ids)
    except NextcloudApiError as exc:
        raise ValueError(f"Не удалось предоставить доступ к рабочему пространству проекта в Nextcloud: {exc}") from exc


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
    is_direction = (notification.payload or {}).get("letter_template_type") == "direction_confirmation"
    all_performer_ids = list(notification.performer_links.values_list("performer_id", flat=True))

    if is_direction and action_choice == Notification.ActionChoice.CONFIRMED:
        dh_employee_id = notification.recipient.employee_profile.pk
        self_performer_ids = list(
            notification.performer_links
            .filter(performer__employee_id=dh_employee_id)
            .exclude(performer__participation_response=Performer.ParticipationResponse.CONFIRMED)
            .values_list("performer_id", flat=True)
        )
        if self_performer_ids:
            Performer.objects.filter(pk__in=self_performer_ids).update(
                participation_response=Performer.ParticipationResponse.CONFIRMED,
                participation_response_at=now,
                contract_signing_note="Разрабатывается проект договора",
            )
            from contracts_app.services import prefill_contract_adjustment_fields
            from worktime_app.services import ensure_confirmed_assignments_for_performers

            prefill_contract_adjustment_fields(self_performer_ids, confirmed_at=now)
            ensure_confirmed_assignments_for_performers(self_performer_ids)
            _grant_nextcloud_workspace_access_for_confirmed_performers(self_performer_ids)
        all_confirmed = not Performer.objects.filter(
            pk__in=all_performer_ids,
        ).exclude(
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        ).exists()
        is_fully_processed = all_confirmed
    else:
        response_value = Performer.ParticipationResponse.CONFIRMED
        if action_choice == Notification.ActionChoice.DECLINED:
            response_value = Performer.ParticipationResponse.DECLINED
        update_kwargs = {
            "participation_response": response_value,
            "participation_response_at": now,
        }
        if action_choice == Notification.ActionChoice.CONFIRMED:
            update_kwargs["contract_signing_note"] = "Разрабатывается проект договора"
        Performer.objects.filter(pk__in=all_performer_ids).update(**update_kwargs)
        if action_choice == Notification.ActionChoice.CONFIRMED:
            from contracts_app.services import prefill_contract_adjustment_fields
            from worktime_app.services import ensure_confirmed_assignments_for_performers

            prefill_contract_adjustment_fields(all_performer_ids, confirmed_at=now)
            ensure_confirmed_assignments_for_performers(all_performer_ids)
            _grant_nextcloud_workspace_access_for_confirmed_performers(all_performer_ids)
        is_fully_processed = True

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now
        notification.read_by = actor
    notification.is_processed = is_fully_processed
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

    check_direction_notifications_completion(all_performer_ids)

    return notification


def _build_info_request_payload(*, recipient, project, performers, request_sent_at, deadline_at, duration_hours, sender=None):
    services = [_service_line(performer) for performer in performers]
    project_label_parts = [project.short_uid]
    if project.type_short_display:
        project_label_parts.append(project.type_short_display)
    if project.name:
        project_label_parts.append(project.name)
    project_label = " ".join(part for part in project_label_parts if part)
    recipient_name = _user_full_name(recipient)
    deadline_at_label = timezone.localtime(deadline_at).strftime("%H:%M %d.%m.%Y") if deadline_at else "—"
    sent_at_label = timezone.localtime(request_sent_at).strftime("%d.%m.%y %H:%M")

    services_html = (
        "<ul>" + "".join(f"<li>{s}</li>" for s in services) + "</ul>"
        if services else "<ul><li>—</li></ul>"
    )

    template_vars = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "services_list": services_html,
        "duration_hours": str(duration_hours),
        "deadline_at": deadline_at_label,
    }

    title_text = f"Согласование запроса по проекту {project_label}".strip()
    content_text = None

    try:
        from letters_app.services import get_effective_template, render_template, render_subject
        tpl = get_effective_template("request_approval", sender)
        if tpl:
            content_text = render_template(tpl.body_html, template_vars, safe_keys={"services_list"})
            if tpl.subject_template:
                title_text = render_subject(tpl.subject_template, template_vars)
    except Exception:
        logger.debug("letters_app template lookup failed for request_approval, using fallback", exc_info=True)

    if content_text is None:
        content_lines = [
            f"Добрый день, {recipient_name}!",
            "",
            f"Прошу согласовать информационный запрос по проекту {project_label} по следующим разделам:",
        ]
        for service in services:
            content_lines.append(f"- {service}")
        content_lines.extend(
            [
                "",
                (
                    f"Для согласования информационного запроса необходимо изучить сформированный "
                    f"типовой чек-лист по проекту {project_label} в разделе «Чек-листы», "
                    f"при необходимости внести изменения и согласовать все разделы итогового чек-листа, "
                    f"кликнув на кнопку «Согласовать запрос (чек-лист)» в разделе «Чек-листы» внизу страницы "
                    f"или согласовать запрос по отдельным разделам, кликая на кнопки "
                    f"«Согласовать раздел чек-листа» в каждом выбранном в фильтре разделе."
                ),
                "",
                (
                    f"Согласовать запрос необходимо в течение {duration_hours} "
                    f"часов с момента отправки данного сообщения\u00a0— до {deadline_at_label}."
                ),
                "",
                "С уважением,",
                "IMC Montan AI",
            ]
        )
        content_text = "\n".join(content_lines).strip()

    payload = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "services": services,
        "duration_hours": duration_hours,
        "request_sent_at_display": sent_at_label,
        "deadline_at_display": deadline_at_label,
    }
    return title_text, content_text, payload


@transaction.atomic
def create_info_request_notifications(*, performers, sender, request_sent_at, deadline_at, duration_hours):
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
        title_text, content_text, payload = _build_info_request_payload(
            recipient=recipient,
            project=project,
            performers=grouped_performers,
            request_sent_at=request_sent_at,
            deadline_at=deadline_at,
            duration_hours=duration_hours,
            sender=sender,
        )
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_INFO_REQUEST_APPROVAL,
            related_section=Notification.RelatedSection.CHECKLISTS,
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


def _short_fio(full_name):
    raw = " ".join(str(full_name or "").split())
    if not raw:
        return ""
    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


def _build_contract_payload(*, recipient, project, performers, request_sent_at, deadline_at, duration_hours, sender=None):
    services = [_service_line(performer) for performer in performers]
    agreed_amount = sum((performer.agreed_amount or Decimal("0")) for performer in performers)

    project_label_parts = [project.short_uid]
    if project.type_short_display:
        project_label_parts.append(project.type_short_display)
    if project.name:
        project_label_parts.append(project.name)
    project_label = " ".join(part for part in project_label_parts if part)

    recipient_name = _user_full_name(recipient)
    executor_fio = _short_fio(performers[0].executor) if performers else "—"
    deadline_label = project.deadline.strftime("%d.%m.%Y") if project.deadline else "—"

    currency_code = ""
    for p in performers:
        if p.currency:
            currency_code = p.currency.code_alpha or ""
            break

    prepayment_values = [p.prepayment for p in performers if p.prepayment is not None]
    final_payment_values = [p.final_payment for p in performers if p.final_payment is not None]
    prepayment_display = f"{int(prepayment_values[0])}%" if prepayment_values else "—"
    final_payment_display = f"{int(final_payment_values[0])}%" if final_payment_values else "—"

    document_docx_link = ""
    document_pdf_link = ""
    for p in performers:
        if p.contract_project_link:
            document_docx_link = p.contract_project_link
            break
    for p in performers:
        if p.contract_pdf_link:
            document_pdf_link = p.contract_pdf_link
            break

    deadline_at_label = timezone.localtime(deadline_at).strftime("%H:%M %d.%m.%Y") if deadline_at else "—"
    services_html = "<ul>" + "".join(f"<li>{s}</li>" for s in services) + "</ul>" if services else "<ul><li>—</li></ul>"

    title_text = f"Отправлен проект договора по проекту {project_label}".strip()

    template_vars = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "executor": executor_fio,
        "services_list": services_html,
        "agreed_amount": f"{_display_amount(agreed_amount)} {currency_code}".strip(),
        "currency_code": currency_code,
        "prepayment_percent": prepayment_display,
        "final_payment_percent": final_payment_display,
        "document_docx_link": document_docx_link,
        "document_pdf_link": document_pdf_link,
        "document_link": document_docx_link,
        "project_deadline": deadline_label,
        "duration_hours": str(duration_hours),
        "deadline_at": deadline_at_label,
    }

    content_text = None
    try:
        from letters_app.services import get_effective_template, render_template, render_subject
        tpl = get_effective_template("contract_sending", sender)
        if tpl:
            document_docx_link_html = (
                f'<a href="{document_docx_link}" target="_blank" rel="noopener">{document_docx_link}</a>'
                if document_docx_link else ""
            )
            document_pdf_link_html = (
                f'<a href="{document_pdf_link}" target="_blank" rel="noopener">{document_pdf_link}</a>'
                if document_pdf_link else ""
            )
            body_vars = {
                **template_vars,
                "document_docx_link": document_docx_link_html,
                "document_pdf_link": document_pdf_link_html,
                "document_link": document_docx_link_html,
            }
            content_text = render_template(
                tpl.body_html,
                body_vars,
                safe_keys={"services_list", "document_docx_link", "document_pdf_link", "document_link"},
            )
            if tpl.subject_template:
                title_text = render_subject(tpl.subject_template, template_vars)
    except Exception:
        logger.debug("letters_app template lookup failed for contract_sending, using fallback", exc_info=True)

    if content_text is None:
        content_lines = [
            f"Добрый день, {recipient_name}",
            "",
            f"В связи с вашим подтверждением готовности принять участие в проекте {project_label} "
            f"направляем проект договора.",
            "Состав активов:",
        ]
        for service in services:
            content_lines.append(f"- {service}")
        content_lines.extend(
            [
                "",
                f"Проект: {project_label}",
                f"Исполнитель: {executor_fio}",
                f"Оплата услуг без учета налогов: {_display_amount(agreed_amount)} {currency_code}".strip(),
                f"Порядок оплаты: {prepayment_display} аванс, {final_payment_display} окончательный платёж",
                f"Срок исполнения: до {deadline_label}",
                f"DOCX доступен для скачивания по ссылке: {document_docx_link}",
            ]
        )
        if document_pdf_link:
            content_lines.append(f"PDF доступен для скачивания по ссылке: {document_pdf_link}")
        content_lines.extend(
            [
                "",
                (
                    f"Подписать договор и загрузить подписанную скан-копию в разделе «Договоры» "
                    f"на сайте imcmontanai.ru необходимо в течение {duration_hours} "
                    f"часов с момента отправки данного сообщения — до {deadline_at_label}."
                ),
                "",
                "С уважением,",
                "IMC Montan AI",
            ]
        )
        content_text = "\n".join(content_lines).strip()

    payload = {
        "recipient_name": recipient_name,
        "project_label": project_label,
        "executor_fio": executor_fio,
        "services": services,
        "agreed_amount_display": _display_amount(agreed_amount),
        "currency_code": currency_code,
        "prepayment_display": prepayment_display,
        "final_payment_display": final_payment_display,
        "document_docx_link": document_docx_link,
        "document_pdf_link": document_pdf_link,
        "document_link": document_docx_link,
        "project_deadline_display": deadline_label,
        "duration_hours": duration_hours,
        "request_sent_at_display": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
        "deadline_at_display": deadline_at_label,
    }
    return title_text, content_text, payload


@transaction.atomic
def create_contract_notifications(
    *,
    performers,
    sender,
    request_sent_at,
    deadline_at,
    duration_hours,
    delivery_channels=None,
):
    delivery_channels = normalize_delivery_channels(delivery_channels)
    performers = list(performers)
    missing_employee = [performer for performer in performers if not performer.employee_id]
    if missing_employee:
        names = ", ".join(sorted({(performer.executor or f"#{performer.pk}").strip() for performer in missing_employee}))
        raise ValueError(f"Для части строк не найден сотрудник-получатель: {names}.")

    grouped = defaultdict(list)
    for performer in performers:
        if performer.contract_batch_id:
            key = ("contract_batch", performer.contract_batch_id, performer.employee_id)
        else:
            key = ("registration", performer.registration_id, performer.employee_id)
        grouped[key].append(performer)

    created = []
    system_email_jobs = []
    connected_email_jobs = []
    should_create_notifications = DELIVERY_CHANNEL_SYSTEM in delivery_channels
    for _group_key, grouped_performers in grouped.items():
        first = grouped_performers[0]
        recipient = first.employee.user
        project = first.registration
        title_text, content_text, payload = _build_contract_payload(
            recipient=recipient,
            project=project,
            performers=grouped_performers,
            request_sent_at=request_sent_at,
            deadline_at=deadline_at,
            duration_hours=duration_hours,
            sender=sender,
        )
        if should_create_notifications:
            notification = Notification.objects.create(
                notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION,
                related_section=Notification.RelatedSection.CONTRACTS,
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
        if DELIVERY_CHANNEL_SYSTEM_EMAIL in delivery_channels:
            system_email_jobs.append(
                {
                    "recipient": recipient,
                    "subject": title_text,
                    "content": content_text,
                    "sender": sender,
                }
            )
        if DELIVERY_CHANNEL_CONNECTED_EMAIL in delivery_channels:
            connected_email_jobs.append(
                {
                    "recipient": recipient,
                    "subject": title_text,
                    "content": content_text,
                    "sender": sender,
                }
            )

    system_email_requested = DELIVERY_CHANNEL_SYSTEM_EMAIL in delivery_channels
    connected_email_requested = DELIVERY_CHANNEL_CONNECTED_EMAIL in delivery_channels
    email_delivery = {
        "requested": system_email_requested or connected_email_requested,
        "attempted": len(system_email_jobs) + len(connected_email_jobs),
        "sent": 0,
        "failed": 0,
        "errors": [],
        "channels": {
            DELIVERY_CHANNEL_SYSTEM_EMAIL: _empty_email_delivery_summary(
                delivery_channel=DELIVERY_CHANNEL_SYSTEM_EMAIL,
                email_requested=system_email_requested,
                attempted=len(system_email_jobs),
            ),
            DELIVERY_CHANNEL_CONNECTED_EMAIL: _empty_email_delivery_summary(
                delivery_channel=DELIVERY_CHANNEL_CONNECTED_EMAIL,
                email_requested=connected_email_requested,
                attempted=len(connected_email_jobs),
            ),
        },
    }
    if system_email_jobs:
        transaction.on_commit(
            lambda: _update_email_delivery_summary(
                aggregate=email_delivery,
                channel_summary=email_delivery["channels"][DELIVERY_CHANNEL_SYSTEM_EMAIL],
                delivered_summary=_deliver_notification_email_jobs(
                    system_email_jobs,
                    delivery_channel=DELIVERY_CHANNEL_SYSTEM_EMAIL,
                    email_requested=system_email_requested,
                ),
            )
        )
    if connected_email_jobs:
        transaction.on_commit(
            lambda: _update_email_delivery_summary(
                aggregate=email_delivery,
                channel_summary=email_delivery["channels"][DELIVERY_CHANNEL_CONNECTED_EMAIL],
                delivered_summary=_deliver_notification_email_jobs(
                    connected_email_jobs,
                    delivery_channel=DELIVERY_CHANNEL_CONNECTED_EMAIL,
                    email_requested=connected_email_requested,
                ),
            )
        )
    return {
        "notifications": created,
        "delivery_channels": delivery_channels,
        "email_delivery": email_delivery,
    }


@transaction.atomic
def process_info_request_notification(notification, actor):
    if notification.notification_type != Notification.NotificationType.PROJECT_INFO_REQUEST_APPROVAL:
        raise ValueError("Этот тип уведомления не поддерживает согласование.")
    if notification.is_processed:
        return notification

    now = timezone.now()

    performer_ids = list(notification.performer_links.values_list("performer_id", flat=True))
    Performer.objects.filter(pk__in=performer_ids).update(
        info_approval_status=Performer.InfoApprovalStatus.APPROVED,
        info_approval_at=now,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now
        notification.read_by = actor
    notification.is_processed = True
    notification.action_at = now
    notification.action_by = actor
    notification.action_choice = Notification.ActionChoice.APPROVED
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


def _build_scan_payload(*, recipient, project, performers, sender=None):
    agreed_amount = sum((performer.agreed_amount or Decimal("0")) for performer in performers)

    project_label_parts = [project.short_uid]
    if project.type_short_display:
        project_label_parts.append(project.type_short_display)
    if project.name:
        project_label_parts.append(project.name)
    project_label = " ".join(part for part in project_label_parts if part)

    executor_fio = _short_fio(performers[0].executor) if performers else "—"
    deadline_label = project.deadline.strftime("%d.%m.%Y") if project.deadline else "—"

    currency_code = ""
    for p in performers:
        if p.currency:
            currency_code = p.currency.code_alpha or ""
            break

    prepayment_values = [p.prepayment for p in performers if p.prepayment is not None]
    final_payment_values = [p.final_payment for p in performers if p.final_payment is not None]
    prepayment_display = f"{int(prepayment_values[0])}%" if prepayment_values else "—"
    final_payment_display = f"{int(final_payment_values[0])}%" if final_payment_values else "—"

    document_link_scan = ""
    for p in performers:
        if p.contract_employee_scan_link:
            document_link_scan = p.contract_employee_scan_link
            break

    recipient_name_lawer = _user_full_name(recipient)

    title_text = f"Исполнитель ({executor_fio}) отправил скан договора по проекту {project_label}".strip()

    template_vars = {
        "recipient_name_lawer": recipient_name_lawer,
        "project_label": project_label,
        "executor": executor_fio,
        "agreed_amount": f"{_display_amount(agreed_amount)} {currency_code}".strip(),
        "prepayment_percent": prepayment_display,
        "final_payment_percent": final_payment_display,
        "project_deadline": deadline_label,
        "document_link_scan": document_link_scan,
    }

    content_text = None
    try:
        from letters_app.services import get_effective_template, render_template, render_subject
        tpl = get_effective_template("scan_sending", sender)
        if tpl:
            scan_link_html = (
                f'<a href="{document_link_scan}" target="_blank" rel="noopener">{document_link_scan}</a>'
                if document_link_scan else ""
            )
            body_vars = {**template_vars, "document_link_scan": scan_link_html}
            content_text = render_template(tpl.body_html, body_vars, safe_keys={"document_link_scan"})
            if tpl.subject_template:
                title_text = render_subject(tpl.subject_template, template_vars)
    except Exception:
        logger.debug("letters_app template lookup failed for scan_sending, using fallback", exc_info=True)

    if content_text is None:
        content_lines = [
            f"Добрый день, {recipient_name_lawer}",
            "",
            f"Вам отправлена подписанная исполнителем скан-копия договора по проекту {project_label}.",
            "",
            f"Проект: {project_label}",
            f"Исполнитель: {executor_fio}",
            f"Оплата услуг без учета налогов: {_display_amount(agreed_amount)} {currency_code}".strip(),
            f"Порядок оплаты: {prepayment_display} аванс, {final_payment_display} окончательный платёж",
            f"Срок исполнения: до {deadline_label}",
            f"Документ доступен для скачивания по ссылке: {document_link_scan}",
            "",
            "Необходимо подписать договор и загрузить скан-копию итогового варианта "
            "договора, подписанного двумя сторонами, на сайт imcmontanai.ru "
            "в таблицу «Договоры» раздела «Договоры».",
            "",
            "С уважением,",
            "IMC Montan AI",
        ]
        content_text = "\n".join(content_lines).strip()

    payload = {
        "recipient_name_lawer": recipient_name_lawer,
        "project_label": project_label,
        "executor_fio": executor_fio,
        "agreed_amount_display": _display_amount(agreed_amount),
        "currency_code": currency_code,
        "prepayment_display": prepayment_display,
        "final_payment_display": final_payment_display,
        "document_link_scan": document_link_scan,
        "project_deadline_display": deadline_label,
    }
    return title_text, content_text, payload


@transaction.atomic
def create_scan_notifications(*, performers, sender):
    from django.contrib.auth import get_user_model
    from policy_app.models import LAWYER_GROUP
    User = get_user_model()

    lawyer_user = (
        User.objects
        .filter(groups__name=LAWYER_GROUP, is_staff=True, is_active=True)
        .order_by("pk")
        .first()
    )
    if not lawyer_user:
        raise ValueError("Не найден пользователь с ролью «Юрист».")

    performers = list(performers)
    grouped = defaultdict(list)
    for performer in performers:
        grouped[(performer.registration_id, performer.employee_id)].append(performer)

    created = []
    now = timezone.now()
    for (_registration_id, _employee_id), grouped_performers in grouped.items():
        first = grouped_performers[0]
        project = first.registration
        title_text, content_text, payload = _build_scan_payload(
            recipient=lawyer_user,
            project=project,
            performers=grouped_performers,
            sender=sender,
        )
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.EMPLOYEE_SCAN_SENT,
            related_section=Notification.RelatedSection.CONTRACTS,
            recipient=lawyer_user,
            sender=sender,
            project=project,
            title_text=title_text,
            content_text=content_text,
            payload=payload,
            sent_at=now,
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


def serialize_notification_cards(notifications):
    pending_notifications = [item for item in notifications if item.requires_attention]
    pending_numbers = {item.pk: len(pending_notifications) - index for index, item in enumerate(pending_notifications)}

    cards = []
    for notification in notifications:
        payload = notification.payload or {}
        is_direction = payload.get("letter_template_type") == "direction_confirmation"

        show_self_confirm = False
        if is_direction and not notification.is_processed:
            recipient_user_id = notification.recipient_id
            for link in notification.performer_links.all():
                perf = link.performer
                if (perf.employee_id
                        and perf.employee.user_id == recipient_user_id
                        and perf.participation_response != Performer.ParticipationResponse.CONFIRMED):
                    show_self_confirm = True
                    break

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
                "executor_fio": payload.get("executor_fio") or "—",
                "currency_code": payload.get("currency_code") or "",
                "prepayment_display": payload.get("prepayment_display") or "—",
                "final_payment_display": payload.get("final_payment_display") or "—",
                "document_docx_link": payload.get("document_docx_link") or payload.get("document_link") or "",
                "document_pdf_link": payload.get("document_pdf_link") or "",
                "document_link": payload.get("document_docx_link") or payload.get("document_link") or "",
                "document_link_scan": payload.get("document_link_scan") or "",
                "recipient_name_lawer": payload.get("recipient_name_lawer") or "",
                "content_html": (notification.content_text or "")
                    if (notification.content_text or "").lstrip().startswith("<")
                    else "",
                "is_direction_confirmation": is_direction,
                "show_self_confirm_button": show_self_confirm,
            }
        )
    return cards
