"""Bulk row-order specs for the projects panel (see core.row_order).

Performers keep their dedicated endpoint (``performer_row_order``); the project
schedule (Gantt tasks) is not a positional table and is intentionally excluded.
"""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import LegalEntity, ProjectRegistration, ReportCheckRule, ReportMacro, WorkVolume
from .report_access import can_manage_report_checks
from .report_submission import report_folder_locked_asset_keys, workspace_project_ids

HX_PROJECTS_UPDATED_EVENT = "projects-updated"
WORK_LOCKED_MESSAGE = "Нельзя переместить строку: папка отчета по активу уже заблокирована."
WORKSPACE_LOCKED_MESSAGE = "Нельзя переместить строку: для проекта уже создано рабочее пространство."


def _refresh_registration_numbers(request, result):
    numbers = set()
    for scope in result.scopes:
        moved = set(scope.moved_ids)
        for row in scope.after:
            if row.pk in moved:
                numbers.add(row.number)
    if numbers:
        ProjectRegistration.refresh_number_sequences(numbers)


def _validate_work_volume_locks(request, scope):
    project_id = scope.scope_key[0] if scope.scope_key else None
    if not project_id:
        return None
    displaced = any(before.pk != after.pk for before, after in zip(scope.before, scope.after))
    if not displaced:
        return None
    # Asset codes (A1, A2, …) follow the row order and are frozen once the
    # project workspace exists: report folders and file names already carry them.
    if project_id in workspace_project_ids([project_id]):
        return WORKSPACE_LOCKED_MESSAGE
    locked_keys = report_folder_locked_asset_keys([project_id])
    if not locked_keys:
        return None
    for before_row, after_row in zip(scope.before, scope.after):
        if before_row.pk == after_row.pk:
            continue
        for row in (before_row, after_row):
            asset = (row.asset_name or "").strip()
            if (project_id, asset) in locked_keys:
                return WORK_LOCKED_MESSAGE
    return None


def _report_manage_allowed(request):
    return staff_only(request) and can_manage_report_checks(request.user)


register_row_orders([
    RowOrderSpec(
        key="project-registration",
        model=ProjectRegistration,
        extra_fields=("number",),
        after_save=_refresh_registration_numbers,
        events={HX_PROJECTS_UPDATED_EVENT: True},
    ),
    RowOrderSpec(
        key="work-volume",
        model=WorkVolume,
        scope_fields=("project_id",),
        extra_fields=("asset_name",),
        validate=_validate_work_volume_locks,
    ),
    RowOrderSpec(
        key="legal-entity",
        model=LegalEntity,
        scope_fields=("project_id",),
    ),
    RowOrderSpec(
        key="report-check",
        model=ReportCheckRule,
        permission=_report_manage_allowed,
    ),
    RowOrderSpec(
        key="report-macro",
        model=ReportMacro,
        permission=_report_manage_allowed,
    ),
])
