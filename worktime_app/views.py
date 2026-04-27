import csv
import hashlib
import io
import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from classifiers_app.models import OKSMCountry, ProductionCalendarDay
from group_app.models import GroupMember
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
MAX_HOURS_PER_DAY = Decimal("24")
WORKTIME_HOURS_QUANT = Decimal("0.01")
ZERO_DECIMAL = Decimal("0")
HUNDRED_DECIMAL = Decimal("100")
REGULAR_WORKDAY_HOURS = Decimal("8")
SHORTENED_WORKDAY_HOURS = Decimal("7")
PERSONAL_WEEK_LIMIT_WEEKS = 2
PERSONAL_WEEK_LIMIT_ERROR = "Нельзя выбрать слишком далекую будущую неделю. Доступны текущая неделя и только две следующие."
WORKTIME_ACCESS_ERROR = 'Табель доступен только штатным сотрудникам с правами staff. Пользователи с трудоустройством "Внештатный сотрудник" не допускаются.'
WORKTIME_CSV_MODE_ERROR = "Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам."
WORKTIME_CSV_ADMIN_ERROR = "Загрузка и скачивание CSV доступны только пользователям с ролью Администратор."
WORKTIME_CSV_BASE_HEADERS = ("Сотрудник", "Проект", "Тип", "Название")
WORKTIME_COMPANY_FILTER_ALL = "__all__"
WORKTIME_COMPOSITION_CATEGORIES = (
    {
        "key": "downtime",
        "label": "Простой",
        "color": "#9474c5",
    },
    {
        "key": "absence",
        "label": "Отсутствие",
        "color": "#8b95a1",
    },
    {
        "key": "vacation",
        "label": "Отпуск",
        "color": "#e39bc9",
    },
    {
        "key": "development",
        "label": "Развитие",
        "color": "#559e39",
    },
    {
        "key": "work",
        "label": "Рабочие процессы",
        "color": "#075d94",
    },
)
WORKTIME_COMPOSITION_CATEGORY_BY_KEY = {
    category["key"]: category for category in WORKTIME_COMPOSITION_CATEGORIES
}
WORKTIME_NON_WORKING_DAY_BLOCKED_RECORD_TYPES = {
    WorktimeAssignment.RecordType.VACATION,
    WorktimeAssignment.RecordType.OTHER_ABSENCE,
    WorktimeAssignment.RecordType.SICK_LEAVE,
    WorktimeAssignment.RecordType.TIME_OFF,
}
WORKTIME_DAILY_HISTOGRAM_SEGMENTS = (
    {
        "key": "downtime",
        "record_type": WorktimeAssignment.RecordType.DOWNTIME,
        "label": "Простой",
        "category_key": "downtime",
        "category_label": "Простой",
        "color": "#a78ed5",
    },
    {
        "key": "other_absence",
        "record_type": WorktimeAssignment.RecordType.OTHER_ABSENCE,
        "label": "Прочее отсутствие",
        "category_key": "absence",
        "category_label": "Отсутствие",
        "color": "#b8c2cc",
    },
    {
        "key": "sick_leave",
        "record_type": WorktimeAssignment.RecordType.SICK_LEAVE,
        "label": "Больничный",
        "category_key": "absence",
        "category_label": "Отсутствие",
        "color": "#cbd3db",
    },
    {
        "key": "time_off",
        "record_type": WorktimeAssignment.RecordType.TIME_OFF,
        "label": "Отгул",
        "category_key": "absence",
        "category_label": "Отсутствие",
        "color": "#d9e0e6",
    },
    {
        "key": "vacation",
        "record_type": WorktimeAssignment.RecordType.VACATION,
        "label": "Отпуск",
        "category_key": "vacation",
        "category_label": "Отпуск",
        "color": "#f5c9e1",
    },
    {
        "key": "strategic_development",
        "record_type": WorktimeAssignment.RecordType.STRATEGIC_DEVELOPMENT,
        "label": "Стратегическое развитие",
        "category_key": "development",
        "category_label": "Развитие",
        "color": "#c2efab",
    },
    {
        "key": "business_development",
        "record_type": WorktimeAssignment.RecordType.BUSINESS_DEVELOPMENT,
        "label": "Бизнес-девелопмент",
        "category_key": "development",
        "category_label": "Развитие",
        "color": "#89d463",
    },
    {
        "key": "tkp",
        "record_type": WorktimeAssignment.RecordType.TKP,
        "label": "ТКП",
        "category_key": "development",
        "category_label": "Развитие",
        "color": "#5fb142",
    },
    {
        "key": "administration",
        "record_type": WorktimeAssignment.RecordType.ADMINISTRATION,
        "label": "Администрирование",
        "category_key": "work",
        "category_label": "Рабочие процессы",
        "color": "#4f95bf",
    },
    {
        "key": "project",
        "record_type": WorktimeAssignment.RecordType.PROJECT,
        "label": "Проект",
        "category_key": "work",
        "category_label": "Рабочие процессы",
        "color": "#2a74a1",
    },
)
WORKTIME_DAILY_HISTOGRAM_SEGMENT_BY_KEY = {
    segment["key"]: segment for segment in WORKTIME_DAILY_HISTOGRAM_SEGMENTS
}
WORKTIME_DAILY_HISTOGRAM_SEGMENT_KEY_BY_RECORD_TYPE = {
    segment["record_type"]: segment["key"] for segment in WORKTIME_DAILY_HISTOGRAM_SEGMENTS
}


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


def _normalize_worktime_company_text(value):
    return " ".join(str(value or "").split()).strip()


def _worktime_company_key(value):
    return _normalize_worktime_company_text(value).casefold()


def _parse_worktime_company_filter_ids(raw_value):
    raw_text = str(raw_value or "").strip()
    if not raw_text or raw_text == WORKTIME_COMPANY_FILTER_ALL:
        return []
    parsed_ids = []
    seen_ids = set()
    for part in raw_text.split(","):
        try:
            company_id = int(str(part).strip())
        except (TypeError, ValueError):
            continue
        if company_id <= 0 or company_id in seen_ids:
            continue
        seen_ids.add(company_id)
        parsed_ids.append(company_id)
    return parsed_ids


def _resolve_worktime_company_filter(raw_value):
    selected_ids = _parse_worktime_company_filter_ids(raw_value)
    if not selected_ids:
        return WORKTIME_COMPANY_FILTER_ALL, []

    members_by_id = {
        member.pk: member
        for member in GroupMember.objects.filter(pk__in=selected_ids).exclude(short_name="")
    }
    valid_ids = []
    selected_names = []
    for company_id in selected_ids:
        member = members_by_id.get(company_id)
        if member is None:
            continue
        short_name = _normalize_worktime_company_text(member.short_name)
        if not short_name:
            continue
        valid_ids.append(str(company_id))
        selected_names.append(short_name)

    if not valid_ids:
        return WORKTIME_COMPANY_FILTER_ALL, []
    return ",".join(valid_ids), selected_names


def _production_calendar_country_for_group_member(group_member):
    if group_member is None:
        return None

    country_code = str(group_member.country_code or "").strip()
    if country_code:
        country = OKSMCountry.objects.filter(code=country_code).first()
        if country is not None:
            return country

    country_alpha2 = str(group_member.country_alpha2 or "").strip()
    if country_alpha2:
        country = OKSMCountry.objects.filter(alpha2__iexact=country_alpha2).first()
        if country is not None:
            return country

    country_name = str(group_member.country_name or "").strip()
    if country_name:
        return OKSMCountry.objects.filter(short_name__iexact=country_name).first()

    return None


def _production_calendar_country_for_employee(employee):
    employment = _normalize_worktime_company_text(getattr(employee, "employment", ""))
    if not employment:
        return None

    group_member = GroupMember.objects.filter(short_name__iexact=employment).first()
    return _production_calendar_country_for_group_member(group_member)


def _production_calendar_country_for_company_filter(company_filter_value, assignments):
    selected_ids = _parse_worktime_company_filter_ids(company_filter_value)
    countries_by_pk = {}
    if selected_ids:
        members = GroupMember.objects.filter(pk__in=selected_ids)
    else:
        company_names = {
            _normalize_worktime_company_text(getattr(getattr(assignment, "employee", None), "employment", ""))
            for assignment in assignments or []
        }
        company_names.discard("")
        if not company_names:
            return None
        members = GroupMember.objects.filter(short_name__in=company_names)

    for member in members:
        country = _production_calendar_country_for_group_member(member)
        if country is not None:
            countries_by_pk[country.pk] = country
    return next(iter(countries_by_pk.values())) if len(countries_by_pk) == 1 else None


def _production_calendar_marks_for_user(user, start_date, end_date):
    employee = getattr(user, "employee_profile", None)
    country = _production_calendar_country_for_employee(employee)
    if country is None:
        return {}

    lookup_start = start_date - timedelta(days=7)
    lookup_end = end_date + timedelta(days=7)
    calendar_days = list(
        ProductionCalendarDay.objects
        .filter(country=country, date__range=(lookup_start, lookup_end))
        .only("date", "is_working_day", "is_holiday", "is_shortened_day")
        .order_by("date")
    )
    calendar_day_by_date = {item.date: item for item in calendar_days}

    def non_working_block_has_holiday(day):
        cursor = day
        while True:
            item = calendar_day_by_date.get(cursor)
            if item is None or item.is_working_day:
                break
            if item.is_holiday:
                return True
            cursor -= timedelta(days=1)
        cursor = day + timedelta(days=1)
        while True:
            item = calendar_day_by_date.get(cursor)
            if item is None or item.is_working_day:
                break
            if item.is_holiday:
                return True
            cursor += timedelta(days=1)
        return False

    marks = {}
    for item in calendar_days:
        if item.date < start_date or item.date > end_date:
            continue
        if item.is_holiday or (not item.is_working_day and non_working_block_has_holiday(item.date)):
            marks[item.date.isoformat()] = "holiday"
        elif not item.is_working_day:
            marks[item.date.isoformat()] = "weekend"
        elif item.is_shortened_day:
            marks[item.date.isoformat()] = "shortened"
    return marks


def _production_calendar_marks_for_year(user, year):
    return _production_calendar_marks_for_user(user, date(year, 1, 1), date(year, 12, 31))


def _fallback_working_hours_for_day(work_day):
    return REGULAR_WORKDAY_HOURS if work_day.weekday() < 5 else ZERO_DECIMAL


def _production_calendar_working_hours_for_country(country, visible_days):
    visible_days = list(visible_days or [])
    if not visible_days:
        return {}

    fallback_hours = {work_day: _fallback_working_hours_for_day(work_day) for work_day in visible_days}
    if country is None:
        return fallback_hours

    calendar_days = {
        item.date: item
        for item in (
            ProductionCalendarDay.objects
            .filter(country=country, date__in=visible_days)
            .only("date", "is_working_day", "is_holiday", "is_shortened_day", "working_hours")
        )
    }
    working_hours = {}
    for work_day in visible_days:
        item = calendar_days.get(work_day)
        if item is None:
            working_hours[work_day] = fallback_hours[work_day]
        elif item.is_holiday or not item.is_working_day:
            working_hours[work_day] = ZERO_DECIMAL
        elif item.is_shortened_day:
            working_hours[work_day] = _coerce_worktime_decimal(item.working_hours or SHORTENED_WORKDAY_HOURS)
        else:
            working_hours[work_day] = _coerce_worktime_decimal(item.working_hours or REGULAR_WORKDAY_HOURS)
    return working_hours


def _production_calendar_working_hours_for_user(user, visible_days):
    employee = getattr(user, "employee_profile", None)
    country = _production_calendar_country_for_employee(employee)
    return _production_calendar_working_hours_for_country(country, visible_days)


def _production_calendar_working_hours_for_employee(employee, visible_days):
    country = _production_calendar_country_for_employee(employee)
    if country is None:
        return None
    return _production_calendar_working_hours_for_country(country, visible_days)


def _production_calendar_working_hours_for_company_filter(company_filter_value, assignments, visible_days):
    country = _production_calendar_country_for_company_filter(company_filter_value, assignments)
    return _production_calendar_working_hours_for_country(country, visible_days)


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


def _week_starts_for_period(range_start, range_end):
    if range_start is None or range_end is None:
        return []
    week_start = _start_of_week(range_start)
    week_starts = []
    while week_start <= range_end:
        week_starts.append(week_start)
        week_start += timedelta(days=7)
    return week_starts


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


def _general_worktime_period_data(user, month_start, *, scale="month", breakdown="employees", company_names=None):
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
        company_names=company_names,
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


def _proposal_registration_csv_descriptor(registration):
    type_value = getattr(registration, "type", None)
    return {
        "project_code": getattr(registration, "short_uid", "") or "—",
        "type_label": (getattr(type_value, "short_name", "") or str(type_value)) if type_value is not None else "—",
        "name_label": getattr(registration, "name", "") or "—",
    }


def _build_worktime_csv_project_index():
    projects_by_code = {}
    projects_by_key = {}
    duplicate_project_keys = set()
    registrations = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related("product_links__product")
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


def _build_worktime_csv_proposal_index():
    proposals_by_code = {}
    proposals_by_key = {}
    duplicate_proposal_keys = set()
    registrations = (
        ProposalRegistration.objects
        .select_related("type")
        .order_by("id")
    )
    for registration in registrations:
        descriptor = _proposal_registration_csv_descriptor(registration)
        code_key = _normalize_worktime_csv_text(descriptor["project_code"]).casefold()
        if code_key:
            proposals_by_code[code_key] = registration
        proposal_key = _worktime_csv_project_key(
            descriptor["project_code"],
            descriptor["type_label"],
            descriptor["name_label"],
        )
        if proposal_key in proposals_by_key:
            duplicate_proposal_keys.add(proposal_key)
            continue
        proposals_by_key[proposal_key] = registration
    for proposal_key in duplicate_proposal_keys:
        proposals_by_key.pop(proposal_key, None)
    return proposals_by_code, proposals_by_key, duplicate_proposal_keys


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


def _resolve_worktime_csv_proposal_registration(project_code, type_label, name_label, *, proposals_by_code, proposals_by_key, duplicate_proposal_keys):
    code_key = _normalize_worktime_csv_text(project_code).casefold()
    if code_key:
        registration = proposals_by_code.get(code_key)
        if registration is not None:
            return registration
    proposal_key = _worktime_csv_project_key(project_code, type_label, name_label)
    if proposal_key in duplicate_proposal_keys:
        raise forms.ValidationError("ТКП определено неоднозначно.")
    return proposals_by_key.get(proposal_key)


def _build_worktime_csv_manual_record_type_index():
    index = {}
    for value, label in WorktimeAssignment.RecordType.choices:
        if value in {WorktimeAssignment.RecordType.PROJECT, WorktimeAssignment.RecordType.TKP}:
            continue
        index[_normalize_worktime_csv_text(label).casefold()] = value
        index.setdefault(_normalize_worktime_csv_text(value).casefold(), value)
    return index


def _resolve_worktime_csv_manual_record_type(project_code, type_label, name_label, *, manual_record_types_by_label):
    for candidate in (name_label, project_code, type_label):
        normalized = _normalize_worktime_csv_text(candidate).casefold()
        if not normalized:
            continue
        record_type = manual_record_types_by_label.get(normalized)
        if record_type:
            return record_type
    return None


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
    proposals_by_code,
    proposals_by_key,
    duplicate_proposal_keys,
    manual_record_types_by_label,
):
    assignment = assignments_by_key.get(row_key)
    if assignment is not None:
        _ensure_worktime_csv_week_links(assignment, week_starts)
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
    proposal_registration = None
    manual_record_type = None
    if registration is not None:
        assignment, _ = ensure_personal_week_assignment(
            registration=registration,
            employee=employee,
            week_start=week_starts[0],
            record_type=WorktimeAssignment.RecordType.PROJECT,
        )
    else:
        proposal_registration = _resolve_worktime_csv_proposal_registration(
            project_code,
            type_label,
            name_label,
            proposals_by_code=proposals_by_code,
            proposals_by_key=proposals_by_key,
            duplicate_proposal_keys=duplicate_proposal_keys,
        )
        if proposal_registration is not None:
            assignment, _ = ensure_personal_week_assignment(
                registration=None,
                proposal_registration=proposal_registration,
                employee=employee,
                week_start=week_starts[0],
                record_type=WorktimeAssignment.RecordType.TKP,
            )
        else:
            manual_record_type = _resolve_worktime_csv_manual_record_type(
                project_code,
                type_label,
                name_label,
                manual_record_types_by_label=manual_record_types_by_label,
            )
            if manual_record_type is None:
                raise forms.ValidationError(
                    f'запись "{project_code or name_label or type_label or "без названия"}" '
                    "не найдена среди существующих проектов, ТКП или видов записей."
                )
            assignment, _ = ensure_personal_week_assignment(
                registration=None,
                proposal_registration=None,
                employee=employee,
                week_start=week_starts[0],
                record_type=manual_record_type,
            )
    if assignment is None:
        raise forms.ValidationError("не удалось создать строку табеля для сотрудника.")

    _ensure_worktime_csv_week_links(assignment, week_starts)

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
    return _parse_worktime_hours_value(
        raw_value,
        work_day,
        invalid_message=f"Строка {row_number}: значение за {work_day.strftime('%d.%m.%Y')} должно быть числом.",
        precision_message=(
            f"Строка {row_number}: значение за {work_day.strftime('%d.%m.%Y')} "
            "должно быть числом с не более чем двумя знаками после запятой."
        ),
        range_message=(
            f"Строка {row_number}: количество часов за {work_day.strftime('%d.%m.%Y')} "
            f"должно быть в диапазоне от 0 до {MAX_HOURS_PER_DAY}."
        ),
    )


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


def _ensure_worktime_csv_week_links(assignment, week_starts):
    if assignment is None or assignment.source_type != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK:
        return
    for week_start in week_starts or []:
        PersonalWorktimeWeekAssignment.objects.get_or_create(
            assignment=assignment,
            week_start=week_start,
        )


def _parse_worktime_hours_value(raw_value, work_day, *, invalid_message, precision_message, range_message):
    raw_text = str(raw_value or "").strip().replace(",", ".")
    if not raw_text:
        return None
    try:
        hours = Decimal(raw_text)
    except (InvalidOperation, TypeError, ValueError):
        raise forms.ValidationError(invalid_message)
    if not hours.is_finite():
        raise forms.ValidationError(invalid_message)
    try:
        normalized_hours = hours.quantize(WORKTIME_HOURS_QUANT)
    except InvalidOperation:
        raise forms.ValidationError(invalid_message)
    if normalized_hours != hours:
        raise forms.ValidationError(precision_message)
    if normalized_hours < 0 or normalized_hours > MAX_HOURS_PER_DAY:
        raise forms.ValidationError(range_message)
    return normalized_hours


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


def _resolve_assignment_employee(assignment):
    employee = getattr(assignment, "employee", None)
    if employee is None:
        employee = Performer.resolve_employee_from_executor(getattr(assignment, "executor_name", ""))
        if employee is not None:
            assignment.employee = employee
    return employee


def _assignment_is_worktime_visible(assignment):
    employee = _resolve_assignment_employee(assignment)
    return is_worktime_eligible_employee(employee)


def _assignment_matches_worktime_company_filter(assignment, selected_company_keys):
    if not selected_company_keys:
        return True
    employee = _resolve_assignment_employee(assignment)
    return _worktime_company_key(getattr(employee, "employment", "")) in selected_company_keys


def _personal_assignment_filters(user):
    employee, employee_name = _current_employee_and_name(user)
    filters = Q(pk__in=[])
    if employee is not None:
        filters = Q(employee__user=user)
    if employee_name:
        filters |= Q(employee__isnull=True, executor_name=employee_name)
    return filters, employee, employee_name


def _personal_week_link_queryset(user, week_start):
    _, employee, employee_name = _personal_assignment_filters(user)
    queryset = PersonalWorktimeWeekAssignment.objects.select_related(
        "assignment",
        "assignment__registration",
        "assignment__registration__type",
        "assignment__proposal_registration",
        "assignment__proposal_registration__type",
        "assignment__employee",
        "assignment__employee__user",
        "assignment__performer",
    ).filter(week_start=week_start)
    if employee is not None:
        return queryset.filter(
            Q(assignment__employee__user=user)
            | Q(assignment__employee__isnull=True, assignment__executor_name=employee_name)
        )
    if employee_name:
        return queryset.filter(
            assignment__employee__isnull=True,
            assignment__executor_name=employee_name,
        )
    return queryset.none()


def _personal_assignment_order_sort_key(assignment):
    if getattr(assignment, "record_type", "") == WorktimeAssignment.RecordType.DOWNTIME:
        return (2, assignment.id)
    week_position = getattr(assignment, "_personal_week_position", None)
    if week_position:
        return (0, int(week_position), assignment.id)
    return (1,) + _assignment_sort_key(assignment)


def _ensure_personal_downtime_assignment(user, week_start):
    employee, employee_name = _current_employee_and_name(user)
    if employee is None or not employee_name or week_start is None:
        return None
    assignment, _ = ensure_personal_week_assignment(
        registration=None,
        proposal_registration=None,
        employee=employee,
        week_start=week_start,
        record_type=WorktimeAssignment.RecordType.DOWNTIME,
    )
    return assignment


def _visible_personal_assignments_for_week(user, week_start):
    _ensure_personal_downtime_assignment(user, week_start)
    week_links = list(_personal_week_link_queryset(user, week_start))
    week_link_by_assignment_id = {link.assignment_id: link for link in week_links}
    hidden_assignment_ids = {
        link.assignment_id
        for link in week_links
        if getattr(link, "is_hidden", False)
    }
    global_assignments = _worktime_assignment_queryset(user, personal_only=True)
    manual_assignments = _personal_manual_week_assignment_queryset(user, week_start)
    combined = {}
    for assignment in global_assignments:
        if assignment.pk in hidden_assignment_ids:
            continue
        combined[assignment.pk] = assignment
    for assignment in manual_assignments:
        link = week_link_by_assignment_id.get(assignment.pk)
        if link is None or getattr(link, "is_hidden", False):
            continue
        combined[assignment.pk] = assignment
    visible_assignments = []
    for assignment in combined.values():
        link = week_link_by_assignment_id.get(assignment.pk)
        assignment._personal_week_link = link
        assignment._personal_week_position = getattr(link, "position", 0) or 0
        visible_assignments.append(assignment)
    return sorted(visible_assignments, key=_personal_assignment_order_sort_key)


def _personal_week_order_ids(user, week_start):
    return [
        assignment.pk
        for assignment in _visible_personal_assignments_for_week(user, week_start)
        if assignment.record_type != WorktimeAssignment.RecordType.DOWNTIME
    ]


def _personal_week_order_signature(ordered_assignment_ids):
    raw_order = ",".join(str(assignment_id) for assignment_id in ordered_assignment_ids)
    return hashlib.sha256(raw_order.encode("utf-8")).hexdigest()


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


def _manual_entry_visibility_filter(range_start, range_end):
    visible_filter = Q(pk__in=[])
    for week_start in _week_starts_for_period(range_start, range_end):
        week_end = week_start + timedelta(days=6)
        visible_filter |= Q(
            personal_week_links__week_start=week_start,
            personal_week_links__is_hidden=False,
            entries__work_date__range=(max(range_start, week_start), min(range_end, week_end)),
        )
    return visible_filter


def _manual_assignments_for_period(range_start, range_end):
    return (
        _base_worktime_assignment_queryset()
        .filter(
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        .filter(_manual_entry_visibility_filter(range_start, range_end))
        .distinct()
        .order_by("executor_name", "registration__number", "registration__id", "id")
    )


def _visible_manual_week_starts_for_assignments(assignments, range_start, range_end):
    manual_assignment_ids = [
        assignment.pk
        for assignment in assignments
        if assignment.source_type == WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK
    ]
    if not manual_assignment_ids:
        return {}
    week_starts = _week_starts_for_period(range_start, range_end)
    if not week_starts:
        return {}
    visible_week_starts = {}
    for assignment_id, week_start in (
        PersonalWorktimeWeekAssignment.objects
        .filter(
            assignment_id__in=manual_assignment_ids,
            week_start__in=week_starts,
            is_hidden=False,
        )
        .values_list("assignment_id", "week_start")
    ):
        visible_week_starts.setdefault(assignment_id, set()).add(week_start)
    return visible_week_starts


def _filter_entries_for_visible_manual_weeks(entries, assignments, range_start, range_end):
    manual_assignment_ids = {
        assignment.pk
        for assignment in assignments
        if assignment.source_type == WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK
    }
    if not manual_assignment_ids:
        return entries
    visible_week_starts = _visible_manual_week_starts_for_assignments(assignments, range_start, range_end)
    assignments_by_id = {assignment.pk: assignment for assignment in assignments}
    filtered_entries = []
    for entry in entries:
        assignment = assignments_by_id.get(entry.assignment_id)
        if getattr(assignment, "source_type", "") != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK:
            filtered_entries.append(entry)
            continue
        if _start_of_week(entry.work_date) in visible_week_starts.get(entry.assignment_id, set()):
            filtered_entries.append(entry)
    return filtered_entries


def _visible_assignments_for_period(
    user,
    *,
    personal_only=False,
    visible_days=None,
    week_start=None,
    range_start=None,
    range_end=None,
    breakdown="employees",
    company_names=None,
):
    if not _has_worktime_access(user):
        return []
    if personal_only:
        return [
            assignment for assignment in _visible_personal_assignments_for_week(user, week_start)
            if _assignment_is_worktime_visible(assignment)
        ]
    global_assignments = _worktime_assignment_queryset(user, personal_only=personal_only)
    manual_assignments = _manual_assignments_for_period(range_start, range_end)
    selected_company_keys = {
        _worktime_company_key(company_name)
        for company_name in (company_names or [])
        if _worktime_company_key(company_name)
    }
    return [
        assignment for assignment in _combine_assignments(
            global_assignments,
            manual_assignments,
            sort_key=lambda assignment: _assignment_breakdown_sort_key(assignment, breakdown),
        )
        if _assignment_is_worktime_visible(assignment)
        and _assignment_matches_worktime_company_filter(assignment, selected_company_keys)
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
        personal_week_links__is_hidden=False,
    ).exists()


def _delete_assignment_entries_for_week(assignment, week_start):
    if assignment is None or week_start is None:
        return 0
    range_start, range_end = _week_days(week_start)[0], _week_days(week_start)[-1]
    deleted_count, _ = WorktimeEntry.objects.filter(
        assignment=assignment,
        work_date__range=(range_start, range_end),
    ).delete()
    return deleted_count


def _build_assignment_row(assignment, visible_days, entry_map, *, breakdown="employees", non_working_days=None):
    row_total = 0
    cells = []
    day_values = entry_map.get(assignment.pk, {})
    scheduled_hours = getattr(assignment, "_worktime_scheduled_hours", {}) or {}
    is_calculated_downtime = bool(getattr(assignment, "_worktime_calculated_downtime", False))
    histogram_segment_key = _worktime_daily_histogram_segment_key(assignment)
    is_vacation_row = histogram_segment_key == "vacation"
    blocks_non_working_day_input = _worktime_blocks_non_working_day_input(assignment)
    non_working_days = set(non_working_days or [])
    hidden_downtime_zero_days = set(getattr(assignment, "_worktime_hidden_downtime_zero_days", set()) or [])
    for work_day in visible_days:
        value = day_values.get(work_day)
        if value is not None:
            row_total += value
        should_hide_downtime_zero = (
            is_calculated_downtime
            and work_day in hidden_downtime_zero_days
            and _coerce_worktime_decimal(value) <= ZERO_DECIMAL
        )
        cells.append(
            {
                "date": work_day,
                "input_name": f"hours_{assignment.pk}_{work_day:%Y%m%d}",
                "value": value,
                "scheduled_hours": scheduled_hours.get(work_day),
                "is_non_working_day": work_day in non_working_days,
                "is_vacation_non_working_day": is_vacation_row and work_day in non_working_days,
                "is_blocked_non_working_day": blocks_non_working_day_input and work_day in non_working_days,
                "hide_downtime_zero": should_hide_downtime_zero,
            }
        )
    row = {
        "assignment": assignment,
        "cells": cells,
        "total_hours": row_total,
        "sort_key": _employee_row_sort_key(assignment) if breakdown == "activities" else _assignment_sort_key(assignment),
        "daily_histogram_segment_key": histogram_segment_key,
        "is_calculated_downtime": is_calculated_downtime,
        "is_locked": is_calculated_downtime,
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


def _grouped_assignment_rows(assignments, month_days, entry_map, *, breakdown="employees", non_working_days=None):
    groups = []
    current_group = None
    current_key = None
    non_working_days = set(non_working_days or [])
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
                "vacation_column_totals": {work_day: ZERO_DECIMAL for work_day in month_days},
                "grand_total": 0,
                "sort_key": group_sort_key,
            }
            groups.append(current_group)
        row = _build_assignment_row(
            assignment,
            month_days,
            entry_map,
            breakdown=breakdown,
            non_working_days=non_working_days,
        )
        for cell in row["cells"]:
            if cell["value"] is not None:
                current_group["column_totals"][cell["date"]] += cell["value"]
                if row.get("daily_histogram_segment_key") == "vacation":
                    current_group["vacation_column_totals"][cell["date"]] += cell["value"]
        current_group["rows"].append(row)
        current_group["grand_total"] += row["total_hours"]

    for group in groups:
        group["column_cells"] = _build_summary_column_cells(
            group["column_totals"],
            group["vacation_column_totals"],
            month_days,
            non_working_days=non_working_days,
        )
        group["column_totals"] = [cell["total"] for cell in group["column_cells"]]
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


def _build_total_column_cells(column_totals, visible_days, *, non_working_days=None):
    non_working_days = set(non_working_days or [])
    return [
        {
            "date": work_day,
            "total": column_totals[index] if index < len(column_totals) else ZERO_DECIMAL,
            "is_non_working_day": work_day in non_working_days,
        }
        for index, work_day in enumerate(visible_days)
    ]


def _attach_group_histograms(groups):
    if not groups:
        return groups
    min_width_percent = Decimal("18")
    row_min_width_percent = Decimal("2")
    max_width_percent = Decimal("100")
    totals = [_coerce_worktime_decimal(group.get("grand_total", 0) or 0) for group in groups]
    min_total = min(totals)
    max_total = max(totals)
    spread = max_total - min_total
    for group in groups:
        value = _coerce_worktime_decimal(group.get("grand_total", 0) or 0)
        if value <= ZERO_DECIMAL:
            normalized = ZERO_DECIMAL
        elif spread <= 0:
            normalized = max_width_percent if max_total > 0 else min_width_percent
        else:
            normalized = min_width_percent + ((value - min_total) / spread) * (max_width_percent - min_width_percent)
        group_max_width = round(normalized, 3)
        group["histogram_width_percent"] = group_max_width
        row_totals = [_coerce_worktime_decimal(row.get("total_hours", 0) or 0) for row in group.get("rows", [])]
        if not row_totals:
            continue
        min_row_total = min(row_totals)
        max_row_total = max(row_totals)
        row_spread = max_row_total - min_row_total
        for row in group.get("rows", []):
            row_total = _coerce_worktime_decimal(row.get("total_hours", 0) or 0)
            if row_total <= ZERO_DECIMAL:
                row_normalized = ZERO_DECIMAL
            elif row_spread <= 0:
                row_normalized = group_max_width if max_row_total > 0 else row_min_width_percent
            elif max_row_total <= 0:
                row_normalized = row_min_width_percent
            else:
                row_normalized = row_min_width_percent + ((row_total - min_row_total) / row_spread) * max(
                    group_max_width - row_min_width_percent, Decimal("0")
                )
            row["histogram_width_percent"] = round(row_normalized, 3)
    return groups


def _attach_row_histograms(rows):
    if not rows:
        return rows
    min_width_percent = Decimal("18")
    max_width_percent = Decimal("100")
    totals = [_coerce_worktime_decimal(row.get("total_hours", 0) or 0) for row in rows]
    min_total = min(totals)
    max_total = max(totals)
    spread = max_total - min_total
    for row in rows:
        value = _coerce_worktime_decimal(row.get("total_hours", 0) or 0)
        if value <= ZERO_DECIMAL:
            normalized = ZERO_DECIMAL
        elif spread <= 0:
            normalized = max_width_percent if max_total > 0 else min_width_percent
        else:
            normalized = min_width_percent + ((value - min_total) / spread) * (max_width_percent - min_width_percent)
        row["histogram_width_percent"] = round(normalized, 3)
    return rows


def _coerce_worktime_decimal(value):
    if value in (None, ""):
        return ZERO_DECIMAL
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _worktime_daily_histogram_segment_key(assignment):
    if assignment.proposal_registration_id is not None:
        return "tkp"
    if assignment.registration_id is not None:
        return "project"
    return WORKTIME_DAILY_HISTOGRAM_SEGMENT_KEY_BY_RECORD_TYPE.get(getattr(assignment, "record_type", ""))


def _worktime_blocks_non_working_day_input(assignment):
    return getattr(assignment, "record_type", "") in WORKTIME_NON_WORKING_DAY_BLOCKED_RECORD_TYPES


def _format_worktime_percentage_value(value):
    decimal_value = _coerce_worktime_decimal(value)
    text = format(decimal_value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _build_worktime_conic_gradient(items):
    prepared_items = [
        {**item, "value": _coerce_worktime_decimal(item.get("value", ZERO_DECIMAL))}
        for item in (items or [])
        if _coerce_worktime_decimal(item.get("value", ZERO_DECIMAL)) > ZERO_DECIMAL
    ]
    total = sum((item["value"] for item in prepared_items), ZERO_DECIMAL)
    if total <= ZERO_DECIMAL:
        return ""
    current = ZERO_DECIMAL
    parts = []
    for item in prepared_items:
        start = (current / total) * HUNDRED_DECIMAL
        current += item["value"]
        end = (current / total) * HUNDRED_DECIMAL
        parts.append(
            f'{item["color"]} {_format_worktime_percentage_value(start)}% {_format_worktime_percentage_value(end)}%'
        )
    return f"conic-gradient({', '.join(parts)})"


def _build_worktime_composition_donut(segment_totals):
    normalized_segment_totals = {
        definition["key"]: _coerce_worktime_decimal((segment_totals or {}).get(definition["key"], ZERO_DECIMAL))
        for definition in WORKTIME_DAILY_HISTOGRAM_SEGMENTS
    }
    total = sum(normalized_segment_totals.values(), ZERO_DECIMAL)
    categories = []
    for category in WORKTIME_COMPOSITION_CATEGORIES:
        category_total = sum(
            (
                normalized_segment_totals[segment["key"]]
                for segment in WORKTIME_DAILY_HISTOGRAM_SEGMENTS
                if segment["category_key"] == category["key"]
            ),
            ZERO_DECIMAL,
        )
        categories.append(
            {
                **category,
                "value": category_total,
                "has_value": category_total > ZERO_DECIMAL,
            }
        )
    segments = [
        {
            **definition,
            "value": normalized_segment_totals[definition["key"]],
            "has_value": normalized_segment_totals[definition["key"]] > ZERO_DECIMAL,
        }
        for definition in WORKTIME_DAILY_HISTOGRAM_SEGMENTS
    ]
    legend_groups = []
    for category in categories:
        category_segments = [
            segment for segment in segments
            if segment["category_key"] == category["key"]
        ]
        if len(category_segments) == 1 and category_segments[0]["label"] == category["label"]:
            legend_children = []
        else:
            legend_children = category_segments
        legend_groups.append(
            {
                **category,
                "children": legend_children,
            }
        )
    return {
        "has_data": total > ZERO_DECIMAL,
        "total": total,
        "categories": categories,
        "segments": segments,
        "legend_groups": legend_groups,
        "outer_gradient": _build_worktime_conic_gradient(categories),
        "inner_gradient": _build_worktime_conic_gradient(segments),
    }


def _build_worktime_daily_histogram(assignments, visible_days, entry_map, *, non_working_days=None):
    non_working_days = set(non_working_days or [])
    columns = [
        {
            "date": work_day,
            "total": ZERO_DECIMAL,
            "segments": {segment["key"]: ZERO_DECIMAL for segment in WORKTIME_DAILY_HISTOGRAM_SEGMENTS},
        }
        for work_day in visible_days
    ]
    segment_totals = {segment["key"]: ZERO_DECIMAL for segment in WORKTIME_DAILY_HISTOGRAM_SEGMENTS}
    max_total = ZERO_DECIMAL
    for column_index, work_day in enumerate(visible_days):
        column = columns[column_index]
        for assignment in assignments:
            segment_key = _worktime_daily_histogram_segment_key(assignment)
            if not segment_key:
                continue
            hours = _coerce_worktime_decimal(entry_map.get(assignment.pk, {}).get(work_day))
            if hours <= ZERO_DECIMAL:
                continue
            column["segments"][segment_key] += hours
            column["total"] += hours
            segment_totals[segment_key] += hours
        if column["total"] > max_total:
            max_total = column["total"]

    prepared_columns = []
    for column in columns:
        prepared_segments = []
        for definition in WORKTIME_DAILY_HISTOGRAM_SEGMENTS:
            value = column["segments"][definition["key"]]
            if max_total > ZERO_DECIMAL and value > ZERO_DECIMAL:
                height_percent = round((value / max_total) * HUNDRED_DECIMAL, 3)
            else:
                height_percent = ZERO_DECIMAL
            prepared_segments.append(
                {
                    "key": definition["key"],
                    "label": definition["label"],
                    "category_label": definition["category_label"],
                    "value": value,
                    "height_percent": height_percent,
                    "has_value": value > ZERO_DECIMAL,
                }
            )
        prepared_columns.append(
            {
                "date": column["date"],
                "total": column["total"],
                "has_value": column["total"] > ZERO_DECIMAL,
                "is_non_working_day": column["date"] in non_working_days,
                "segments": prepared_segments,
            }
        )
    return {
        "columns": prepared_columns,
        "has_data": max_total > ZERO_DECIMAL,
        "segments": WORKTIME_DAILY_HISTOGRAM_SEGMENTS,
        "composition": _build_worktime_composition_donut(segment_totals),
    }


def _format_worktime_hours_for_csv(value):
    if value is None:
        return ""
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    text = format(decimal_value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


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


def _apply_row_histogram_sort(rows, hist_sort):
    if hist_sort not in {"asc", "desc"}:
        return rows
    reverse = hist_sort == "desc"
    sortable_rows = [row for row in rows if not row.get("is_calculated_downtime")]
    locked_rows = [row for row in rows if row.get("is_calculated_downtime")]
    return sorted(
        sortable_rows,
        key=lambda row: (
            row.get("total_hours", 0) or 0,
            row.get("sort_key", ()),
        ),
        reverse=reverse,
    ) + locked_rows


def _build_summary_column_cells(column_totals_by_day, vacation_column_totals_by_day, visible_days, *, non_working_days=None):
    summary_column_cells = []
    non_working_days = set(non_working_days or [])
    for work_day in visible_days:
        total = _coerce_worktime_decimal(column_totals_by_day.get(work_day, ZERO_DECIMAL))
        vacation_total = _coerce_worktime_decimal(vacation_column_totals_by_day.get(work_day, ZERO_DECIMAL))
        other_total = total - vacation_total
        has_vacation = vacation_total > ZERO_DECIMAL
        vacation_only = has_vacation and other_total <= ZERO_DECIMAL
        display_total = other_total if has_vacation and other_total > ZERO_DECIMAL else total
        summary_column_cells.append(
            {
                "total": total,
                "display_total": display_total,
                "has_vacation": has_vacation,
                "vacation_only": vacation_only,
                "is_non_working_day": work_day in non_working_days,
                "is_empty_non_working_day": work_day in non_working_days and total <= ZERO_DECIMAL,
            }
        )
    return summary_column_cells


def _assignment_rows(assignments, visible_days, entry_map, *, non_working_days=None):
    rows = []
    column_totals = {work_day: 0 for work_day in visible_days}
    vacation_column_totals = {work_day: ZERO_DECIMAL for work_day in visible_days}
    grand_total = 0
    for assignment in assignments:
        row = _build_assignment_row(
            assignment,
            visible_days,
            entry_map,
            breakdown="employees",
            non_working_days=non_working_days,
        )
        for cell in row["cells"]:
            if cell["value"] is not None:
                column_totals[cell["date"]] += cell["value"]
                if row.get("daily_histogram_segment_key") == "vacation":
                    vacation_column_totals[cell["date"]] += cell["value"]
        grand_total += row["total_hours"]
        rows.append(row)
    rows = _attach_row_histograms(rows)
    summary_column_cells = _build_summary_column_cells(
        column_totals,
        vacation_column_totals,
        visible_days,
        non_working_days=non_working_days,
    )
    return rows, [column_totals[work_day] for work_day in visible_days], grand_total, summary_column_cells


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


def _calculated_downtime_assignment(assignments):
    for assignment in assignments or []:
        if getattr(assignment, "record_type", "") == WorktimeAssignment.RecordType.DOWNTIME:
            return assignment
    return None


def _entry_map_with_calculated_downtime(user, assignments, visible_days, entry_map):
    downtime_assignment = _calculated_downtime_assignment(assignments)
    if downtime_assignment is None:
        return entry_map, entry_map

    working_hours = _production_calendar_working_hours_for_user(user, visible_days)
    non_working_days = {
        work_day
        for work_day in visible_days
        if _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL)) <= ZERO_DECIMAL
    }
    display_entry_map = {assignment_id: dict(day_values) for assignment_id, day_values in entry_map.items()}
    for assignment in assignments:
        if not _worktime_blocks_non_working_day_input(assignment):
            continue
        day_values = display_entry_map.get(assignment.pk)
        if not day_values:
            continue
        for work_day in non_working_days:
            day_values.pop(work_day, None)

    other_totals_by_day = {work_day: ZERO_DECIMAL for work_day in visible_days}
    vacation_days = set()
    for assignment in assignments:
        if assignment.pk == downtime_assignment.pk:
            continue
        is_vacation_assignment = _worktime_daily_histogram_segment_key(assignment) == "vacation"
        day_values = display_entry_map.get(assignment.pk, {})
        for work_day in visible_days:
            value = _coerce_worktime_decimal(day_values.get(work_day))
            if value > ZERO_DECIMAL:
                other_totals_by_day[work_day] += value
                if is_vacation_assignment:
                    vacation_days.add(work_day)

    downtime_values = {}
    chart_downtime_values = {}
    for work_day in visible_days:
        scheduled_hours = _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL))
        other_total = other_totals_by_day[work_day]
        if scheduled_hours <= ZERO_DECIMAL:
            downtime_value = ZERO_DECIMAL
        else:
            downtime_value = max(scheduled_hours - other_total, ZERO_DECIMAL)
        downtime_values[work_day] = downtime_value
        chart_downtime_values[work_day] = downtime_value if other_total > ZERO_DECIMAL else ZERO_DECIMAL

    downtime_assignment._worktime_calculated_downtime = True
    downtime_assignment._worktime_scheduled_hours = working_hours
    downtime_assignment._worktime_non_working_days = non_working_days
    downtime_assignment._worktime_hidden_downtime_zero_days = {
        work_day
        for work_day in visible_days
        if (
            _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL)) <= ZERO_DECIMAL
            or work_day in vacation_days
        )
    }
    display_entry_map[downtime_assignment.pk] = downtime_values
    chart_entry_map = {assignment_id: dict(day_values) for assignment_id, day_values in display_entry_map.items()}
    chart_entry_map[downtime_assignment.pk] = chart_downtime_values
    return display_entry_map, chart_entry_map


def _worktime_context(
    user,
    *,
    personal_only=False,
    month_start=None,
    scale="month",
    hist_sort="",
    breakdown="employees",
    company_filter=WORKTIME_COMPANY_FILTER_ALL,
    error_message="",
    success_message="",
):
    month_start = month_start or _resolve_general_period(None, scale)
    week_start = None
    week_error = ""
    general_scale = _resolve_scale(scale)
    histogram_sort_value = _resolve_hist_sort(hist_sort)
    breakdown_value = _resolve_breakdown(breakdown)
    company_filter_value, selected_company_names = _resolve_worktime_company_filter(company_filter)
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
        company_names=[] if personal_only else selected_company_names,
    ) if has_worktime_access else []
    entries = (
        WorktimeEntry.objects
        .filter(assignment_id__in=[assignment.pk for assignment in assignments], work_date__range=(range_start, range_end))
        .only("assignment_id", "work_date", "hours")
    )
    if not personal_only:
        entries = _filter_entries_for_visible_manual_weeks(entries, assignments, range_start, range_end)
    entry_map = _build_entry_map(entries, scale="week" if personal_only else general_scale)
    chart_entry_map = entry_map
    if personal_only:
        entry_map, chart_entry_map = _entry_map_with_calculated_downtime(user, assignments, visible_days, entry_map)
    non_working_days = set()
    if personal_only:
        downtime_assignment = _calculated_downtime_assignment(assignments)
        non_working_days = set(getattr(downtime_assignment, "_worktime_non_working_days", set()) or [])
    elif general_scale == "month":
        working_hours = _production_calendar_working_hours_for_company_filter(
            company_filter_value,
            assignments,
            visible_days,
        )
        non_working_days = {
            work_day
            for work_day in visible_days
            if _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL)) <= ZERO_DECIMAL
        }
    rows = []
    column_totals = []
    total_column_cells = []
    summary_column_cells = []
    grand_total = 0
    groups = []
    personal_order_ids = []
    if personal_only:
        personal_order_ids = [
            assignment.pk
            for assignment in assignments
            if assignment.record_type != WorktimeAssignment.RecordType.DOWNTIME
        ]
        rows, column_totals, grand_total, summary_column_cells = _assignment_rows(
            assignments,
            visible_days,
            entry_map,
            non_working_days=non_working_days,
        )
        rows = _apply_row_histogram_sort(rows, histogram_sort_value)
    else:
        groups = _grouped_assignment_rows(
            assignments,
            visible_days,
            entry_map,
            breakdown=breakdown_value,
            non_working_days=non_working_days,
        )
        groups = _attach_group_histograms(groups)
        groups = _apply_histogram_sort(groups, histogram_sort_value)
        column_totals, grand_total = _group_totals(groups, visible_days)
        total_column_cells = _build_total_column_cells(
            column_totals,
            visible_days,
            non_working_days=non_working_days,
        )
    daily_histogram = _build_worktime_daily_histogram(
        assignments,
        visible_days,
        chart_entry_map,
        non_working_days=non_working_days,
    ) if has_worktime_access else {
        "columns": [],
        "has_data": False,
        "segments": WORKTIME_DAILY_HISTOGRAM_SEGMENTS,
        "composition": {
            "has_data": False,
            "total": ZERO_DECIMAL,
            "categories": [],
            "segments": [],
            "legend_groups": [],
            "outer_gradient": "",
            "inner_gradient": "",
        },
    }

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
    show_composition_legend = has_worktime_access and not _has_worktime_csv_access(user)
    personal_calendar_mark_years = sorted({work_day.year for work_day in visible_days}) if personal_only else []
    personal_calendar_marks = {}
    if personal_only and has_worktime_access:
        for calendar_year in personal_calendar_mark_years:
            personal_calendar_marks.update(_production_calendar_marks_for_year(user, calendar_year))

    return {
        "groups": groups,
        "rows": rows,
        "days": [
            {
                "date": work_day,
                "day_number": work_day.day if personal_only or general_scale == "month" else "",
                "weekday_label": WEEKDAY_LABELS[work_day.weekday()] if personal_only or general_scale == "month" else "",
                "header_label": MONTH_SHORT_LABELS[work_day.month] if (not personal_only and general_scale == "year") else "",
                "is_non_working_day": work_day in non_working_days,
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
        "company_filter_value": company_filter_value,
        "breakdown_label": "по активностям" if breakdown_value == "activities" else "по сотрудникам",
        "is_activity_breakdown": breakdown_value == "activities",
        "scale_label": "год" if general_scale == "year" else "месяц",
        "period_value": period_value,
        "period_label": period_label,
        "column_totals": column_totals,
        "total_column_cells": total_column_cells,
        "summary_column_cells": summary_column_cells,
        "grand_total": grand_total,
        "daily_histogram": daily_histogram,
        "show_composition_legend": show_composition_legend,
        "worktime_csv_controls_visible": csv_controls_visible,
        "worktime_csv_controls_enabled": csv_controls_enabled,
        "worktime_csv_upload_url": reverse("worktime_csv_upload") if not personal_only else "",
        "worktime_csv_download_url": reverse("worktime_csv_download") if not personal_only else "",
        "worktime_csv_disabled_hint": WORKTIME_CSV_MODE_ERROR,
        "partial_path": reverse("personal_worktime_partial" if personal_only else "worktime_partial"),
        "personal_calendar_marks_json": json.dumps(personal_calendar_marks, ensure_ascii=False),
        "personal_calendar_marks_url": reverse("personal_worktime_calendar_marks") if personal_only else "",
        "personal_calendar_mark_years": ",".join(str(year) for year in personal_calendar_mark_years),
        "personal_add_row_url": reverse("personal_worktime_row_form") if personal_only else "",
        "personal_reorder_url": reverse("personal_worktime_row_order") if personal_only else "",
        "personal_order_signature": _personal_week_order_signature(personal_order_ids) if personal_only else "",
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
            parsed[(assignment_id, work_day)] = _parse_worktime_hours_value(
                raw_value,
                work_day,
                invalid_message=f"Значение за {work_day.strftime('%d.%m.%Y')} должно быть числом.",
                precision_message=(
                    f"Значение за {work_day.strftime('%d.%m.%Y')} "
                    "должно быть числом с не более чем двумя знаками после запятой."
                ),
                range_message=(
                    f"Количество часов за {work_day.strftime('%d.%m.%Y')} "
                    f"должно быть в диапазоне от 0 до {MAX_HOURS_PER_DAY}."
                ),
            )
    return parsed


def _remove_personal_blocked_hours_on_non_working_days(user, assignments, visible_days, parsed_values):
    blocked_assignment_ids = {
        assignment.pk
        for assignment in assignments
        if _worktime_blocks_non_working_day_input(assignment)
    }
    if not blocked_assignment_ids:
        return parsed_values

    working_hours = _production_calendar_working_hours_for_user(user, visible_days)
    non_working_days = {
        work_day
        for work_day in visible_days
        if _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL)) <= ZERO_DECIMAL
    }
    if not non_working_days:
        return parsed_values

    sanitized_values = dict(parsed_values)
    for assignment_id in blocked_assignment_ids:
        for work_day in non_working_days:
            sanitized_values[(assignment_id, work_day)] = None
    return sanitized_values


def _assignment_employee_key(assignment):
    employee = _resolve_assignment_employee(assignment)
    if employee is not None:
        return ("employee", employee.pk)
    executor_name = _normalize_worktime_company_text(getattr(assignment, "executor_name", ""))
    if executor_name:
        return ("executor", executor_name.casefold())
    return None


def _manual_employee_assignment(employee, executor_name, record_type):
    normalized_name, resolved_employee = resolve_employee_and_name(
        employee=employee,
        executor_name=executor_name,
    )
    if resolved_employee is None or not normalized_name:
        return None
    return WorktimeAssignment.objects.filter(
        registration__isnull=True,
        proposal_registration__isnull=True,
        executor_name=normalized_name,
        source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        record_type=record_type,
    ).first()


def _remove_csv_blocked_hours_on_non_working_days(assignments_by_id, visible_days, parsed_values):
    sanitized_values = dict(parsed_values)
    for assignment in assignments_by_id.values():
        if not _worktime_blocks_non_working_day_input(assignment):
            continue
        employee = _resolve_assignment_employee(assignment)
        working_hours = _production_calendar_working_hours_for_employee(employee, visible_days)
        if working_hours is None:
            continue
        for work_day in visible_days:
            key = (assignment.pk, work_day)
            if key not in sanitized_values:
                continue
            if _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL)) <= ZERO_DECIMAL:
                sanitized_values[key] = None
    return sanitized_values


def _apply_csv_calculated_downtime(assignments_by_id, visible_days, range_start, range_end, parsed_values):
    parsed_values = dict(parsed_values)
    assignments_by_employee = {}
    active_days_by_employee = {}
    for assignment in assignments_by_id.values():
        employee_key = _assignment_employee_key(assignment)
        if employee_key is None:
            continue
        assignments_by_employee.setdefault(employee_key, []).append(assignment)

    for assignment_id, work_day in parsed_values:
        assignment = assignments_by_id.get(assignment_id)
        if assignment is None or getattr(assignment, "record_type", "") == WorktimeAssignment.RecordType.DOWNTIME:
            continue
        employee_key = _assignment_employee_key(assignment)
        if employee_key is None:
            continue
        active_days_by_employee.setdefault(employee_key, set()).add(work_day)

    if not active_days_by_employee:
        return parsed_values, [], 0

    existing_entries = {
        (entry.assignment_id, entry.work_date): entry.hours
        for entry in WorktimeEntry.objects.filter(
            assignment_id__in=list(assignments_by_id),
            work_date__range=(range_start, range_end),
        ).only("assignment_id", "work_date", "hours")
    }
    extra_assignment_ids = []
    created_assignments_count = 0
    missing = object()

    for employee_key, active_days in active_days_by_employee.items():
        employee_assignments = assignments_by_employee.get(employee_key, [])
        if not employee_assignments:
            continue
        sample_assignment = employee_assignments[0]
        employee = _resolve_assignment_employee(sample_assignment)
        if employee is None:
            continue
        working_hours = _production_calendar_working_hours_for_employee(employee, visible_days)
        if working_hours is None:
            continue

        downtime_assignment = next(
            (
                assignment
                for assignment in employee_assignments
                if getattr(assignment, "record_type", "") == WorktimeAssignment.RecordType.DOWNTIME
            ),
            None,
        )
        if downtime_assignment is None:
            downtime_assignment = _manual_employee_assignment(
                employee,
                getattr(sample_assignment, "executor_name", ""),
                WorktimeAssignment.RecordType.DOWNTIME,
            )
            if downtime_assignment is not None:
                assignments_by_id[downtime_assignment.pk] = downtime_assignment
                employee_assignments.append(downtime_assignment)

        computed_values = {}
        for work_day in active_days:
            scheduled_hours = _coerce_worktime_decimal(working_hours.get(work_day, ZERO_DECIMAL))
            if scheduled_hours <= ZERO_DECIMAL:
                computed_values[work_day] = None
                continue
            other_total = ZERO_DECIMAL
            for assignment in employee_assignments:
                if getattr(assignment, "record_type", "") == WorktimeAssignment.RecordType.DOWNTIME:
                    continue
                raw_value = parsed_values.get((assignment.pk, work_day), missing)
                if raw_value is missing:
                    raw_value = existing_entries.get((assignment.pk, work_day))
                other_total += _coerce_worktime_decimal(raw_value)
            downtime_value = max(scheduled_hours - other_total, ZERO_DECIMAL)
            computed_values[work_day] = downtime_value if downtime_value > ZERO_DECIMAL else None

        if downtime_assignment is None and any(value is not None for value in computed_values.values()):
            existing_assignment = _manual_employee_assignment(
                employee,
                getattr(sample_assignment, "executor_name", ""),
                WorktimeAssignment.RecordType.DOWNTIME,
            )
            positive_week_starts = sorted({
                _start_of_week(work_day)
                for work_day, value in computed_values.items()
                if value is not None
            })
            for week_start in positive_week_starts:
                downtime_assignment, _ = ensure_personal_week_assignment(
                    registration=None,
                    proposal_registration=None,
                    employee=employee,
                    week_start=week_start,
                    record_type=WorktimeAssignment.RecordType.DOWNTIME,
                )
            if downtime_assignment is None:
                continue
            assignments_by_id[downtime_assignment.pk] = downtime_assignment
            employee_assignments.append(downtime_assignment)
            if existing_assignment is None:
                created_assignments_count += 1
        elif downtime_assignment is not None:
            positive_week_starts = sorted({
                _start_of_week(work_day)
                for work_day, value in computed_values.items()
                if value is not None
            })
            _ensure_worktime_csv_week_links(downtime_assignment, positive_week_starts)

        if downtime_assignment is None:
            continue
        extra_assignment_ids.append(downtime_assignment.pk)
        for work_day, value in computed_values.items():
            parsed_values[(downtime_assignment.pk, work_day)] = value

    return parsed_values, extra_assignment_ids, created_assignments_count


def _remove_general_manual_hours_outside_visible_weeks(assignments, range_start, range_end, parsed_values):
    visible_week_starts = _visible_manual_week_starts_for_assignments(assignments, range_start, range_end)
    manual_assignment_ids = {
        assignment.pk
        for assignment in assignments
        if assignment.source_type == WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK
    }
    if not manual_assignment_ids:
        return parsed_values
    sanitized_values = dict(parsed_values)
    for assignment_id, work_day in parsed_values:
        if assignment_id not in manual_assignment_ids:
            continue
        if _start_of_week(work_day) not in visible_week_starts.get(assignment_id, set()):
            sanitized_values[(assignment_id, work_day)] = None
    return sanitized_values


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
            company_filter=request.GET.get("company") if request.method == "GET" else request.POST.get("company"),
            error_message=error_message,
            success_message=success_message,
        ),
    )


def _personal_worktime_assignment_for_user(user, assignment_id):
    filters, _, _ = _personal_assignment_filters(user)
    return (
        _base_worktime_assignment_queryset()
        .filter(filters, pk=assignment_id)
        .first()
    )


def _persist_personal_week_assignment_order(user, week_start, ordered_assignment_ids):
    if not ordered_assignment_ids:
        return
    existing_links = {
        link.assignment_id: link
        for link in _personal_week_link_queryset(user, week_start).filter(assignment_id__in=ordered_assignment_ids)
    }
    to_create = []
    to_update = []
    for index, assignment_id in enumerate(ordered_assignment_ids, start=1):
        link = existing_links.get(assignment_id)
        if link is None:
            to_create.append(
                PersonalWorktimeWeekAssignment(
                    assignment_id=assignment_id,
                    week_start=week_start,
                    position=index,
                    is_hidden=False,
                )
            )
            continue
        updated = False
        if link.position != index:
            link.position = index
            updated = True
        if link.is_hidden:
            link.is_hidden = False
            updated = True
        if updated:
            to_update.append(link)
    with transaction.atomic():
        if to_create:
            PersonalWorktimeWeekAssignment.objects.bulk_create(to_create)
        if to_update:
            PersonalWorktimeWeekAssignment.objects.bulk_update(to_update, ["position", "is_hidden", "updated_at"])


def _resequence_visible_personal_assignments(user, week_start):
    visible_assignment_ids = _personal_week_order_ids(user, week_start)
    _persist_personal_week_assignment_order(user, week_start, visible_assignment_ids)


def _parse_personal_order_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
    return request.POST


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
            company_filter=request.GET.get("company"),
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
    _, selected_company_names = _resolve_worktime_company_filter(request.POST.get("company") or request.GET.get("company"))
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
        company_names=selected_company_names,
    )
    try:
        _validate_worktime_csv_header(rows[0], month_days)
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    assignments_by_key, duplicate_keys = _build_worktime_csv_assignment_index(assignments)
    assignments_by_id = {assignment.pk: assignment for assignment in assignments}
    projects_by_code, projects_by_key, duplicate_project_keys = _build_worktime_csv_project_index()
    proposals_by_code, proposals_by_key, duplicate_proposal_keys = _build_worktime_csv_proposal_index()
    manual_record_types_by_label = _build_worktime_csv_manual_record_type_index()
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
                proposals_by_code=proposals_by_code,
                proposals_by_key=proposals_by_key,
                duplicate_proposal_keys=duplicate_proposal_keys,
                manual_record_types_by_label=manual_record_types_by_label,
            )
        except forms.ValidationError as exc:
            warnings.append(f"Строка {row_number}: {exc.message}")
            continue
        if assignment is None:
            continue
        assignments_by_id[assignment.pk] = assignment
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

    parsed_values = _remove_csv_blocked_hours_on_non_working_days(
        assignments_by_id,
        month_days,
        parsed_values,
    )
    parsed_values, extra_assignment_ids, extra_created_assignments_count = _apply_csv_calculated_downtime(
        assignments_by_id,
        month_days,
        range_start,
        range_end,
        parsed_values,
    )
    touched_assignment_ids = sorted({*touched_assignment_ids, *extra_assignment_ids})
    created_assignments_count += extra_created_assignments_count

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
    _, selected_company_names = _resolve_worktime_company_filter(request.GET.get("company"))
    if not _worktime_csv_controls_enabled(scale, breakdown):
        return HttpResponseBadRequest(WORKTIME_CSV_MODE_ERROR)

    month_days, range_start, range_end, assignments = _general_worktime_period_data(
        request.user,
        period_start,
        scale=scale,
        breakdown=breakdown,
        company_names=selected_company_names,
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
                    _format_worktime_hours_for_csv(day_values.get(work_day))
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
@require_http_methods(["GET"])
def personal_worktime_calendar_marks(request):
    if not _has_worktime_access(request.user):
        return JsonResponse({"days": {}})

    try:
        year = int(str(request.GET.get("year") or "").strip())
    except (TypeError, ValueError):
        year = timezone.localdate().year
    if year < 1900 or year > 2100:
        year = timezone.localdate().year

    return JsonResponse({"days": _production_calendar_marks_for_year(request.user, year)})


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
            existing_week_link = None
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
            if existing_assignment is not None:
                existing_week_link = PersonalWorktimeWeekAssignment.objects.filter(
                    assignment=existing_assignment,
                    week_start=week_start,
                ).first()
            if (
                record_type == WorktimeAssignment.RecordType.PROJECT
                and existing_assignment
                and existing_assignment.source_type != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK
                and not (existing_week_link and existing_week_link.is_hidden)
            ):
                form.add_error("registration", "Строка по выбранному проекту уже присутствует в табеле.")
            elif (
                record_type == WorktimeAssignment.RecordType.TKP
                and existing_assignment
                and existing_assignment.source_type != WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK
                and not (existing_week_link and existing_week_link.is_hidden)
            ):
                form.add_error("proposal_registration", "Строка по выбранному ТКП уже присутствует в табеле.")
            elif _personal_manual_assignment_exists(
                employee_name=employee_name,
                week_start=week_start,
                record_type=record_type,
            ):
                form.add_error("record_type", "Строка с выбранным видом записи уже добавлена для этой недели.")
            else:
                with transaction.atomic():
                    assignment, _ = ensure_personal_week_assignment(
                        registration=registration,
                        proposal_registration=proposal_registration,
                        employee=employee,
                        week_start=week_start,
                        record_type=record_type,
                    )
                    if existing_week_link is None or existing_week_link.is_hidden:
                        _delete_assignment_entries_for_week(assignment, week_start)
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
def personal_worktime_row_delete(request, pk):
    if not _has_worktime_access(request.user):
        return HttpResponseForbidden(WORKTIME_ACCESS_ERROR)
    week_anchor = _resolve_week_anchor(request.POST.get("week") or request.GET.get("week"))
    week_start, week_error = _personal_week_bounds(week_anchor)
    if week_error:
        return HttpResponseBadRequest(week_error)
    assignment = _personal_worktime_assignment_for_user(request.user, pk)
    if assignment is None:
        return HttpResponse(status=404)
    if assignment.record_type == WorktimeAssignment.RecordType.DOWNTIME:
        return HttpResponseBadRequest("Строку Простой нельзя удалить.")
    with transaction.atomic():
        _delete_assignment_entries_for_week(assignment, week_start)
        week_link, created = PersonalWorktimeWeekAssignment.objects.get_or_create(
            assignment=assignment,
            week_start=week_start,
            defaults={
                "position": 0,
                "is_hidden": True,
            },
        )
        if not created and not week_link.is_hidden:
            week_link.is_hidden = True
            week_link.save(update_fields=["is_hidden", "updated_at"])
    _resequence_visible_personal_assignments(request.user, week_start)
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def personal_worktime_row_order(request):
    if not _has_worktime_access(request.user):
        return HttpResponseForbidden(WORKTIME_ACCESS_ERROR)
    payload = _parse_personal_order_payload(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "Некорректные данные порядка строк."}, status=400)
    week_anchor = _resolve_week_anchor(payload.get("week") or request.GET.get("week"))
    week_start, week_error = _personal_week_bounds(week_anchor)
    if week_error:
        return JsonResponse({"ok": False, "error": week_error}, status=400)

    raw_ids = payload.get("ordered_assignment_ids")
    if raw_ids is None:
        raw_ids = payload.getlist("ordered_assignment_ids") if hasattr(payload, "getlist") else None
    if not isinstance(raw_ids, (list, tuple)):
        return JsonResponse({"ok": False, "error": "Не передан порядок строк."}, status=400)

    try:
        ordered_assignment_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Порядок строк содержит некорректные идентификаторы."}, status=400)
    if len(ordered_assignment_ids) != len(set(ordered_assignment_ids)):
        return JsonResponse({"ok": False, "error": "Порядок строк содержит дубли."}, status=400)

    base_signature = str(payload.get("base_order_signature") or "")

    with transaction.atomic():
        list(_personal_week_link_queryset(request.user, week_start).select_for_update(of=("self",)))
        current_assignment_ids = _personal_week_order_ids(request.user, week_start)
        current_signature = _personal_week_order_signature(current_assignment_ids)
        desired_signature = _personal_week_order_signature(ordered_assignment_ids)

        conflict_payload = {
            "ok": False,
            "error": "Порядок строк был изменен. Таблица будет обновлена.",
            "current_assignment_ids": current_assignment_ids,
            "order_signature": current_signature,
        }
        if base_signature and base_signature != current_signature:
            if ordered_assignment_ids == current_assignment_ids:
                return JsonResponse({"ok": True, "order_signature": current_signature})
            return JsonResponse(conflict_payload, status=409)
        if set(ordered_assignment_ids) != set(current_assignment_ids):
            return JsonResponse(conflict_payload, status=409)

        _persist_personal_week_assignment_order(request.user, week_start, ordered_assignment_ids)
    return JsonResponse({"ok": True, "order_signature": desired_signature})


def _move_personal_worktime_row(request, pk, direction):
    if not _has_worktime_access(request.user):
        return HttpResponseForbidden(WORKTIME_ACCESS_ERROR)
    week_anchor = _resolve_week_anchor(request.POST.get("week") or request.GET.get("week"))
    week_start, week_error = _personal_week_bounds(week_anchor)
    if week_error:
        return HttpResponseBadRequest(week_error)
    assignment = _personal_worktime_assignment_for_user(request.user, pk)
    if assignment is None:
        return HttpResponse(status=404)
    if assignment.record_type == WorktimeAssignment.RecordType.DOWNTIME:
        return HttpResponse(status=204)
    ordered_assignment_ids = [
        item.pk
        for item in _visible_personal_assignments_for_week(request.user, week_start)
    ]
    try:
        current_index = ordered_assignment_ids.index(assignment.pk)
    except ValueError:
        return HttpResponse(status=204)
    swap_index = current_index - 1 if direction == "up" else current_index + 1
    if swap_index < 0 or swap_index >= len(ordered_assignment_ids):
        return HttpResponse(status=204)
    ordered_assignment_ids[current_index], ordered_assignment_ids[swap_index] = (
        ordered_assignment_ids[swap_index],
        ordered_assignment_ids[current_index],
    )
    _persist_personal_week_assignment_order(request.user, week_start, ordered_assignment_ids)
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def personal_worktime_row_move_up(request, pk):
    return _move_personal_worktime_row(request, pk, "up")


@login_required
@require_http_methods(["POST"])
def personal_worktime_row_move_down(request, pk):
    return _move_personal_worktime_row(request, pk, "down")


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
    if personal_only:
        parsed_values = _remove_personal_blocked_hours_on_non_working_days(
            request.user,
            assignments,
            visible_days,
            parsed_values,
        )
    else:
        parsed_values = _remove_general_manual_hours_outside_visible_weeks(
            assignments,
            range_start,
            range_end,
            parsed_values,
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
