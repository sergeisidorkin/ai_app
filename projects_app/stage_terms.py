"""Сроки этапов реестра проектов.

Цепочка дат совпадает с калькулятором модалки договоров: дата начала,
исходные данные, предварительный отчёт, итоговый отчёт и лаг между этапами.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

SOURCE_DATA_UNITS = ("days", "weeks", "months")
PRELIMINARY_UNITS = ("months", "days", "weeks")
FINAL_UNITS = ("days", "weeks", "months")
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y")
TERMS_COLUMN_KEYS = (
    "source_date_collapsed",
    "preliminary_date_collapsed",
    "final_date_collapsed",
)


def _blank_stage(rank=1, product_id=""):
    return {
        "rank": rank,
        "product_id": str(product_id or ""),
        "evaluation_date_enabled": True,
        "evaluation_date": "",
        "source_data_term_enabled": int(rank) == 1,
        "source_data_term": "",
        "source_data_term_unit": "weeks",
        "source_data_date_enabled": False,
        "source_data_date": "",
        "service_term_months_enabled": True,
        "service_term_months": "",
        "preliminary_report_term_unit": "months",
        "preliminary_report_date_enabled": False,
        "preliminary_report_date": "",
        "final_report_term_weeks": "",
        "final_report_term_unit": "weeks",
        "final_report_date_enabled": False,
        "final_report_date": "",
        "next_stage_delay_days": 0,
        "next_stage_delay_unit": "days",
    }


def enabled_flag(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "off", "no", "нет"}


def parse_decimal(value):
    if value is None:
        return None
    raw = str(value).strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        parsed = Decimal(raw)
    except Exception:
        return None
    if parsed < 0:
        return Decimal("0")
    return parsed


def format_decimal(value):
    if value is None:
        return ""
    quantized = Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def format_date(value):
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.isoformat()


def _unit(value, allowed, default):
    raw = str(value or "").strip()
    if raw in allowed:
        return raw
    return default


def term_to_days(value, unit):
    parsed = parse_decimal(value)
    if parsed is None:
        return Decimal("0")
    if unit == "days":
        return parsed.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if unit == "months":
        return parsed * Decimal("30")
    return parsed * Decimal("7")


def days_to_term(days, unit):
    safe_days = Decimal(days or 0)
    if safe_days < 0:
        safe_days = Decimal("0")
    if unit == "days":
        return safe_days.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if unit == "months":
        return (safe_days / Decimal("30")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return (safe_days / Decimal("7")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _add_days(value, days):
    if not value:
        return None
    rounded = int(Decimal(days or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return value + timedelta(days=rounded)


def _add_months(value, months):
    if not value:
        return None
    safe_months = max(parse_decimal(months) or Decimal("0"), Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(
        ((safe_months - Decimal(whole_months)) * Decimal("30")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    month_index = (value.month - 1) + whole_months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _month_end_day(year, month))
    return date(year, month, day) + timedelta(days=fractional_days)


def _month_end_day(year, month):
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _apply_stage_delay(anchor, stage):
    if not anchor:
        return None
    unit = stage.get("next_stage_delay_unit") or "days"
    if unit not in SOURCE_DATA_UNITS:
        unit = "days"
    amount = stage.get("next_stage_delay_days") or 0
    return add_term(anchor, amount, unit) or anchor


def add_term(value, amount, unit):
    if not value:
        return None
    parsed = parse_decimal(amount)
    if parsed is None:
        return None
    if unit == "days":
        return _add_days(value, parsed)
    if unit == "months":
        return _add_months(value, parsed)
    return _add_days(value, parsed * Decimal("7"))


def normalize_stage(raw, rank, product_id=""):
    source = raw if isinstance(raw, dict) else {}
    stage = _blank_stage(rank, product_id or source.get("product_id") or "")
    stage["evaluation_date_enabled"] = enabled_flag(source.get("evaluation_date_enabled"), True)
    stage["evaluation_date"] = format_date(source.get("evaluation_date")) if stage["evaluation_date_enabled"] else ""
    if "evaluation_date_common" in source:
        stage["evaluation_date_common"] = enabled_flag(source.get("evaluation_date_common"), True)
    stage["source_data_term_enabled"] = enabled_flag(source.get("source_data_term_enabled"), True)
    stage["source_data_term_unit"] = _unit(source.get("source_data_term_unit"), SOURCE_DATA_UNITS, "weeks")
    source_term = parse_decimal(source.get("source_data_term"))
    stage["source_data_term"] = format_decimal(source_term) if stage["source_data_term_enabled"] and source_term is not None else ""
    stage["source_data_date_enabled"] = enabled_flag(source.get("source_data_date_enabled"), True)
    stage["source_data_date"] = format_date(source.get("source_data_date")) if stage["source_data_date_enabled"] else ""
    stage["service_term_months_enabled"] = enabled_flag(source.get("service_term_months_enabled"), True)
    stage["preliminary_report_term_unit"] = _unit(
        source.get("preliminary_report_term_unit"),
        PRELIMINARY_UNITS,
        "months",
    )
    preliminary_term = parse_decimal(source.get("service_term_months"))
    stage["service_term_months"] = (
        format_decimal(preliminary_term)
        if stage["service_term_months_enabled"] and preliminary_term is not None
        else ""
    )
    stage["preliminary_report_date_enabled"] = enabled_flag(source.get("preliminary_report_date_enabled"), True)
    stage["preliminary_report_date"] = (
        format_date(source.get("preliminary_report_date")) if stage["preliminary_report_date_enabled"] else ""
    )
    stage["final_report_term_unit"] = _unit(source.get("final_report_term_unit"), FINAL_UNITS, "weeks")
    final_term = parse_decimal(source.get("final_report_term_weeks"))
    stage["final_report_term_weeks"] = format_decimal(final_term) if final_term is not None else ""
    stage["final_report_date_enabled"] = enabled_flag(source.get("final_report_date_enabled"), True)
    stage["final_report_date"] = format_date(source.get("final_report_date")) if stage["final_report_date_enabled"] else ""
    stage["next_stage_delay_unit"] = _unit(source.get("next_stage_delay_unit"), SOURCE_DATA_UNITS, "days")
    delay = parse_decimal(source.get("next_stage_delay_days"))
    if delay is None or delay == 0:
        stage["next_stage_delay_days"] = 0
    elif stage["next_stage_delay_unit"] == "days":
        stage["next_stage_delay_days"] = int(delay.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        stage["next_stage_delay_days"] = format_decimal(delay)
    return stage


def legacy_stage_from_registration(registration, rank=1, product_id=""):
    stage = _blank_stage(rank, product_id)
    stage["source_data_term_enabled"] = True
    stage["source_data_date_enabled"] = True
    stage["preliminary_report_date_enabled"] = True
    stage["final_report_date_enabled"] = True
    input_days = getattr(registration, "input_data", None)
    stage["source_data_term_unit"] = "days"
    stage["source_data_term"] = "" if input_days in (None, "") else str(int(input_days))
    stage["service_term_months"] = format_decimal(getattr(registration, "stage1_weeks", None) or 0)
    stage["preliminary_report_term_unit"] = "months"
    stage["final_report_term_weeks"] = format_decimal(getattr(registration, "stage2_weeks", None) or 0)
    stage["final_report_term_unit"] = "weeks"
    stage["preliminary_report_date"] = format_date(getattr(registration, "stage1_end", None))
    stage["final_report_date"] = format_date(getattr(registration, "stage2_end", None))
    stage["evaluation_date"] = format_date(getattr(registration, "evaluation_date", None))
    return stage


def stages_from_registration(registration):
    stored = list(getattr(registration, "stage_terms_json", None) or [])
    product_id = ""
    products = []
    if registration is not None and getattr(registration, "pk", None):
        try:
            products = list(registration.ordered_products())
        except Exception:
            products = []
    if products:
        product_id = str(getattr(products[0], "pk", "") or "")
    if stored:
        rows = []
        for index, item in enumerate(stored, start=1):
            item_product = ""
            if isinstance(item, dict):
                item_product = item.get("product_id") or ""
            rows.append(normalize_stage(item, index, item_product or (product_id if index == 1 else "")))
        return rows
    return [legacy_stage_from_registration(registration, 1, product_id)]


def _forward_stage(start, stage):
    """Возвращает даты этапа и дату старта следующего этапа."""
    source_enabled = stage["source_data_term_enabled"]
    source_term = parse_decimal(stage["source_data_term"]) if source_enabled else Decimal("0")
    if source_enabled and source_term is None:
        return stage, _apply_stage_delay(start, stage)

    source_date = add_term(start, source_term or 0, stage["source_data_term_unit"]) if start else None
    preliminary_enabled = stage["service_term_months_enabled"]
    preliminary_term = parse_decimal(stage["service_term_months"]) if preliminary_enabled else Decimal("0")
    if preliminary_enabled and preliminary_term is None:
        next_start = _apply_stage_delay(source_date, stage)
        stage = dict(stage)
        stage["source_data_date"] = format_date(source_date) if stage["source_data_date_enabled"] else ""
        stage["preliminary_report_date"] = ""
        stage["final_report_date"] = ""
        stage["_calculated_final_report_date"] = ""
        return stage, next_start

    preliminary_date = (
        add_term(source_date, preliminary_term or 0, stage["preliminary_report_term_unit"]) if source_date else None
    )
    final_term = parse_decimal(stage["final_report_term_weeks"])
    if final_term is None:
        next_start = _apply_stage_delay(preliminary_date, stage)
        stage = dict(stage)
        stage["source_data_date"] = format_date(source_date) if stage["source_data_date_enabled"] else ""
        stage["preliminary_report_date"] = (
            format_date(preliminary_date) if stage["preliminary_report_date_enabled"] else ""
        )
        stage["final_report_date"] = ""
        stage["_calculated_final_report_date"] = ""
        return stage, next_start

    final_date = add_term(preliminary_date, final_term, stage["final_report_term_unit"]) if preliminary_date else None
    anchor = final_date or preliminary_date or source_date or start
    next_start = _apply_stage_delay(anchor, stage)
    updated = dict(stage)
    updated["source_data_date"] = format_date(source_date) if stage["source_data_date_enabled"] else ""
    updated["preliminary_report_date"] = format_date(preliminary_date) if stage["preliminary_report_date_enabled"] else ""
    updated["final_report_date"] = format_date(final_date) if stage["final_report_date_enabled"] else ""
    updated["_calculated_final_report_date"] = format_date(final_date)
    return updated, next_start


def compute_stage_chain(project_start, stages):
    start = parse_date(project_start)
    computed = []
    cursor = start
    for index, stage in enumerate(stages, start=1):
        normalized = normalize_stage(stage, index, stage.get("product_id") if isinstance(stage, dict) else "")
        if cursor is None:
            normalized["source_data_date"] = ""
            normalized["preliminary_report_date"] = ""
            normalized["final_report_date"] = ""
            computed.append(normalized)
            continue
        updated, cursor = _forward_stage(cursor, normalized)
        computed.append(updated)
    return computed


def project_stage_scalars(stage):
    source_days = Decimal("0")
    if stage.get("source_data_term_enabled"):
        source_days = term_to_days(stage.get("source_data_term"), stage.get("source_data_term_unit"))
    input_data = int(source_days.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if stage.get("service_term_months_enabled"):
        preliminary_days = term_to_days(stage.get("service_term_months"), stage.get("preliminary_report_term_unit"))
    else:
        preliminary_days = Decimal("0")
    final_days = term_to_days(stage.get("final_report_term_weeks"), stage.get("final_report_term_unit"))
    stage1_weeks = days_to_term(preliminary_days, "months")
    stage2_weeks = days_to_term(final_days, "weeks")
    evaluation_date = parse_date(stage.get("evaluation_date")) if stage.get("evaluation_date_enabled") else None
    return {
        "input_data": input_data,
        "stage1_weeks": stage1_weeks,
        "stage2_weeks": stage2_weeks,
        "stage1_end": parse_date(stage.get("preliminary_report_date")),
        "stage2_end": parse_date(stage.get("final_report_date")),
        "evaluation_date": evaluation_date,
    }


def apply_stages_to_registration(registration, stages, project_start):
    computed = compute_stage_chain(project_start, stages or [_blank_stage()])
    registration.project_start_date = parse_date(project_start)
    for stage in computed:
        stage.pop("_calculated_final_report_date", None)
    registration.stage_terms_json = computed
    scalars = project_stage_scalars(computed[-1])
    for field_name, value in scalars.items():
        setattr(registration, field_name, value)
    registration.completion_calc = registration.stage2_end
    return registration


def apply_single_stage_to_registration(registration, stage, project_start):
    return apply_stages_to_registration(registration, [stage], project_start)


def store_stage_snapshot(registration, stage, project_start):
    """Кладёт уже посчитанный этап на запись, не пересчитывая цепочку с нуля."""
    normalized = normalize_stage(stage, 1, stage.get("product_id") if isinstance(stage, dict) else "")
    registration.project_start_date = parse_date(project_start)
    registration.stage_terms_json = [normalized]
    for field_name, value in project_stage_scalars(normalized).items():
        setattr(registration, field_name, value)
    registration.completion_calc = registration.stage2_end
    return registration


def patch_stage_from_scalars(stage, *, input_data, stage1_weeks, stage2_weeks, evaluation_date):
    updated = dict(stage)
    updated["source_data_term_enabled"] = True
    updated["source_data_term_unit"] = "days"
    updated["source_data_term"] = "" if input_data in (None, "") else str(int(input_data))
    updated["service_term_months_enabled"] = True
    updated["preliminary_report_term_unit"] = "months"
    updated["service_term_months"] = format_decimal(stage1_weeks or 0)
    updated["final_report_term_unit"] = "weeks"
    updated["final_report_term_weeks"] = format_decimal(stage2_weeks or 0)
    if evaluation_date is not None or "evaluation_date" in updated:
        updated["evaluation_date_enabled"] = True
        updated["evaluation_date"] = format_date(evaluation_date)
    return updated


def sync_registration_json_from_scalars(registration):
    """Обновляет последний этап JSON из скалярных полей, не трогая остальные этапы."""
    stored = list(registration.stage_terms_json or [])
    if not stored:
        return registration
    stages = [normalize_stage(item, index) for index, item in enumerate(stored, start=1)]
    stages[-1] = patch_stage_from_scalars(
        stages[-1],
        input_data=registration.input_data,
        stage1_weeks=registration.stage1_weeks,
        stage2_weeks=registration.stage2_weeks,
        evaluation_date=registration.evaluation_date,
    )
    anchor = registration.project_start_date or registration.contract_start
    return apply_stages_to_registration(registration, stages, anchor)


def _list_value(data, key):
    if hasattr(data, "getlist"):
        return [str(value or "").strip() for value in data.getlist(key)]
    value = data.get(key, [])
    if isinstance(value, (list, tuple)):
        return [str(item or "").strip() for item in value]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def empty_terms_columns():
    return {key: False for key in TERMS_COLUMN_KEYS}


def parse_posted_terms_columns(data):
    """Свёрнутые столбцы дат из формы. None — поля не пришли, сохранённое не трогаем."""
    if data is None:
        return None
    keys = data.keys() if hasattr(data, "keys") else []
    if not any(key in keys for key in TERMS_COLUMN_KEYS):
        return None

    def collapsed(key):
        raw = str(data.get(key) or "").strip().lower()
        return raw in {"1", "true", "on", "yes"}

    return {key: collapsed(key) for key in TERMS_COLUMN_KEYS}


def terms_columns_for_registration(registration, data=None):
    posted = parse_posted_terms_columns(data)
    if posted is not None:
        return posted
    owner = registration
    if registration is not None and getattr(registration, "stage_project_id", None):
        owner = registration.stage_project
    raw = getattr(owner, "terms_columns_json", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    state = empty_terms_columns()
    for key in TERMS_COLUMN_KEYS:
        state[key] = bool(raw.get(key))
    return state


def store_terms_columns(registration, data):
    state = parse_posted_terms_columns(data)
    if state is None or registration is None:
        return False
    registration.terms_columns_json = state
    return True


def has_posted_stage_terms(data):
    if data is None:
        return False
    keys = data.keys() if hasattr(data, "keys") else []
    return any(
        key in keys
        for key in (
            "source_data_term",
            "service_term_months",
            "final_report_term_weeks",
            "source_data_date",
            "preliminary_report_date",
            "final_report_date",
        )
    )


def has_posted_legacy_stage_terms(data):
    if data is None:
        return False
    keys = data.keys() if hasattr(data, "keys") else []
    return "stage1_weeks" in keys or "stage2_weeks" in keys


def evaluation_dates_are_common(rows):
    """Общая дата оценки: явный флаг важнее совпадения значений."""
    stages = [row for row in (rows or []) if isinstance(row, dict)]
    if len(stages) <= 1:
        return True
    flags = [
        enabled_flag(row.get("evaluation_date_common"), True)
        for row in stages
        if "evaluation_date_common" in row
    ]
    if flags:
        return all(flags)
    first = stages[0]
    first_date = first.get("evaluation_date") or ""
    first_enabled = bool(first.get("evaluation_date_enabled", True))
    return all(
        (row.get("evaluation_date") or "") == first_date
        and bool(row.get("evaluation_date_enabled", True)) == first_enabled
        for row in stages[1:]
    )


def parse_posted_stages(data, product_ids=None):
    """Строки этапов из модалки. None — новые поля сроков не пришли."""
    if not has_posted_stage_terms(data):
        if not has_posted_legacy_stage_terms(data):
            return None
        return _parse_legacy_posted_stages(data, product_ids)
    source_terms = _list_value(data, "source_data_term")
    preliminary_terms = _list_value(data, "service_term_months")
    final_terms = _list_value(data, "final_report_term_weeks")
    count = max(
        len(source_terms),
        len(preliminary_terms),
        len(final_terms),
        len(product_ids or []),
        1,
    )
    products = list(product_ids or [])
    posted_keys = data.keys() if hasattr(data, "keys") else []
    has_common_flag = "evaluation_date_common" in posted_keys
    common_enabled = _posted_last_flag(data, "evaluation_date_common") if has_common_flag else False
    evaluation_dates = _list_value(data, "evaluation_date")
    evaluation_enabled = _list_value(data, "evaluation_date_enabled")
    shared_evaluation = _at(evaluation_dates, 0)
    shared_evaluation_enabled = _at(evaluation_enabled, 0, "true")
    rows = []
    for index in range(count):
        product_id = products[index] if index < len(products) else ""
        raw = {
            "product_id": product_id,
            "source_data_term": _at(source_terms, index),
            "source_data_term_unit": _at(_list_value(data, "source_data_term_unit"), index),
            "source_data_term_enabled": _at(_list_value(data, "source_data_term_enabled"), index, "true"),
            "source_data_date": _at(_list_value(data, "source_data_date"), index),
            "source_data_date_enabled": _at(_list_value(data, "source_data_date_enabled"), index, "true"),
            "service_term_months": _at(preliminary_terms, index),
            "preliminary_report_term_unit": _at(_list_value(data, "preliminary_report_term_unit"), index),
            "service_term_months_enabled": _at(_list_value(data, "service_term_months_enabled"), index, "true"),
            "preliminary_report_date": _at(_list_value(data, "preliminary_report_date"), index),
            "preliminary_report_date_enabled": _at(_list_value(data, "preliminary_report_date_enabled"), index, "true"),
            "final_report_term_weeks": _at(final_terms, index),
            "final_report_term_unit": _at(_list_value(data, "final_report_term_unit"), index),
            "final_report_date": _at(_list_value(data, "final_report_date"), index),
            "final_report_date_enabled": _at(_list_value(data, "final_report_date_enabled"), index, "true"),
            "next_stage_delay_days": _at(_list_value(data, "next_stage_delay_days"), index, "0"),
            "next_stage_delay_unit": _at(_list_value(data, "next_stage_delay_unit"), index, "days"),
            "evaluation_date": _at(evaluation_dates, index),
            "evaluation_date_enabled": _at(evaluation_enabled, index, "true"),
        }
        if has_common_flag:
            raw["evaluation_date_common"] = "true" if common_enabled else "false"
            if common_enabled and count > 1:
                raw["evaluation_date"] = shared_evaluation
                raw["evaluation_date_enabled"] = shared_evaluation_enabled
        rows.append(normalize_stage(raw, index + 1, product_id))
    return rows


def _parse_legacy_posted_stages(data, product_ids=None):
    stage1_values = _list_value(data, "stage1_weeks")
    stage2_values = _list_value(data, "stage2_weeks")
    products = list(product_ids or [])
    count = max(len(stage1_values), len(stage2_values), len(products), 1)
    shared_input = _list_value(data, "input_data")
    shared_evaluation = _list_value(data, "evaluation_date")
    rows = []
    for index in range(count):
        raw = {
            "product_id": products[index] if index < len(products) else "",
            "source_data_term": shared_input[0] if shared_input else "0",
            "source_data_term_unit": "days",
            "source_data_term_enabled": "true",
            "service_term_months": _at(stage1_values, index, "0"),
            "preliminary_report_term_unit": "months",
            "service_term_months_enabled": "true",
            "final_report_term_weeks": _at(stage2_values, index, "0"),
            "final_report_term_unit": "weeks",
            "evaluation_date": shared_evaluation[index] if index < len(shared_evaluation) else (
                shared_evaluation[0] if len(shared_evaluation) == 1 else ""
            ),
            "evaluation_date_enabled": "true",
        }
        rows.append(normalize_stage(raw, index + 1, raw["product_id"]))
    return rows


def _at(values, index, default=""):
    if index < len(values):
        return values[index]
    return default


def _posted_last_flag(data, key, default=True):
    values = _list_value(data, key)
    if not values:
        return default
    return enabled_flag(values[-1], default)


SIGNED_CONTRACT_STATUSES = (
    "Договор подписан ЭЦП",
    "Договор в 2 экз. отправлен почтой",
    "Договор в 2 экз. получен клиентом",
    "Договор с экз. IMCM отправлен почтой",
    "Договор с экз. IMCM получен",
)

CONTRACT_STAGE_TERM_KEYS = (
    "product_id",
    "source_data_term_enabled",
    "source_data_term",
    "source_data_term_unit",
    "source_data_date_enabled",
    "source_data_date",
    "service_term_months_enabled",
    "service_term_months",
    "preliminary_report_term_unit",
    "preliminary_report_date_enabled",
    "preliminary_report_date",
    "final_report_term_weeks",
    "final_report_term_unit",
    "final_report_date_enabled",
    "final_report_date",
    "next_stage_delay_days",
    "next_stage_delay_unit",
    "evaluation_date_enabled",
    "evaluation_date",
    "evaluation_date_common",
)


def contract_is_signed(status):
    return str(status or "") in SIGNED_CONTRACT_STATUSES


def slim_contract_stage(raw):
    source = raw if isinstance(raw, dict) else {}
    slim = {}
    for key in CONTRACT_STAGE_TERM_KEYS:
        slim[key] = source.get(key, "")
    return slim


def stage_term_days(stage):
    """Исходные данные, предварительный и итоговый сроки в днях. Лаг не входит."""
    if stage.get("source_data_term_enabled"):
        source_days = term_to_days(stage.get("source_data_term"), stage.get("source_data_term_unit"))
    else:
        source_days = Decimal("0")
    if stage.get("service_term_months_enabled"):
        preliminary_days = term_to_days(stage.get("service_term_months"), stage.get("preliminary_report_term_unit"))
    else:
        preliminary_days = Decimal("0")
    final_days = term_to_days(stage.get("final_report_term_weeks"), stage.get("final_report_term_unit"))
    total = source_days + preliminary_days + final_days
    if total < 0:
        total = Decimal("0")
    return total


def stage_term_weeks(stage):
    return days_to_term(stage_term_days(stage), "weeks")


def group_term_weeks(stages):
    total_days = Decimal("0")
    for stage in stages:
        total_days += stage_term_days(stage)
    return days_to_term(total_days, "weeks")


def group_term_days(stages):
    total_days = Decimal("0")
    for stage in stages:
        total_days += stage_term_days(stage)
    return int(total_days.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def display_date(value):
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d.%m.%Y")


def group_stages_by_contract(rows):
    groups = []
    current = None
    for row in rows:
        contract_id = str(row.get("contract_id") or "")
        if current is None or current["contract_id"] != contract_id:
            current = {
                "contract_id": contract_id,
                "contract_end": "",
                "contract_end_enabled": True,
                "rows": [],
            }
            groups.append(current)
        if not current["rows"] and "contract_end_enabled" in row:
            current["contract_end_enabled"] = bool(row.get("contract_end_enabled"))
        current["rows"].append(row)
        if not current["contract_end"] and row.get("contract_end"):
            current["contract_end"] = format_date(row.get("contract_end"))
    return groups


def _apply_contract_run(rows, contract_date):
    computed_rows = compute_stage_chain(
        contract_date,
        [
            normalize_stage(row.get("_contract_payload") or {}, index, row.get("product_id"))
            for index, row in enumerate(rows, start=1)
        ],
    )
    for row, computed in zip(rows, computed_rows):
        row["_calculated_final_report_date"] = computed.get("_calculated_final_report_date") or ""
        row["visible"] = _visible_stage(row, computed)


def _apply_project_run(rows, project_start):
    computed_rows = compute_stage_chain(project_start, rows)
    for row, computed in zip(rows, computed_rows):
        row["contract_locked"] = False
        row["_calculated_final_report_date"] = computed.get("_calculated_final_report_date") or ""
        row["visible"] = _visible_stage(row, computed)


def _visible_stage(stage, computed):
    visible = dict(stage)
    for key in CONTRACT_STAGE_TERM_KEYS:
        if key == "product_id":
            continue
        if key in computed:
            visible[key] = computed[key]
    return visible


def _last_final_date(stages):
    """Расчётная дата итогового отчёта последнего этапа, даже если её тоггл выключен."""
    for stage in reversed(list(stages or [])):
        calculated = stage.get("_calculated_final_report_date")
        if calculated:
            return calculated
        visible = stage.get("visible") if isinstance(stage.get("visible"), dict) else stage
        if visible.get("final_report_date_enabled", True) and visible.get("final_report_date"):
            return visible.get("final_report_date") or ""
    return ""


def _match_contract_stage(contract_stages, product_id, used):
    if not product_id:
        return None
    for index, item in enumerate(contract_stages):
        if index in used:
            continue
        if str(item.get("product_id") or "") == str(product_id):
            used.add(index)
            return item
    return None


def decorate_contract_term_groups(rows, contracts_by_id, project_start):
    """Группы для блока «Сроки».

    Неподписанный договор считается от даты начала проекта.
    Подписанный показывает сроки договора от даты договора и не подменяет
    сохранённые в строке сроки проекта: они остаются в исходных ключах.
    """
    groups = group_stages_by_contract(rows)
    for group in groups:
        for row in group["rows"]:
            row["contract_end"] = format_date(row.get("contract_end"))
            row["contract_id"] = str(row.get("contract_id") or "")
        contract = (contracts_by_id or {}).get(group["contract_id"]) or {}
        signed = bool(contract.get("signed"))
        group["signed"] = signed
        group["short_uid"] = contract.get("short_uid") or ""
        group["agreement_number"] = contract.get("agreement_number") or ""
        group["contract_date"] = contract.get("contract_date") or ""
        contract_stages = list(contract.get("stages") or [])
        used = set()
        if signed and contract_stages:
            for row in group["rows"]:
                payload = _match_contract_stage(contract_stages, row.get("product_id"), used)
                row["_contract_payload"] = payload
                row["contract_locked"] = payload is not None
            run = []
            for row in group["rows"]:
                if row.get("contract_locked"):
                    run.append(row)
                    continue
                if run:
                    _apply_contract_run(run, group["contract_date"])
                    run = []
            if run:
                _apply_contract_run(run, group["contract_date"])
        project_run = []
        for row in group["rows"]:
            if row.get("contract_locked"):
                if project_run:
                    _apply_project_run(project_run, project_start)
                    project_run = []
                continue
            project_run.append(row)
        if project_run:
            _apply_project_run(project_run, project_start)
        for row in group["rows"]:
            row.setdefault("contract_locked", False)
            row.setdefault("visible", dict(row))
        visible_rows = [row.get("visible") or row for row in group["rows"]]
        def column_disabled(key):
            return bool(visible_rows) and all(not item.get(key, True) for item in visible_rows)

        group["source_data_term_disabled"] = column_disabled("source_data_term_enabled")
        group["source_data_date_disabled"] = column_disabled("source_data_date_enabled")
        group["preliminary_term_disabled"] = column_disabled("service_term_months_enabled")
        group["preliminary_date_disabled"] = column_disabled("preliminary_report_date_enabled")
        group["final_date_disabled"] = column_disabled("final_report_date_enabled")
        group["completion_iso"] = format_date(_last_final_date(group["rows"]))
        group["completion_display"] = display_date(group["completion_iso"])
        group["term_weeks"] = format(group_term_weeks(visible_rows), "f")
        group["term_days"] = group_term_days(visible_rows)
        if not group["signed"]:
            group["signed"] = False
    return groups


def compute_grouped_stage_chains(project_start, stages, contract_ids):
    """Цепочка каждого договора начинается заново от даты начала проекта."""
    if not stages:
        return []
    ids = [str(item or "") for item in (contract_ids or [])]
    while len(ids) < len(stages):
        ids.append("")
    computed = []
    bucket = []
    current = None

    def flush():
        if not bucket:
            return
        computed.extend(compute_stage_chain(project_start, bucket))
        bucket.clear()

    for stage, contract_id in zip(stages, ids):
        if bucket and contract_id != current:
            flush()
        current = contract_id
        bucket.append(stage)
    flush()
    for stage in computed:
        stage.pop("_calculated_final_report_date", None)
    return computed
