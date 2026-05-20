import uuid

from django.db import models
from django.utils import timezone

from core.cloud_storage import sanitize_folder_name
from contacts_app.models import CitizenshipRecord
from group_app.models import GroupMember
from projects_app.models import Performer
from users_app.forms import FREELANCER_LABEL
from users_app.models import Employee


def normalize_contract_person_name(value):
    return " ".join(str(value or "").split()).strip()


def build_contract_number(performer, sent_at, addendum_number=None):
    reg = getattr(performer, "registration", None)
    if not reg or getattr(reg, "group_alpha2", "") != "RU":
        return ""
    parts = (performer.executor or "").split()
    if len(parts) < 2:
        return ""
    initials = parts[0][0] + parts[1][0]
    local_dt = timezone.localtime(sent_at)
    base = f"IMCM/{reg.number}-{initials}/{local_dt:%m-%y}"
    if addendum_number is not None:
        base = f"{base} ДС{addendum_number}"
    return base


def contract_executor_short_name(executor_full_name):
    raw = " ".join(str(executor_full_name or "").split())
    if not raw:
        return "Unknown"
    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(part[0] for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


def contract_kind_label(*, is_addendum=False, addendum_number=None):
    if is_addendum:
        return f"ДС{addendum_number or ''}".strip()
    return "Договор"


def contract_project_number_display(project):
    if not project:
        return ""
    short_uid = (getattr(project, "short_uid", "") or "").strip()
    suffix = short_uid[-3:] if len(short_uid) >= 3 else f"{project.group_order_number}{project.group_alpha2}"
    return f"{project.formatted_number}{suffix}"


def _has_multiple_contract_stages(performers):
    stage_keys = set()
    for performer in performers or []:
        project = getattr(performer, "registration", None)
        if not project:
            continue
        stage_keys.add(getattr(project, "pk", None) or getattr(project, "short_uid", ""))
    return len(stage_keys) > 1


def build_contract_file_name(
    performer,
    *,
    extension=".docx",
    is_addendum=None,
    addendum_number=None,
    batch_performers=None,
):
    project = getattr(performer, "registration", None)
    if batch_performers is not None and _has_multiple_contract_stages(batch_performers):
        project_id = contract_project_number_display(project)
    else:
        project_id = str(getattr(project, "short_uid", "") or "") if project else ""
    project_prefix = project_id or "Unknown"
    executor_name = contract_executor_short_name(getattr(performer, "executor", ""))
    ext = extension if str(extension or "").startswith(".") else f".{extension or 'docx'}"
    if is_addendum is None:
        is_addendum = bool(getattr(performer, "contract_is_addendum", False))
    if addendum_number is None:
        addendum_number = getattr(performer, "contract_addendum_number", None)
    kind = contract_kind_label(is_addendum=is_addendum, addendum_number=addendum_number)
    suffix = f"_{kind}" if is_addendum and kind else ""
    return sanitize_folder_name(f"Договор {project_prefix}_{executor_name}{suffix}{ext}")


def effective_contract_employee_ids(performers):
    performer_list = list(performers)
    executor_names_without_employee = {
        normalize_contract_person_name(p.executor)
        for p in performer_list
        if not p.employee_id and normalize_contract_person_name(p.executor)
    }
    employee_id_by_name = {}
    if executor_names_without_employee:
        for employee in Employee.objects.select_related("user", "person_record").all():
            full_name = normalize_contract_person_name(Performer.employee_full_name(employee))
            if full_name in executor_names_without_employee and full_name not in employee_id_by_name:
                employee_id_by_name[full_name] = employee.pk

    performer_effective_employee_id = {}
    employee_ids = set()
    for performer in performer_list:
        employee_id = performer.employee_id
        if not employee_id:
            employee_id = employee_id_by_name.get(normalize_contract_person_name(performer.executor))
        performer_effective_employee_id[id(performer)] = employee_id
        if employee_id:
            employee_ids.add(employee_id)
    return performer_effective_employee_id, employee_ids


def group_member_for_country(country):
    if not country:
        return None
    code = (getattr(country, "code", "") or "").strip()
    name = (getattr(country, "short_name", "") or "").strip()
    alpha2 = (getattr(country, "alpha2", "") or "").strip()
    filters = models.Q()
    if code:
        filters |= models.Q(country_code=code)
    if name:
        filters |= models.Q(country_name=name)
    if alpha2:
        filters |= models.Q(country_alpha2__iexact=alpha2)
    if not filters:
        return None
    return (
        GroupMember.objects
        .exclude(country_alpha2="")
        .filter(filters)
        .order_by("position", "id")
        .first()
    )


def default_contract_group_members(performers):
    performer_list = list(performers)
    if not performer_list:
        return {}

    performer_employee_id, employee_ids = effective_contract_employee_ids(performer_list)
    employee_person_ids = {}
    if employee_ids:
        employee_person_ids = dict(
            Employee.objects
            .filter(pk__in=employee_ids, person_record_id__isnull=False)
            .values_list("pk", "person_record_id")
        )

    person_ids = set(employee_person_ids.values())
    country_by_person_id = {}
    if person_ids:
        citizenships = (
            CitizenshipRecord.objects
            .select_related("country")
            .filter(person_id__in=person_ids, is_active=True, country_id__isnull=False)
            .order_by("position", "id")
        )
        for citizenship in citizenships:
            country_by_person_id.setdefault(citizenship.person_id, citizenship.country)

    group_by_country_id = {}
    for country in country_by_person_id.values():
        if country and country.pk not in group_by_country_id:
            group_by_country_id[country.pk] = group_member_for_country(country)

    result = {}
    for performer in performer_list:
        employee_id = performer_employee_id.get(id(performer))
        person_id = employee_person_ids.get(employee_id)
        country = country_by_person_id.get(person_id)
        result[performer.pk] = group_by_country_id.get(getattr(country, "pk", None))
    return result


def attach_contract_group_members(performers):
    performer_list = list(performers)
    if not performer_list:
        return performer_list

    default_groups = default_contract_group_members(performer_list)
    for performer in performer_list:
        selected_group = getattr(performer, "contract_group_member", None)
        default_group = default_groups.get(performer.pk)
        effective_group = selected_group or default_group
        performer.contract_group_member_default = default_group
        performer.contract_group_member_effective = effective_group
        performer.contract_group_display = (
            effective_group.group_code_label if effective_group else ""
        )

    return performer_list


def prefill_contract_adjustment_fields(performer_ids, *, confirmed_at=None):
    ids = [int(pk) for pk in performer_ids if pk]
    if not ids:
        return 0

    confirmed_at = confirmed_at or timezone.now()
    performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__group_member",
            "employee",
            "employee__user",
            "employee__person_record",
            "contract_group_member",
        )
        .filter(
            pk__in=ids,
            employee__employment=FREELANCER_LABEL,
        )
        .order_by("registration_id", "executor", "position", "id")
    )
    if not performers:
        return 0

    default_groups = default_contract_group_members(performers)
    grouped = {}
    for performer in performers:
        executor = normalize_contract_person_name(performer.executor)
        if performer.participation_batch_id:
            key = ("participation_batch", performer.participation_batch_id, executor)
        else:
            key = ("registration", performer.registration_id, executor)
        grouped.setdefault(key, []).append(performer)

    updated = 0
    for (group_kind, group_value, executor), group_performers in grouped.items():
        batch_filter = models.Q(executor=executor)
        if group_kind == "participation_batch":
            batch_filter &= models.Q(participation_batch_id=group_value)
        else:
            batch_filter &= models.Q(registration_id=group_value)

        pending_batch_id = next((p.contract_batch_id for p in group_performers if p.contract_batch_id), None)
        if not pending_batch_id:
            existing_pending = (
                Performer.objects
                .filter(batch_filter, contract_batch_id__isnull=False)
                .filter(contract_project_created=False, contract_project_disk_folder="")
                .order_by("position", "id")
                .first()
            )
            pending_batch_id = existing_pending.contract_batch_id if existing_pending else uuid.uuid4()

        created_batches = (
            Performer.objects
            .filter(batch_filter, contract_batch_id__isnull=False)
            .filter(models.Q(contract_project_created=True) | ~models.Q(contract_project_disk_folder=""))
            .values("contract_batch_id")
            .distinct()
        )
        created_batch_count = created_batches.count()
        is_addendum = created_batch_count > 0
        addendum_number = created_batch_count if is_addendum else None

        base_date = confirmed_at
        if is_addendum:
            first_performer = (
                Performer.objects
                .filter(batch_filter, contract_batch_id__isnull=False, contract_is_addendum=False)
                .filter(models.Q(contract_project_created=True) | ~models.Q(contract_project_disk_folder=""))
                .order_by("contract_sent_at", "id")
                .first()
            )
            if first_performer and first_performer.contract_sent_at:
                base_date = first_performer.contract_sent_at

        representative = group_performers[0]
        file_name_performers = group_performers
        if group_kind == "participation_batch":
            file_name_performers = list(
                Performer.objects
                .select_related("registration")
                .filter(
                    batch_filter,
                    participation_response=Performer.ParticipationResponse.CONFIRMED,
                    employee__employment=FREELANCER_LABEL,
                )
                .order_by("registration__agreement_sequence", "registration_id", "position", "id")
            ) or group_performers
        generated_number = build_contract_number(representative, base_date, addendum_number)
        generated_file = build_contract_file_name(
            representative,
            is_addendum=is_addendum,
            addendum_number=addendum_number,
            batch_performers=file_name_performers,
        )
        contract_date = timezone.localtime(confirmed_at).date()

        for performer in group_performers:
            update_fields = {}
            if performer.contract_batch_id != pending_batch_id:
                update_fields["contract_batch_id"] = pending_batch_id
            if performer.contract_is_addendum != is_addendum:
                update_fields["contract_is_addendum"] = is_addendum
            if performer.contract_addendum_number != addendum_number:
                update_fields["contract_addendum_number"] = addendum_number
            if not performer.contract_group_member_id:
                default_group = default_groups.get(performer.pk)
                if default_group:
                    update_fields["contract_group_member_id"] = default_group.pk
            if not (performer.contract_number or "").strip() and generated_number:
                update_fields["contract_number"] = generated_number
            if not (performer.contract_file or "").strip() and generated_file:
                update_fields["contract_file"] = generated_file
            if performer.contract_date is None:
                update_fields["contract_date"] = contract_date
            if update_fields:
                Performer.objects.filter(pk=performer.pk).update(**update_fields)
                updated += 1

    return updated
