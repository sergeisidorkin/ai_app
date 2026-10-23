"""Подразделение, организация и руководитель специальности из направления экспертизы."""

from group_app.models import GroupMember, OrgUnit
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, DIRECTOR_GROUP, ExpertiseDirection

ACCESS_ADMIN = "admin"
ACCESS_DIRECTOR = "director"
ACCESS_DEPARTMENT_HEAD = "department_head"
ACCESS_READONLY = "readonly"
SCOPED_SPECIALTY_ACCESS = (ACCESS_DIRECTOR, ACCESS_DEPARTMENT_HEAD)


def management_level_one_unit():
    """Подразделение уровня 1 единственной управляющей компании."""
    company_id = (
        GroupMember.objects.filter(is_management_company=True)
        .order_by("position", "id")
        .values_list("pk", flat=True)
        .first()
    )
    if not company_id:
        return None
    return (
        OrgUnit.objects.filter(company_id=company_id, level=1)
        .order_by("position", "id")
        .first()
    )


def head_role_for_unit(unit, management_unit):
    if unit is None:
        return None
    if management_unit is not None and unit.pk == management_unit.pk:
        return DIRECTOR_GROUP
    return DEPARTMENT_HEAD_GROUP


def resolve_head_for_direction(direction, management_unit=None):
    """Должность каталога: директор уровня 1 УК или руководитель единственного подразделения."""
    from group_app.expertise_management import catalog_head

    return catalog_head(direction)


def _specialty_access_for_role(role):
    if role == ADMIN_GROUP:
        return ACCESS_ADMIN
    if role == DIRECTOR_GROUP:
        return ACCESS_DIRECTOR
    if role == DEPARTMENT_HEAD_GROUP:
        return ACCESS_DEPARTMENT_HEAD
    return None


def specialty_table_access(user):
    """Кто может менять специальности исполнителей.

    Роль сотрудника важнее группы. Директор в этой системе ещё и суперпользователь,
    но строки он правит только в своём направлении, а не как администратор.
    Суперпользователь без роли администратора, директора или руководителя направления
    по-прежнему редактирует все строки.
    """
    if not getattr(user, "is_authenticated", False):
        return ACCESS_READONLY
    employee = getattr(user, "employee_profile", None)
    role = (getattr(employee, "role", "") or "").strip()
    access = _specialty_access_for_role(role)
    if access:
        return access
    if role:
        return ACCESS_READONLY
    if getattr(user, "pk", None):
        names = set(user.groups.values_list("name", flat=True))
        for name in (ADMIN_GROUP, DIRECTOR_GROUP, DEPARTMENT_HEAD_GROUP):
            if name in names:
                return _specialty_access_for_role(name)
    if getattr(user, "is_superuser", False):
        return ACCESS_ADMIN
    return ACCESS_READONLY


def directions_for_user(user):
    """Направления, чья пара по режиму содержит подразделение пользователя.

    Совпадают и подразделение, и организация: одинаковое название в другой компании не открывает строку.
    Правило одно для ролей «Руководитель направления» и «Директор».
    """
    if specialty_table_access(user) not in SCOPED_SPECIALTY_ACCESS:
        return []
    employee = getattr(user, "employee_profile", None)
    unit = getattr(employee, "department", None)
    if unit is None or not unit.pk:
        return []
    from group_app.expertise_management import ExpertiseAssignmentIndex

    directions = list(ExpertiseDirection.objects.order_by("position", "id"))
    index = ExpertiseAssignmentIndex([item.pk for item in directions])
    return [
        direction
        for direction in directions
        if any(item.pk == unit.pk for item in index.display_units(direction.pk))
    ]


def direction_for_user(user):
    """Единственное направление пользователя. Если их несколько, берётся первое по порядку."""
    directions = directions_for_user(user)
    return directions[0] if directions else None


def specialty_table_flags(user):
    access = specialty_table_access(user)
    return {
        "esp_can_edit": access != ACCESS_READONLY,
        "esp_scope_own_rows": access in SCOPED_SPECIALTY_ACCESS,
    }


def specialty_row_editable(user, specialty, *, direction_ids=None):
    """Строка открыта, если у её направления совпали подразделение и организация пользователя."""
    access = specialty_table_access(user)
    if access == ACCESS_ADMIN:
        return True
    if access not in SCOPED_SPECIALTY_ACCESS:
        return False
    if direction_ids is None:
        direction_ids = {item.pk for item in directions_for_user(user)}
    return specialty.expertise_dir_id in direction_ids


def mark_specialty_row_access(specialties, user):
    access = specialty_table_access(user)
    direction_ids = set()
    if access in SCOPED_SPECIALTY_ACCESS:
        direction_ids = {item.pk for item in directions_for_user(user)}
    for specialty in specialties:
        specialty.esp_row_editable = specialty_row_editable(
            user,
            specialty,
            direction_ids=direction_ids,
        )
    return specialties


def specialty_display_rows(specialties):
    """Одна визуальная строка на пару подразделение/организация направления."""
    rows = []
    for specialty in specialties:
        units = list(getattr(specialty, "_managed_display_units", None) or [])
        pairs = []
        for unit in units:
            company = getattr(unit, "company", None)
            pairs.append({
                "department": str(getattr(unit, "department_name", "") or "").strip(),
                "organization": str(getattr(company, "short_name", "") or "").strip(),
            })
        if not pairs:
            pairs = [{"department": "", "organization": ""}]
        total = len(pairs)
        for index, pair in enumerate(pairs, start=1):
            rows.append({
                "specialty": specialty,
                "department": pair["department"],
                "organization": pair["organization"],
                "is_first": index == 1,
                "is_continuation": index > 1,
                "has_next": index < total,
                "group_key": specialty.pk,
            })
    return rows


def attach_specialty_heads(specialties):
    """Проставляет подразделение, организацию и _resolved_head без запроса на каждую строку."""
    from group_app.expertise_management import ExpertiseAssignmentIndex

    specialties = list(specialties)
    direction_ids = [item.expertise_dir_id for item in specialties if item.expertise_dir_id]
    index = ExpertiseAssignmentIndex(direction_ids)
    for specialty in specialties:
        units = index.display_units(specialty.expertise_dir_id) if specialty.expertise_dir_id else []
        specialty._managed_display_units = units
        specialty._resolved_head = index.catalog_head(specialty.expertise_dir_id) if specialty.expertise_dir_id else None
    return specialties
