from policy_app.models import DEPARTMENT_HEAD_GROUP
from projects_app.models import Performer
from django.db.models import Max, Q

from .models import PersonalWorktimeWeekAssignment, WorktimeAssignment

FREELANCER_LABEL = "Внештатный сотрудник"
SOURCE_PRIORITY = {
    WorktimeAssignment.SourceType.PROJECT_MANAGER: 10,
    WorktimeAssignment.SourceType.DIRECTION_HEAD_REQUEST: 20,
    WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION: 30,
    WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK: 1,
}


def normalize_executor_name(value):
    return " ".join(str(value or "").split()).strip()


def resolve_employee_and_name(*, employee=None, executor_name=""):
    normalized_name = normalize_executor_name(executor_name)
    if employee is not None:
        normalized_name = Performer.employee_full_name(employee) or normalized_name
    if employee is None and normalized_name:
        employee = Performer.resolve_employee_from_executor(normalized_name)
    return normalized_name, employee


def is_worktime_eligible_employee(employee):
    if employee is None:
        return False
    user = getattr(employee, "user", None)
    if user is None or not getattr(user, "is_staff", False):
        return False
    return normalize_executor_name(getattr(employee, "employment", "")) != FREELANCER_LABEL


def _should_promote_source(current_source, new_source):
    return SOURCE_PRIORITY.get(new_source, 0) > SOURCE_PRIORITY.get(current_source, 0)


def _personal_week_link_scope_queryset(*, week_start, employee=None, executor_name=""):
    normalized_name, resolved_employee = resolve_employee_and_name(
        employee=employee,
        executor_name=executor_name,
    )
    queryset = PersonalWorktimeWeekAssignment.objects.filter(week_start=week_start)
    if resolved_employee is not None:
        return queryset.filter(
            Q(assignment__employee=resolved_employee)
            | Q(assignment__employee__isnull=True, assignment__executor_name=normalized_name)
        )
    if normalized_name:
        return queryset.filter(assignment__executor_name=normalized_name)
    return queryset.none()


def _next_personal_week_link_position(*, week_start, employee=None, executor_name=""):
    max_position = (
        _personal_week_link_scope_queryset(
            week_start=week_start,
            employee=employee,
            executor_name=executor_name,
        )
        .filter(is_hidden=False)
        .aggregate(max_position=Max("position"))
        .get("max_position")
        or 0
    )
    return int(max_position) + 1


def ensure_worktime_assignment(
    *,
    registration,
    source_type,
    performer=None,
    employee=None,
    executor_name="",
):
    normalized_name, resolved_employee = resolve_employee_and_name(
        employee=employee,
        executor_name=executor_name or getattr(performer, "executor", ""),
    )
    if not registration or not normalized_name or not is_worktime_eligible_employee(resolved_employee):
        return None

    defaults = {
        "performer": performer,
        "employee": resolved_employee,
        "source_type": source_type,
    }
    assignment, created = WorktimeAssignment.objects.get_or_create(
        registration=registration,
        executor_name=normalized_name,
        defaults=defaults,
    )
    if created:
        return assignment

    updated_fields = []
    if assignment.employee_id is None and resolved_employee is not None:
        assignment.employee = resolved_employee
        updated_fields.append("employee")
    if assignment.performer_id is None and performer is not None:
        assignment.performer = performer
        updated_fields.append("performer")
    if _should_promote_source(assignment.source_type, source_type):
        assignment.source_type = source_type
        updated_fields.append("source_type")
    if updated_fields:
        assignment.save(update_fields=updated_fields + ["updated_at"])
    return assignment


def ensure_personal_week_assignment(
    *,
    registration,
    proposal_registration=None,
    employee,
    week_start,
    record_type=WorktimeAssignment.RecordType.PROJECT,
):
    normalized_name, resolved_employee = resolve_employee_and_name(
        employee=employee,
        executor_name="",
    )
    if resolved_employee is None or not normalized_name or not is_worktime_eligible_employee(resolved_employee):
        return None, None
    if record_type == WorktimeAssignment.RecordType.PROJECT and not registration:
        return None, None
    if record_type == WorktimeAssignment.RecordType.TKP and not proposal_registration:
        return None, None

    if record_type == WorktimeAssignment.RecordType.PROJECT:
        assignment = WorktimeAssignment.objects.filter(
            registration=registration,
            executor_name=normalized_name,
        ).first()
    elif record_type == WorktimeAssignment.RecordType.TKP:
        assignment = WorktimeAssignment.objects.filter(
            proposal_registration=proposal_registration,
            executor_name=normalized_name,
        ).first()
    else:
        assignment = WorktimeAssignment.objects.filter(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=normalized_name,
            record_type=record_type,
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        ).first()
    if assignment is None:
        assignment = WorktimeAssignment.objects.create(
            registration=registration,
            proposal_registration=proposal_registration,
            employee=resolved_employee,
            executor_name=normalized_name,
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=record_type,
        )

    week_link, _ = PersonalWorktimeWeekAssignment.objects.get_or_create(
        assignment=assignment,
        week_start=week_start,
    )
    update_fields = []
    if week_link.is_hidden:
        week_link.is_hidden = False
        update_fields.append("is_hidden")
    if week_link.position <= 0 or "is_hidden" in update_fields:
        week_link.position = _next_personal_week_link_position(
            week_start=week_start,
            employee=resolved_employee,
            executor_name=normalized_name,
        )
        update_fields.append("position")
    if update_fields:
        week_link.save(update_fields=update_fields + ["updated_at"])
    return assignment, week_link


def ensure_worktime_assignment_for_performer(performer, source_type):
    if performer is None or performer.registration_id is None:
        return None
    return ensure_worktime_assignment(
        registration=performer.registration,
        performer=performer,
        employee=performer.employee,
        executor_name=performer.executor,
        source_type=source_type,
    )


def ensure_confirmed_assignments_for_performers(performer_ids):
    performers = (
        Performer.objects
        .select_related("registration", "employee", "employee__user")
        .filter(pk__in=list(performer_ids or []))
    )
    for performer in performers:
        ensure_worktime_assignment_for_performer(
            performer,
            WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )


def ensure_direction_head_request_assignments(performers):
    for performer in performers or []:
        employee = getattr(performer, "employee", None)
        if employee is None or getattr(employee, "role", "") != DEPARTMENT_HEAD_GROUP:
            continue
        ensure_worktime_assignment_for_performer(
            performer,
            WorktimeAssignment.SourceType.DIRECTION_HEAD_REQUEST,
        )


def sync_project_manager_assignment(registration, previous_project_manager=""):
    current_name = normalize_executor_name(getattr(registration, "project_manager", ""))
    previous_name = normalize_executor_name(previous_project_manager)

    if previous_name and previous_name != current_name:
        WorktimeAssignment.objects.filter(
            registration=registration,
            executor_name=previous_name,
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        ).delete()

    if current_name:
        ensure_worktime_assignment(
            registration=registration,
            executor_name=current_name,
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
