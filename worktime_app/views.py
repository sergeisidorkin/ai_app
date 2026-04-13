import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from projects_app.models import Performer, ProjectRegistration
from proposals_app.models import ProposalRegistration

from .forms import PersonalWorktimeWeekAssignmentForm
from .models import WorktimeAssignment, WorktimeEntry
from .services import ensure_personal_week_assignment, is_worktime_eligible_employee

WORKTIME_PARTIAL_TEMPLATE = "worktime_app/worktime_partial.html"
MONTH_LABELS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
MONTH_SHORT_LABELS = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MAX_HOURS_PER_DAY = 24
PERSONAL_WEEK_LIMIT_WEEKS = 2
PERSONAL_WEEK_LIMIT_ERROR = "Нельзя выбрать слишком далекую будущую неделю. Доступны текущая неделя и только две следующие."
WORKTIME_ACCESS_ERROR = 'Табель доступен только штатным сотрудникам с правами staff. Пользователи с трудоустройством "Внештатный сотрудник" не допускаются.'


def _resolve_month(raw_value):
    today = timezone.localdate()
    if raw_value:
        try:
            year_text, month_text = str(raw_value).split("-", 1)
            year = int(year_text)
            month = int(month_text)
            return date(year, month, 1)
        except (TypeError, ValueError):
            pass
    return date(today.year, today.month, 1)


def _resolve_scale(raw_value):
    return "year" if str(raw_value or "").strip() == "year" else "month"


def _resolve_hist_sort(raw_value):
    raw_text = str(raw_value or "").strip().lower()
    return raw_text if raw_text in {"asc", "desc"} else ""


def _resolve_breakdown(raw_value):
    raw_text = str(raw_value or "").strip().lower()
    return "activities" if raw_text == "activities" else "employees"


def _resolve_general_period(raw_value, scale):
    today = timezone.localdate()
    raw_text = str(raw_value or "").strip()
    if scale == "year":
        if raw_text:
            year_part = raw_text.split("-", 1)[0]
            try:
                return date(int(year_part), 1, 1)
            except (TypeError, ValueError):
                pass
        return date(today.year, 1, 1)
    return _resolve_month(raw_text)


def _start_of_week(value):
    return value - timedelta(days=value.weekday())


def _end_of_week(value):
    return _start_of_week(value) + timedelta(days=6)


def _resolve_week_anchor(raw_value):
    today = timezone.localdate()
    if raw_value:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(str(raw_value), fmt).date()
            except (TypeError, ValueError):
                continue
        try:
            return date.fromisoformat(str(raw_value))
        except (TypeError, ValueError):
            pass
    return today


def _personal_week_bounds(anchor_date):
    week_start = _start_of_week(anchor_date)
    max_week_start = _start_of_week(timezone.localdate()) + timedelta(weeks=PERSONAL_WEEK_LIMIT_WEEKS)
    if week_start > max_week_start:
        return _start_of_week(timezone.localdate()), PERSONAL_WEEK_LIMIT_ERROR
    return week_start, ""


def _month_days(month_start):
    total_days = monthrange(month_start.year, month_start.month)[1]
    return [date(month_start.year, month_start.month, day) for day in range(1, total_days + 1)]


def _week_days(week_start):
    return [week_start + timedelta(days=offset) for offset in range(7)]


def _year_months(year_start):
    return [date(year_start.year, month, 1) for month in range(1, 13)]


def _previous_month_value(month_start):
    if month_start.month == 1:
        return date(month_start.year - 1, 12, 1)
    return date(month_start.year, month_start.month - 1, 1)


def _next_month_value(month_start):
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _visible_period_bounds(period_start, scale):
    if scale == "year":
        return date(period_start.year, 1, 1), date(period_start.year, 12, 31)
    return period_start, date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])


def _base_worktime_assignment_queryset():
    return WorktimeAssignment.objects.select_related(
        "registration",
        "registration__type",
        "proposal_registration",
        "proposal_registration__type",
        "employee",
        "employee__user",
        "performer",
    )


def _current_employee_and_name(user):
    employee = getattr(user, "employee_profile", None)
    if not is_worktime_eligible_employee(employee):
        return None, ""
    return employee, Performer.employee_full_name(employee)


def _has_worktime_access(user):
    return is_worktime_eligible_employee(getattr(user, "employee_profile", None))


def _assignment_is_worktime_visible(assignment):
    employee = getattr(assignment, "employee", None)
    if employee is None:
        employee = Performer.resolve_employee_from_executor(getattr(assignment, "executor_name", ""))
        if employee is not None:
            assignment.employee = employee
    return is_worktime_eligible_employee(employee)


def _personal_assignment_filters(user):
    employee, employee_name = _current_employee_and_name(user)
    filters = Q(pk__in=[])
    if employee is not None:
        filters = Q(employee__user=user)
    if employee_name:
        filters |= Q(employee__isnull=True, executor_name=employee_name)
    return filters, employee, employee_name


def _assignment_sort_key(assignment):
    registration = assignment.registration
    proposal_registration = assignment.proposal_registration
    if assignment.registration_id is not None:
        row_rank = 0
    elif assignment.proposal_registration_id is not None:
        row_rank = 1
    else:
        row_rank = 2
    return (
        assignment.display_executor_name or assignment.executor_name or "",
        row_rank,
        getattr(registration, "number", 0) or 0,
        getattr(proposal_registration, "number", 0) or 0,
        getattr(registration, "id", 0) or 0,
        getattr(proposal_registration, "id", 0) or 0,
        assignment.get_record_type_display() if not assignment.has_linked_registry_row else "",
        assignment.id,
    )


def _compose_group_label(*parts):
    normalized_parts = []
    for part in parts:
        text = str(part or "").strip()
        if not text or text == "—":
            continue
        normalized_parts.append(text)
    return " ".join(normalized_parts) or "—"


def _activity_group_key(assignment):
    if assignment.registration_id is not None:
        return f"activities:project:{assignment.registration_id}"
    if assignment.proposal_registration_id is not None:
        return f"activities:tkp:{assignment.proposal_registration_id}"
    return f"activities:manual:{assignment.record_type}"


def _activity_group_label(assignment):
    if assignment.has_linked_registry_row:
        return _compose_group_label(
            assignment.display_project_code,
            assignment.display_type_label,
            assignment.display_project_name,
        )
    return assignment.display_manual_label


def _activity_group_sort_key(assignment):
    registration = assignment.registration
    proposal_registration = assignment.proposal_registration
    if assignment.registration_id is not None:
        row_rank = 0
    elif assignment.proposal_registration_id is not None:
        row_rank = 1
    else:
        row_rank = 2
    return (
        row_rank,
        getattr(registration, "number", 0) or 0,
        getattr(proposal_registration, "number", 0) or 0,
        getattr(registration, "id", 0) or 0,
        getattr(proposal_registration, "id", 0) or 0,
        assignment.get_record_type_display() if not assignment.has_linked_registry_row else "",
        _activity_group_label(assignment),
    )


def _employee_row_sort_key(assignment):
    return (
        assignment.display_executor_name or assignment.executor_name or "",
        assignment.id,
    )


def _assignment_breakdown_sort_key(assignment, breakdown):
    if breakdown == "activities":
        return _activity_group_sort_key(assignment) + _employee_row_sort_key(assignment)
    return _assignment_sort_key(assignment)


def _combine_assignments(*assignment_sets, sort_key=None):
    combined = {}
    for assignment_set in assignment_sets:
        for assignment in assignment_set:
            combined[assignment.pk] = assignment
    return sorted(combined.values(), key=sort_key or _assignment_sort_key)


def _worktime_assignment_queryset(user, personal_only=False):
    assignments = (
        _base_worktime_assignment_queryset()
        .exclude(source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK)
        .order_by("executor_name", "registration__number", "registration__id", "id")
    )
    if personal_only:
        filters = Q(employee__user=user)
        employee = getattr(user, "employee_profile", None)
        employee_name = Performer.employee_full_name(employee)
        if employee_name:
            filters |= Q(employee__isnull=True, executor_name=employee_name)
        assignments = assignments.filter(filters)
    return assignments


def _personal_manual_week_assignment_queryset(user, week_start):
    filters, _, _ = _personal_assignment_filters(user)
    return (
        _base_worktime_assignment_queryset()
        .filter(
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            personal_week_links__week_start=week_start,
        )
        .filter(filters)
        .distinct()
        .order_by("executor_name", "registration__number", "registration__id", "id")
    )


def _manual_assignments_for_period(range_start, range_end):
    return (
        _base_worktime_assignment_queryset()
        .filter(
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            entries__work_date__range=(range_start, range_end),
        )
        .distinct()
        .order_by("executor_name", "registration__number", "registration__id", "id")
    )


def _visible_assignments_for_period(
    user,
    *,
    personal_only=False,
    visible_days=None,
    week_start=None,
    range_start=None,
    range_end=None,
    breakdown="employees",
):
    if not _has_worktime_access(user):
        return []
    global_assignments = _worktime_assignment_queryset(user, personal_only=personal_only)
    if personal_only:
        manual_assignments = _personal_manual_week_assignment_queryset(user, week_start)
    else:
        manual_assignments = _manual_assignments_for_period(range_start, range_end)
    return [
        assignment for assignment in _combine_assignments(
            global_assignments,
            manual_assignments,
            sort_key=lambda assignment: _assignment_breakdown_sort_key(assignment, breakdown),
        )
        if _assignment_is_worktime_visible(assignment)
    ]


def _available_personal_week_registrations(user, week_start):
    visible_assignments = _visible_assignments_for_period(
        user,
        personal_only=True,
        visible_days=_week_days(week_start),
        week_start=week_start,
    )
    used_registration_ids = {
        assignment.registration_id
        for assignment in visible_assignments
        if assignment.registration_id is not None
    }
    return (
        ProjectRegistration.objects
        .select_related("type")
        .exclude(pk__in=used_registration_ids)
        .order_by("number", "id")
    )


def _available_personal_week_proposals(user, week_start):
    visible_assignments = _visible_assignments_for_period(
        user,
        personal_only=True,
        visible_days=_week_days(week_start),
        week_start=week_start,
    )
    used_proposal_ids = {
        assignment.proposal_registration_id
        for assignment in visible_assignments
        if assignment.proposal_registration_id is not None
    }
    return (
        ProposalRegistration.objects
        .select_related("type")
        .exclude(pk__in=used_proposal_ids)
        .order_by("-number", "-id")
    )


def _personal_manual_assignment_exists(*, employee_name, week_start, record_type):
    if not employee_name or record_type == WorktimeAssignment.RecordType.PROJECT:
        return False
    return WorktimeAssignment.objects.filter(
        executor_name=employee_name,
        record_type=record_type,
        source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        registration__isnull=True,
        proposal_registration__isnull=True,
        personal_week_links__week_start=week_start,
    ).exists()


def _build_assignment_row(assignment, visible_days, entry_map, *, breakdown="employees"):
    row_total = 0
    cells = []
    day_values = entry_map.get(assignment.pk, {})
    for work_day in visible_days:
        value = day_values.get(work_day)
        if value is not None:
            row_total += value
        cells.append(
            {
                "date": work_day,
                "input_name": f"hours_{assignment.pk}_{work_day:%Y%m%d}",
                "value": value,
            }
        )
    row = {
        "assignment": assignment,
        "cells": cells,
        "total_hours": row_total,
        "sort_key": _employee_row_sort_key(assignment) if breakdown == "activities" else _assignment_sort_key(assignment),
    }
    if breakdown == "activities":
        row["display_mode"] = "merged"
        row["merged_label"] = assignment.display_executor_name or assignment.executor_name or "—"
        row["is_tkp"] = False
        return row
    if assignment.has_linked_registry_row:
        row["display_mode"] = "registry"
        row["project_code"] = assignment.display_project_code
        row["type_label"] = assignment.display_type_label
        row["name_label"] = assignment.display_project_name
        row["is_tkp"] = bool(assignment.proposal_registration_id)
    else:
        row["display_mode"] = "merged"
        row["merged_label"] = assignment.display_manual_label
        row["is_tkp"] = False
    return row


def _grouped_assignment_rows(assignments, month_days, entry_map, *, breakdown="employees"):
    groups = []
    current_group = None
    current_key = None
    for assignment in assignments:
        if breakdown == "activities":
            group_key = _activity_group_key(assignment)
            label = _activity_group_label(assignment)
            group_sort_key = _activity_group_sort_key(assignment)
        else:
            label = assignment.display_executor_name or assignment.executor_name or "—"
            group_key = f"employees:{label}"
            group_sort_key = (label,)
        if group_key != current_key:
            current_key = group_key
            current_group = {
                "key": group_key,
                "label": label,
                "rows": [],
                "column_totals": {work_day: 0 for work_day in month_days},
                "grand_total": 0,
                "sort_key": group_sort_key,
            }
            groups.append(current_group)
        row = _build_assignment_row(assignment, month_days, entry_map, breakdown=breakdown)
        for cell in row["cells"]:
            if cell["value"] is not None:
                current_group["column_totals"][cell["date"]] += cell["value"]
        current_group["rows"].append(row)
        current_group["grand_total"] += row["total_hours"]

    for group in groups:
        group["column_totals"] = [group["column_totals"][work_day] for work_day in month_days]
    return groups


def _group_totals(groups, visible_days):
    if not groups:
        return [0 for _ in visible_days], 0
    column_totals = [0 for _ in visible_days]
    grand_total = 0
    for group in groups:
        for index, value in enumerate(group.get("column_totals", [])):
            column_totals[index] += value or 0
        grand_total += group.get("grand_total", 0) or 0
    return column_totals, grand_total


def _attach_group_histograms(groups):
    if not groups:
        return groups
    min_width_percent = 18.0
    row_min_width_percent = 2.0
    totals = [group.get("grand_total", 0) or 0 for group in groups]
    min_total = min(totals)
    max_total = max(totals)
    spread = max_total - min_total
    for group in groups:
        value = group.get("grand_total", 0) or 0
        if spread <= 0:
            normalized = 100.0 if max_total > 0 else min_width_percent
        else:
            normalized = min_width_percent + ((value - min_total) / spread) * (100.0 - min_width_percent)
        group["histogram_width_percent"] = round(normalized, 3)
        group_max_width = group["histogram_width_percent"]
        row_totals = [row.get("total_hours", 0) or 0 for row in group.get("rows", [])]
        if not row_totals:
            continue
        min_row_total = min(row_totals)
        max_row_total = max(row_totals)
        row_spread = max_row_total - min_row_total
        for row in group.get("rows", []):
            row_total = row.get("total_hours", 0) or 0
            if row_spread <= 0:
                row_normalized = group_max_width if max_row_total > 0 else row_min_width_percent
            elif max_row_total <= 0:
                row_normalized = row_min_width_percent
            else:
                row_normalized = row_min_width_percent + ((row_total - min_row_total) / row_spread) * max(
                    group_max_width - row_min_width_percent, 0
                )
            row["histogram_width_percent"] = round(row_normalized, 3)
    return groups


def _apply_histogram_sort(groups, hist_sort):
    if hist_sort not in {"asc", "desc"}:
        return groups
    reverse = hist_sort == "desc"
    sorted_groups = []
    for group in groups:
        sorted_group = dict(group)
        sorted_group["rows"] = sorted(
            group.get("rows", []),
            key=lambda row: (
                row.get("total_hours", 0) or 0,
                row.get("sort_key", ()),
            ),
            reverse=reverse,
        )
        sorted_groups.append(sorted_group)
    return sorted(
        sorted_groups,
        key=lambda group: (
            group.get("grand_total", 0) or 0,
            group.get("sort_key", ()),
        ),
        reverse=reverse,
    )


def _assignment_rows(assignments, visible_days, entry_map):
    rows = []
    column_totals = {work_day: 0 for work_day in visible_days}
    grand_total = 0
    for assignment in assignments:
        row = _build_assignment_row(assignment, visible_days, entry_map, breakdown="employees")
        for cell in row["cells"]:
            if cell["value"] is not None:
                column_totals[cell["date"]] += cell["value"]
        grand_total += row["total_hours"]
        rows.append(row)
    return rows, [column_totals[work_day] for work_day in visible_days], grand_total


def _build_entry_map(entries, *, scale):
    entry_map = {}
    for entry in entries:
        if scale == "year":
            bucket_key = date(entry.work_date.year, entry.work_date.month, 1)
            assignment_buckets = entry_map.setdefault(entry.assignment_id, {})
            assignment_buckets[bucket_key] = assignment_buckets.get(bucket_key, 0) + entry.hours
        else:
            entry_map.setdefault(entry.assignment_id, {})[entry.work_date] = entry.hours
    return entry_map


def _worktime_context(
    user,
    *,
    personal_only=False,
    month_start=None,
    scale="month",
    hist_sort="",
    breakdown="employees",
    error_message="",
    success_message="",
):
    month_start = month_start or _resolve_general_period(None, scale)
    week_start = None
    week_error = ""
    general_scale = _resolve_scale(scale)
    histogram_sort_value = _resolve_hist_sort(hist_sort)
    breakdown_value = _resolve_breakdown(breakdown)
    _, current_employee_name = _current_employee_and_name(user)
    has_worktime_access = _has_worktime_access(user)
    if personal_only:
        week_start, week_error = _personal_week_bounds(month_start)
        visible_days = _week_days(week_start)
        range_start, range_end = visible_days[0], visible_days[-1]
    else:
        if general_scale == "year":
            visible_days = _year_months(month_start)
        else:
            visible_days = _month_days(month_start)
        range_start, range_end = _visible_period_bounds(month_start, general_scale)
    assignments = _visible_assignments_for_period(
        user,
        personal_only=personal_only,
        visible_days=visible_days,
        week_start=week_start,
        range_start=range_start,
        range_end=range_end,
        breakdown=breakdown_value,
    ) if has_worktime_access else []
    entries = (
        WorktimeEntry.objects
        .filter(assignment_id__in=[assignment.pk for assignment in assignments], work_date__range=(range_start, range_end))
        .only("assignment_id", "work_date", "hours")
    )
    entry_map = _build_entry_map(entries, scale="week" if personal_only else general_scale)
    rows = []
    column_totals = []
    grand_total = 0
    groups = []
    if personal_only:
        rows, column_totals, grand_total = _assignment_rows(assignments, visible_days, entry_map)
    else:
        groups = _grouped_assignment_rows(assignments, visible_days, entry_map, breakdown=breakdown_value)
        groups = _attach_group_histograms(groups)
        groups = _apply_histogram_sort(groups, histogram_sort_value)
        column_totals, grand_total = _group_totals(groups, visible_days)

    effective_error = error_message or week_error or ("" if has_worktime_access else WORKTIME_ACCESS_ERROR)
    week_end = _end_of_week(week_start) if week_start else None
    max_week_start = _start_of_week(timezone.localdate()) + timedelta(weeks=PERSONAL_WEEK_LIMIT_WEEKS)
    period_value = month_start.strftime("%Y" if general_scale == "year" else "%Y-%m")
    period_label = (
        f"{month_start.year} г."
        if general_scale == "year"
        else f"{MONTH_LABELS[month_start.month]}, {month_start.year} г."
    )

    return {
        "groups": groups,
        "rows": rows,
        "days": [
            {
                "date": work_day,
                "day_number": work_day.day if personal_only or general_scale == "month" else "",
                "weekday_label": WEEKDAY_LABELS[work_day.weekday()] if personal_only or general_scale == "month" else "",
                "header_label": MONTH_SHORT_LABELS[work_day.month] if (not personal_only and general_scale == "year") else "",
            }
            for work_day in visible_days
        ],
        "month_value": month_start.strftime("%Y-%m"),
        "month_label": f"{MONTH_LABELS[month_start.month]} {month_start.year}",
        "scope": "personal" if personal_only else "all",
        "error_message": effective_error,
        "success_message": success_message,
        "is_personal_week_view": personal_only,
        "is_general_year_view": not personal_only and general_scale == "year",
        "week_value": week_start.isoformat() if week_start else "",
        "week_label": (
            f"с {week_start.strftime('%d.%m.%y')} по {week_end.strftime('%d.%m.%y')}"
            if week_start and week_end else ""
        ),
        "week_max_value": max_week_start.isoformat(),
        "scale_value": general_scale,
        "histogram_sort_value": histogram_sort_value,
        "breakdown_value": breakdown_value,
        "breakdown_label": "по активностям" if breakdown_value == "activities" else "по сотрудникам",
        "is_activity_breakdown": breakdown_value == "activities",
        "scale_label": "год" if general_scale == "year" else "месяц",
        "period_value": period_value,
        "period_label": period_label,
        "column_totals": column_totals,
        "grand_total": grand_total,
        "partial_path": reverse("personal_worktime_partial" if personal_only else "worktime_partial"),
        "personal_add_row_url": reverse("personal_worktime_row_form") if personal_only else "",
        "current_employee_name": current_employee_name or "—",
    }


def _parse_hours_payload(request_post, assignment_ids, month_days):
    parsed = {}
    for assignment_id in assignment_ids:
        for work_day in month_days:
            key = f"hours_{assignment_id}_{work_day:%Y%m%d}"
            raw_value = str(request_post.get(key, "")).strip()
            if not raw_value:
                parsed[(assignment_id, work_day)] = None
                continue
            try:
                hours = int(raw_value)
            except (TypeError, ValueError):
                raise forms.ValidationError(
                    f"Значение за {work_day.strftime('%d.%m.%Y')} должно быть целым числом."
                )
            if hours < 0 or hours > MAX_HOURS_PER_DAY:
                raise forms.ValidationError(
                    f"Количество часов за {work_day.strftime('%d.%m.%Y')} должно быть в диапазоне от 0 до {MAX_HOURS_PER_DAY}."
                )
            parsed[(assignment_id, work_day)] = hours
    return parsed


def _render_worktime_panel(request, *, personal_only=False, month_start=None, error_message="", success_message=""):
    return render(
        request,
        WORKTIME_PARTIAL_TEMPLATE,
        _worktime_context(
            request.user,
            personal_only=personal_only,
            month_start=month_start,
            scale=request.GET.get("scale") if request.method == "GET" else request.POST.get("scale"),
            hist_sort=request.GET.get("hist_sort") if request.method == "GET" else request.POST.get("hist_sort"),
            breakdown=request.GET.get("breakdown") if request.method == "GET" else request.POST.get("breakdown"),
            error_message=error_message,
            success_message=success_message,
        ),
    )


@login_required
@require_http_methods(["GET"])
def worktime_partial(request):
    scale = _resolve_scale(request.GET.get("scale"))
    period_start = _resolve_general_period(request.GET.get("period") or request.GET.get("month"), scale)
    return render(
        request,
        WORKTIME_PARTIAL_TEMPLATE,
        _worktime_context(
            request.user,
            month_start=period_start,
            scale=scale,
            hist_sort=request.GET.get("hist_sort"),
            breakdown=request.GET.get("breakdown"),
        ),
    )


@login_required
@require_http_methods(["GET"])
def personal_worktime_partial(request):
    week_anchor = _resolve_week_anchor(request.GET.get("week"))
    return _render_worktime_panel(request, personal_only=True, month_start=week_anchor)


@login_required
@require_http_methods(["GET", "POST"])
def personal_worktime_row_form(request):
    week_anchor = _resolve_week_anchor(request.GET.get("week") or request.POST.get("week"))
    week_start, week_error = _personal_week_bounds(week_anchor)
    registration_queryset = _available_personal_week_registrations(request.user, week_start)
    proposal_queryset = _available_personal_week_proposals(request.user, week_start)
    form = PersonalWorktimeWeekAssignmentForm(
        request.POST or None,
        initial={"week": week_start.isoformat()},
        registration_queryset=registration_queryset,
        proposal_queryset=proposal_queryset,
    )

    if not _has_worktime_access(request.user):
        form.add_error(None, WORKTIME_ACCESS_ERROR)
        return render(
            request,
            "worktime_app/personal_worktime_row_form.html",
            {
                "form": form,
                "has_available_registrations": False,
                "has_available_proposals": False,
                "week_value": week_start.isoformat(),
                "week_label": f"с {week_start.strftime('%d.%m.%y')} по {_end_of_week(week_start).strftime('%d.%m.%y')}",
                "week_error": week_error,
            },
        )

    if request.method == "POST":
        employee, employee_name = _current_employee_and_name(request.user)
        if week_error:
            form.add_error(None, week_error)
        elif employee is None or not employee_name:
            form.add_error(None, "Для текущего пользователя не найден сотрудник для создания строки табеля.")
        elif form.is_valid():
            registration = form.cleaned_data["registration"]
            proposal_registration = form.cleaned_data["proposal_registration"]
            record_type = form.cleaned_data["record_type"]
            existing_assignment = None
            if record_type == WorktimeAssignment.RecordType.PROJECT:
                existing_assignment = WorktimeAssignment.objects.filter(
                    registration=registration,
                    executor_name=employee_name,
                ).first()
            elif record_type == WorktimeAssignment.RecordType.TKP:
                existing_assignment = WorktimeAssignment.objects.filter(
                    proposal_registration=proposal_registration,
                    executor_name=employee_name,
                ).first()
            if record_type == WorktimeAssignment.RecordType.PROJECT and existing_assignment and existing_assignment.source_type != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK:
                form.add_error("registration", "Строка по выбранному проекту уже присутствует в табеле.")
            elif record_type == WorktimeAssignment.RecordType.TKP and existing_assignment and existing_assignment.source_type != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK:
                form.add_error("proposal_registration", "Строка по выбранному ТКП уже присутствует в табеле.")
            elif _personal_manual_assignment_exists(
                employee_name=employee_name,
                week_start=week_start,
                record_type=record_type,
            ):
                form.add_error("record_type", "Строка с выбранным видом записи уже добавлена для этой недели.")
            else:
                ensure_personal_week_assignment(
                    registration=registration,
                    proposal_registration=proposal_registration,
                    employee=employee,
                    week_start=week_start,
                    record_type=record_type,
                )
                response = HttpResponse(status=204)
                response["HX-Trigger"] = json.dumps({"worktime-updated": True})
                return response

    return render(
        request,
        "worktime_app/personal_worktime_row_form.html",
        {
            "form": form,
            "has_available_registrations": registration_queryset.exists(),
            "has_available_proposals": proposal_queryset.exists(),
            "week_value": week_start.isoformat(),
            "week_label": f"с {week_start.strftime('%d.%m.%y')} по {_end_of_week(week_start).strftime('%d.%m.%y')}",
            "week_error": week_error,
        },
    )


@login_required
@require_http_methods(["POST"])
def worktime_save(request):
    autosave = request.POST.get("autosave") == "1"
    personal_only = request.POST.get("scope") == "personal"
    if personal_only:
        month_start = _resolve_week_anchor(request.POST.get("week") or request.POST.get("month"))
        week_start, week_error = _personal_week_bounds(month_start)
        if week_error:
            if autosave:
                return JsonResponse({"ok": False, "error": week_error}, status=400)
            return _render_worktime_panel(
                request,
                personal_only=True,
                month_start=week_start,
                error_message=week_error,
            )
        visible_days = _week_days(week_start)
        range_start, range_end = visible_days[0], visible_days[-1]
        scale = "month"
    else:
        scale = _resolve_scale(request.POST.get("scale"))
        month_start = _resolve_general_period(request.POST.get("period") or request.POST.get("month"), scale)
        if scale == "year":
            visible_days = _year_months(month_start)
        else:
            visible_days = _month_days(month_start)
        range_start, range_end = _visible_period_bounds(month_start, scale)
    if not _has_worktime_access(request.user):
        if autosave:
            return JsonResponse({"ok": False, "error": WORKTIME_ACCESS_ERROR}, status=403)
        return _render_worktime_panel(
            request,
            personal_only=personal_only,
            month_start=month_start,
            error_message=WORKTIME_ACCESS_ERROR,
        )
    visible_assignments = {
        assignment.pk: assignment
        for assignment in _visible_assignments_for_period(
            request.user,
            personal_only=personal_only,
            visible_days=visible_days,
            week_start=week_start if personal_only else None,
            range_start=range_start,
            range_end=range_end,
        )
    }

    raw_assignment_ids = request.POST.getlist("assignment_ids")
    try:
        assignment_ids = sorted({int(value) for value in raw_assignment_ids if str(value).strip()})
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Передан некорректный список строк табеля.")

    assignments = [visible_assignments[assignment_id] for assignment_id in assignment_ids if assignment_id in visible_assignments]
    if len(assignments) != len(assignment_ids):
        return HttpResponseBadRequest("Часть строк табеля недоступна для сохранения.")

    try:
        parsed_values = _parse_hours_payload(request.POST, assignment_ids, visible_days)
    except forms.ValidationError as exc:
        if autosave:
            return JsonResponse({"ok": False, "error": exc.message}, status=400)
        return _render_worktime_panel(
            request,
            personal_only=personal_only,
            month_start=month_start,
            error_message=exc.message,
        )

    existing_entries = {
        (entry.assignment_id, entry.work_date): entry
        for entry in WorktimeEntry.objects.filter(
            assignment_id__in=assignment_ids,
            work_date__range=(range_start, range_end),
        )
    }
    to_create = []
    to_update = []
    to_delete_ids = []

    for key, hours in parsed_values.items():
        existing = existing_entries.get(key)
        if hours is None:
            if existing is not None:
                to_delete_ids.append(existing.pk)
            continue
        if existing is None:
            to_create.append(WorktimeEntry(assignment_id=key[0], work_date=key[1], hours=hours))
            continue
        if existing.hours != hours:
            existing.hours = hours
            to_update.append(existing)

    with transaction.atomic():
        if to_delete_ids:
            WorktimeEntry.objects.filter(pk__in=to_delete_ids).delete()
        if to_create:
            WorktimeEntry.objects.bulk_create(to_create)
        if to_update:
            WorktimeEntry.objects.bulk_update(to_update, ["hours", "updated_at"])

    if autosave:
        return JsonResponse({"ok": True})

    return _render_worktime_panel(
        request,
        personal_only=personal_only,
        month_start=month_start,
        success_message="Табель сохранен.",
    )
