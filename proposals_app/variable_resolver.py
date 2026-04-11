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
}

VARIABLE_ALIASES = {
    "{{client_country_full_name}}": ["{{country_full_name}}"],
    "{{country_full_name}}": ["{{client_country_full_name}}"],
}


def resolve_variables(proposal, variables) -> tuple[dict[str, str], dict]:
    replacements: dict[str, str] = {}
    list_replacements: dict[str, list[str]] = {}
    for variable in variables:
        if getattr(variable, "is_computed", False):
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
    return replacements, list_replacements
