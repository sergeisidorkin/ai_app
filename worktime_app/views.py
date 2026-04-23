import csv
import io
import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from policy_app.models import ADMIN_GROUP
from projects_app.models import Performer, ProjectRegistration
from proposals_app.models import ProposalRegistration

from .forms import PersonalWorktimeWeekAssignmentForm
from .models import PersonalWorktimeWeekAssignment, WorktimeAssignment, WorktimeEntry
from .services import (
    ensure_personal_week_assignment,
    is_worktime_eligible_employee,
    resolve_employee_and_name,
)

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
WORKTIME_CSV_MODE_ERROR = "Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам."
WORKTIME_CSV_ADMIN_ERROR = "Загрузка и скачивание CSV доступны только пользователям с ролью Администратор."
WORKTIME_CSV_BASE_HEADERS = ("Сотрудник", "Проект", "Тип", "Название")


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


def _resolve_general_worktime_request_state(request):
    scale = _resolve_scale(request.POST.get("scale") or request.GET.get("scale"))
    breakdown = _resolve_breakdown(request.POST.get("breakdown") or request.GET.get("breakdown"))
    period_start = _resolve_general_period(
        request.POST.get("period")
        or request.POST.get("month")
        or request.GET.get("period")
        or request.GET.get("month"),
        scale,
    )
    return scale, breakdown, period_start


def _worktime_csv_controls_enabled(scale, breakdown):
    return _resolve_scale(scale) == "month" and _resolve_breakdown(breakdown) == "employees"


def _general_worktime_period_data(user, month_start, *, scale="month", breakdown="employees"):
    if scale == "year":
        visible_days = _year_months(month_start)
    else:
        visible_days = _month_days(month_start)
    range_start, range_end = _visible_period_bounds(month_start, scale)
    assignments = _visible_assignments_for_period(
        user,
        personal_only=False,
        visible_days=visible_days,
        range_start=range_start,
        range_end=range_end,
        breakdown=breakdown,
    )
    return visible_days, range_start, range_end, assignments


def _normalize_worktime_csv_text(value):
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _worktime_csv_headers(month_days):
    return [*WORKTIME_CSV_BASE_HEADERS, *[str(day.day) for day in month_days]]


def _worktime_csv_row_descriptor(assignment):
    employee_name = assignment.display_executor_name or assignment.executor_name or ""
    if assignment.has_linked_registry_row:
        return {
            "employee_name": employee_name,
            "project_code": assignment.display_project_code or "",
            "type_label": assignment.display_type_label or "",
            "name_label": assignment.display_project_name or "",
        }
    return {
        "employee_name": employee_name,
        "project_code": "",
        "type_label": "",
        "name_label": assignment.display_manual_label or "",
    }


def _worktime_csv_row_key(employee_name, project_code, type_label, name_label):
    return tuple(
        _normalize_worktime_csv_text(value).casefold()
        for value in (employee_name, project_code, type_label, name_label)
    )


def _worktime_csv_assignment_key(assignment):
    descriptor = _worktime_csv_row_descriptor(assignment)
    return _worktime_csv_row_key(
        descriptor["employee_name"],
        descriptor["project_code"],
        descriptor["type_label"],
        descriptor["name_label"],
    )


def _build_worktime_csv_assignment_index(assignments):
    index = {}
    duplicate_keys = set()
    for assignment in assignments:
        row_key = _worktime_csv_assignment_key(assignment)
        if row_key in index:
            duplicate_keys.add(row_key)
            continue
        index[row_key] = assignment
    for row_key in duplicate_keys:
        index.pop(row_key, None)
    return index, duplicate_keys


def _worktime_csv_project_key(project_code, type_label, name_label):
    return tuple(
        _normalize_worktime_csv_text(value).casefold()
        for value in (project_code, type_label, name_label)
    )


def _project_registration_csv_descriptor(registration):
    return {
        "project_code": getattr(registration, "short_uid", "") or "—",
        "type_label": getattr(registration, "type_short_display", "") or "—",
        "name_label": getattr(registration, "name", "") or "—",
    }


def _build_worktime_csv_project_index():
    projects_by_code = {}
    projects_by_key = {}
    duplicate_project_keys = set()
    registrations = (
        ProjectRegistration.objects
        .select_related("type")
        .order_by("id")
    )
    for registration in registrations:
        descriptor = _project_registration_csv_descriptor(registration)
        code_key = _normalize_worktime_csv_text(descriptor["project_code"]).casefold()
        if code_key:
            projects_by_code[code_key] = registration
        project_key = _worktime_csv_project_key(
            descriptor["project_code"],
            descriptor["type_label"],
            descriptor["name_label"],
        )
        if project_key in projects_by_key:
            duplicate_project_keys.add(project_key)
            continue
        projects_by_key[project_key] = registration
    for project_key in duplicate_project_keys:
        projects_by_key.pop(project_key, None)
    return projects_by_code, projects_by_key, duplicate_project_keys


def _resolve_worktime_csv_project_registration(project_code, type_label, name_label, *, projects_by_code, projects_by_key, duplicate_project_keys):
    code_key = _normalize_worktime_csv_text(project_code).casefold()
    if code_key:
        registration = projects_by_code.get(code_key)
        if registration is not None:
            return registration
    project_key = _worktime_csv_project_key(project_code, type_label, name_label)
    if project_key in duplicate_project_keys:
        raise forms.ValidationError("проект определен неоднозначно.")
    return projects_by_key.get(project_key)


def _find_or_create_worktime_csv_assignment(
    *,
    employee_name,
    project_code,
    type_label,
    name_label,
    week_starts,
    row_key,
    assignments_by_key,
    projects_by_code,
    projects_by_key,
    duplicate_project_keys,
):
    assignment = assignments_by_key.get(row_key)
    if assignment is not None:
        return assignment, False

    if not week_starts:
        return None, False

    normalized_name, employee = resolve_employee_and_name(executor_name=employee_name)
    if employee is None or not normalized_name or not is_worktime_eligible_employee(employee):
        raise forms.ValidationError(f'сотрудник "{employee_name}" не найден среди штатных сотрудников.')

    registration = _resolve_worktime_csv_project_registration(
        project_code,
        type_label,
        name_label,
        projects_by_code=projects_by_code,
        projects_by_key=projects_by_key,
        duplicate_project_keys=duplicate_project_keys,
    )
    if registration is None:
        raise forms.ValidationError(
            f'проект "{project_code or name_label or "без названия"}" не найден среди существующих проектов.'
        )

    assignment, _ = ensure_personal_week_assignment(
        registration=registration,
        employee=employee,
        week_start=week_starts[0],
        record_type=WorktimeAssignment.RecordType.PROJECT,
    )
    if assignment is None:
        raise forms.ValidationError("не удалось создать строку табеля для проекта и сотрудника.")

    for week_start in week_starts[1:]:
        PersonalWorktimeWeekAssignment.objects.get_or_create(
            assignment=assignment,
            week_start=week_start,
        )

    assignments_by_key[row_key] = assignment
    assignments_by_key[_worktime_csv_assignment_key(assignment)] = assignment
    return assignment, True


def _read_uploaded_csv_rows(csv_file):
    if not csv_file:
        raise forms.ValidationError("Файл не выбран.")
    if not csv_file.name.lower().endswith(".csv"):
        raise forms.ValidationError("Допустимы только файлы CSV.")
    raw_bytes = csv_file.read()
    raw_text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            raw_text = raw_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    if raw_text is None:
        raise forms.ValidationError("Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251).")
    reader = csv.reader(io.StringIO(raw_text), delimiter=";")
    rows = list(reader)
    if rows and len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw_text), delimiter=",")
        rows = list(reader)
    if not rows:
        raise forms.ValidationError("Файл пуст.")
    if len(rows) < 2:
        raise forms.ValidationError("Файл должен содержать заголовок и хотя бы одну строку данных.")
    return rows


def _validate_worktime_csv_header(header, month_days):
    expected_header = _worktime_csv_headers(month_days)
    normalized_header = list(header or [])
    while normalized_header and not _normalize_worktime_csv_text(normalized_header[-1]):
        normalized_header.pop()
    normalized_header = [_normalize_worktime_csv_text(cell) for cell in normalized_header]
    if normalized_header != expected_header:
        raise forms.ValidationError(
            "CSV должен содержать колонки: "
            + ", ".join(expected_header)
            + "."
        )


def _normalize_worktime_csv_row(row, expected_length):
    normalized_row = list(row or [])
    if len(normalized_row) < expected_length:
        normalized_row.extend([""] * (expected_length - len(normalized_row)))
        return normalized_row
    if len(normalized_row) > expected_length:
        extra_cells = normalized_row[expected_length:]
        if any(_normalize_worktime_csv_text(cell) for cell in extra_cells):
            raise forms.ValidationError("Строка содержит лишние столбцы.")
        return normalized_row[:expected_length]
    return normalized_row


def _parse_worktime_csv_hours(raw_value, work_day, *, row_number):
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return None
    try:
        hours = int(raw_text)
    except (TypeError, ValueError):
        raise forms.ValidationError(
            f"Строка {row_number}: значение за {work_day.strftime('%d.%m.%Y')} должно быть целым числом."
        )
    if hours < 0 or hours > MAX_HOURS_PER_DAY:
        raise forms.ValidationError(
            f"Строка {row_number}: количество часов за {work_day.strftime('%d.%m.%Y')} должно быть в диапазоне от 0 до {MAX_HOURS_PER_DAY}."
        )
    return hours


def _parse_worktime_csv_row_values(month_days, raw_values, *, row_number):
    return {
        work_day: _parse_worktime_csv_hours(cell_value, work_day, row_number=row_number)
        for work_day, cell_value in zip(month_days, raw_values)
    }


def _worktime_csv_week_starts(day_values):
    return sorted({
        _start_of_week(work_day)
        for work_day, hours in (day_values or {}).items()
        if hours is not None
    })


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


def _has_worktime_csv_access(user):
    employee = getattr(user, "employee_profile", None)
    return _has_worktime_access(user) and getattr(employee, "role", "") == ADMIN_GROUP


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
    csv_controls_enabled = (
        (not personal_only)
        and _has_worktime_csv_access(user)
        and _worktime_csv_controls_enabled(general_scale, breakdown_value)
    )
    csv_controls_visible = (not personal_only) and _has_worktime_csv_access(user)

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
        "worktime_csv_controls_visible": csv_controls_visible,
        "worktime_csv_controls_enabled": csv_controls_enabled,
        "worktime_csv_upload_url": reverse("worktime_csv_upload") if not personal_only else "",
        "worktime_csv_download_url": reverse("worktime_csv_download") if not personal_only else "",
        "worktime_csv_disabled_hint": WORKTIME_CSV_MODE_ERROR,
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


def _sync_worktime_entries(parsed_values, *, assignment_ids, range_start, range_end):
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

    return {
        "created": len(to_create),
        "updated": len(to_update),
        "deleted": len(to_delete_ids),
    }


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
@require_http_methods(["POST"])
def worktime_csv_upload(request):
    if not _has_worktime_access(request.user):
        return JsonResponse({"ok": False, "error": WORKTIME_ACCESS_ERROR}, status=403)
    if not _has_worktime_csv_access(request.user):
        return JsonResponse({"ok": False, "error": WORKTIME_CSV_ADMIN_ERROR}, status=403)

    scale, breakdown, period_start = _resolve_general_worktime_request_state(request)
    if not _worktime_csv_controls_enabled(scale, breakdown):
        return JsonResponse({"ok": False, "error": WORKTIME_CSV_MODE_ERROR}, status=400)

    try:
        rows = _read_uploaded_csv_rows(request.FILES.get("csv_file"))
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    month_days, range_start, range_end, assignments = _general_worktime_period_data(
        request.user,
        period_start,
        scale=scale,
        breakdown=breakdown,
    )
    try:
        _validate_worktime_csv_header(rows[0], month_days)
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    assignments_by_key, duplicate_keys = _build_worktime_csv_assignment_index(assignments)
    projects_by_code, projects_by_key, duplicate_project_keys = _build_worktime_csv_project_index()
    expected_row_length = len(_worktime_csv_headers(month_days))
    warnings = []
    parsed_values = {}
    touched_assignment_ids = []
    touched_keys = set()
    created_assignments_count = 0

    for row_number, raw_row in enumerate(rows[1:], start=2):
        if not any(_normalize_worktime_csv_text(cell) for cell in raw_row):
            continue
        try:
            row = _normalize_worktime_csv_row(raw_row, expected_row_length)
        except forms.ValidationError as exc:
            warnings.append(f"Строка {row_number}: {exc.message}")
            continue

        employee_name, project_code, type_label, name_label = row[:4]
        row_key = _worktime_csv_row_key(employee_name, project_code, type_label, name_label)
        row_label = _normalize_worktime_csv_text(name_label) or _normalize_worktime_csv_text(project_code) or "без названия"

        if row_key in touched_keys:
            warnings.append(f'Строка {row_number}: дублирует запись табеля сотрудника "{employee_name}" ({row_label}).')
            continue
        if row_key in duplicate_keys:
            warnings.append(f'Строка {row_number}: строка табеля для сотрудника "{employee_name}" определена неоднозначно.')
            continue

        try:
            row_day_values = _parse_worktime_csv_row_values(
                month_days,
                row[4:],
                row_number=row_number,
            )
        except forms.ValidationError as exc:
            warnings.append(exc.message)
            continue

        week_starts = _worktime_csv_week_starts(row_day_values)
        try:
            assignment, assignment_created = _find_or_create_worktime_csv_assignment(
                employee_name=employee_name,
                project_code=project_code,
                type_label=type_label,
                name_label=name_label,
                week_starts=week_starts,
                row_key=row_key,
                assignments_by_key=assignments_by_key,
                projects_by_code=projects_by_code,
                projects_by_key=projects_by_key,
                duplicate_project_keys=duplicate_project_keys,
            )
        except forms.ValidationError as exc:
            warnings.append(f"Строка {row_number}: {exc.message}")
            continue
        if assignment is None:
            continue
        if assignment_created:
            created_assignments_count += 1

        row_payload = {
            (assignment.pk, work_day): hours
            for work_day, hours in row_day_values.items()
        }

        touched_keys.add(row_key)
        touched_assignment_ids.append(assignment.pk)
        parsed_values.update(row_payload)

    if not touched_assignment_ids:
        payload = {"ok": False, "error": "Не удалось обработать ни одной строки табеля."}
        if warnings:
            payload["warnings"] = warnings[:50]
        return JsonResponse(payload, status=400)

    sync_result = _sync_worktime_entries(
        parsed_values,
        assignment_ids=touched_assignment_ids,
        range_start=range_start,
        range_end=range_end,
    )
    result = {
        "ok": True,
        "created": sync_result["created"],
        "updated": sync_result["updated"],
        "deleted": sync_result["deleted"],
    }
    if created_assignments_count:
        result["created_assignments"] = created_assignments_count
    if warnings:
        result["warnings"] = warnings[:50]
    return JsonResponse(result)


@login_required
@require_http_methods(["GET"])
def worktime_csv_download(request):
    if not _has_worktime_access(request.user):
        return HttpResponseForbidden(WORKTIME_ACCESS_ERROR)
    if not _has_worktime_csv_access(request.user):
        return HttpResponseForbidden(WORKTIME_CSV_ADMIN_ERROR)

    scale, breakdown, period_start = _resolve_general_worktime_request_state(request)
    if not _worktime_csv_controls_enabled(scale, breakdown):
        return HttpResponseBadRequest(WORKTIME_CSV_MODE_ERROR)

    month_days, range_start, range_end, assignments = _general_worktime_period_data(
        request.user,
        period_start,
        scale=scale,
        breakdown=breakdown,
    )
    entries = (
        WorktimeEntry.objects
        .filter(assignment_id__in=[assignment.pk for assignment in assignments], work_date__range=(range_start, range_end))
        .only("assignment_id", "work_date", "hours")
    )
    entry_map = _build_entry_map(entries, scale=scale)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="worktime-{period_start:%Y-%m}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(_worktime_csv_headers(month_days))

    for assignment in assignments:
        descriptor = _worktime_csv_row_descriptor(assignment)
        day_values = entry_map.get(assignment.pk, {})
        writer.writerow(
            [
                descriptor["employee_name"],
                descriptor["project_code"],
                descriptor["type_label"],
                descriptor["name_label"],
                *[
                    "" if day_values.get(work_day) is None else day_values.get(work_day)
                    for work_day in month_days
                ],
            ]
        )

    return response


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
    _sync_worktime_entries(
        parsed_values,
        assignment_ids=assignment_ids,
        range_start=range_start,
        range_end=range_end,
    )

    if autosave:
        return JsonResponse({"ok": True})

    return _render_worktime_panel(
        request,
        personal_only=personal_only,
        month_start=month_start,
        success_message="Табель сохранен.",
    )
