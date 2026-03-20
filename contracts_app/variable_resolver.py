"""
Resolve ContractVariable bindings to actual values for a given Performer.

Each ContractVariable has (source_section, source_table, source_column) that
points into COLUMN_REGISTRY.  FIELD_MAP translates those coordinates into
a callable that extracts the value from ExpertProfile / Performer / related
models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experts_app.models import ExpertProfile
    from projects_app.models import Performer


def _ep_full_name(ep: ExpertProfile, _p: Performer) -> str:
    return ep.full_name if ep else ""


def _ep_email(ep: ExpertProfile, _p: Performer) -> str:
    if not ep:
        return ""
    return getattr(getattr(ep.employee, "user", None), "email", "") or ""


def _ep_phone(ep: ExpertProfile, _p: Performer) -> str:
    if not ep:
        return ""
    return getattr(ep.employee, "phone", "") or ""


def _ep_expertise_direction(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.expertise_direction_id:
        return ""
    return getattr(ep.expertise_direction, "department_name", "") or ""


def _ep_specialty(ep: ExpertProfile, _p: Performer) -> str:
    if not ep:
        return ""
    first_ranked = ep.ranked_specialties.select_related("specialty").first()
    return first_ranked.specialty.specialty if first_ranked else ""


def _ep_grade(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.grade_id:
        return ""
    return getattr(ep.grade, "grade_ru", "") or ""


def _ep_country(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.country_id:
        return ""
    return ep.country.short_name


def _ep_region(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.region_id:
        return ""
    return getattr(ep.region, "region_name", "") or ""


def _str_field(field_name: str):
    """Return a resolver that reads a CharField / TextField from ExpertProfile."""
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        return str(getattr(ep, field_name, "") or "")
    return _resolver


def _date_field(field_name: str, fmt: str = "dd.mm.YYYY"):
    """Return a resolver that formats a DateField matching the UI table.

    Supported *fmt* values (mirroring Django template filters used in tables):
      ``"dd.mm.YYYY"``  → ``15.03.2026``   (``date:"d.m.Y"``)
      ``"dd.mm.yy"``    → ``15.03.26``     (``date:"d.m.y"``)
      ``"j E Y г."``    → ``15 марта 2026 г.`` (``date_ru:"j E Y"`` + " г.")
    """
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        val = getattr(ep, field_name, None)
        if val is None:
            return ""
        if fmt == "j E Y г.":
            from core.dates import format_date_ru
            return format_date_ru(val, "j E Y") + " г."
        if fmt == "dd.mm.yy":
            return val.strftime("%d.%m.%y")
        return val.strftime("%d.%m.%Y")
    return _resolver


def _int_field(field_name: str, suffix: str = ""):
    """Return a resolver that reads an integer field from ExpertProfile."""
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        val = getattr(ep, field_name, None)
        return f"{val}{suffix}" if val is not None else ""
    return _resolver


def _gender_display(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.gender:
        return ""
    return ep.get_gender_display()


# ---- Performer-level helpers (projects.performers.*) ----

def _perf_project(_ep: ExpertProfile, p: Performer) -> str:
    return p.registration.short_uid if p.registration else ""


def _perf_type(_ep: ExpertProfile, p: Performer) -> str:
    if not p.registration or not p.registration.type:
        return ""
    return p.registration.type.short_name or str(p.registration.type)


def _perf_name(_ep: ExpertProfile, p: Performer) -> str:
    return p.registration.name if p.registration else ""


def _perf_performer(_ep: ExpertProfile, p: Performer) -> str:
    raw = " ".join(str(p.executor or "").split())
    if not raw:
        return ""
    parts = raw.split(" ")
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{parts[0]} {initials}".strip()


def _perf_grade(_ep: ExpertProfile, p: Performer) -> str:
    return p.grade_name or p.grade or ""


def _perf_typical_section(_ep: ExpertProfile, p: Performer) -> str:
    s = p.typical_section
    if not s:
        return ""
    code = getattr(s, "code", "") or ""
    short_name_ru = getattr(s, "short_name_ru", "") or ""
    return " ".join(part for part in (code, short_name_ru) if part).strip()


def _perf_money(field_name: str):
    """Format a Decimal field as ``1 234 567,89 CUR`` matching the UI."""
    def _resolver(_ep: ExpertProfile, p: Performer) -> str:
        from decimal import Decimal, InvalidOperation
        val = getattr(p, field_name, None)
        if val is None:
            return ""
        try:
            d = Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return ""
        sign = "-" if d < 0 else ""
        d = abs(d)
        integer_part = int(d)
        frac = f"{d - integer_part:.2f}"[1:]
        int_str = f"{integer_part:,}".replace(",", "\u00a0")
        result = f"{sign}{int_str}{frac}".replace(".", ",")
        if p.currency:
            result += f" {p.currency.code_alpha}"
        return result
    return _resolver


def _perf_percent(field_name: str):
    """Format a numeric field as ``NN%`` matching the UI."""
    def _resolver(_ep: ExpertProfile, p: Performer) -> str:
        val = getattr(p, field_name, None)
        if val is None:
            return ""
        return f"{int(val)}%"
    return _resolver


# ---------------------------------------------------------------------------
#  (section, table, column) → callable(expert_profile, performer) → str
# ---------------------------------------------------------------------------
FIELD_MAP: dict[tuple[str, str, str], callable] = {
    # ---- experts.experts_base ----
    ("experts", "experts_base", "full_name"): _ep_full_name,
    ("experts", "experts_base", "email"): _ep_email,
    ("experts", "experts_base", "extra_email"): _str_field("extra_email"),
    ("experts", "experts_base", "phone"): _ep_phone,
    ("experts", "experts_base", "extra_phone"): _str_field("extra_phone"),
    ("experts", "experts_base", "expertise_direction"): _ep_expertise_direction,
    ("experts", "experts_base", "specialty"): _ep_specialty,
    ("experts", "experts_base", "grade"): _ep_grade,
    ("experts", "experts_base", "country"): _ep_country,
    ("experts", "experts_base", "region"): _ep_region,
    ("experts", "experts_base", "status"): _str_field("status"),

    # ---- experts.contract_details ----
    ("experts", "contract_details", "full_name"): _ep_full_name,
    ("experts", "contract_details", "full_name_genitive"): _str_field("full_name_genitive"),
    ("experts", "contract_details", "self_employed"): _date_field("self_employed", "dd.mm.yy"),
    ("experts", "contract_details", "tax_rate"): _int_field("tax_rate", "%"),
    ("experts", "contract_details", "citizenship"): _str_field("citizenship"),
    ("experts", "contract_details", "gender"): _gender_display,
    ("experts", "contract_details", "inn"): _str_field("inn"),
    ("experts", "contract_details", "snils"): _str_field("snils"),
    ("experts", "contract_details", "birth_date"): _date_field("birth_date", "dd.mm.YYYY"),
    ("experts", "contract_details", "passport_series"): _str_field("passport_series"),
    ("experts", "contract_details", "passport_number"): _str_field("passport_number"),
    ("experts", "contract_details", "passport_issued_by"): _str_field("passport_issued_by"),
    ("experts", "contract_details", "passport_issue_date"): _date_field("passport_issue_date", "j E Y г."),
    ("experts", "contract_details", "passport_expiry"): _date_field("passport_expiry_date", "dd.mm.YYYY"),
    ("experts", "contract_details", "passport_division_code"): _str_field("passport_division_code"),
    ("experts", "contract_details", "registration_address"): _str_field("registration_address"),
    ("experts", "contract_details", "bank_name"): _str_field("bank_name"),
    ("experts", "contract_details", "swift"): _str_field("bank_swift"),
    ("experts", "contract_details", "bank_inn"): _str_field("bank_inn"),
    ("experts", "contract_details", "bik"): _str_field("bank_bik"),
    ("experts", "contract_details", "settlement_account"): _str_field("settlement_account"),
    ("experts", "contract_details", "correspondent_account"): _str_field("corr_account"),
    ("experts", "contract_details", "bank_address"): _str_field("bank_address"),
    ("experts", "contract_details", "corr_bank_name"): _str_field("corr_bank_name"),
    ("experts", "contract_details", "corr_bank_address"): _str_field("corr_bank_address"),
    ("experts", "contract_details", "corr_bank_bik"): _str_field("corr_bank_bik"),
    ("experts", "contract_details", "corr_bank_swift"): _str_field("corr_bank_swift"),
    ("experts", "contract_details", "corr_bank_settlement"): _str_field("corr_bank_settlement_account"),
    ("experts", "contract_details", "corr_bank_correspondent"): _str_field("corr_bank_corr_account"),

    # ---- projects.performers ----
    ("projects", "performers", "project"): _perf_project,
    ("projects", "performers", "type"): _perf_type,
    ("projects", "performers", "name"): _perf_name,
    ("projects", "performers", "asset_name"): lambda _ep, p: p.asset_name or "",
    ("projects", "performers", "performer"): _perf_performer,
    ("projects", "performers", "grade"): _perf_grade,
    ("projects", "performers", "typical_section"): _perf_typical_section,
    ("projects", "performers", "adjusted_costs"): _perf_money("actual_costs"),
    ("projects", "performers", "calculated_costs"): _perf_money("estimated_costs"),
    ("projects", "performers", "approved"): _perf_money("agreed_amount"),
    ("projects", "performers", "advance"): _perf_percent("prepayment"),
    ("projects", "performers", "final_payment"): _perf_percent("final_payment"),
    ("projects", "performers", "contract_number"): lambda _ep, p: p.contract_number or "",
}


# ---------------------------------------------------------------------------
#  Computed variable resolvers  (is_computed=True)
#  Signature: (ep, performer, all_performers) → str
# ---------------------------------------------------------------------------

def _money_no_currency(value) -> str:
    """Format a Decimal as ``1 234 567,89`` (no currency code)."""
    from decimal import Decimal, InvalidOperation
    if value is None:
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if d < 0 else ""
    d = abs(d)
    integer_part = int(d)
    frac = f"{d - integer_part:.2f}"[1:]
    int_str = f"{integer_part:,}".replace(",", "\u00a0")
    return f"{sign}{int_str}{frac}".replace(".", ",")


def _money_no_currency_int(value) -> str:
    """Format an integer as ``1 234 567`` (no decimals, no currency code)."""
    if value is None:
        return ""
    n = int(value)
    sign = "-" if n < 0 else ""
    int_str = f"{abs(n):,}".replace(",", "\u00a0")
    return f"{sign}{int_str}"


def _calc_contract_price(ep, all_performers):
    """Raw Decimal contract_price rounded to integer."""
    from decimal import Decimal, ROUND_HALF_UP
    total = Decimal("0")
    for p in all_performers:
        if p.agreed_amount is not None:
            total += p.agreed_amount
    tax_rate = 0
    if ep and ep.tax_rate is not None:
        tax_rate = int(ep.tax_rate)
    divisor = 1 - Decimal(tax_rate) / 100
    if divisor:
        result = total / divisor
    else:
        result = total
    return result.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _computed_contract_price(ep, _p, all_performers) -> str:
    return _money_no_currency(_calc_contract_price(ep, all_performers))


def _computed_avansplat_sum(ep, _p, all_performers) -> str:
    from decimal import Decimal, ROUND_HALF_UP
    price = _calc_contract_price(ep, all_performers)
    pct = Decimal("0")
    for p in all_performers:
        if p.prepayment is not None:
            pct = p.prepayment
            break
    result = (price * pct / 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return _money_no_currency(result)


def _computed_finplat_sum(ep, _p, all_performers) -> str:
    from decimal import Decimal, ROUND_HALF_UP
    price = _calc_contract_price(ep, all_performers)
    pct = Decimal("0")
    for p in all_performers:
        if p.prepayment is not None:
            pct = p.prepayment
            break
    avans = (price * pct / 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    result = price - avans
    return _money_no_currency(result)


COMPUTED_MAP: dict[str, callable] = {
    "{{contract_price}}": _computed_contract_price,
    "{{avansplat_sum}}": _computed_avansplat_sum,
    "{{finplat_sum}}": _computed_finplat_sum,
}


def resolve_variables(performer, variables, all_performers=None) -> dict[str, str]:
    """Build {placeholder_key: resolved_value} for every bound variable.

    *performer* must have ``employee`` pre-fetched (``select_related``).
    *variables* is an iterable of ``ContractVariable`` instances.
    *all_performers* is the list of all selected Performer rows for this
    executor+project pair (needed for computed / aggregate variables).
    """
    from experts_app.models import ExpertProfile

    expert: ExpertProfile | None = None
    if performer.employee_id:
        expert = (
            ExpertProfile.objects
            .select_related("employee__user", "country", "region",
                            "expertise_direction", "grade")
            .filter(employee_id=performer.employee_id)
            .first()
        )

    if all_performers is None:
        all_performers = [performer]

    result: dict[str, str] = {}
    for var in variables:
        if var.is_computed:
            computed_fn = COMPUTED_MAP.get(var.key)
            if computed_fn:
                try:
                    result[var.key] = computed_fn(expert, performer, all_performers)
                except Exception:
                    result[var.key] = ""
            continue

        coord = (var.source_section, var.source_table, var.source_column)
        resolver = FIELD_MAP.get(coord)
        if resolver is None:
            continue
        try:
            value = resolver(expert, performer)
        except Exception:
            value = ""
        result[var.key] = value

    return result
