"""Bulk row-order spec for checklist items (see core.row_order).

Mirrors ``checklists_app.views.item_move``: items are ordered inside
(project, section, item type, additional request number) and the section is
renumbered after the move.
"""
from django.db.models import Q

from core.row_order import RowOrderSpec, register_row_orders

from .models import ChecklistItem


def _scope_key(item):
    if item.item_type == ChecklistItem.ItemType.ADDITIONAL and item.additional_number is not None:
        return (item.project_id, item.section_id, ChecklistItem.ItemType.ADDITIONAL, item.additional_number)
    return (item.project_id, item.section_id, ChecklistItem.ItemType.BASIC, None)


def _scope_filter(scope_key):
    project_id, section_id, item_type, additional_number = scope_key
    q = Q(project_id=project_id, section_id=section_id)
    if item_type == ChecklistItem.ItemType.ADDITIONAL:
        return q & Q(item_type=ChecklistItem.ItemType.ADDITIONAL, additional_number=additional_number)
    return q & Q(item_type=ChecklistItem.ItemType.BASIC)


def _renumber_sections(request, result):
    # Imported lazily to avoid importing the views module during app loading.
    from .views import _renumber_checklist_items

    touched = {}
    for scope in result.scopes:
        if not scope.moved_ids:
            continue
        project_id, section_id = scope.scope_key[0], scope.scope_key[1]
        touched.setdefault(project_id, set()).add(section_id)
    for project_id, section_ids in touched.items():
        _renumber_checklist_items(project_id, section_ids)


register_row_orders([
    RowOrderSpec(
        key="checklist-item",
        model=ChecklistItem,
        scope_fields=("project_id", "section_id", "item_type", "additional_number"),
        scope_key=_scope_key,
        scope_filter=_scope_filter,
        after_save=_renumber_sections,
        events={"checklists:saved": True},
    ),
])
