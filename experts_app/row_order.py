"""Bulk row-order specs for the experts panel (see core.row_order)."""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import ExpertProfile, ExpertSpecialty

register_row_orders([
    RowOrderSpec(key="expert-specialty", model=ExpertSpecialty, permission=staff_only),
    RowOrderSpec(key="expert-profile", model=ExpertProfile, permission=staff_only),
])
