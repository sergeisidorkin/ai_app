import json
from uuid import UUID, uuid4
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from logs_app import utils as plog

def _u(v):
    try:
        return UUID(str(v)) if v else None
    except Exception:
        return None

@csrf_exempt
@require_POST
def api_logs_ingest(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    token = request.headers.get('X-IMC-Logs-Token')
    if getattr(settings, 'LOGS_INGEST_TOKEN', None):
        if token != settings.LOGS_INGEST_TOKEN:
            return HttpResponseForbidden("bad token")

    entries = payload if isinstance(payload, list) else [payload]
    ingested = 0

    for e in entries:
        level   = (e.get("level") or "info").lower()
        phase   = e.get("phase") or "agent"
        event   = e.get("event") or "log"
        message = e.get("message") or ""
        job_id  = _u(e.get("jobId") or e.get("job_id"))
        trace   = _u(e.get("traceId") or e.get("trace_id")) or uuid4()  # гарантируем NOT NULL
        doc_url = e.get("docUrl") or e.get("doc_url") or ""
        data    = e.get("data") or {}

        fn = getattr(plog, level if level in ("debug", "info", "warn", "error") else "info")
        fn(
            None,
            phase=phase,
            event=event,
            message=message,
            job_id=job_id,
            doc_url=doc_url,
            trace_id=trace,
            data=data,
            via="ingest",   # помечаем источник
        )
        ingested += 1

    return JsonResponse({"ok": True, "ingested": ingested})
