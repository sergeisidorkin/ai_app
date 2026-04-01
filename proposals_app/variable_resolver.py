from __future__ import annotations

import sys

from datetime import date
from decimal import Decimal, InvalidOperation


sys.modules.setdefault("proposals_app.variable_resolver", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.variable_resolver", sys.modules[__name__])


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


def _proposal_date(proposal) -> str:
    return _format_date(proposal.registration_date, "%d.%m.%y")


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


def _proposal_service_composition(proposal) -> str:
    return proposal.service_composition or ""


def _proposal_evaluation_date(proposal) -> str:
    return _format_date(proposal.evaluation_date)


def _proposal_service_term_months(proposal) -> str:
    return _format_decimal(proposal.service_term_months, precision=1)


def _proposal_preliminary_report_date(proposal) -> str:
    return _format_date(proposal.preliminary_report_date)


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
    return _format_decimal(proposal.advance_percent, strip_trailing_zeros=True)


def _proposal_advance_term_days(proposal) -> str:
    return str(proposal.advance_term_days or "")


def _proposal_preliminary_report_percent(proposal) -> str:
    return _format_decimal(proposal.preliminary_report_percent, strip_trailing_zeros=True)


def _proposal_preliminary_report_term_days(proposal) -> str:
    return str(proposal.preliminary_report_term_days or "")


def _proposal_final_report_percent(proposal) -> str:
    return _format_decimal(proposal.final_report_percent, strip_trailing_zeros=True)


def _proposal_final_report_term_days(proposal) -> str:
    return str(proposal.final_report_term_days or "")


FIELD_MAP = {
    ("proposals", "registry", "number"): _proposal_number,
    ("proposals", "registry", "group"): _proposal_group,
    ("proposals", "registry", "tkp_id"): _proposal_tkp_id,
    ("proposals", "registry", "type"): _proposal_type,
    ("proposals", "registry", "name"): _proposal_name,
    ("proposals", "registry", "kind"): _proposal_kind,
    ("proposals", "registry", "year"): _proposal_year,
    ("proposals", "registry", "customer"): _proposal_customer,
    ("proposals", "registry", "country"): _proposal_country,
    ("proposals", "registry", "country_full_name"): _proposal_country_full_name,
    ("proposals", "registry", "identifier"): _proposal_identifier,
    ("proposals", "registry", "registration_number"): _proposal_registration_number,
    ("proposals", "registry", "date"): _proposal_date,
    ("proposals", "registry", "purpose"): _proposal_purpose,
    ("proposals", "registry", "service_composition"): _proposal_service_composition,
    ("proposals", "registry", "evaluation_date"): _proposal_evaluation_date,
    ("proposals", "registry", "term"): _proposal_service_term_months,
    ("proposals", "registry", "preliminary_report_date"): _proposal_preliminary_report_date,
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


def resolve_variables(proposal, variables) -> tuple[dict[str, str], dict]:
    replacements: dict[str, str] = {}
    for variable in variables:
        key = (
            variable.source_section or "",
            variable.source_table or "",
            variable.source_column or "",
        )
        resolver = FIELD_MAP.get(key)
        if not resolver:
            continue
        replacements[variable.key] = str(resolver(proposal) or "")
    return replacements, {}
