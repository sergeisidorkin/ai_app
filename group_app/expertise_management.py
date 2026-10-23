"""Подразделение и руководитель направления по режиму управления и организации проекта."""

from collections import defaultdict

from policy_app.models import DEPARTMENT_HEAD_GROUP, DIRECTOR_GROUP
from users_app.models import Employee

from .models import ExpertiseManagementMode, GroupMember, OrgUnit


def ensure_management_mode(direction):
    if direction is None or not getattr(direction, "pk", None):
        return None
    mode, _created = ExpertiseManagementMode.objects.get_or_create(
        expertise_direction=direction,
        defaults={"mode": ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY},
    )
    return mode


def ensure_mode_for_direction(sender, instance, created, **kwargs):
    if created:
        ensure_management_mode(instance)


def management_company():
    return (
        GroupMember.objects.filter(is_management_company=True)
        .order_by("position", "id")
        .first()
    )


def _company_id(company):
    return getattr(company, "pk", None)


class ExpertiseAssignmentIndex:
    """Режимы, подразделения и руководители направлений одним набором запросов."""

    def __init__(self, direction_ids):
        ids = {item for item in direction_ids if item}
        self.modes = {
            row.expertise_direction_id: row.mode
            for row in ExpertiseManagementMode.objects.filter(expertise_direction_id__in=ids)
        }
        self.units_by_direction = defaultdict(list)
        if ids:
            units = (
                OrgUnit.objects.select_related("company")
                .filter(expertise_id__in=ids)
                .order_by("company__position", "company_id", "position", "id")
            )
            for unit in units:
                self.units_by_direction[unit.expertise_id].append(unit)
        self.uk = management_company()
        unit_ids = [unit.pk for grouped in self.units_by_direction.values() for unit in grouped]
        self.heads = {}
        if unit_ids:
            employees = (
                Employee.objects.select_related("user")
                .filter(
                    department_id__in=unit_ids,
                    role__in=(DEPARTMENT_HEAD_GROUP, DIRECTOR_GROUP),
                )
                .order_by("position", "id")
            )
            for employee in employees:
                self.heads.setdefault((employee.department_id, employee.role), employee)

    def mode_for(self, direction_id):
        if not direction_id:
            return ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY
        return self.modes.get(direction_id, ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY)

    def company_for(self, direction_id, group_member=None):
        if self.mode_for(direction_id) == ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY:
            return self.uk
        return group_member

    def units_for_company(self, direction_id, company):
        company_id = _company_id(company)
        if not direction_id or not company_id:
            return []
        return [
            unit
            for unit in self.units_by_direction.get(direction_id, [])
            if unit.company_id == company_id
        ]

    def display_units(self, direction_id):
        if not direction_id:
            return []
        if self.mode_for(direction_id) == ExpertiseManagementMode.MODE_SEPARATE:
            return self._uk_units_first(list(self.units_by_direction.get(direction_id, [])))
        return self.units_for_company(direction_id, self.uk)

    def _uk_units_first(self, units):
        uk_id = getattr(self.uk, "pk", None)
        if not uk_id:
            return units
        return (
            [unit for unit in units if unit.company_id == uk_id]
            + [unit for unit in units if unit.company_id != uk_id]
        )

    def operation_units(self, direction_id, group_member=None):
        company = self.company_for(direction_id, group_member)
        return [
            unit
            for unit in self.units_for_company(direction_id, company)
            if (unit.level or 1) != 1
        ]

    def operation_unit(self, direction_id, group_member=None):
        units = self.operation_units(direction_id, group_member)
        if len(units) == 1:
            return units[0]
        return None

    def operation_head(self, direction_id, group_member=None):
        unit = self.operation_unit(direction_id, group_member)
        if unit is None:
            return None
        return self.heads.get((unit.pk, DEPARTMENT_HEAD_GROUP))

    def catalog_head(self, direction_id):
        units = self.display_units(direction_id)
        if len(units) != 1:
            return None
        unit = units[0]
        role = DIRECTOR_GROUP if (unit.level or 1) == 1 else DEPARTMENT_HEAD_GROUP
        return self.heads.get((unit.pk, role))


def _direction_id(direction):
    if direction is None or isinstance(direction, bool):
        return None
    if isinstance(direction, int):
        return direction
    return getattr(direction, "pk", None)


def _index_for(direction):
    direction_id = _direction_id(direction)
    return ExpertiseAssignmentIndex([direction_id] if direction_id else [])


def display_units(direction):
    direction_id = _direction_id(direction)
    if not direction_id:
        return []
    cached = getattr(direction, "_managed_display_units", None)
    if cached is not None:
        return cached
    return _index_for(direction_id).display_units(direction_id)


def operation_unit(direction, group_member=None):
    direction_id = _direction_id(direction)
    return _index_for(direction_id).operation_unit(direction_id, group_member)


def operation_head(direction, group_member=None):
    direction_id = _direction_id(direction)
    return _index_for(direction_id).operation_head(direction_id, group_member)


def catalog_head(direction):
    direction_id = _direction_id(direction)
    if not direction_id:
        return None
    return _index_for(direction_id).catalog_head(direction_id)


def format_departments(units):
    names = []
    for unit in units:
        name = str(getattr(unit, "department_name", "") or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def format_organizations(units):
    names = []
    for unit in units:
        company = getattr(unit, "company", None)
        name = str(getattr(company, "short_name", "") or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def catalog_labels(direction_ids):
    """Подписи подразделения, организации и должности для списка направлений."""
    index = ExpertiseAssignmentIndex(direction_ids)
    labels = {}
    for direction_id in direction_ids:
        if not direction_id:
            continue
        units = index.display_units(direction_id)
        head = index.catalog_head(direction_id)
        labels[direction_id] = {
            "department": format_departments(units),
            "organization": format_organizations(units),
            "head": str(getattr(head, "job_title", "") or ""),
            "units": units,
            "head_employee": head,
        }
    return labels


def attach_display_units(objects, direction_attr="expertise_dir"):
    """Кладёт пары режима на объекты и на их направления, без запроса на каждую строку."""
    objects = list(objects)
    direction_ids = []
    for obj in objects:
        direction = obj if direction_attr is None else getattr(obj, direction_attr, None)
        direction_id = getattr(direction, "pk", None)
        if direction_id:
            direction_ids.append(direction_id)
    index = ExpertiseAssignmentIndex(direction_ids)
    for obj in objects:
        direction = obj if direction_attr is None else getattr(obj, direction_attr, None)
        direction_id = getattr(direction, "pk", None)
        units = index.display_units(direction_id) if direction_id else []
        obj._managed_display_units = units
        if direction is not None and direction is not obj:
            direction._managed_display_units = units
    return objects


def sync_missing_modes():
    existing = set(ExpertiseManagementMode.objects.values_list("expertise_direction_id", flat=True))
    from policy_app.models import ExpertiseDirection

    missing_ids = list(
        ExpertiseDirection.objects.exclude(pk__in=existing).values_list("pk", flat=True)
    )
    if missing_ids:
        ExpertiseManagementMode.objects.bulk_create(
            [
                ExpertiseManagementMode(
                    expertise_direction_id=direction_id,
                    mode=ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY,
                )
                for direction_id in missing_ids
            ]
        )
    return (
        ExpertiseManagementMode.objects.select_related("expertise_direction")
        .order_by("expertise_direction__position", "expertise_direction_id")
    )
