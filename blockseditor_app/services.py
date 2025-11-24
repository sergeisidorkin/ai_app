from __future__ import annotations
from typing import Dict, Iterable, Tuple
from django.db import transaction
from .models import BlockNode

DEFAULT_LAYOUT = (
    {
        "slug": "checklist",
        "title": "Статус чек-листа",
        "node_type": BlockNode.NodeType.CHECKLIST,
        "position_x": 40,
        "position_y": 40,
        "display_order": 10,
    },
    {
        "slug": "agent",
        "title": "Агент",
        "node_type": BlockNode.NodeType.AGENT,
        "position_x": 520,
        "position_y": 40,
        "display_order": 20,
    },
)

MAX_COORDINATE = 5000

def ensure_block_layout(block) -> Tuple[Iterable[BlockNode], Dict[str, BlockNode]]:
    with transaction.atomic():
        existing = {
            node.slug: node
            for node in block.editor_nodes.select_for_update()
        }

        missing = []
        for spec in DEFAULT_LAYOUT:
            if spec["slug"] not in existing:
                missing.append(BlockNode(block=block, **spec))

        if missing:
            BlockNode.objects.bulk_create(missing)
            existing.update(
                {node.slug: node for node in block.editor_nodes.filter(slug__in=[m.slug for m in missing])}
            )

    nodes = block.editor_nodes.order_by("display_order", "pk")
    return nodes, {node.slug: node for node in nodes}

def clamp_coordinate(value: int) -> int:
    if value is None:
        return 0
    return max(0, min(int(value), MAX_COORDINATE))