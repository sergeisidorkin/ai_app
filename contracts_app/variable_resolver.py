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


# ---- Registration-level helpers (projects.registration.* / contract_terms.*) ----

def _reg_date(field_name: str):
    """Format a DateField from ProjectRegistration as ``dd.mm.yy``."""
    def _resolver(_ep: ExpertProfile, p: Performer) -> str:
        if not p.registration:
            return ""
        val = getattr(p.registration, field_name, None)
        return val.strftime("%d.%m.%y") if val else ""
    return _resolver


def _reg_short_fio(field_name: str):
    """Format a CharField from ProjectRegistration as ``Фамилия И.О.``."""
    def _resolver(_ep: ExpertProfile, p: Performer) -> str:
        if not p.registration:
            return ""
        raw = " ".join(str(getattr(p.registration, field_name, "") or "").split())
        if not raw:
            return ""
        parts = raw.split(" ")
        initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
        return f"{parts[0]} {initials}".strip()
    return _resolver


def _reg_decimal(field_name: str):
    """Format a DecimalField from ProjectRegistration as ``N,N`` (1 decimal, comma)."""
    def _resolver(_ep: ExpertProfile, p: Performer) -> str:
        if not p.registration:
            return ""
        val = getattr(p.registration, field_name, None)
        if val is None:
            return ""
        return f"{float(val):.1f}".replace(".", ",")
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

    # ---- projects.registration ----
    ("projects", "registration", "number"): lambda _ep, p: str(p.registration.number) if p.registration else "",
    ("projects", "registration", "group"): lambda _ep, p: p.registration.group if p.registration else "",
    ("projects", "registration", "agreement_type"): lambda _ep, p: p.registration.get_agreement_type_display() if p.registration else "",
    ("projects", "registration", "project_id"): _perf_project,
    ("projects", "registration", "type"): _perf_type,
    ("projects", "registration", "name"): _perf_name,
    ("projects", "registration", "status"): lambda _ep, p: p.registration.status if p.registration else "",
    ("projects", "registration", "deadline"): _reg_date("deadline"),
    ("projects", "registration", "year"): lambda _ep, p: str(p.registration.year) if p.registration and p.registration.year else "",
    ("projects", "registration", "project_manager"): _reg_short_fio("project_manager"),
    ("projects", "registration", "customer"): lambda _ep, p: p.registration.customer if p.registration else "",
    ("projects", "registration", "country"): lambda _ep, p: p.registration.country.short_name if p.registration and p.registration.country_id else "",
    ("projects", "registration", "identifier"): lambda _ep, p: p.registration.identifier if p.registration else "",
    ("projects", "registration", "registration_number"): lambda _ep, p: p.registration.registration_number if p.registration else "",
    ("projects", "registration", "date"): _reg_date("registration_date"),

    # ---- projects.contract_terms ----
    ("projects", "contract_terms", "project"): _perf_project,
    ("projects", "contract_terms", "type"): _perf_type,
    ("projects", "contract_terms", "name"): _perf_name,
    ("projects", "contract_terms", "agreement_type"): lambda _ep, p: p.registration.get_agreement_type_display() if p.registration else "",
    ("projects", "contract_terms", "agreement_number"): lambda _ep, p: p.registration.agreement_number if p.registration else "",
    ("projects", "contract_terms", "start_date"): _reg_date("contract_start"),
    ("projects", "contract_terms", "end_date"): _reg_date("contract_end"),
    ("projects", "contract_terms", "end_date_locked"): _reg_date("completion_calc"),
    ("projects", "contract_terms", "source_data"): lambda _ep, p: str(p.registration.input_data) if p.registration and p.registration.input_data is not None else "",
    ("projects", "contract_terms", "stage1_weeks"): _reg_decimal("stage1_weeks"),
    ("projects", "contract_terms", "stage1_end"): _reg_date("stage1_end"),
    ("projects", "contract_terms", "stage2_weeks"): _reg_decimal("stage2_weeks"),
    ("projects", "contract_terms", "stage2_end"): _reg_date("stage2_end"),
    ("projects", "contract_terms", "stage3_weeks"): _reg_decimal("stage3_weeks"),
    ("projects", "contract_terms", "total_weeks"): _reg_decimal("term_weeks"),
    ("projects", "contract_terms", "contract_subject"): lambda _ep, p: p.registration.contract_subject if p.registration else "",

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


def _calc_avansplat(ep, all_performers):
    """Raw Decimal avansplat_sum rounded to 1 decimal place."""
    from decimal import Decimal, ROUND_HALF_UP
    price = _calc_contract_price(ep, all_performers)
    pct = Decimal("0")
    for p in all_performers:
        if p.prepayment is not None:
            pct = p.prepayment
            break
    return (price * pct / 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _calc_finplat(ep, all_performers):
    """Raw Decimal finplat_sum = contract_price − avansplat_sum."""
    return _calc_contract_price(ep, all_performers) - _calc_avansplat(ep, all_performers)


def _kopecks(value) -> str:
    """Extract 2-digit fractional part from a Decimal, e.g. 35294.1 → '10'."""
    from decimal import Decimal
    d = value.quantize(Decimal("0.01"))
    frac = abs(d) - int(abs(d))
    return f"{frac:.2f}"[2:]


def _computed_contract_price(ep, _p, all_performers) -> str:
    return _money_no_currency_int(_calc_contract_price(ep, all_performers))


def _computed_avansplat_sum(ep, _p, all_performers) -> str:
    return _money_no_currency_int(int(_calc_avansplat(ep, all_performers)))


def _computed_finplat_sum(ep, _p, all_performers) -> str:
    return _money_no_currency_int(int(_calc_finplat(ep, all_performers)))


def _computed_avansplat_sum_kop(ep, _p, all_performers) -> str:
    return _kopecks(_calc_avansplat(ep, all_performers))


def _computed_finplat_sum_kop(ep, _p, all_performers) -> str:
    return _kopecks(_calc_finplat(ep, all_performers))


def _computed_contract_price_text(ep, _p, all_performers) -> str:
    from core.num2words_ru import number_to_words_ru
    return number_to_words_ru(int(_calc_contract_price(ep, all_performers)))


def _computed_avansplat_sum_text(ep, _p, all_performers) -> str:
    from core.num2words_ru import number_to_words_ru
    return number_to_words_ru(int(_calc_avansplat(ep, all_performers)))


def _computed_avansplat_sum_kop_text(ep, _p, all_performers) -> str:
    from core.num2words_ru import number_to_words_ru
    return number_to_words_ru(int(_kopecks(_calc_avansplat(ep, all_performers))))


def _computed_finplat_sum_text(ep, _p, all_performers) -> str:
    from core.num2words_ru import number_to_words_ru
    return number_to_words_ru(int(_calc_finplat(ep, all_performers)))


def _computed_finplat_sum_kop_text(ep, _p, all_performers) -> str:
    from core.num2words_ru import number_to_words_ru
    return number_to_words_ru(int(_kopecks(_calc_finplat(ep, all_performers))))


def _computed_deadline_ru(_ep, p, _all_performers) -> str:
    from core.dates import format_date_ru
    if not p.registration or not p.registration.deadline:
        return ""
    return format_date_ru(p.registration.deadline, "j E Y") + " г."


def _computed_year(_ep, _p, _all_performers) -> str:
    from datetime import date
    return str(date.today().year)


def _computed_day(_ep, _p, _all_performers) -> str:
    from datetime import date
    return f"{date.today().day:02d}"


def _computed_month(_ep, _p, _all_performers) -> str:
    from core.dates import MONTHS_RU_GENITIVE
    from datetime import date
    return MONTHS_RU_GENITIVE[date.today().month]


def _computed_named(ep, _p, _all_performers) -> str:
    if not ep or not ep.gender:
        return ""
    return "именуемый" if ep.gender == "male" else "именуемая"


# ---------------------------------------------------------------------------
#  List computed resolvers  (is_computed=True, key uses [[...]])
#  Signature: (ep, performer, all_performers) → list[str]
# ---------------------------------------------------------------------------

def _computed_actives_name(_ep, _p, all_performers) -> list[str]:
    seen = set()
    result = []
    for p in all_performers:
        name = p.asset_name or ""
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _computed_chapters_name(_ep, _p, all_performers):
    """Build a multi-level numbered list: assets → sections → subsections.

    Returns ``list[tuple[int, str]]`` where int is nesting level (0, 1, 2).
    If only 1 asset: sections at level 0, subsections at level 1.
    If N assets: assets at level 0, sections at level 1, subsections at level 2.
    """
    from collections import OrderedDict
    from policy_app.models import SectionStructure

    product_id = None
    assets_sections: OrderedDict[str, list] = OrderedDict()
    seen_pairs = set()
    for p in all_performers:
        asset = p.asset_name or ""
        sec = p.typical_section
        if not asset or not sec:
            continue
        if product_id is None and p.registration_id:
            product_id = p.registration.type_id
        pair = (asset, sec.pk)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        assets_sections.setdefault(asset, []).append(sec)

    section_ids = {sec.pk for secs in assets_sections.values() for sec in secs}
    subsections_map: dict[int, list[str]] = {}
    if section_ids:
        qs = SectionStructure.objects.filter(section_id__in=section_ids)
        if product_id:
            qs = qs.filter(product_id=product_id)
        for ss in qs.order_by("position"):
            lines = [ln.strip() for ln in ss.subsections.split("\n") if ln.strip()]
            if lines:
                subsections_map.setdefault(ss.section_id, []).extend(lines)

    multi_asset = len(assets_sections) > 1
    items: list[tuple[int, str]] = []

    for asset_name, sections in assets_sections.items():
        if multi_asset:
            items.append((0, asset_name))
        sec_lvl = 1 if multi_asset else 0
        sub_lvl = 2 if multi_asset else 1
        for sec in sections:
            items.append((sec_lvl, sec.name_ru))
            for sub in subsections_map.get(sec.pk, []):
                items.append((sub_lvl, sub))

    return items


def _computed_number_of_contract(_ep, performer, _all_performers) -> str:
    return performer.contract_number or ""


def _computed_contract_name(_ep, performer, _all_performers) -> str:
    from contracts_app.models import ContractSubject
    product_id = getattr(getattr(performer, "registration", None), "type_id", None)
    if not product_id:
        return ""
    cs = ContractSubject.objects.filter(product_id=product_id).first()
    return cs.subject_text if cs else ""


COMPUTED_LIST_MAP: dict[str, callable] = {
    "[[actives_name]]": _computed_actives_name,
    "[[chapters_name]]": _computed_chapters_name,
}

COMPUTED_MAP: dict[str, callable] = {
    "{{contract_price}}": _computed_contract_price,
    "{{avansplat_sum}}": _computed_avansplat_sum,
    "{{finplat_sum}}": _computed_finplat_sum,
    "{{avansplat_sum_kop}}": _computed_avansplat_sum_kop,
    "{{finplat_sum_kop}}": _computed_finplat_sum_kop,
    "{{contract_price_text}}": _computed_contract_price_text,
    "{{avansplat_sum_text}}": _computed_avansplat_sum_text,
    "{{avansplat_sum_kop_text}}": _computed_avansplat_sum_kop_text,
    "{{finplat_sum_text}}": _computed_finplat_sum_text,
    "{{finplat_sum_kop_text}}": _computed_finplat_sum_kop_text,
    "{{deadline_ru}}": _computed_deadline_ru,
    "{{year}}": _computed_year,
    "{{day}}": _computed_day,
    "{{month}}": _computed_month,
    "{{named}}": _computed_named,
    "{{number_of_contract}}": _computed_number_of_contract,
    "{{contract_name}}": _computed_contract_name,
}


def resolve_variables(
    performer, variables, all_performers=None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Build resolved values for every bound variable.

    Returns ``(scalars, lists)`` where:
    - *scalars*: ``{"{{key}}": "value", ...}``
    - *lists*:   ``{"[[key]]": ["item1", "item2", ...], ...}``

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

    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}

    for var in variables:
        if var.is_computed:
            list_fn = COMPUTED_LIST_MAP.get(var.key)
            if list_fn:
                try:
                    lists[var.key] = list_fn(expert, performer, all_performers)
                except Exception:
                    lists[var.key] = []
                continue
            computed_fn = COMPUTED_MAP.get(var.key)
            if computed_fn:
                try:
                    scalars[var.key] = computed_fn(expert, performer, all_performers)
                except Exception:
                    scalars[var.key] = ""
            continue

        coord = (var.source_section, var.source_table, var.source_column)
        resolver = FIELD_MAP.get(coord)
        if resolver is None:
            continue
        try:
            value = resolver(expert, performer)
        except Exception:
            value = ""
        scalars[var.key] = value

    return scalars, lists
