"""Bulk row-order specs for ТКП reference tables (see core.row_order).

The ТКП registry keeps its dedicated endpoint (``proposal_row_order``).
"""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import ProposalTemplate, ProposalVariable

register_row_orders([
    RowOrderSpec(key="proposal-template", model=ProposalTemplate, permission=staff_only),
    RowOrderSpec(key="proposal-variable", model=ProposalVariable, permission=staff_only),
])
