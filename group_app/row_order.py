"""Bulk row-order specs for the group panel (see core.row_order)."""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import GroupMember, OrgUnit, resequence_group_members


def _resequence_members(request, result):
    if result.moved_ids:
        resequence_group_members()


register_row_orders([
    RowOrderSpec(
        key="group-member",
        model=GroupMember,
        permission=staff_only,
        after_save=_resequence_members,
    ),
    RowOrderSpec(
        key="org-unit",
        model=OrgUnit,
        permission=staff_only,
    ),
])
