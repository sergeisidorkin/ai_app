from __future__ import annotations

from experts_app.models import ExpertProfile
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, EXPERT_GROUP, LAWYER_GROUP

from .models import Performer, ProjectRegistration

_UNSET_DIRECTION_LABEL = "не установлено"


def _staff_user(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _employee_of(user):
    return getattr(user, "employee_profile", None) if user else None


def _user_role(user) -> str:
    employee = _employee_of(user)
    return (getattr(employee, "role", "") or "") if employee else ""


def _normalize(value) -> str:
    return " ".join(str(value or "").split()).strip()


def is_admin_user(user) -> bool:
    if not _staff_user(user):
        return False
    return (
        _user_role(user) == ADMIN_GROUP
        or user.groups.filter(name=ADMIN_GROUP).exists()
    )


def is_lawyer_user(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return (
        _user_role(user) == LAWYER_GROUP
        or user.groups.filter(name=LAWYER_GROUP).exists()
    )


def is_expert_user(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return (
        _user_role(user) == EXPERT_GROUP
        or user.groups.filter(name=EXPERT_GROUP).exists()
    )


def is_direction_head_user(user) -> bool:
    return _user_role(user) == DEPARTMENT_HEAD_GROUP


def can_manage_report_checks(user) -> bool:
    return is_admin_user(user)


def can_send_reports(user) -> bool:
    return _staff_user(user) and not is_lawyer_user(user)


def is_report_readonly_user(user) -> bool:
    return is_lawyer_user(user)


def is_project_manager_of(user, registration) -> bool:
    employee = _employee_of(user)
    if not employee or not registration:
        return False
    prs = _normalize(getattr(employee, "formatted_prs_id", "") or "")
    name = _normalize(Performer.employee_full_name(employee))
    if prs and _normalize(getattr(registration, "project_manager_prs_id", "")) == prs:
        return True
    return bool(name) and _normalize(getattr(registration, "project_manager", "")) == name


def _is_unset_direction(direction) -> bool:
    if direction is None:
        return True
    labels = (
        getattr(direction, "department_name", ""),
        getattr(direction, "short_name", ""),
    )
    return any(str(label or "").strip().casefold() == _UNSET_DIRECTION_LABEL for label in labels)


def _is_own_assignment(employee, performer) -> bool:
    if not employee or not performer:
        return False
    if performer.employee_id and performer.employee_id == employee.pk:
        return True
    name = _normalize(Performer.employee_full_name(employee))
    return bool(name) and _normalize(performer.executor) == name


def _direction_expert_employee_ids(head_employee) -> set[int]:
    department_id = getattr(head_employee, "department_id", None)
    if not department_id:
        return set()
    ids = set()
    profiles = (
        ExpertProfile.objects
        .select_related("expertise_direction")
        .filter(expertise_direction_id=department_id)
    )
    for profile in profiles:
        if _is_unset_direction(profile.expertise_direction):
            continue
        if profile.employee_id:
            ids.add(profile.employee_id)
    return ids


def _is_direction_expert_assignment(head_employee, performer) -> bool:
    if not head_employee or not performer or not performer.employee_id:
        return False
    department_id = getattr(head_employee, "department_id", None)
    if not department_id:
        return False
    profile = getattr(getattr(performer, "employee", None), "expert_profile", None)
    if profile is None:
        profile = (
            ExpertProfile.objects
            .select_related("expertise_direction")
            .filter(employee_id=performer.employee_id)
            .first()
        )
    if profile is None or not profile.expertise_direction_id:
        return False
    if _is_unset_direction(profile.expertise_direction):
        return False
    return profile.expertise_direction_id == department_id


def _can_act_on_performer(user, performer) -> bool:
    employee = _employee_of(user)
    if not employee or not performer:
        return False
    if _is_own_assignment(employee, performer):
        if is_direction_head_user(user):
            return True
        return performer.participation_response == Performer.ParticipationResponse.CONFIRMED
    return is_direction_head_user(user) and _is_direction_expert_assignment(employee, performer)


def _slot_performers(*, performer=None, performers=None, performer_ids=None):
    items = list(performers or [])
    if not items and performer is not None:
        items = [performer]
    if not items and performer_ids:
        items = list(
            Performer.objects
            .select_related(
                "employee",
                "employee__user",
                "employee__expert_profile",
                "employee__expert_profile__expertise_direction",
            )
            .filter(pk__in=list(performer_ids))
        )
    return items


def can_mutate_report_slot(
    user,
    *,
    project,
    performer=None,
    performers=None,
    performer_ids=None,
    is_all_sections=False,
    is_full_report=False,
) -> bool:
    if is_admin_user(user):
        return True
    if not _staff_user(user) or is_lawyer_user(user):
        return False
    if is_full_report:
        return is_project_manager_of(user, project)
    items = _slot_performers(
        performer=performer,
        performers=performers,
        performer_ids=performer_ids,
    )
    if not items:
        return False
    return all(_can_act_on_performer(user, item) for item in items)


def can_mutate_report_upload(user, upload) -> bool:
    if not upload:
        return False
    performers = None
    if upload.is_all_sections and not upload.is_full_report:
        performers = list(
            Performer.objects
            .select_related(
                "employee",
                "employee__user",
                "employee__expert_profile",
                "employee__expert_profile__expertise_direction",
            )
            .filter(
                registration_id=upload.registration_id,
                executor=upload.executor or "",
                asset_name=upload.asset_name or "",
            )
        )
    return can_mutate_report_slot(
        user,
        project=getattr(upload, "registration", None),
        performer=getattr(upload, "performer", None),
        performers=performers,
        is_all_sections=bool(upload.is_all_sections),
        is_full_report=bool(upload.is_full_report),
    )


def report_visible_registration_ids(user):
    if is_admin_user(user) or is_lawyer_user(user):
        return None
    if not _staff_user(user):
        return set()
    employee = _employee_of(user)
    ids = set()
    if employee:
        own_qs = Performer.objects.filter(employee=employee)
        if not is_direction_head_user(user):
            own_qs = own_qs.filter(participation_response=Performer.ParticipationResponse.CONFIRMED)
        ids.update(own_qs.values_list("registration_id", flat=True))
        name = _normalize(Performer.employee_full_name(employee))
        if name:
            name_qs = Performer.objects.filter(executor=name)
            if not is_direction_head_user(user):
                name_qs = name_qs.filter(participation_response=Performer.ParticipationResponse.CONFIRMED)
            ids.update(name_qs.values_list("registration_id", flat=True))
        if is_direction_head_user(user):
            expert_ids = _direction_expert_employee_ids(employee)
            if expert_ids:
                ids.update(
                    Performer.objects
                    .filter(employee_id__in=expert_ids)
                    .values_list("registration_id", flat=True)
                )
        pm_q = None
        prs = _normalize(getattr(employee, "formatted_prs_id", "") or "")
        if prs:
            pm_q = ProjectRegistration.objects.filter(project_manager_prs_id=prs)
        if name:
            name_pm = ProjectRegistration.objects.filter(project_manager=name)
            pm_q = name_pm if pm_q is None else pm_q | name_pm
        if pm_q is not None:
            ids.update(pm_q.values_list("pk", flat=True))
    return ids


def show_finding_adjustment_columns(user) -> bool:
    return is_admin_user(user) or is_direction_head_user(user)


def can_view_report_upload(user, upload) -> bool:
    if not upload:
        return False
    if not _staff_user(user):
        return False
    visible = report_visible_registration_ids(user)
    if visible is None:
        return True
    return upload.registration_id in visible


def can_adjust_report_findings(user, upload) -> bool:
    """Администратор правит любую автопроверку, руководитель направления — строки своего направления."""
    if not upload:
        return False
    if is_admin_user(user):
        return True
    if not is_direction_head_user(user):
        return False
    employee = _employee_of(user)
    department_id = getattr(employee, "department_id", None)
    if not department_id:
        return False
    from .report_review import upload_org_direction_ids

    return int(department_id) in upload_org_direction_ids(upload)


def _row_direction_ids(row) -> set[int]:
    ids = set()
    performer = getattr(row, "performer", None)
    section = getattr(performer, "typical_section", None) if performer is not None else getattr(row, "typical_section", None)
    direction_id = getattr(section, "expertise_direction_id", None)
    if direction_id:
        ids.add(int(direction_id))
    if ids and not getattr(row, "is_all_sections", False) and not getattr(row, "is_full_report", False):
        return ids
    performer_ids = list(getattr(row, "performer_ids", None) or [])
    if performer_ids:
        ids.update(
            Performer.objects.filter(pk__in=performer_ids)
            .exclude(typical_section__expertise_direction_id=None)
            .values_list("typical_section__expertise_direction_id", flat=True)
        )
    return {int(item) for item in ids if item}


def _direction_head_sees_row(user, row) -> bool:
    employee = _employee_of(user)
    department_id = getattr(employee, "department_id", None)
    if not department_id:
        return False
    upload = getattr(row, "upload", None)
    if upload is not None:
        return can_adjust_report_findings(user, upload)
    return int(department_id) in _row_direction_ids(row)


def annotate_report_submission_rows(user, rows):
    for row in rows:
        allowed = can_mutate_report_slot(
            user,
            project=getattr(row, "registration", None),
            performer=getattr(row, "performer", None),
            performer_ids=getattr(row, "performer_ids", None),
            is_all_sections=bool(getattr(row, "is_all_sections", False)),
            is_full_report=bool(getattr(row, "is_full_report", False)),
        )
        upload = getattr(row, "upload", None)
        entry = getattr(row, "review_entry", None)
        current = bool(getattr(row, "is_current", False))
        from .report_review import (
            REVIEW_PHASE_REVIEW,
            REVIEW_PHASE_REWORK,
            entry_status,
            manual_status_label,
            user_matches_review_step,
        )
        from .report_submission import report_workflow_status_class

        row.conceal_pending_remarks = False
        if entry is not None:
            if entry.remarks_notice_pending and not entry.settled:
                if user_matches_review_step(user, entry.upload, entry.step):
                    row.workflow_status = entry_status(entry)
                else:
                    row.conceal_pending_remarks = True
                    row.workflow_status = manual_status_label(entry.step, REVIEW_PHASE_REVIEW)
                    row.finding_count_display = "—"
                    row.finding_info_disabled = False
                row.workflow_status_class = report_workflow_status_class(row.workflow_status)
            row.can_upload = bool(
                allowed and current and entry.phase == REVIEW_PHASE_REWORK and not entry.settled
            )
            row.can_send = False
            row.can_review_upload = bool(
                current
                and entry.phase == REVIEW_PHASE_REVIEW
                and not entry.settled
                and not (entry.review_file_name or entry.review_cloud_path)
                and user_matches_review_step(user, entry.upload, entry.step)
            )
            row.can_discard_remarks = bool(
                current
                and entry.remarks_notice_pending
                and not entry.settled
                and user_matches_review_step(user, entry.upload, entry.step)
            )
        else:
            row.can_upload = bool(allowed and current)
            row.can_send = bool(allowed and current and not (getattr(upload, "review_step", "") or ""))
            row.can_review_upload = False
            row.can_discard_remarks = False
        if is_admin_user(user):
            row.finding_adjustment_visible = True
        elif is_direction_head_user(user):
            row.finding_adjustment_visible = _direction_head_sees_row(user, row)
        else:
            row.finding_adjustment_visible = False
        row.can_correct_findings = bool(
            row.finding_adjustment_visible and getattr(row, "show_finding_info", False) and upload
        )
    return rows
