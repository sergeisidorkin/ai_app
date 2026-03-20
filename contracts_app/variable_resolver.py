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
    return str(ep.expertise_direction)


def _ep_specialty(ep: ExpertProfile, _p: Performer) -> str:
    if not ep:
        return ""
    first = ep.specialties.first()
    return str(first) if first else ""


def _ep_grade(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.grade_id:
        return ""
    return str(ep.grade)


def _ep_country(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.country_id:
        return ""
    return ep.country.short_name


def _ep_region(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.region_id:
        return ""
    return str(ep.region)


def _str_field(field_name: str):
    """Return a resolver that reads a CharField / TextField from ExpertProfile."""
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        return str(getattr(ep, field_name, "") or "")
    return _resolver


def _date_field(field_name: str):
    """Return a resolver that formats a DateField from ExpertProfile."""
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        val = getattr(ep, field_name, None)
        if val is None:
            return ""
        return val.strftime("%d.%m.%Y")
    return _resolver


def _int_field(field_name: str):
    """Return a resolver that reads an integer field from ExpertProfile."""
    def _resolver(ep: ExpertProfile, _p: Performer) -> str:
        if not ep:
            return ""
        val = getattr(ep, field_name, None)
        return str(val) if val is not None else ""
    return _resolver


def _gender_display(ep: ExpertProfile, _p: Performer) -> str:
    if not ep or not ep.gender:
        return ""
    return ep.get_gender_display()


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
    ("experts", "contract_details", "self_employed"): _date_field("self_employed"),
    ("experts", "contract_details", "tax_rate"): _int_field("tax_rate"),
    ("experts", "contract_details", "citizenship"): _str_field("citizenship"),
    ("experts", "contract_details", "gender"): _gender_display,
    ("experts", "contract_details", "inn"): _str_field("inn"),
    ("experts", "contract_details", "snils"): _str_field("snils"),
    ("experts", "contract_details", "birth_date"): _date_field("birth_date"),
    ("experts", "contract_details", "passport_series"): _str_field("passport_series"),
    ("experts", "contract_details", "passport_number"): _str_field("passport_number"),
    ("experts", "contract_details", "passport_issued_by"): _str_field("passport_issued_by"),
    ("experts", "contract_details", "passport_issue_date"): _date_field("passport_issue_date"),
    ("experts", "contract_details", "passport_expiry"): _date_field("passport_expiry_date"),
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
}


def resolve_variables(performer, variables) -> dict[str, str]:
    """Build {placeholder_key: resolved_value} for every bound variable.

    *performer* must have ``employee`` pre-fetched (``select_related``).
    *variables* is an iterable of ``ContractVariable`` instances whose
    ``source_section``, ``source_table``, ``source_column`` are non-empty.
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

    result: dict[str, str] = {}
    for var in variables:
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
