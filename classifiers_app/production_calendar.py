from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import holidays
from django.db import transaction
from django.db.models import Q

from .models import OKSMCountry, ProductionCalendarDay


DEFAULT_WEEKEND = {5, 6}
SOURCE_HOLIDAYS = "holidays"
SOURCE_ISDAYOFF = "isdayoff/calendars"
ISDAYOFF_DATA_DIR = Path(__file__).resolve().parent / "data" / "isdayoff_calendars"
ISDAYOFF_REPOSITORY_RAW_URL = "https://raw.githubusercontent.com/isdayoff/calendars/main/db"
REGULAR_WORKING_HOURS = Decimal("8.0")
SHORTENED_WORKING_HOURS = Decimal("7.0")
DAY_OFF_HOURS = Decimal("0.0")


def supported_country_codes():
    """Return ISO alpha-2 codes available in local snapshots or python-holidays."""
    codes = set(local_isdayoff_country_codes())
    codes.update(holidays_supported_country_codes())
    return codes


@lru_cache(maxsize=1)
def holidays_supported_country_codes():
    if hasattr(holidays, "list_supported_countries"):
        return frozenset(str(code).upper() for code in holidays.list_supported_countries().keys())
    return frozenset()


def supported_countries_queryset():
    today = date.today()
    return (
        OKSMCountry.objects.filter(alpha2__in=supported_country_codes())
        .filter(Q(approval_date__isnull=True) | Q(approval_date__lte=today))
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
        .order_by("short_name", "position", "id")
    )


def is_country_supported(country):
    return bool(country and (country.alpha2 or "").upper() in supported_country_codes())


def default_country():
    qs = supported_countries_queryset()
    return qs.filter(alpha2="RU").first() or qs.first()


def normalize_year(value):
    try:
        year = int(value)
    except (TypeError, ValueError):
        return date.today().year
    if year < 1900 or year > 2100:
        return date.today().year
    return year


def iter_year_dates(year):
    current = date(year, 1, 1)
    last = date(year, 12, 31)
    while current <= last:
        yield current
        current += timedelta(days=1)


def _calendar_for_country(country, year):
    code = (country.alpha2 or "").upper()
    if not code:
        raise ValueError("У страны не заполнен буквенный код Альфа-2.")
    if code not in supported_country_codes():
        raise ValueError(f"Страна {code} не поддерживается локальным календарем или библиотекой holidays.")
    if code not in holidays_supported_country_codes():
        return {}
    return holidays.country_holidays(code, years=[year])


def _weekend_days(calendar):
    weekend = getattr(calendar, "weekend", None)
    if weekend is None:
        return DEFAULT_WEEKEND
    return {int(day) for day in weekend}


def _parse_mmdd(value, year):
    value = str(value).strip()
    if len(value) != 4 or not value.isdigit():
        return None
    return date(year, int(value[:2]), int(value[2:]))


def _isdayoff_file_path(country_code, year):
    code = str(country_code or "").lower()
    return ISDAYOFF_DATA_DIR / str(year) / f"{code}{year}.json"


def _isdayoff_download_url(country_code, year):
    code = str(country_code or "").lower()
    return f"{ISDAYOFF_REPOSITORY_RAW_URL}/{year}/{code}{year}.json"


def _display_path(path):
    try:
        return path.relative_to(Path(__file__).resolve().parent).as_posix()
    except ValueError:
        return path.as_posix()


@lru_cache(maxsize=256)
def local_isdayoff_country_codes():
    if not ISDAYOFF_DATA_DIR.exists():
        return frozenset()

    codes = set()
    for path in ISDAYOFF_DATA_DIR.glob("*/*.json"):
        stem = path.stem.lower()
        code = stem[:2]
        year = stem[2:]
        if len(code) == 2 and year.isdigit():
            codes.add(code.upper())
    return frozenset(codes)


@lru_cache(maxsize=256)
def load_isdayoff_calendar(country_code, year):
    code = str(country_code or "").lower()
    if not code:
        return None

    path = _isdayoff_file_path(code, year)
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    def parsed_set(key):
        return {parsed for value in data.get(key, []) if (parsed := _parse_mmdd(value, year))}

    return {
        "source_path": _display_path(path),
        "author": str(data.get("author", "")).strip(),
        "dayoff": parsed_set("dayoff"),
        "predayoff": parsed_set("predayoff"),
        "workday": parsed_set("workday"),
        "holiday": parsed_set("holiday"),
        "covidday": parsed_set("covidday"),
    }


def clear_isdayoff_calendar_caches():
    local_isdayoff_country_codes.cache_clear()
    load_isdayoff_calendar.cache_clear()


def isdayoff_calendar_status(country, year):
    if not country:
        return None

    code = (country.alpha2 or "").upper()
    path = _isdayoff_file_path(code, year)
    snapshot = load_isdayoff_calendar(code, year)
    return {
        "country_code": code,
        "year": year,
        "exists": snapshot is not None,
        "path": _display_path(path),
        "download_url": _isdayoff_download_url(code, year),
        "source_document": _source_document(snapshot) if snapshot else "",
        "dayoff_count": len(snapshot["dayoff"]) if snapshot else 0,
        "predayoff_count": len(snapshot["predayoff"]) if snapshot else 0,
        "holiday_count": len(snapshot["holiday"]) if snapshot else 0,
    }


def _validate_isdayoff_payload(data, country_code, year):
    if not isinstance(data, dict):
        raise ValueError("Файл календаря должен быть JSON-объектом.")

    payload_year = data.get("year")
    if payload_year is not None and int(payload_year) != int(year):
        raise ValueError(f"Файл относится к {payload_year} году, а выбран {year}.")

    payload_code = str(data.get("countrycode", "")).upper()
    if payload_code and payload_code != str(country_code).upper():
        raise ValueError(f"Файл относится к стране {payload_code}, а выбрана {country_code}.")

    for key in ("dayoff", "predayoff", "dayoff6", "predayoff6", "workday", "covidday", "holiday"):
        value = data.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"Поле {key} должно быть списком дат MMDD.")
        for item in value:
            if _parse_mmdd(item, year) is None:
                raise ValueError(f"Некорректная дата {item!r} в поле {key}.")


def download_isdayoff_calendar(country, year, *, timeout=10):
    if not country:
        raise ValueError("Страна не выбрана.")

    code = (country.alpha2 or "").upper()
    if not code:
        raise ValueError("У страны не заполнен буквенный код Альфа-2.")

    url = _isdayoff_download_url(code, year)
    request = Request(url, headers={"User-Agent": "ai-app-production-calendar"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_data = response.read()
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f"В isdayoff/calendars нет файла для {code} за {year} год.") from exc
        raise ValueError(f"Не удалось загрузить календарь isdayoff: HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Не удалось подключиться к isdayoff/calendars: {exc.reason}.") from exc

    try:
        data = json.loads(raw_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Загруженный календарь не является корректным JSON.") from exc

    _validate_isdayoff_payload(data, code, year)

    path = _isdayoff_file_path(code, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp_path.replace(path)
    clear_isdayoff_calendar_caches()

    return isdayoff_calendar_status(country, year)


def _source_document(snapshot):
    author = snapshot.get("author")
    source_path = snapshot.get("source_path", "")
    if author:
        return f"{source_path}; author: {author}"
    return source_path


def _holiday_name(calendar, day, is_holiday):
    if not is_holiday:
        return ""
    return str(calendar.get(day) or "")


def _working_hours(is_working_day, is_shortened_day):
    if not is_working_day:
        return DAY_OFF_HOURS
    if is_shortened_day:
        return SHORTENED_WORKING_HOURS
    return REGULAR_WORKING_HOURS


def build_day_values_from_isdayoff(snapshot, calendar, day):
    is_regular_weekend = day.weekday() in DEFAULT_WEEKEND
    is_extra_dayoff = day in snapshot["dayoff"] or day in snapshot["covidday"]
    is_forced_workday = day in snapshot["workday"]
    is_holiday = day in snapshot["holiday"]
    is_working_day = is_forced_workday or not (is_regular_weekend or is_extra_dayoff or is_holiday)
    is_shortened_day = bool(is_working_day and day in snapshot["predayoff"])

    return {
        "is_weekend": not is_working_day and (is_regular_weekend or is_extra_dayoff),
        "is_holiday": is_holiday,
        "is_working_day": is_working_day,
        "is_shortened_day": is_shortened_day,
        "working_hours": _working_hours(is_working_day, is_shortened_day),
        "holiday_name": _holiday_name(calendar, day, is_holiday),
        "source": SOURCE_ISDAYOFF,
        "source_document": _source_document(snapshot),
    }


def build_day_values_from_holidays(calendar, day):
    holiday_name = calendar.get(day) or ""
    is_weekend = day.weekday() in _weekend_days(calendar)
    is_holiday = bool(holiday_name)
    is_working_day = not is_weekend and not is_holiday
    return {
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "is_working_day": is_working_day,
        "is_shortened_day": False,
        "working_hours": _working_hours(is_working_day, False),
        "holiday_name": str(holiday_name),
        "source": SOURCE_HOLIDAYS,
        "source_document": "python-holidays",
    }


def build_day_values(calendar, day, snapshot=None):
    if snapshot is not None:
        return build_day_values_from_isdayoff(snapshot, calendar, day)
    return build_day_values_from_holidays(calendar, day)


@transaction.atomic
def generate_calendar_year(country, year):
    year = normalize_year(year)
    calendar = _calendar_for_country(country, year)
    snapshot = load_isdayoff_calendar(country.alpha2, year)
    created = 0
    updated = 0
    preserved_manual = 0

    existing = {
        item.date: item
        for item in ProductionCalendarDay.objects.filter(
            country=country,
            date__year=year,
        )
    }
    for day in iter_year_dates(year):
        values = build_day_values(calendar, day, snapshot=snapshot)
        item = existing.get(day)
        if item is None:
            ProductionCalendarDay.objects.create(country=country, date=day, **values)
            created += 1
            continue
        if item.is_manual:
            preserved_manual += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                changed = True
        if changed:
            item.save(update_fields=[*values.keys(), "updated_at"])
            updated += 1

    return {
        "created": created,
        "updated": updated,
        "preserved_manual": preserved_manual,
        "total_days": 366 if monthrange(year, 2)[1] == 29 else 365,
    }


def get_calendar_days(country, year):
    return ProductionCalendarDay.objects.filter(country=country, date__year=year).select_related("country")


def is_business_day(country, day):
    item = ProductionCalendarDay.objects.filter(country=country, date=day).first()
    if item is not None:
        return item.is_working_day
    calendar = _calendar_for_country(country, day.year)
    snapshot = load_isdayoff_calendar(country.alpha2, day.year)
    return build_day_values(calendar, day, snapshot=snapshot)["is_working_day"]
