from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from django.db.models import Q
from .models import LogEvent

def _event_to_dict(e: LogEvent) -> dict:
    return {
        "id": e.id,
        "created_at": e.created_at,
        "level": e.level,
        "phase": e.phase,
        "event": e.event,
        "via": e.via or "",
        "email": e.email or "",
        "job_id": e.job_id,
        "trace_id": e.trace_id,
        "doc_url": e.doc_url or "",
        "message": e.message or "",
        "data": e.data or {},
    }

@require_GET
def logs_list(request):
    qs = LogEvent.objects.all().order_by("-created_at")

    phase    = (request.GET.get("phase") or "").strip()
    via      = (request.GET.get("via") or "").strip()
    email    = (request.GET.get("email") or "").strip()
    block_id = (request.GET.get("block_id") or "").strip()
    job_id   = (request.GET.get("job_id") or "").strip()
    trace_id = (request.GET.get("trace_id") or "").strip()
    q        = (request.GET.get("q") or "").strip()

    if phase:    qs = qs.filter(phase=phase)
    if via:      qs = qs.filter(via=via)
    if email:    qs = qs.filter(email__icontains=email)  # FIX: было user_email__icontains
    if block_id: qs = qs.filter(block_id=block_id)
    if job_id:   qs = qs.filter(job_id=job_id)
    if trace_id: qs = qs.filter(trace_id=trace_id)
    if q:
        qs = qs.filter(
            Q(event__icontains=q) |
            Q(message__icontains=q) |
            Q(doc_url__icontains=q)
        )

    limit = max(1, min(int(request.GET.get("limit", 200)), 1000))
    items = [_event_to_dict(e) for e in qs[:limit]]
    return JsonResponse({"ok": True, "count": len(items), "items": items})

@require_GET
def log_detail(request, pk: int):
    e = get_object_or_404(LogEvent, pk=pk)
    return JsonResponse({"ok": True, "item": _event_to_dict(e)})
