import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from .service import deliver_addin_job
from .compiler import compile_docops_to_addin_job
from logs_app import utils as plog


@csrf_exempt
@require_GET
def ping(request):
    return JsonResponse({"ok": True})

@csrf_exempt
@require_POST
def compile_view(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    docops = data.get("docops")
    anchor = data.get("anchor") or None
    meta   = data.get("meta")   or None

    try:
        job = compile_docops_to_addin_job(docops, anchor=anchor, meta=meta)
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    return JsonResponse({"ok": True, "job": job})

def _pick_doc_url(data: dict) -> str:
    """ Берём URL именно текущего ОТКРЫТОГО документа (то, что видит панель). """
    doc = (data.get("doc") or {})  # допускаем «doc»: {webUrl|url|shareUrl}
    # Порядок предпочтений:
    for k in ("webUrl", "url", "shareUrl"):
        v = (doc.get(k) or "").strip()
        if v:
            return v
    # как аварийный вариант — плоское поле
    v = (data.get("docUrl") or "").strip()
    if v:
        return v
    return ""

@csrf_exempt
@require_POST
def compile_enqueue_view(request):
    """
    Полный цикл: компилируем DocOps, ставим addin.job в очередь и возвращаем jobId.
    Ожидаемый JSON:
    {
      "docops": {...},
      "anchor": {"text": "..."} | null,
      "meta":   {...},           # опционально
      "doc":    {"webUrl": "...", "url": "...", "shareUrl": "..."}  # один из них ОБЯЗАТЕЛЕН
    }
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    doc_url = _pick_doc_url(data)
    if not doc_url:
        return HttpResponseBadRequest("document url required (doc.webUrl/url/shareUrl or docUrl)")

    docops = data.get("docops")
    anchor = data.get("anchor") or None
    meta   = data.get("meta")   or None

    try:
        job = compile_docops_to_addin_job(docops, anchor=anchor, meta=meta)
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    # Кому слать по WS не важно — мы шлём в очередь (панель сама подберёт через /api/docs/next)
    # email берём из meta, если есть (не обязательно)
    email = (meta or {}).get("email") or None

    # Пробрасываем в логи привязку к документу
    plog.info(None, phase="deliver", event="ok", message="queue",
              email=email, doc_url=doc_url)

    job_id = deliver_addin_job(
        via="queue",
        email=email or "",  # не обязателен для очереди
        job=job,
        doc_url=doc_url,
        priority=10,
    )

    return JsonResponse({"ok": True, "jobId": job_id, "via": "queue"})