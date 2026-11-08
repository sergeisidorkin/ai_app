from django.utils import timezone

from .models import ProjectRegistration, RegistrationGroupSummaryState

NOT_STARTED_STATUS = "Не начат"
DEFERRED_STATUS = "Отложен"
SUMMARY_PROGRESS_STATUSES = ("В работе", "На проверке", "Завершён")
SUMMARY_TYPE_CHAIN_LIMIT = 3


def stage_count_label(count):
    """Счётная форма: 1 этап, 4 этапа, 5 этапов, 11 этапов, 21 этап, 22 этапа."""
    number = abs(int(count))
    last_two = number % 100
    last = number % 10
    if last == 1 and last_two != 11:
        word = "этап"
    elif last in {2, 3, 4} and last_two not in {12, 13, 14}:
        word = "этапа"
    else:
        word = "этапов"
    return f"{number} {word}"


def registration_summary_type_label(stages):
    """Тип сводной строки: цепочка до трёх этапов, дальше — число этапов."""
    items = list(stages)
    if len(items) > SUMMARY_TYPE_CHAIN_LIMIT:
        return stage_count_label(len(items))
    labels = []
    for item in items:
        label = str(getattr(item, "type_short_display", "") or "").strip()
        if label:
            labels.append(label)
    return "-".join(labels)


def registration_summary_state(statuses, deferred):
    latest = None
    for index, status in enumerate(statuses, start=1):
        if status in SUMMARY_PROGRESS_STATUSES:
            latest = (status, index)
    if latest is None:
        auto_label = NOT_STARTED_STATUS
    else:
        status, index = latest
        auto_label = f"{status} ({index}/{len(statuses)})"
    is_deferred = bool(deferred)
    all_not_started = bool(statuses) and all(status == NOT_STARTED_STATUS for status in statuses)
    return {
        "label": DEFERRED_STATUS if is_deferred else auto_label,
        "auto_label": auto_label,
        "deferred": is_deferred,
        "can_launch": all_not_started and not is_deferred,
    }


def summary_indicator_class(label):
    if label == DEFERRED_STATUS:
        return "reg-launch-status--deferred"
    if str(label or "").startswith("В работе"):
        return "reg-launch-status--work"
    if str(label or "").startswith("На проверке"):
        return "reg-launch-status--review"
    if str(label or "").startswith("Завершён") or str(label or "").startswith("Завершен"):
        return "reg-launch-status--done"
    return ""


def _prime_group_member_cache(items):
    for item in items:
        if not item.group_member_id:
            continue
        member = item.__dict__.get("group_member")
        if member is not None and getattr(member, "pk", None) == item.group_member_id:
            item._group_member_cache = member


def load_ordered_registrations():
    items = list(
        ProjectRegistration.objects.select_related("group_member", "stage_project", "stage_project__group_member").order_by("position", "id")
    )
    _prime_group_member_cache(items)
    return items


def iter_summary_blocks(items):
    start = 0
    while start < len(items):
        current_number = items[start].number
        current_group = items[start].group_display
        end = start + 1
        while (
            end < len(items)
            and items[end].number == current_number
            and items[end].group_display == current_group
        ):
            end += 1
        block = items[start:end]
        if len(block) >= 2:
            yield block, current_group
        start = end


def _parent_stage_blocks(items):
    grouped = {}
    for item in items:
        if not item.stage_project_id:
            continue
        grouped.setdefault(item.stage_project_id, []).append(item)
    for block in grouped.values():
        if len(block) >= 2:
            yield block, block[0].group_display


def summary_block_for_pk(pk, items=None):
    rows = items if items is not None else load_ordered_registrations()
    for block, group_label in _parent_stage_blocks(rows):
        if any(item.pk == pk for item in block):
            return block, group_label
    for block, group_label in iter_summary_blocks(rows):
        if any(item.stage_project_id for item in block):
            continue
        if any(item.pk == pk for item in block):
            return block, group_label
    return None, ""


def summary_block_for_project(project_id, items=None):
    rows = items if items is not None else load_ordered_registrations()
    for block, group_label in _parent_stage_blocks(rows):
        if block[0].stage_project_id == project_id:
            return block, group_label
    return None, ""


def summary_block_for_group(number, group_label, items=None):
    rows = items if items is not None else load_ordered_registrations()
    for block, label in _parent_stage_blocks(rows):
        parent = block[0].stage_project
        parent_number = parent.number if parent is not None else block[0].number
        parent_group = parent.group_display if parent is not None else label
        if parent_number == number and parent_group == group_label:
            return block
    for block, label in iter_summary_blocks(rows):
        if any(item.stage_project_id for item in block):
            continue
        if block[0].number == number and label == group_label:
            return block
    return None


def deferred_pairs_for_numbers(numbers):
    number_list = list(numbers)
    if not number_list:
        return set()
    return set(
        RegistrationGroupSummaryState.objects.filter(number__in=number_list, deferred=True)
        .values_list("number", "group_label")
    )


def is_group_deferred(number, group_label):
    return RegistrationGroupSummaryState.objects.filter(
        number=number,
        group_label=group_label,
        deferred=True,
    ).exists()


def summary_status_date_for_block(block, group_label):
    if not block:
        return None
    parent_id = block[0].stage_project_id
    if parent_id:
        return (
            ProjectRegistration.objects.filter(pk=parent_id)
            .values_list("summary_status_date", flat=True)
            .first()
        )
    return (
        RegistrationGroupSummaryState.objects.filter(
            number=block[0].number,
            group_label=group_label,
        )
        .values_list("status_date", flat=True)
        .first()
    )


def legacy_summary_status_dates(numbers):
    number_list = list(numbers)
    if not number_list:
        return {}
    return {
        (number, group_label): status_date
        for number, group_label, status_date in RegistrationGroupSummaryState.objects.filter(
            number__in=number_list
        ).values_list("number", "group_label", "status_date")
    }


def write_summary_status_date(block, group_label, value=None):
    if not block:
        return None
    value = timezone.localdate() if value is None else value
    parent_id = block[0].stage_project_id
    if parent_id:
        ProjectRegistration.objects.filter(pk=parent_id).update(summary_status_date=value)
        parent = getattr(block[0], "stage_project", None)
        if parent is not None and getattr(parent, "pk", None) == parent_id:
            parent.summary_status_date = value
        return value
    state, _created = RegistrationGroupSummaryState.objects.get_or_create(
        number=block[0].number,
        group_label=group_label,
    )
    if state.status_date != value:
        state.status_date = value
        state.save(update_fields=["status_date"])
    return value


def sync_summary_status_date_for_label_change(block, group_label, previous_label, new_label):
    if previous_label == new_label:
        return summary_status_date_for_block(block, group_label)
    return write_summary_status_date(block, group_label)


def sync_summary_status_date_for_status_change(registration, previous_status):
    block, group_label = summary_block_for_pk(registration.pk)
    if not block:
        return None
    deferred = block_is_deferred(block)
    previous_statuses = [
        previous_status if item.pk == registration.pk else item.status
        for item in block
    ]
    previous_label = registration_summary_state(previous_statuses, deferred)["label"]
    current_label = registration_summary_state([item.status for item in block], deferred)["label"]
    return sync_summary_status_date_for_label_change(
        block,
        group_label,
        previous_label,
        current_label,
    )


def summary_payload(block, group_label, deferred):
    state = registration_summary_state([item.status for item in block], deferred)
    first = block[0]
    project_id = first.stage_project_id
    key = f"project:{project_id}" if project_id else f"{first.formatted_number}:{group_label}"
    status_date = None if state["label"] == NOT_STARTED_STATUS else summary_status_date_for_block(block, group_label)
    return {
        "key": key,
        "number": first.number,
        "group": group_label,
        "label": state["label"],
        "autoLabel": state["auto_label"],
        "deferred": state["deferred"],
        "canLaunch": state["can_launch"],
        "indicatorClass": "" if state["can_launch"] else summary_indicator_class(state["label"]),
        "statusDate": status_date.isoformat() if status_date else "",
        "statusDateLabel": status_date.strftime("%d.%m.%Y") if status_date else "",
    }


def block_is_deferred(block):
    if not block:
        return False
    parent_id = block[0].stage_project_id
    if parent_id:
        parent = block[0].stage_project
        if parent is not None and getattr(parent, "pk", None) == parent_id:
            return bool(parent.summary_deferred)
        return bool(
            ProjectRegistration.objects.filter(pk=parent_id).values_list("summary_deferred", flat=True).first()
        )
    return is_group_deferred(block[0].number, block[0].group_display)


def summary_payload_for_registration(registration):
    block, group_label = summary_block_for_pk(registration.pk)
    if not block:
        return None
    for item in block:
        if item.pk == registration.pk:
            item.status = registration.status
    return summary_payload(block, group_label, block_is_deferred(block))
