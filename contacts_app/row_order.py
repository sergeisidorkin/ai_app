"""Bulk row-order specs for the contacts panel (see core.row_order)."""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import (
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    ResidenceAddressRecord,
    SpecialtyRecord,
)

register_row_orders([
    RowOrderSpec(key="prs", model=PersonRecord),
    RowOrderSpec(key="ctz", model=CitizenshipRecord, permission=staff_only),
    RowOrderSpec(key="adr", model=ResidenceAddressRecord, permission=staff_only),
    RowOrderSpec(key="psn", model=PositionRecord),
    RowOrderSpec(key="tel", model=PhoneRecord, permission=staff_only),
    RowOrderSpec(key="eml", model=EmailRecord, permission=staff_only),
    RowOrderSpec(key="spc", model=SpecialtyRecord, permission=staff_only),
])
