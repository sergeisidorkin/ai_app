"""Ситуативные права в проекте: специальность сотрудника и назначение на позицию в Реестре проектов.

Позицию занимает сотрудник, который указан в её поле проекта (по ID-PRS или ФИО) и у которого есть
специальность позиции с флагом «Даёт права в проекте». Права в проекте объединяются по всем позициям.
"""

from __future__ import annotations

from dataclasses import dataclass

from experts_app.models import ExpertProfileSpecialty, ExpertSpecialty
from experts_app.project_permissions import PROJECT_COORDINATOR_SPECIALTY, PROJECT_MANAGER_SPECIALTY
from users_app.models import Employee

from .models import Performer, ProjectRegistration

SLOT_COORDINATOR = "coordinator"
SLOT_MANAGER = "manager"


@dataclass(frozen=True)
class ProjectSlot:
    name_field: str
    prs_field: str
    specialty: str


PROJECT_SLOTS = {
    SLOT_COORDINATOR: ProjectSlot("project_coordinator", "project_coordinator_prs_id", PROJECT_COORDINATOR_SPECIALTY),
    SLOT_MANAGER: ProjectSlot("project_manager", "project_manager_prs_id", PROJECT_MANAGER_SPECIALTY),
}


def _normalize(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _employee_of(user):
    return getattr(user, "employee_profile", None) if user else None


def _employee_prs(employee) -> str:
    return _normalize(getattr(employee, "formatted_prs_id", "") or "")


def _employee_name(employee) -> str:
    return _normalize(Performer.employee_full_name(employee))


def slot_employees_queryset(slot):
    specialties = ExpertSpecialty.objects.filter(
        specialty=PROJECT_SLOTS[slot].specialty,
        grants_project_rights=True,
    )
    return (
        Employee.objects
        .select_related("user", "person_record")
        .filter(expert_profile__specialties__in=specialties)
        .distinct()
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )


def employee_slot_permissions(employee) -> dict[str, frozenset[str]]:
    """Позиции, на которые сотрудник может быть назначен, и права каждой из них."""
    if not employee or not getattr(employee, "pk", None):
        return {}
    cached = getattr(employee, "_project_slot_permissions", None)
    if cached is not None:
        return cached
    slots_by_specialty = {slot.specialty: code for code, slot in PROJECT_SLOTS.items()}
    rows = (
        ExpertProfileSpecialty.objects
        .filter(
            profile__employee_id=employee.pk,
            specialty__grants_project_rights=True,
            specialty__specialty__in=list(slots_by_specialty),
        )
        .values_list("specialty__specialty", "specialty__project_permissions")
    )
    result = {
        slots_by_specialty[name]: frozenset(permissions or [])
        for name, permissions in rows
    }
    employee._project_slot_permissions = result
    return result


def employee_has_slot_specialty(employee, slot) -> bool:
    return slot in employee_slot_permissions(employee)


def is_assigned_to_slot(employee, registration, slot) -> bool:
    """Сотрудник указан в поле позиции проекта. Специальность здесь не проверяется."""
    if not employee or not registration:
        return False
    spec = PROJECT_SLOTS[slot]
    prs = _employee_prs(employee)
    if prs and _normalize(getattr(registration, spec.prs_field, "")) == prs:
        return True
    name = _employee_name(employee)
    return bool(name) and _normalize(getattr(registration, spec.name_field, "")) == name


def assigned_registration_ids(employee, slot) -> set[int]:
    if not employee:
        return set()
    spec = PROJECT_SLOTS[slot]
    prs = _employee_prs(employee)
    name = _employee_name(employee)
    qs = None
    if prs:
        qs = ProjectRegistration.objects.filter(**{spec.prs_field: prs})
    if name:
        by_name = ProjectRegistration.objects.filter(**{spec.name_field: name})
        qs = by_name if qs is None else qs | by_name
    return set(qs.values_list("pk", flat=True)) if qs is not None else set()


def employee_project_slots(employee, registration) -> list[str]:
    slots = employee_slot_permissions(employee)
    return [slot for slot in PROJECT_SLOTS if slot in slots and is_assigned_to_slot(employee, registration, slot)]


def user_project_slots(user, registration) -> list[str]:
    return employee_project_slots(_employee_of(user), registration)


def employee_project_permissions(employee, registration) -> set[str]:
    slots = employee_slot_permissions(employee)
    permissions = set()
    for slot in employee_project_slots(employee, registration):
        permissions |= slots[slot]
    return permissions


def user_project_permissions(user, registration) -> set[str]:
    return employee_project_permissions(_employee_of(user), registration)


def has_project_permission(user, registration, code) -> bool:
    return code in user_project_permissions(user, registration)


def slots_with_permission(employee, code) -> list[str]:
    return [slot for slot, permissions in employee_slot_permissions(employee).items() if code in permissions]


def registration_ids_with_permission(employee, code) -> set[int]:
    ids = set()
    for slot in slots_with_permission(employee, code):
        ids |= assigned_registration_ids(employee, slot)
    return ids


def slot_holders(registration, slot) -> list:
    """Сотрудники с нужной специальностью, назначенные на позицию проекта."""
    spec = PROJECT_SLOTS[slot]
    prs = _normalize(getattr(registration, spec.prs_field, ""))
    name = _normalize(getattr(registration, spec.name_field, ""))
    if not prs and not name:
        return []
    candidates = list(slot_employees_queryset(slot))
    if prs:
        by_prs = [employee for employee in candidates if _employee_prs(employee) == prs]
        if by_prs:
            return by_prs
    return [employee for employee in candidates if name and _employee_name(employee) == name]


def registration_permission_holders(registration, code) -> list:
    holders = []
    seen = set()
    for slot in PROJECT_SLOTS:
        for employee in slot_holders(registration, slot):
            if employee.pk in seen:
                continue
            if code in employee_project_permissions(employee, registration):
                seen.add(employee.pk)
                holders.append(employee)
    return holders
