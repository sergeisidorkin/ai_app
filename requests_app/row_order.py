"""Bulk row-order spec for request tables (see core.row_order).

Rows are ordered inside their ``RequestTable``; the «все разделы» view shows several
tables at once, so the scope keeps moves from crossing section boundaries.
The per-row move views have no authentication requirement; this mirrors that.
"""
from core.row_order import RowOrderSpec, register_row_orders

from .models import RequestItem

register_row_orders([
    RowOrderSpec(
        key="request-item",
        model=RequestItem,
        scope_fields=("table_id",),
        login_required=False,
    ),
])
