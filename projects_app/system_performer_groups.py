"""Системные специальности в таблице «Исполнители».

Руководитель проекта и Координатор получают исполнителя из реестра.
В многоэтапном проекте эти строки, как и Директор, собираются в одну
визуальную группу на все этапы и активы.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.db.models.signals import post_save

from experts_app.project_permissions import (
    PROJECT_COORDINATOR_SPECIALTY,
    PROJECT_DIRECTOR_SPECIALTY,
    PROJECT_MANAGER_SPECIALTY,
)

SYSTEM_SPECIALTY_NAMES = (
    PROJECT_MANAGER_SPECIALTY,
    PROJECT_COORDINATOR_SPECIALTY,
    PROJECT_DIRECTOR_SPECIALTY,
)
REGISTRY_ASSIGNED_SPECIALTIES = frozenset({
    PROJECT_MANAGER_SPECIALTY,
    PROJECT_COORDINATOR_SPECIALTY,
})
SECTION_CODE_SPECIALTIES = {
    "PRD": PROJECT_MANAGER_SPECIALTY,
    "CRD": PROJECT_COORDINATOR_SPECIALTY,
}

_sync_guard = False


def _clean_name(value) -> str:
    return " ".join(str(value or "").split()).strip()


def section_system_specialty(section) -> str:
    """Специальность строки: связь блока услуг, русское имя раздела или код PRD/CRD."""
    if section is None:
        return ""
    ranked = []
    block = getattr(section, "service_block", None)
    links = getattr(block, "ranked_specialties", None) if block is not None else None
    if links is not None:
        for link in links.all():
            specialty = getattr(link, "specialty", None)
            name = _clean_name(getattr(specialty, "specialty", ""))
            if name in SYSTEM_SPECIALTY_NAMES:
                ranked.append((getattr(link, "rank", 0) or 0, getattr(link, "pk", 0) or 0, name))
    if ranked:
        ranked.sort()
        return ranked[0][2]
    for attr in ("short_name_ru", "name_ru"):
        name = _clean_name(getattr(section, attr, ""))
        if name in SYSTEM_SPECIALTY_NAMES:
            return name
    code = _clean_name(getattr(section, "code", "")).upper()
    return SECTION_CODE_SPECIALTIES.get(code, "")


def is_registry_assigned_section(section) -> bool:
    return section_system_specialty(section) in REGISTRY_ASSIGNED_SPECIALTIES


def registry_executor_name(registration, section):
    """Имя из реестра либо None, если раздел не назначается из реестра."""
    if registration is None:
        return None
    specialty = section_system_specialty(section)
    if specialty == PROJECT_MANAGER_SPECIALTY:
        return _clean_name(getattr(registration, "project_manager", ""))
    if specialty == PROJECT_COORDINATOR_SPECIALTY:
        return _clean_name(getattr(registration, "project_coordinator", ""))
    return None


def project_key(registration):
    if registration is None or not getattr(registration, "pk", None):
        return None
    return (registration.number, _clean_name(registration.group_display))


def _performers_for_registry_sync(registration_ids=None):
    from .models import Performer

    queryset = (
        Performer.objects
        .select_related(
            "registration",
            "typical_section",
            "typical_section__service_block",
            "employee",
            "employee__user",
        )
        .prefetch_related("typical_section__service_block__ranked_specialties__specialty")
    )
    if registration_ids is not None:
        queryset = queryset.filter(registration_id__in=list(registration_ids))
    return queryset


def sync_registry_assigned_executors(registration_ids=None, *, manager=True, coordinator=True):
    """Переписывает исполнителя строк из полей реестра. Грейд и затраты не меняет."""
    wanted = set()
    if manager:
        wanted.add(PROJECT_MANAGER_SPECIALTY)
    if coordinator:
        wanted.add(PROJECT_COORDINATOR_SPECIALTY)
    if not wanted:
        return 0
    from .models import Performer

    updated = 0
    for performer in _performers_for_registry_sync(registration_ids):
        specialty = section_system_specialty(performer.typical_section)
        if specialty not in wanted:
            continue
        name = registry_executor_name(performer.registration, performer.typical_section)
        if name is None or _clean_name(performer.executor) == name:
            continue
        performer.executor = name
        if name:
            performer.employee = Performer.resolve_employee_from_executor(name)
        else:
            performer.employee = None
        performer.save()
        updated += 1
    return updated


def iter_multistage_blocks(items=None):
    from .registration_summary import _parent_stage_blocks, iter_summary_blocks, load_ordered_registrations

    rows = items if items is not None else load_ordered_registrations()
    yielded = set()
    for block, label in _parent_stage_blocks(rows):
        yielded.update(item.pk for item in block)
        yield block, _clean_name(label)
    for block, label in iter_summary_blocks(rows):
        if any(item.stage_project_id or item.pk in yielded for item in block):
            continue
        yield block, _clean_name(label)


def _state_for(number, label, specialty_name):
    from .models import PerformerSystemGroupState

    state, _created = PerformerSystemGroupState.objects.get_or_create(
        project_number=number,
        group_label=label,
        specialty_name=specialty_name,
    )
    return state


def _performers_for_display_groups(registration_ids=None, *, exclude_registration_ids=None):
    from .models import Performer

    queryset = (
        Performer.objects
        .select_related(
            "registration",
            "registration__group_member",
            "typical_section",
            "typical_section__service_block",
        )
        .prefetch_related("typical_section__service_block__ranked_specialties__specialty")
    )
    if registration_ids is not None:
        queryset = queryset.filter(registration_id__in=list(registration_ids))
    if exclude_registration_ids:
        queryset = queryset.exclude(registration_id__in=list(exclude_registration_ids))
    return list(queryset)


def _assign_system_display_group(number, label, specialty_name, members):
    """Одна визуальная группа специальности. Разъединение директора сюда не попадает."""
    from .models import Performer

    if len(members) < 2 or number is None:
        return
    state = _state_for(number, label, specialty_name)
    if state.display_group_id is None:
        state.display_group_id = uuid.uuid4()
        state.save(update_fields=["display_group_id"])
    stale_ids = [
        member.pk
        for member in members
        if member.display_group_id != state.display_group_id
    ]
    if stale_ids:
        Performer.objects.filter(pk__in=stale_ids).update(display_group_id=state.display_group_id)


def sync_system_performer_display_groups():
    """Ставит одну визуальную группу на специальность проекта.

    Многоэтапный проект собирает руководителя, координатора и директора
    по всем этапам и активам. Руководитель и координатор одного этапа
    с несколькими активами тоже остаются одной группой: сохранение строки
    не должно её распускать.
    """
    global _sync_guard
    if _sync_guard:
        return
    _sync_guard = True
    try:
        blocks = list(iter_multistage_blocks())
        covered_ids = {item.pk for block, _label in blocks for item in block}
        performers = _performers_for_display_groups(covered_ids) if covered_ids else []
        if covered_ids:
            by_registration = defaultdict(list)
            for performer in performers:
                by_registration[performer.registration_id].append(performer)
            for block, label in blocks:
                grouped = defaultdict(list)
                for item in block:
                    for performer in by_registration.get(item.pk, []):
                        specialty_name = section_system_specialty(performer.typical_section)
                        if specialty_name:
                            grouped[specialty_name].append(performer)
                for specialty_name, members in grouped.items():
                    if specialty_name == PROJECT_DIRECTOR_SPECIALTY:
                        state = _state_for(block[0].number, label, specialty_name)
                        if state.split_by_user:
                            continue
                    _assign_system_display_group(block[0].number, label, specialty_name, members)

        single_stage_performers = _performers_for_display_groups(
            exclude_registration_ids=covered_ids,
        )
        grouped = defaultdict(list)
        for performer in single_stage_performers:
            specialty_name = section_system_specialty(performer.typical_section)
            if specialty_name not in REGISTRY_ASSIGNED_SPECIALTIES:
                continue
            key = project_key(performer.registration)
            if key is None:
                continue
            grouped[(key, specialty_name)].append(performer)
        for (key, specialty_name), members in grouped.items():
            number, label = key
            _assign_system_display_group(number, label, specialty_name, members)
    finally:
        _sync_guard = False


def protected_system_group_ids():
    from .models import PerformerSystemGroupState

    return set(
        PerformerSystemGroupState.objects
        .exclude(display_group_id__isnull=True)
        .values_list("display_group_id", flat=True)
    )


def performer_matches_system_group(performer, state) -> bool:
    """Строка всё ещё относится к сохранённой системной группе."""
    if section_system_specialty(performer.typical_section) != state.specialty_name:
        return False
    return project_key(performer.registration) == (state.project_number, state.group_label)


def release_obsolete_system_group_members(grouped) -> list:
    """Снимает системную группу со строк, которые в неё больше не входят.

    Синхронизация только назначает текущих участников и не очищает прежних.
    Пока старый id числится в PerformerSystemGroupState, обычная нормализация
    такую строку не трогает.
    """
    from .models import Performer, PerformerSystemGroupState

    states = {
        state.display_group_id: state
        for state in PerformerSystemGroupState.objects.exclude(display_group_id__isnull=True)
    }
    if not states:
        return []
    obsolete_ids = []
    for members in grouped.values():
        if not members:
            continue
        state = states.get(members[0].display_group_id)
        if state is None:
            continue
        for member in members:
            if not performer_matches_system_group(member, state):
                obsolete_ids.append(member.pk)
    if not obsolete_ids:
        return []
    Performer.objects.filter(pk__in=obsolete_ids).update(display_group_id=None)
    obsolete = set(obsolete_ids)
    for group_id, members in list(grouped.items()):
        grouped[group_id] = [member for member in members if member.pk not in obsolete]
    return obsolete_ids


def is_protected_registry_group(members) -> bool:
    """Руководитель и координатор не распускаются, даже если затраты или этап различаются."""
    if len(members) < 2:
        return False
    specialties = {section_system_specialty(member.typical_section) for member in members}
    return len(specialties) == 1 and specialties <= REGISTRY_ASSIGNED_SPECIALTIES


def is_homogeneous_director_group(members) -> bool:
    if len(members) < 2:
        return False
    if any(section_system_specialty(member.typical_section) != PROJECT_DIRECTOR_SPECIALTY for member in members):
        return False
    keys = {project_key(member.registration) for member in members}
    return len(keys) == 1 and None not in keys


def locked_specialty_merge_error(performers) -> str:
    if any(section_system_specialty(performer.typical_section) in REGISTRY_ASSIGNED_SPECIALTIES for performer in performers):
        return "Строки руководителя проекта и координатора группируются автоматически."
    return ""


def merge_director_display_group(performers):
    """Объединяет строки директора одного проекта. None — это не такой набор."""
    from .models import Performer

    if len(performers) < 2:
        return None
    if any(section_system_specialty(performer.typical_section) != PROJECT_DIRECTOR_SPECIALTY for performer in performers):
        return None
    keys = {project_key(performer.registration) for performer in performers}
    if len(keys) != 1 or None in keys:
        return {"error": "Для объединения строки директора должны относиться к одному проекту."}
    number, label = keys.pop()
    group_id = uuid.uuid4()
    selected_ids = [performer.pk for performer in performers]
    old_group_ids = {performer.display_group_id for performer in performers if performer.display_group_id}
    Performer.objects.filter(pk__in=selected_ids).update(display_group_id=group_id)
    all_ids = {
        performer.pk
        for performer in _director_performers(number, label)
    }
    state = _state_for(number, label, PROJECT_DIRECTOR_SPECIALTY)
    if set(selected_ids) == all_ids:
        state.split_by_user = False
        state.display_group_id = group_id
    else:
        state.split_by_user = True
    state.save(update_fields=["split_by_user", "display_group_id"])
    return {
        "ok": True,
        "display_group_id": str(group_id),
        "performer_ids": selected_ids,
        "old_group_ids": old_group_ids,
    }


def _director_performers(number, label):
    from .models import Performer, ProjectRegistration

    registrations = ProjectRegistration.objects.filter(number=number).select_related("group_member")
    registration_ids = [
        registration.pk
        for registration in registrations
        if project_key(registration) == (number, label)
    ]
    if not registration_ids:
        return []
    performers = (
        Performer.objects
        .filter(registration_id__in=registration_ids)
        .select_related("typical_section", "typical_section__service_block", "registration", "registration__group_member")
        .prefetch_related("typical_section__service_block__ranked_specialties__specialty")
    )
    return [
        performer
        for performer in performers
        if section_system_specialty(performer.typical_section) == PROJECT_DIRECTOR_SPECIALTY
    ]


def locked_split_error(performers) -> str:
    grouped = defaultdict(list)
    for performer in performers:
        grouped[performer.display_group_id].append(performer)
    for members in grouped.values():
        specialties = {section_system_specialty(member.typical_section) for member in members}
        if specialties and specialties <= REGISTRY_ASSIGNED_SPECIALTIES:
            return "Эту группу нельзя разъединить."
    return ""


def remember_director_split(performers):
    keys = set()
    for performer in performers:
        if section_system_specialty(performer.typical_section) != PROJECT_DIRECTOR_SPECIALTY:
            continue
        key = project_key(performer.registration)
        if key is not None:
            keys.add(key)
    for number, label in keys:
        state = _state_for(number, label, PROJECT_DIRECTOR_SPECIALTY)
        if not state.split_by_user:
            state.split_by_user = True
            state.save(update_fields=["split_by_user"])


def _connect_registry_executor_sync():
    from .models import ProjectRegistration

    post_save.connect(
        sync_registry_executors_on_registration_save,
        sender=ProjectRegistration,
        dispatch_uid="projects_app.sync_registry_executors",
    )


def sync_registry_executors_on_registration_save(sender, instance, raw=False, update_fields=None, **kwargs):
    global _sync_guard
    if raw or _sync_guard:
        return
    if update_fields is not None:
        fields = set(update_fields)
        manager = bool(fields & {"project_manager", "project_manager_prs_id"})
        coordinator = bool(fields & {"project_coordinator", "project_coordinator_prs_id"})
        if not manager and not coordinator:
            return
    else:
        manager = coordinator = True
    _sync_guard = True
    try:
        sync_registry_assigned_executors([instance.pk], manager=manager, coordinator=coordinator)
    finally:
        _sync_guard = False


_connect_registry_executor_sync()
