"""Bulk row-order specs for the projects panel (see core.row_order).

Performers keep their dedicated endpoint (``performer_row_order``); the project
schedule (Gantt tasks) is not a positional table and is intentionally excluded.
"""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import LegalEntity, ProjectRegistration, ReportCheckRule, ReportMacro, WorkVolume
from .report_access import can_manage_report_checks
from .report_submission import work_scope_order_lock_reason
from .service_scope import mirror_scoped_row_order

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
    displaced = []
    seen = set()
    for before_row, after_row in zip(scope.before, scope.after):
        if before_row.pk == after_row.pk:
            continue
        for row in (before_row, after_row):
            if row.pk in seen:
                continue
            seen.add(row.pk)
            displaced.append(row)
    if not displaced:
        return None
    # Asset codes follow the shared scope order. A later stage can already have
    # a workspace or a locked report folder even when the visible stage does not.
    reason = work_scope_order_lock_reason(displaced)
    if reason == "workspace":
        return WORKSPACE_LOCKED_MESSAGE
    if reason == "folder":
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
        extra_fields=("asset_name", "scope_key"),
        validate=_validate_work_volume_locks,
        after_save=lambda request, result: mirror_scoped_row_order(WorkVolume, result),
    ),
    RowOrderSpec(
        key="legal-entity",
        model=LegalEntity,
        scope_fields=("project_id",),
        extra_fields=("scope_key",),
        after_save=lambda request, result: mirror_scoped_row_order(LegalEntity, result),
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
