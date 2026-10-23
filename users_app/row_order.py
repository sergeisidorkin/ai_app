"""Bulk row-order specs for the users panel (see core.row_order)."""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import Employee

register_row_orders([
    RowOrderSpec(
        key="employee",
        model=Employee,
        base_filter={"user__is_staff": True},
        permission=staff_only,
    ),
    RowOrderSpec(
        key="external-employee",
        model=Employee,
        base_filter={"user__is_staff": False},
        permission=staff_only,
    ),
])
