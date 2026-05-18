"""Copy a typical-service-term Gantt into a project and remap calendars.

Source data lives in ``policy_app.TypicalServiceTerm.gantt_data`` and is built
against an *abstract* calendar (Mon-Fri working, Sat/Sun off, no holidays).
When a project is launched (status ``Не начат → В работе``) we snapshot that
schedule into ``ProjectRegistration.gantt_data`` and re-anchor it to the
launch date using the *production* calendar of the requested country
(default: Russia).

Working-day duration of every task is preserved. Calendar dates shift forward
so non-working days (RU holidays, weekends, переноса) are skipped.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from classifiers_app.models import OKSMCountry, ProductionCalendarDay
from classifiers_app.production_calendar import (
    _calendar_for_country,
    is_country_supported,
    load_isdayoff_calendar,
    build_day_values,
)


DEFAULT_COUNTRY_CODE = "RU"
PRODUCTION_CALENDAR_KIND = "production"
PROJECT_EXECUTOR_DISPLAY = "executor"


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _serialize_date(value):
    return value.isoformat() if value else ""


def _is_abstract_working_day(day: date) -> bool:
    return day.weekday() < 5


def _abstract_working_days_between(start: date, end: date) -> int:
    """Count abstract working days in [start, end). Includes start, excludes end."""
    if not start or not end or end <= start:
        return 0
    cur = start
    count = 0
    while cur < end:
        if _is_abstract_working_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


@dataclass
class _ProductionCalendar:
    country: OKSMCountry | None
    non_working: set
    working_overrides: set

    def is_working(self, day: date) -> bool:
        iso = day.isoformat()
        if iso in self.working_overrides:
            return True
        if iso in self.non_working:
            return False
        return day.weekday() < 5


def _load_production_calendar(country: OKSMCountry, year_from: int, year_to: int) -> _ProductionCalendar:
    non_working: set = set()
    working_overrides: set = set()

    if year_to < year_from:
        year_from, year_to = year_to, year_from

    stored = ProductionCalendarDay.objects.filter(
        country=country, date__year__gte=year_from, date__year__lte=year_to
    ).only("date", "is_working_day")
    stored_dates = set()
    for item in stored:
        stored_dates.add(item.date)
        if item.is_working_day:
            if item.date.weekday() >= 5:
                working_overrides.add(item.date.isoformat())
        else:
            if item.date.weekday() < 5:
                non_working.add(item.date.isoformat())

    for year in range(year_from, year_to + 1):
        try:
            calendar_obj = _calendar_for_country(country, year)
        except Exception:
            calendar_obj = None
        snapshot = None
        try:
            snapshot = load_isdayoff_calendar(country.alpha2, year)
        except Exception:
            snapshot = None
        if calendar_obj is None and snapshot is None:
            continue
        cur = date(year, 1, 1)
        end = date(year, 12, 31)
        while cur <= end:
            if cur in stored_dates:
                cur += timedelta(days=1)
                continue
            try:
                values = build_day_values(calendar_obj, cur, snapshot=snapshot)
            except Exception:
                values = None
            if values:
                if values.get("is_working_day"):
                    if cur.weekday() >= 5:
                        working_overrides.add(cur.isoformat())
                else:
                    if cur.weekday() < 5:
                        non_working.add(cur.isoformat())
            cur += timedelta(days=1)

    return _ProductionCalendar(country=country, non_working=non_working, working_overrides=working_overrides)


def _add_working_days(calendar: _ProductionCalendar, start: date, working_days: int) -> date:
    """Return the date `working_days` working days after `start` (exclusive end)."""
    if working_days <= 0:
        return start
    cur = start
    remaining = working_days
    safety = 0
    while remaining > 0 and safety < 10000:
        if calendar.is_working(cur):
            remaining -= 1
            if remaining == 0:
                return cur + timedelta(days=1)
        cur += timedelta(days=1)
        safety += 1
    return cur


def _next_working_day(calendar: _ProductionCalendar, day: date) -> date:
    cur = day
    safety = 0
    while not calendar.is_working(cur) and safety < 1000:
        cur += timedelta(days=1)
        safety += 1
    return cur


def _resolve_default_country() -> OKSMCountry | None:
    country = OKSMCountry.objects.filter(alpha2__iexact=DEFAULT_COUNTRY_CODE).first()
    if country and is_country_supported(country):
        return country
    return None


def _mark_as_production_calendar(meta: dict, country: OKSMCountry | None, *, unavailable: bool = False) -> dict:
    meta["calendar_kind"] = PRODUCTION_CALENDAR_KIND
    if country and country.pk:
        meta["calendar_country_id"] = country.pk
    else:
        meta.pop("calendar_country_id", None)
    meta["executor_display"] = PROJECT_EXECUTOR_DISPLAY
    meta["calendar"] = {
        "kind": PRODUCTION_CALENDAR_KIND,
        "country": DEFAULT_COUNTRY_CODE,
        **({"country_id": country.pk} if country and country.pk else {}),
        **({"unavailable": True} if unavailable else {}),
    }
    return meta


def _abstract_date_to_production(
    value,
    *,
    abstract_origin: date,
    project_start: date,
    calendar: _ProductionCalendar,
) -> date | None:
    source_date = _parse_date(value)
    if not source_date:
        return None
    offset = _abstract_working_days_between(abstract_origin, source_date)
    converted = _add_working_days(calendar, project_start, offset) if offset else project_start
    return _next_working_day(calendar, converted)


def _default_empty_payload(launch_date: date) -> dict:
    iso = _serialize_date(launch_date)
    country = _resolve_default_country()
    return {
        "data": [],
        "links": [],
        "meta": _mark_as_production_calendar({
            "base_date": iso,
            "project_start": iso,
            "project_end": iso,
            "version": 1,
        }, country, unavailable=country is None),
    }


def _remap_payload_to_production(payload: dict, launch_date: date) -> dict:
    """Re-anchor task dates from the abstract calendar to the RU production calendar."""
    if not isinstance(payload, dict):
        return _default_empty_payload(launch_date)

    new_payload = copy.deepcopy(payload)
    tasks = new_payload.get("data") or []
    if not isinstance(tasks, list) or not tasks:
        country = _resolve_default_country()
        meta = new_payload.get("meta") or {}
        meta.setdefault("base_date", _serialize_date(launch_date))
        meta["project_start"] = _serialize_date(launch_date)
        meta.setdefault("project_end", _serialize_date(launch_date))
        meta.setdefault("version", 1)
        new_payload["meta"] = _mark_as_production_calendar(meta, country, unavailable=country is None)
        new_payload.setdefault("data", [])
        new_payload.setdefault("links", [])
        return new_payload

    parsed_starts = []
    parsed_ends = []
    for task in tasks:
        s = _parse_date(task.get("start_date"))
        e = _parse_date(task.get("end_date"))
        parsed_starts.append(s)
        parsed_ends.append(e)
    valid_starts = [d for d in parsed_starts if d]
    if not valid_starts:
        return _default_empty_payload(launch_date)

    abstract_origin = min(valid_starts)

    country = _resolve_default_country()
    if country is None:
        meta = new_payload.get("meta") or {}
        meta["project_start"] = _serialize_date(launch_date)
        new_payload["meta"] = _mark_as_production_calendar(meta, None, unavailable=True)
        return new_payload

    end_offset_days = 0
    for end in parsed_ends:
        if end:
            end_offset_days = max(end_offset_days, _abstract_working_days_between(abstract_origin, end))

    estimated_end = launch_date + timedelta(days=int(end_offset_days * 1.6) + 30)
    calendar = _load_production_calendar(
        country,
        year_from=launch_date.year,
        year_to=max(estimated_end.year, launch_date.year + 1),
    )

    project_start = _next_working_day(calendar, launch_date)

    project_end = project_start
    for task, start_d, end_d in zip(tasks, parsed_starts, parsed_ends):
        if not start_d:
            continue
        start_offset = _abstract_working_days_between(abstract_origin, start_d)
        if not end_d or end_d <= start_d:
            duration = 0
        else:
            duration = _abstract_working_days_between(start_d, end_d)

        new_start = _add_working_days(calendar, project_start, start_offset) if start_offset else project_start
        new_start = _next_working_day(calendar, new_start)
        if duration <= 0:
            new_end = new_start
        else:
            new_end = _add_working_days(calendar, new_start, duration)

        task["start_date"] = _serialize_date(new_start)
        task["end_date"] = _serialize_date(new_end)
        for date_field in ("deadline", "constraint_date"):
            converted = _abstract_date_to_production(
                task.get(date_field),
                abstract_origin=abstract_origin,
                project_start=project_start,
                calendar=calendar,
            )
            if converted:
                task[date_field] = _serialize_date(converted)
        if "duration" in task or duration:
            task["duration"] = duration
        if new_end > project_end:
            project_end = new_end

    meta = new_payload.get("meta") or {}
    meta["base_date"] = _serialize_date(project_start)
    meta["project_start"] = _serialize_date(project_start)
    meta["project_end"] = _serialize_date(project_end)
    meta.setdefault("version", 1)
    new_payload["meta"] = _mark_as_production_calendar(meta, country)
    new_payload.setdefault("links", [])
    return new_payload


def copy_typical_gantt_to_project(registration, *, launch_date: date | None = None) -> bool:
    """Copy primary product's typical Gantt into the registration.

    Idempotent: returns ``False`` and skips work if ``registration.gantt_data``
    already has any tasks. Returns ``True`` when data was written.
    """
    from policy_app.models import TypicalServiceTerm

    if registration is None:
        return False

    existing = registration.gantt_data if isinstance(registration.gantt_data, dict) else None
    if existing and existing.get("data"):
        return False

    launch_date = launch_date or date.today()
    primary_product = registration.primary_product
    payload = None
    if primary_product is not None:
        term = (
            TypicalServiceTerm.objects.filter(product_id=primary_product.pk)
            .order_by("position", "id")
            .first()
        )
        if term and isinstance(term.gantt_data, dict) and term.gantt_data.get("data"):
            payload = copy.deepcopy(term.gantt_data)

    if payload:
        try:
            from policy_app.views import (
                _roll_up_typical_service_term_gantt_parent_dates,
                _sync_typical_service_term_gantt_system_tasks,
            )

            tasks = payload.get("data")
            if isinstance(tasks, list):
                _sync_typical_service_term_gantt_system_tasks(tasks)
                _roll_up_typical_service_term_gantt_parent_dates(tasks)
                _sync_typical_service_term_gantt_system_tasks(tasks)
        except Exception:
            pass
        new_payload = _remap_payload_to_production(payload, launch_date)
    else:
        new_payload = _default_empty_payload(launch_date)

    registration.gantt_data = new_payload
    if not registration.launched_at:
        registration.launched_at = launch_date
    registration.save(update_fields=["gantt_data", "launched_at"])
    from projects_app.services.schedule_sync import sync_project_gantt_from_sources

    sync_project_gantt_from_sources(registration)
    return True
