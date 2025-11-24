import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from blocks_app.models import Block

from .models import BlockNode
from .services import clamp_coordinate, ensure_block_layout

try:
    from openai_app.service import get_available_models
except Exception:
    def get_available_models(_user):
        return []

def _build_dashboard_url(block):
    product_short = ""
    if block.product and block.product.short_name:
        product_short = block.product.short_name.upper()

    params = {
        "tab": "templates",
        "product": product_short,
        "section": block.section_id or "",
    }
    return f"{reverse('blocks_app:dashboard_partial')}?{urlencode(params)}"

def _common_context(block, request):
    models = get_available_models(request.user) or []
    nodes, nodes_by_slug = ensure_block_layout(block)
    return {
        "block": block,
        "llm_models": models,
        "dashboard_url": _build_dashboard_url(block),
        "editor_nodes": nodes,
        "editor_nodes_map": nodes_by_slug,
    }

@login_required
def editor(request, block_id):
    block = get_object_or_404(Block, pk=block_id)
    return render(request, "blockseditor_app/editor.html", _common_context(block, request))

@login_required
def editor_partial(request, block_id):
    block = get_object_or_404(Block, pk=block_id)
    return render(request, "blockseditor_app/editor_partial.html", _common_context(block, request))

@login_required
@require_http_methods(["POST"])
def update_node_position(request, block_id, slug):
    block = get_object_or_404(Block, pk=block_id)
    node = get_object_or_404(BlockNode, block=block, slug=slug)

    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid json"}, status=400)
    else:
        payload = request.POST

    try:
        x = clamp_coordinate(payload.get("x"))
        y = clamp_coordinate(payload.get("y"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "x and y must be numeric"}, status=400)

    node.position_x = x
    node.position_y = y
    node.save(update_fields=["position_x", "position_y", "updated_at"])

    return JsonResponse(
        {
            "slug": node.slug,
            "x": node.position_x,
            "y": node.position_y,
            "updated_at": node.updated_at.isoformat(),
        }
    )