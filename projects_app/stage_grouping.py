"""Объединение и разъединение этапов в реестре проектов.

Операции меняют родителя этапа, коды проектов и общий состав активов.
Их можно выполнить, только пока по затронутым этапам не начата работа.
"""

import uuid
from collections import defaultdict

from django.db import transaction
from django.db.models import F, Q

from policy_app.models import ADMIN_GROUP, DIRECTOR_GROUP

from .models import (
    MAX_PROJECT_STAGES,
    LegalEntity,
    Performer,
    PerformerReportUpload,
    ProjectRegistration,
    WorkVolume,
)
from .service_scope import align_project_service_scope


class StageGroupingBlocked(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class StageGroupingNeedsConfirm(Exception):
    def __init__(self, warnings):
        self.warnings = list(warnings)
        super().__init__("\n".join(self.warnings))


SHARED_CARD_FIELDS = (
    "number",
    "group_member",
    "group",
    "name",
    "year",
    "country",
    "customer",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "customer_identifier_record",
    "project_manager",
    "project_manager_prs_id",
    "project_coordinator",
    "project_coordinator_prs_id",
    "asset_owner",
    "asset_owner_matches_customer",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
    "asset_owner_identifier_record",
    "project_start_date",
    "contract_subject",
)

CONTRACT_FIELDS = (
    "contract_project_registration",
    "agreement_type",
    "agreement_number",
    "contract_start",
    "contract_end",
    "contract_end_enabled",
)

_DIFFERENCE_LABELS = (
    ("name", "название"),
    ("year", "год"),
    ("project_manager", "руководитель проекта"),
    ("project_coordinator", "координатор проекта"),
    ("customer", "заказчик"),
    ("country_id", "страна заказчика"),
    ("identifier", "идентификатор заказчика"),
    ("registration_number", "регистрационный номер заказчика"),
    ("registration_region", "регион заказчика"),
    ("registration_date", "дата регистрации заказчика"),
    ("asset_owner", "владелец активов"),
    ("asset_owner_country_id", "страна владельца"),
    ("asset_owner_identifier", "идентификатор владельца"),
    ("asset_owner_registration_number", "регистрационный номер владельца"),
    ("asset_owner_region", "регион владельца"),
    ("asset_owner_registration_date", "дата регистрации владельца"),
    ("project_start_date", "дата начала"),
    ("contract_subject", "предмет договора"),
)

NOT_STARTED = "Не начат"


def can_regroup_project_stages(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_staff", False):
        return False
    employee = getattr(user, "employee_profile", None)
    role = (getattr(employee, "role", "") or "") if employee is not None else ""
    if role in {DIRECTOR_GROUP, ADMIN_GROUP}:
        return True
    return user.groups.filter(name__in=[DIRECTOR_GROUP, ADMIN_GROUP]).exists()


def parse_stage_ids(raw_values):
    parsed = []
    seen = set()
    for raw in raw_values:
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = int(part)
            except (TypeError, ValueError) as exc:
                raise StageGroupingBlocked("Передан некорректный список этапов.") from exc
            if value in seen:
                continue
            seen.add(value)
            parsed.append(value)
    return parsed


def merge_stages(stage_ids, *, confirm=False):
    ids = list(stage_ids)
    if len(ids) < 2:
        raise StageGroupingBlocked("Для объединения выберите несколько этапов.")
    with transaction.atomic():
        selected = _lock_rows(ids)
        if len(selected) != len(set(ids)):
            raise StageGroupingBlocked("Часть выбранных строк не найдена.")
        _reject_project_shells(selected)
        _require_same_number_and_group(selected)
        selected = [_ensure_stage_parent(row) for row in selected]
        selected = _lock_rows([row.pk for row in selected])
        parent_ids = {row.stage_project_id for row in selected}
        parents, family = _lock_family(parent_ids)
        _raise_if_blocked(_work_blockers(family, parents))
        if len(parent_ids) == 1:
            raise StageGroupingBlocked("Выбранные этапы уже входят в один проект.")
        anchor = _anchor_parent(selected, parents)
        result_ids = {row.pk for row in family if row.stage_project_id == anchor.pk}
        result_ids.update(row.pk for row in selected)
        if len(result_ids) > MAX_PROJECT_STAGES:
            raise StageGroupingBlocked("В одном проекте не больше девяти этапов.")
        warnings = _merge_warnings(anchor, selected, parents, family)
        if not confirm:
            raise StageGroupingNeedsConfirm(warnings)
        _apply_merge(anchor, selected, parents)
    return warnings


def split_project(parent_id, *, confirm=False):
    try:
        parent_id = int(parent_id)
    except (TypeError, ValueError) as exc:
        raise StageGroupingBlocked(
            "Сводная строка не связана с проектом из нескольких этапов."
        ) from exc
    with transaction.atomic():
        parent = (
            ProjectRegistration.objects.select_for_update()
            .filter(pk=parent_id, stage_project__isnull=True)
            .first()
        )
        if parent is None:
            raise StageGroupingBlocked("Сводная строка не связана с проектом из нескольких этапов.")
        stages = list(
            ProjectRegistration.objects.select_for_update()
            .filter(stage_project_id=parent.pk)
            .order_by("position", "id")
        )
        if len(stages) < 2:
            raise StageGroupingBlocked("Разъединить можно только проект из нескольких этапов.")
        _raise_if_blocked(_work_blockers(stages, [parent]))
        warnings = _split_warnings(parent, stages)
        if not confirm:
            raise StageGroupingNeedsConfirm(warnings)
        _apply_split(parent, stages)
    return warnings


def _lock_rows(ids):
    return list(
        ProjectRegistration.objects.select_for_update(of=("self",))
        .select_related("stage_project", "group_member")
        .filter(pk__in=ids)
        .order_by("position", "id")
    )


def _lock_family(parent_ids):
    parents = list(
        ProjectRegistration.objects.select_for_update()
        .filter(pk__in=parent_ids, stage_project__isnull=True)
        .order_by("position", "id")
    )
    if len(parents) != len(set(parent_ids)):
        raise StageGroupingBlocked("Не удалось найти карточку одного из проектов. Обновите страницу.")
    family = list(
        ProjectRegistration.objects.select_for_update()
        .filter(stage_project_id__in=parent_ids)
        .order_by("position", "id")
    )
    return parents, family


def _reject_project_shells(rows):
    shell_ids = [row.pk for row in rows if not row.stage_project_id]
    if not shell_ids:
        return
    if ProjectRegistration.objects.filter(stage_project_id__in=shell_ids).exists():
        raise StageGroupingBlocked("Выберите строки этапов, а не карточку проекта.")


def _require_same_number_and_group(rows):
    numbers = {row.number for row in rows}
    groups = {_group_key(row) for row in rows}
    if len(numbers) != 1 or len(groups) != 1 or None in groups:
        raise StageGroupingBlocked(
            "Объединять можно только этапы одного четырёхзначного номера и одной группы."
        )


def _group_key(row):
    if row.group_member_id:
        return ("member", row.group_member_id)
    label = (row.group or "").strip().upper()
    if not label:
        return None
    return ("code", label)


def _ensure_stage_parent(row):
    if row.stage_project_id:
        return row
    _release_short_uid(row)
    parent = _create_parent(
        row,
        row,
        position=row.position or 0,
        summary_deferred=bool(row.summary_deferred),
        summary_status_date=row.summary_status_date,
    )
    ProjectRegistration.objects.filter(pk=row.pk).update(stage_project_id=parent.pk)
    row.stage_project_id = parent.pk
    row.stage_project = parent
    return row


def _anchor_parent(selected, parents):
    top = min(selected, key=lambda row: (row.position or 0, row.pk))
    for parent in parents:
        if parent.pk == top.stage_project_id:
            return parent
    raise StageGroupingBlocked("Не удалось найти карточку проекта-опоры. Обновите страницу.")


def _merge_warnings(anchor, selected, parents, family):
    selected_ids = {row.pk for row in selected}
    moved = [row for row in selected if row.stage_project_id != anchor.pk]
    warnings = [
        f"Коды проектов с номером {_number_label(anchor.number)} будут пересчитаны.",
        f"Общая карточка будет взята из проекта {_project_label(anchor)}.",
        "Договоры, продукты и сроки этапов сохранятся.",
    ]
    replaced = _replaced_field_labels(anchor, moved)
    if replaced:
        warnings.append("На перенесённых этапах будут заменены: " + ", ".join(replaced) + ".")
    if any(parent.summary_deferred != anchor.summary_deferred for parent in parents):
        warnings.append("Признак «Отложен» сохранится только у проекта-опоры.")
    ordered_result = sorted(
        [row for row in family if row.stage_project_id == anchor.pk or row.pk in selected_ids],
        key=lambda row: (row.position or 0, row.pk),
    )
    if ordered_result and ordered_result[-1].deadline != anchor.deadline:
        warnings.append("Дедлайн карточки проекта станет дедлайном последнего этапа.")
    for parent in parents:
        if parent.pk == anchor.pk:
            continue
        remaining = [
            row for row in family
            if row.stage_project_id == parent.pk and row.pk not in selected_ids
        ]
        label = _project_label(parent)
        if remaining:
            warnings.append(f"Проект {label} сохранится с оставшимися этапами.")
        else:
            warnings.append(f"Проект {label} перестанет быть отдельной карточкой.")
    result_ids = {row.pk for row in ordered_result}
    if _has_service_rows(result_ids):
        warnings.append("Активы и юридические лица станут общими для всех этапов проекта.")
    return warnings


def _split_warnings(parent, stages):
    warnings = [
        "Каждый этап станет отдельным проектом.",
        f"Коды проектов с номером {_number_label(parent.number)} будут пересчитаны.",
        "Договоры, продукты и сроки этапов сохранятся.",
    ]
    if parent.summary_deferred:
        warnings.append("Признак «Отложен» сохранится у каждого нового проекта.")
    stage_ids = [row.pk for row in stages]
    if _scope_is_shared(WorkVolume, stage_ids) or _scope_is_shared(LegalEntity, stage_ids):
        warnings.append(
            "Общие активы и юридические лица перестанут синхронизироваться между новыми проектами."
        )
    return warnings


def _apply_merge(anchor, selected, parents):
    moved_ids = [row.pk for row in selected if row.stage_project_id != anchor.pk]
    if moved_ids:
        ProjectRegistration.objects.filter(pk__in=moved_ids).update(
            stage_project_id=anchor.pk,
            **_values_for_update(anchor, SHARED_CARD_FIELDS),
        )
        _rekey_transferred_scopes(moved_ids)
    result = list(
        ProjectRegistration.objects.filter(stage_project_id=anchor.pk).order_by("position", "id")
    )
    _pack_positions(result)
    if result:
        ProjectRegistration.objects.filter(pk=anchor.pk).update(deadline=result[-1].deadline)
    align_project_service_scope(anchor)
    empty_ids = [
        parent.pk
        for parent in parents
        if parent.pk != anchor.pk
        and not ProjectRegistration.objects.filter(stage_project_id=parent.pk).exists()
    ]
    if empty_ids:
        ProjectRegistration.objects.filter(pk__in=empty_ids).delete()
    ProjectRegistration.refresh_number_sequences([anchor.number])


def _apply_split(parent, stages):
    stage_ids = [row.pk for row in stages]
    _detach_scope_keys(stage_ids)
    number = parent.number
    for stage in stages:
        new_parent = _create_parent(
            parent,
            stage,
            position=stage.position or 0,
            summary_deferred=bool(parent.summary_deferred),
            summary_status_date=parent.summary_status_date,
        )
        ProjectRegistration.objects.filter(pk=stage.pk).update(stage_project_id=new_parent.pk)
    ProjectRegistration.objects.filter(pk=parent.pk).delete()
    ProjectRegistration.refresh_number_sequences([number])


def _create_parent(card_source, contract_source, *, position, summary_deferred, summary_status_date):
    """Создаёт карточку проекта без пересчёта кодов. Коды ставит общий refresh в конце операции."""
    parent = ProjectRegistration(
        position=position or 0,
        status=NOT_STARTED,
        summary_deferred=bool(summary_deferred),
        summary_status_date=summary_status_date,
        type_id=None,
        deadline=contract_source.deadline,
        short_uid=f"tmp{uuid.uuid4().hex[:16]}",
    )
    for key, value in _values_for_update(card_source, SHARED_CARD_FIELDS).items():
        setattr(parent, key, value)
    for key, value in _values_for_update(contract_source, CONTRACT_FIELDS).items():
        setattr(parent, key, value)
    member = parent._resolved_group_member()
    if member:
        parent.group = member.country_alpha2 or parent.group
    if (
        not parent.agreement_number
        and parent.group_alpha2 == "RU"
        and parent.agreement_type == parent.AgreementType.MAIN
    ):
        parent.agreement_number = f"IMCM/{parent.number}"
    parent.save_base(raw=True)
    return parent


def _values_for_update(source, names):
    values = {}
    for name in names:
        field = ProjectRegistration._meta.get_field(name)
        if field.is_relation:
            if not (field.many_to_one or field.one_to_one):
                continue
            values[field.attname] = getattr(source, field.attname)
        else:
            values[name] = getattr(source, name)
    return values


def _release_short_uid(row):
    ProjectRegistration.objects.filter(pk=row.pk).update(
        short_uid=f"tmp{row.pk}{uuid.uuid4().hex[:8]}"
    )


def _pack_positions(stages):
    if not stages:
        return
    ordered = sorted(stages, key=lambda row: (row.position or 0, row.pk))
    start = ordered[0].position or 0
    ids = [row.pk for row in ordered]
    ProjectRegistration.objects.exclude(pk__in=ids).filter(position__gte=start).update(
        position=F("position") + len(ordered)
    )
    for offset, row in enumerate(ordered):
        ProjectRegistration.objects.filter(pk=row.pk).update(position=start + offset)


def _work_blockers(stages, parents):
    reasons = []
    if any(row.status != NOT_STARTED for row in stages):
        reasons.append("Операция доступна, только пока все затронутые этапы в статусе «Не начат».")
    involved = list(stages) + list(parents)
    if any(_diagram_started(row) for row in involved):
        reasons.append("По затронутым этапам уже есть запуск или диаграмма.")
    stage_ids = [row.pk for row in stages]
    all_ids = stage_ids + [row.pk for row in parents]
    if _workspace_exists(all_ids):
        reasons.append("У проекта уже создано рабочее пространство.")
    if stage_ids and PerformerReportUpload.objects.filter(registration_id__in=stage_ids).exists():
        reasons.append("По этапам уже загружены отчёты.")
    if stage_ids and Performer.objects.filter(registration_id__in=stage_ids).filter(
        Q(participation_request_sent_at__isnull=False) | Q(contract_file__gt="")
    ).exists():
        reasons.append(
            "По этапам уже отправлен запрос подтверждения участия или подготовлен файл договора."
        )
    return reasons


def _raise_if_blocked(reasons):
    if reasons:
        raise StageGroupingBlocked("\n".join(reasons))


def _diagram_started(row):
    if row.launched_at:
        return True
    data = row.gantt_data if isinstance(row.gantt_data, dict) else {}
    tasks = data.get("data") if isinstance(data, dict) else None
    return bool(tasks)


def _workspace_exists(project_ids):
    if not project_ids:
        return False
    from checklists_app.models import ProjectWorkspace, SourceDataWorkspace

    return (
        ProjectWorkspace.objects.filter(project_id__in=project_ids).exists()
        or SourceDataWorkspace.objects.filter(project_id__in=project_ids).exists()
    )


def _replaced_field_labels(anchor, moved):
    labels = []
    for field_name, label in _DIFFERENCE_LABELS:
        anchor_value = getattr(anchor, field_name)
        if any(getattr(row, field_name) != anchor_value for row in moved):
            labels.append(label)
    return labels


def _has_service_rows(project_ids):
    if not project_ids:
        return False
    return (
        WorkVolume.objects.filter(project_id__in=project_ids).exists()
        or LegalEntity.objects.filter(project_id__in=project_ids).exists()
    )


def _scope_is_shared(model, stage_ids):
    seen = {}
    pairs = model.objects.filter(project_id__in=stage_ids).exclude(scope_key__isnull=True).values_list(
        "project_id", "scope_key"
    )
    for project_id, scope_key in pairs:
        owners = seen.setdefault(scope_key, set())
        owners.add(project_id)
        if len(owners) > 1:
            return True
    return False


def _detach_scope_keys(stage_ids):
    _detach_model_scope(WorkVolume, stage_ids)
    _detach_model_scope(LegalEntity, stage_ids)


def _rekey_transferred_scopes(stage_ids):
    """Даёт перенесённым этапам свои ключи, если часть донора остаётся на старых."""
    _rekey_transferred_model_scope(WorkVolume, stage_ids)
    _rekey_transferred_model_scope(LegalEntity, stage_ids)


def _rekey_transferred_model_scope(model, stage_ids):
    moved_ids = list(stage_ids)
    if not moved_ids:
        return
    keys = list(
        model.objects.filter(project_id__in=moved_ids)
        .exclude(scope_key__isnull=True)
        .values_list("scope_key", flat=True)
        .distinct()
    )
    if not keys:
        return
    shared_outside = set(
        model.objects.filter(scope_key__in=keys)
        .exclude(project_id__in=moved_ids)
        .values_list("scope_key", flat=True)
        .distinct()
    )
    for scope_key in shared_outside:
        model.objects.filter(project_id__in=moved_ids, scope_key=scope_key).update(
            scope_key=uuid.uuid4()
        )


def _detach_model_scope(model, stage_ids):
    rows = list(model.objects.filter(project_id__in=stage_ids).exclude(scope_key__isnull=True))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.scope_key].append(row)
    for copies in grouped.values():
        by_project = defaultdict(list)
        for row in copies:
            by_project[row.project_id].append(row)
        if len(by_project) <= 1:
            continue
        for group in by_project.values():
            model.objects.filter(pk__in=[item.pk for item in group]).update(scope_key=uuid.uuid4())


def _number_label(number):
    return f"{int(number or 0):04d}"


def _project_label(row):
    name = " ".join(str(row.name or "").split())
    uid = row.short_uid or _number_label(row.number)
    if name:
        return f"{uid} «{name}»"
    return uid
