from .models import ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from .project_permissions import (
    DEFAULT_PROJECT_PERMISSIONS,
    PROJECT_COORDINATOR_SPECIALTY,
    PROJECT_MANAGER_SPECIALTY,
)


def grant_project_specialty(employee, specialty_name, permissions=None):
    """Выдать сотруднику специальность, дающую права в проекте (для тестов)."""
    specialty, _created = ExpertSpecialty.objects.get_or_create(specialty=specialty_name)
    update_fields = []
    if not specialty.grants_project_rights:
        specialty.grants_project_rights = True
        update_fields.append("grants_project_rights")
    if permissions is not None:
        specialty.project_permissions = list(permissions)
        update_fields.append("project_permissions")
    elif not specialty.project_permissions:
        specialty.project_permissions = list(DEFAULT_PROJECT_PERMISSIONS.get(specialty_name, ()))
        update_fields.append("project_permissions")
    if update_fields:
        specialty.save(update_fields=update_fields)
    profile, _created = ExpertProfile.objects.get_or_create(employee=employee)
    ExpertProfileSpecialty.objects.get_or_create(profile=profile, specialty=specialty)
    if hasattr(employee, "_project_slot_permissions"):
        del employee._project_slot_permissions
    return specialty


def grant_coordinator_specialty(employee, permissions=None):
    return grant_project_specialty(employee, PROJECT_COORDINATOR_SPECIALTY, permissions)


def grant_manager_specialty(employee, permissions=None):
    return grant_project_specialty(employee, PROJECT_MANAGER_SPECIALTY, permissions)
