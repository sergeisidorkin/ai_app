from __future__ import annotations

import sys

from datetime import date
from decimal import Decimal, InvalidOperation

from policy_app.models import ServiceGoalReport

sys.modules.setdefault("proposals_app.variable_resolver", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.variable_resolver", sys.modules[__name__])


def _today() -> date:
    return date.today()


def _proposal_number(proposal) -> str:
    return str(proposal.number or "")


def _proposal_group(proposal) -> str:
    return proposal.group_display or ""


def _proposal_tkp_id(proposal) -> str:
    return proposal.short_uid or ""


def _proposal_type(proposal) -> str:
    if not proposal.type_id:
        return ""
    return proposal.type.short_name or str(proposal.type)


def _proposal_name(proposal) -> str:
    return proposal.name or ""


def _proposal_kind(proposal) -> str:
    return proposal.get_kind_display() or ""


def _proposal_status(proposal) -> str:
    return proposal.get_status_display() or ""


def _proposal_year(proposal) -> str:
    return str(proposal.year or "")


def _proposal_customer(proposal) -> str:
    return proposal.customer or ""


def _proposal_country(proposal) -> str:
    if not proposal.country_id:
        return ""
    return proposal.country.short_name or proposal.country.full_name or ""


def _proposal_country_full_name(proposal) -> str:
    if not proposal.country_id:
        return ""
    return proposal.country.full_name or proposal.country.short_name or ""


def _proposal_identifier(proposal) -> str:
    return proposal.identifier or ""


def _proposal_registration_number(proposal) -> str:
    return proposal.registration_number or ""


def _proposal_registration_region(proposal) -> str:
    return proposal.registration_region or ""


def _proposal_date(proposal) -> str:
    return _format_date(proposal.registration_date, "%d.%m.%y")


def _proposal_asset_owner(proposal) -> str:
    return proposal.asset_owner or ""


def _proposal_asset_owner_country(proposal) -> str:
    if not proposal.asset_owner_country_id:
        return ""
    return proposal.asset_owner_country.short_name or proposal.asset_owner_country.full_name or ""


def _proposal_asset_owner_country_full_name(proposal) -> str:
    if not proposal.asset_owner_country_id:
        return ""
    return proposal.asset_owner_country.full_name or proposal.asset_owner_country.short_name or ""


def _proposal_client_owner_name(proposal) -> str:
    customer = str(getattr(proposal, "customer", "") or "").strip()
    if getattr(proposal, "asset_owner_matches_customer", True):
        return customer
    asset_owner = str(getattr(proposal, "asset_owner", "") or "").strip()
    if customer and asset_owner:
        return f"{customer} / {asset_owner}"
    return customer or asset_owner


def _proposal_service_type_short(proposal) -> str:
    full = str(getattr(proposal, "proposal_project_name", "") or "").strip()
    suffix = str(getattr(proposal, "asset_owner", "") or "").strip()
    if not full:
        return ""
    if suffix and full == suffix:
        return ""
    if suffix and full.endswith(" " + suffix):
        return full[: len(full) - len(suffix)].strip()
    return full


def _proposal_actives_name_list(proposal) -> list[str]:
    if not getattr(proposal, "pk", None):
        return []
    from proposals_app.models import ProposalAsset

    seen = set()
    result = []
    for asset in ProposalAsset.objects.filter(proposal_id=proposal.pk).order_by("position", "id").only("short_name"):
        name = str(asset.short_name or "").strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _proposal_asset_owner_identifier(proposal) -> str:
    return proposal.asset_owner_identifier or ""


def _proposal_asset_owner_registration_number(proposal) -> str:
    return proposal.asset_owner_registration_number or ""


def _proposal_asset_owner_region(proposal) -> str:
    if getattr(proposal, "asset_owner_matches_customer", False):
        return proposal.registration_region or ""
    return proposal.asset_owner_region or ""


def _proposal_asset_owner_registration_date(proposal) -> str:
    return _format_date(proposal.asset_owner_registration_date, "%d.%m.%y")


def _proposal_project_name(proposal) -> str:
    return proposal.proposal_project_name or ""


def _format_date(value, fmt="%d.%m.%Y") -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime(fmt)
    try:
        return date.fromisoformat(str(value)).strftime(fmt)
    except (TypeError, ValueError):
        return str(value)


def _format_decimal(value, precision=2, *, strip_trailing_zeros=False) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    text = f"{number:.{precision}f}".replace(".", ",")
    if strip_trailing_zeros and "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def _format_percent(value, precision=2, *, strip_trailing_zeros=False) -> str:
    text = _format_decimal(value, precision=precision, strip_trailing_zeros=strip_trailing_zeros)
    return f"{text}%" if text else ""


def _format_money(value) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if number < 0 else ""
    number = abs(number)
    integer_part = int(number)
    frac = f"{number - integer_part:.2f}"[1:]
    int_str = f"{integer_part:,}".replace(",", "\u00a0")
    return f"{sign}{int_str}{frac}".replace(".", ",")


def _proposal_purpose(proposal) -> str:
    return proposal.purpose or ""


def _proposal_service_goal_genitive(proposal) -> str:
    if not getattr(proposal, "type_id", None):
        return ""
    item = (
        ServiceGoalReport.objects.filter(product_id=proposal.type_id)
        .order_by("position", "id")
        .only("service_goal_genitive")
        .first()
    )
    if not item:
        return ""
    return item.service_goal_genitive or ""


def _proposal_tkp_preliminary(proposal) -> str:
    try:
        from proposals_app.models import ProposalRegistration

        if getattr(proposal, "status", "") == ProposalRegistration.ProposalStatus.PRELIMINARY:
            return "(предварительное)"
    except Exception:
        if getattr(proposal, "status", "") == "preliminary":
            return "(предварительное)"
    return ""


def _proposal_service_composition(proposal) -> str:
    return proposal.service_composition or ""


def _proposal_scope_of_work(proposal) -> list[dict[str, str] | str]:
    def build_item(html_value, plain_text_value):
        html = str(html_value or "").strip()
        plain_text = str(plain_text_value or "").strip()
        if html:
            return {"html": html}
        if not plain_text:
            return None
        chunks = [chunk.strip() for chunk in plain_text.split("\n\n") if chunk.strip()]
        if len(chunks) <= 1:
            return plain_text
        return chunks

    mode = str(getattr(proposal, "service_composition_mode", "") or "sections").strip()
    if mode == "customer_tz":
        stored = getattr(proposal, "service_customer_tz_editor_state", {}) or {}
        item = build_item(
            stored.get("html") if isinstance(stored, dict) else "",
            stored.get("plain_text") if isinstance(stored, dict) else getattr(proposal, "service_composition_customer_tz", ""),
        )
        if item is None:
            fallback = build_item("", getattr(proposal, "service_composition_customer_tz", ""))
            if fallback is None:
                return []
            return fallback if isinstance(fallback, list) else [fallback]
        return item if isinstance(item, list) else [item]

    result: list[dict[str, str] | str] = []
    stored_sections = getattr(proposal, "service_sections_editor_state", []) or []
    if isinstance(stored_sections, list):
        for section in stored_sections:
            if not isinstance(section, dict):
                continue
            item = build_item(section.get("html"), section.get("plain_text"))
            if item is None:
                continue
            if isinstance(item, list):
                result.extend(item)
            else:
                result.append(item)
    if result:
        return result

    fallback = build_item("", getattr(proposal, "service_composition", ""))
    if fallback is None:
        return []
    return fallback if isinstance(fallback, list) else [fallback]


PROPOSAL_TRAVEL_EXPENSES_LABEL = "Командировочные расходы"
PROPOSAL_SUMMARY_TOTAL_LABEL = "ИТОГО, по расчёту"
PROPOSAL_RUB_TOTAL_LABEL = "ИТОГО, рубли без НДС"
PROPOSAL_RUB_DISCOUNTED_LABEL = "ИТОГО, рубли без НДС с учетом скидки"
PROPOSAL_CONTRACT_TOTAL_LABEL = "ИТОГО в договор, рубли без НДС с учётом доп. скидки"


def _parse_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _sum_day_counts(values) -> int:
    total = 0
    for value in values:
        try:
            total += int(str(value or "").strip() or "0")
        except (TypeError, ValueError):
            continue
    return total


def _round_to_hundred_thousand(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return (value // Decimal("100000")) * Decimal("100000")


def _proposal_budget_table(proposal) -> dict:
    offers = list(proposal.commercial_offers.order_by("position", "id"))
    travel_offer = next(
        (
            item
            for item in offers
            if str(getattr(item, "service_name", "") or "").strip() == PROPOSAL_TRAVEL_EXPENSES_LABEL
        ),
        None,
    )
    regular_offers = [
        item
        for item in offers
        if str(getattr(item, "service_name", "") or "").strip() != PROPOSAL_TRAVEL_EXPENSES_LABEL
    ]

    asset_labels = [
        str(getattr(asset, "short_name", "") or "").strip()
        for asset in proposal.assets.order_by("position", "id")
    ]
    max_asset_count = max(
        [len(getattr(item, "asset_day_counts", []) or []) for item in offers],
        default=0,
    )
    asset_count = max(len(asset_labels), max_asset_count, 1)
    while len(asset_labels) < asset_count:
        asset_labels.append(f"Актив {len(asset_labels) + 1}")
    asset_labels = [label or f"Актив {index + 1}" for index, label in enumerate(asset_labels)]

    rows: list[list[dict[str, object]]] = [
        [
            {"text": "Специалист", "bold": True, "align": "left", "header": True, "vertical_align": "center"},
            {"text": "Должность/направление", "bold": True, "align": "left", "header": True, "vertical_align": "center"},
            {"text": "Ставка,\n€/дн", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
            *[
                {
                    "text": label,
                    "bold": True,
                    "align": "center",
                    "header": True,
                    "vertical_align": "center",
                    "margins_cm": {
                        "top": 0,
                        "right": 0,
                        "bottom": 0,
                        "left": 0,
                    },
                }
                for label in asset_labels
            ],
            {"text": "Кол-во\nдней", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
            {"text": "Итого,\n€ без НДС", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
        ],
    ]

    def build_day_values(raw_values) -> list[str]:
        normalized = [str(value or "").strip() for value in list(raw_values or [])[:asset_count]]
        while len(normalized) < asset_count:
            normalized.append("")
        return normalized

    for item in regular_offers:
        day_values = build_day_values(getattr(item, "asset_day_counts", []) or [])
        direction = ", ".join(
            [
                value
                for value in [
                    str(getattr(item, "job_title", "") or "").strip(),
                    str(getattr(item, "professional_status", "") or "").strip(),
                ]
                if value
            ]
        )
        rows.append(
            [
                {"text": str(getattr(item, "specialist", "") or "").strip()},
                {"text": direction},
                {"text": _format_money(getattr(item, "rate_eur_per_day", None)), "align": "right"},
                *[
                    {"text": value, "align": "right"}
                    for value in day_values
                ],
                {"text": str(_sum_day_counts(day_values)) if _sum_day_counts(day_values) else "", "align": "right"},
                {"text": _format_money(getattr(item, "total_eur_without_vat", None)), "align": "right"},
            ]
        )

    summary_day_values = [
        str(value) if value else ""
        for value in (
            [
                sum(
                    int(str((getattr(item, "asset_day_counts", []) or [""])[index] or "").strip() or "0")
                    for item in regular_offers
                    if index < len(getattr(item, "asset_day_counts", []) or [])
                )
                for index in range(asset_count)
            ]
            if asset_count
            else []
        )
    ]
    summary_total = sum(
        (_parse_decimal(getattr(item, "total_eur_without_vat", None)) or Decimal("0"))
        for item in regular_offers
    )
    totals_state = getattr(proposal, "commercial_totals_json", {}) or {}
    exchange_rate = _parse_decimal(totals_state.get("exchange_rate"))
    discount_percent = _parse_decimal(totals_state.get("discount_percent"))
    rub_total = (summary_total * exchange_rate) if exchange_rate is not None else None
    discounted_total = (
        rub_total - (rub_total * (discount_percent / Decimal("100")))
        if rub_total is not None and discount_percent is not None
        else rub_total
    )
    contract_total = _parse_decimal(totals_state.get("contract_total"))
    contract_total_auto = _parse_decimal(totals_state.get("contract_total_auto"))
    if contract_total in (None, Decimal("0")):
        contract_total = contract_total_auto or _round_to_hundred_thousand(discounted_total)

    def append_fixed_row(label, *, rate="", day_values=None, total="", label_colspan=2):
        current_day_values = list(day_values or [])
        while len(current_day_values) < asset_count:
            current_day_values.append("")
        rows.append(
            [
                {"text": label, "colspan": label_colspan, "bold": True},
                {"text": str(rate or ""), "align": "right"},
                *[
                    {"text": str(value or ""), "align": "right"}
                    for value in current_day_values
                ],
                {"text": str(_sum_day_counts(current_day_values)) if _sum_day_counts(current_day_values) else "", "align": "right"},
                {"text": str(total or ""), "align": "right"},
            ]
        )

    if travel_offer is not None:
        travel_day_values = build_day_values(getattr(travel_offer, "asset_day_counts", []) or [])
        append_fixed_row(
            PROPOSAL_TRAVEL_EXPENSES_LABEL,
            rate="по факту",
            day_values=travel_day_values,
            total=_format_money(getattr(travel_offer, "total_eur_without_vat", None)),
        )

    append_fixed_row(
        PROPOSAL_SUMMARY_TOTAL_LABEL,
        rate="",
        day_values=summary_day_values,
        total=_format_money(summary_total),
    )
    append_fixed_row(
        PROPOSAL_RUB_TOTAL_LABEL,
        rate=_format_decimal(exchange_rate, precision=4, strip_trailing_zeros=True),
        day_values=[],
        total=_format_money(rub_total),
    )
    append_fixed_row(
        PROPOSAL_RUB_DISCOUNTED_LABEL,
        rate=_format_percent(discount_percent, strip_trailing_zeros=True),
        day_values=[],
        total=_format_money(discounted_total),
    )
    append_fixed_row(
        PROPOSAL_CONTRACT_TOTAL_LABEL,
        rate="",
        day_values=[],
        total=_format_money(contract_total),
    )

    return {
        "rows": rows,
        "font_size_pt": 7,
        "style": "Table Grid",
    }


def _proposal_evaluation_date(proposal) -> str:
    return _format_date(proposal.evaluation_date)


def _proposal_service_term_months(proposal) -> str:
    return _format_decimal(proposal.service_term_months, precision=1)


def _proposal_preliminary_report_term_month(proposal) -> str:
    if getattr(proposal, "service_term_months", None) in (None, ""):
        return ""
    try:
        months = Decimal(str(proposal.service_term_months))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if months == Decimal("1"):
        suffix = "месяц"
    elif months < Decimal("5"):
        suffix = "месяца"
    else:
        suffix = "месяцев"
    return f"{_format_decimal(months, precision=1, strip_trailing_zeros=True)} {suffix}"


def _proposal_preliminary_report_date(proposal) -> str:
    return _format_date(proposal.preliminary_report_date)


def _proposal_final_report_term_weeks(proposal) -> str:
    return _format_decimal(proposal.final_report_term_weeks, precision=1)


def _proposal_final_report_date(proposal) -> str:
    return _format_date(proposal.final_report_date)


def _proposal_report_languages(proposal) -> str:
    return proposal.report_languages or ""


def _proposal_service_cost(proposal) -> str:
    return _format_money(proposal.service_cost)


def _proposal_currency(proposal) -> str:
    if not proposal.currency_id:
        return ""
    return proposal.currency.code_alpha or str(proposal.currency)


def _proposal_advance_percent(proposal) -> str:
    return _format_percent(proposal.advance_percent, strip_trailing_zeros=True)


def _proposal_advance_term_days(proposal) -> str:
    return str(proposal.advance_term_days or "")


def _proposal_preliminary_report_percent(proposal) -> str:
    return _format_percent(proposal.preliminary_report_percent, strip_trailing_zeros=True)


def _proposal_preliminary_payment_percentage_full(proposal) -> str:
    try:
        advance = Decimal(str(getattr(proposal, "advance_percent", "") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        advance = Decimal("0")
    try:
        preliminary = Decimal(str(getattr(proposal, "preliminary_report_percent", "") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        preliminary = Decimal("0")
    return _format_percent(advance + preliminary, strip_trailing_zeros=True)


def _proposal_preliminary_report_term_days(proposal) -> str:
    return str(proposal.preliminary_report_term_days or "")


def _proposal_final_report_percent(proposal) -> str:
    return _format_percent(proposal.final_report_percent, strip_trailing_zeros=True)


def _proposal_final_report_term_days(proposal) -> str:
    return str(proposal.final_report_term_days or "")


def _computed_year(_proposal) -> str:
    return str(_today().year)


def _computed_day(_proposal) -> str:
    return f"{_today().day:02d}"


def _computed_month(_proposal) -> str:
    from core.dates import MONTHS_RU_GENITIVE

    return MONTHS_RU_GENITIVE[_today().month]


FIELD_MAP = {
    ("proposals", "registry", "number"): _proposal_number,
    ("proposals", "registry", "group"): _proposal_group,
    ("proposals", "registry", "tkp_id"): _proposal_tkp_id,
    ("proposals", "registry", "type"): _proposal_type,
    ("proposals", "registry", "name"): _proposal_name,
    ("proposals", "registry", "kind"): _proposal_kind,
    ("proposals", "registry", "status"): _proposal_status,
    ("proposals", "registry", "year"): _proposal_year,
    ("proposals", "registry", "customer"): _proposal_customer,
    ("proposals", "registry", "country"): _proposal_country,
    ("proposals", "registry", "country_full_name"): _proposal_country_full_name,
    ("proposals", "registry", "identifier"): _proposal_identifier,
    ("proposals", "registry", "registration_number"): _proposal_registration_number,
    ("proposals", "registry", "registration_region"): _proposal_registration_region,
    ("proposals", "registry", "date"): _proposal_date,
    ("proposals", "registry", "asset_owner"): _proposal_asset_owner,
    ("proposals", "registry", "asset_owner_country"): _proposal_asset_owner_country,
    ("proposals", "registry", "asset_owner_identifier"): _proposal_asset_owner_identifier,
    ("proposals", "registry", "asset_owner_registration_number"): _proposal_asset_owner_registration_number,
    ("proposals", "registry", "asset_owner_region"): _proposal_asset_owner_region,
    ("proposals", "registry", "asset_owner_registration_date"): _proposal_asset_owner_registration_date,
    ("proposals", "registry", "proposal_project_name"): _proposal_project_name,
    ("proposals", "registry", "purpose"): _proposal_purpose,
    ("proposals", "registry", "service_composition"): _proposal_service_composition,
    ("proposals", "registry", "evaluation_date"): _proposal_evaluation_date,
    ("proposals", "registry", "term"): _proposal_service_term_months,
    ("proposals", "registry", "preliminary_report_date"): _proposal_preliminary_report_date,
    ("proposals", "registry", "final_report_term_weeks"): _proposal_final_report_term_weeks,
    ("proposals", "registry", "final_report_date"): _proposal_final_report_date,
    ("proposals", "registry", "report_languages"): _proposal_report_languages,
    ("proposals", "registry", "service_cost"): _proposal_service_cost,
    ("proposals", "registry", "currency"): _proposal_currency,
    ("proposals", "registry", "advance_percent"): _proposal_advance_percent,
    ("proposals", "registry", "advance_term"): _proposal_advance_term_days,
    ("proposals", "registry", "preliminary_report_percent"): _proposal_preliminary_report_percent,
    ("proposals", "registry", "preliminary_report_term"): _proposal_preliminary_report_term_days,
    ("proposals", "registry", "final_report_percent"): _proposal_final_report_percent,
    ("proposals", "registry", "final_report_term"): _proposal_final_report_term_days,
}


COMPUTED_MAP = {
    "{{year}}": _computed_year,
    "{{day}}": _computed_day,
    "{{month}}": _computed_month,
    "{{client_country_full_name}}": _proposal_country_full_name,
    "{{client_owner_name}}": _proposal_client_owner_name,
    "{{service_type_short}}": _proposal_service_type_short,
    "{{service_goal_genitive}}": _proposal_service_goal_genitive,
    "{{tkp_preliminary}}": _proposal_tkp_preliminary,
    "{{preliminary_payment_percentage_full}}": _proposal_preliminary_payment_percentage_full,
    "{{preliminary_report_term_month}}": _proposal_preliminary_report_term_month,
    "{{owner_country_full_name}}": _proposal_asset_owner_country_full_name,
    "{{country_full_name}}": _proposal_country_full_name,
}

COMPUTED_LIST_MAP = {
    "[[actives_name]]": _proposal_actives_name_list,
    "[[scope_of_work]]": _proposal_scope_of_work,
}

COMPUTED_TABLE_MAP = {
    "[[budget_table]]": _proposal_budget_table,
}

VARIABLE_ALIASES = {
    "{{client_country_full_name}}": ["{{country_full_name}}"],
    "{{country_full_name}}": ["{{client_country_full_name}}"],
}


def resolve_variables(proposal, variables) -> tuple[dict[str, str], dict, dict]:
    replacements: dict[str, str] = {}
    list_replacements: dict[str, list[str]] = {}
    table_replacements: dict[str, dict] = {}
    for variable in variables:
        if getattr(variable, "is_computed", False):
            computed_table_resolver = COMPUTED_TABLE_MAP.get(variable.key)
            if computed_table_resolver:
                table_replacements[variable.key] = computed_table_resolver(proposal) or {}
                continue
            computed_list_resolver = COMPUTED_LIST_MAP.get(variable.key)
            if computed_list_resolver:
                list_replacements[variable.key] = list(computed_list_resolver(proposal) or [])
                continue
            computed_resolver = COMPUTED_MAP.get(variable.key)
            if computed_resolver:
                value = str(computed_resolver(proposal) or "")
                replacements[variable.key] = value
                for alias in VARIABLE_ALIASES.get(variable.key, []):
                    replacements[alias] = value
            continue
        key = (
            variable.source_section or "",
            variable.source_table or "",
            variable.source_column or "",
        )
        resolver = FIELD_MAP.get(key)
        if not resolver:
            continue
        value = str(resolver(proposal) or "")
        replacements[variable.key] = value
        for alias in VARIABLE_ALIASES.get(variable.key, []):
            replacements[alias] = value
    return replacements, list_replacements, table_replacements
