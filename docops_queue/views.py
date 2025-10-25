# ai_app/docops_queue/views.py
import json

from datetime import timedelta
from urllib.parse import urlparse, urlunparse, unquote, quote
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from docops_queue.models import Job
from docops_queue.urlkeys import make_doc_key

from logs_app import utils as plog

def _parse_uuid(v):
    try:
        return UUID(str(v))
    except Exception:
        return None

def _trace_from_payload_or_request(body: dict, payload: dict) -> str:
    # пробуем верхний уровень body.traceId (если будете слать),
    # затем payload.meta.trace_id / payload.traceId
    return (
        (body or {}).get('traceId') or
        ((payload or {}).get('meta') or {}).get('trace_id') or
        (payload or {}).get('traceId') or
        ''
    )

def _payload_anchor_text(payload: dict) -> str:
    try:
        a = (payload or {}).get("anchor") or {}
        t = (a.get("text") or "").strip()
        return t
    except Exception:
        return ""

def _url_variants(u: str) -> list[str]:
    """
    Возвращает набор вариантов одного и того же URL:
    - как пришёл;
    - unquote (преобразовать %20 -> пробел);
    - re-quote (обратно экранировать пробелы как %20).
    Плюс прогон через _normalize_url.
    """
    raw = (u or "").strip()
    out = set()
    def _norm(x: str) -> str:
        return _normalize_url(x)

    try:
        out.add(_norm(raw))
        uq = unquote(raw)
        out.add(_norm(uq))
        rq = quote(uq, safe=":/@%._-+=")
        out.add(_norm(rq))
    except Exception:
        pass
    # выкинем пустые
    return [x for x in out if x]

def _normalize_url(u: str) -> str:
    # убираем query/fragment, тримим слеш в конце
    try:
        p = urlparse((u or "").strip())
        p = p._replace(query="", fragment="")
        s = urlunparse(p)
        return s.rstrip("/")
    except Exception:
        return (u or "").strip().rstrip("/")

def _ms_word_link(web_url: str) -> str:
    return f"ms-word:ofe|u|{web_url}"

def _user_bucket(u: str) -> str:
    """
    Вернёт "host/personal/<user>" в нижнем регистре (без слэша в конце)
    для обоих форм URL: и обычной, и '/:w:/g/...'.
    """
    try:
        from urllib.parse import urlparse, unquote
        import re
        p = urlparse((u or "").strip())
        host = (p.netloc or "").lower()
        path = unquote(p.path or "")
        path = re.sub(r"/+", "/", path).strip().rstrip("/").lower()

        # '/:w:/g/personal/<user>/...'
        m = re.match(r"^/:w:/(?:g|r)/(personal/[^/]+)/", path)
        if m:
            return f"{host}/{m.group(1)}"

        # '/personal/<user>/...'
        n = re.match(r"^/(personal/[^/]+)/", path)
        if n:
            return f"{host}/{n.group(1)}"
    except Exception:
        pass
    return ""

def _ops_to_blocks(payload: dict) -> list[dict]:
    if not payload:
        return []

    # 1) короткая форма: {"kind": "...", "text": "..."} или {"op": "..."}
    if isinstance(payload, dict) and ((payload.get("kind") or payload.get("op")) and not payload.get("ops")):
        kind = (payload.get("kind") or payload.get("op") or "").strip().lower()
        if kind:
            b = {"kind": kind}
            if "text" in payload:  b["text"]  = payload["text"]
            if "style" in payload: b["style"] = payload["style"]
            return [b]

    # 2) обычная форма: {"ops":[{...}, {...}]}
    ops = list((payload or {}).get("ops") or [])
    blocks = []
    for op in ops:
        kind = (op.get("kind") or op.get("op") or "").strip().lower()
        if not kind:
            continue
        b = {"kind": kind}
        if "text" in op:  b["text"]  = op["text"]
        if "style" in op: b["style"] = op["style"]
        blocks.append(b)
    return blocks

def _extract_filename(u: str) -> str:
    try:
        from urllib.parse import urlparse, unquote
        name = unquote(urlparse((u or "").strip()).path).rstrip("/").split("/")[-1]
        return (name or "").lower()
    except Exception:
        return ""




def _payload_from_blocks(blocks: list[dict], anchor_text: str | None) -> dict:
    out = {"ops": []}
    for b in blocks or []:
        kind = (b.get("kind") or b.get("op") or "").strip().lower()
        if not kind:
            continue
        item = {"op": kind}
        if "text" in b:
            item["text"] = b["text"]
        if "style" in b:
            item["style"] = b["style"]
        out["ops"].append(item)
    if anchor_text:
        out["anchor"] = {"text": anchor_text}
    return out

@csrf_exempt
@require_POST
def enqueue_from_pipeline(request):
    """
    Вызывается из пайплайна 'Создать' после сборки blocks.
    Ждёт JSON:
      {
        "doc": { "webUrl": "...", "url": "...", "shareUrl": "..." },
        "blocks": [...],             # docops blocks
        "target": {"marker": "..."}  # опционально
        "priority": 10               # опционально
      }
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    doc = data.get("doc") or {}
    # берём любой валидный источник ссылки на ТЕКУЩИЙ документ
    raw_url = doc.get("webUrl") or doc.get("url") or doc.get("shareUrl") or ""
    doc_url = _normalize_url(raw_url)
    if not doc_url:
        return HttpResponseBadRequest("doc.webUrl/url/shareUrl required")

    blocks = data.get("blocks") or []
    marker = ((data.get("target") or {}).get("marker") or "").strip()
    priority = int(data.get("priority") or 10)

    # приводим к payload, совместимому с /api/docs/next
    payload = _payload_from_blocks(blocks, marker)
    trace_raw = _trace_from_payload_or_request(data, payload)
    trace_uuid = _parse_uuid(trace_raw)

    j = Job.objects.create(
        doc_url=doc_url,
        payload=payload,
        priority=priority,
        trace_id=trace_uuid or None,
    )
    plog.info(
        None,
        phase="queue",
        event="enqueue",
        job_id=j.id,
        doc_url=j.doc_url,
        message="Enqueued from pipeline",
        trace_id=(j.trace_id or None),
        data={"ops": len((payload or {}).get("ops") or []),
              "has_anchor": bool(marker)}
    )
    return JsonResponse({"ok": True, "jobId": str(j.id)})

@csrf_exempt
@require_POST
def enqueue(request):
    """
    ТЕСТОВЫЙ endpoint: положить job в очередь.
    body: { "docUrl": "...", "payload": {...}, "priority": 10 }
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    doc_url = _normalize_url(data.get("docUrl") or "")
    payload = data.get("payload") or {}
    trace_raw = _trace_from_payload_or_request(data, payload)
    trace_uuid = _parse_uuid(trace_raw)
    job_obj = data.get("job")
    ops_arr = data.get("ops")

    if payload is None:

        if isinstance(job_obj, dict):
            payload = {"ops": list(job_obj.get("ops") or [])}
            a = (job_obj.get("anchor") or {})
            if isinstance(a, dict) and isinstance(a.get("text"), str) and a["text"].strip():
                        payload["anchor"] = {"text": a["text"].strip()}
        elif isinstance(ops_arr, list):
            payload = {"ops": list(ops_arr)}
        else:
            payload = {}

    priority = int(data.get("priority") or 10)

    if not doc_url:
        return HttpResponseBadRequest("docUrl required")

    j = Job.objects.create(
        doc_url=doc_url,
        payload=payload,
        priority=priority,
        trace_id=trace_uuid or None,
    )

    anchor_text = _payload_anchor_text(payload)
    plog.info(
        None, phase="queue", event="enqueue", message="Job enqueued",
        job_id=j.id, doc_url=j.doc_url, anchor_text=anchor_text,
        trace_id=(j.trace_id or None),
        data={
            "priority": j.priority,
            "ops": len((payload or {}).get("ops") or []),
            "has_anchor": bool(anchor_text),
        },
    )
    return JsonResponse({"ok": True, "jobId": str(j.id)})

@csrf_exempt
@require_POST
def agent_pull(request, agent_id: str):
    """
    Агент тянет следующее задание.
    Приоритет:
      1) уже ASSIGNED на этого же агента (возвращаем как есть);
      2) протухшие ASSIGNED (reclaim) → перепривязываем к этому агенту;
      3) обычные QUEUED → назначаем и отдаём.
    """
    now = timezone.now()
    RECLAIM_AFTER = timedelta(minutes=5)

    # Диагностика очереди перед принятием решения
    stats = list(Job.objects.values("status").annotate(c=Count("id")).order_by())
    top_q = Job.objects.filter(status=Job.Status.QUEUED).order_by("-priority", "created_at").values_list("id",
                                                                                                         flat=True).first()
    plog.debug(
        None, phase="agent", event="pull.in",
        message=f"agent={agent_id}",
        data={"stats": stats, "top_queued": str(top_q) if top_q else None}
    )

    def _job_payload(j: Job) -> JsonResponse:
        web_url = j.doc_url
        return JsonResponse({
            "ok": True,
            "job": {
                "id": str(j.id),
                "webUrl": web_url,
                "msLink": _ms_word_link(web_url),
                "traceId": (str(j.trace_id) if j.trace_id else None),  # ← добавить
            }
        })

    # 1) Уже назначенные на ЭТОГО агента (ASSIGNED или IN_PROGRESS)
    j = Job.objects.filter(
        assigned_agent=agent_id,
        status__in=[Job.Status.ASSIGNED, Job.Status.IN_PROGRESS]
    ).order_by("-priority", "created_at").first()
    if j:
        plog.info(None, phase="agent", event="pull.assigned_existing",
                  message="Return already assigned to this agent",
                  job_id=j.id, doc_url=j.doc_url,
                  trace_id=(j.trace_id or None),
                  data={"agent_id": agent_id, "status": j.status})
        return _job_payload(j)

    # 2) Ре-клейм протухших ASSIGNED (кто-то сделал /pull и исчез)
    j = Job.objects.filter(
            status=Job.Status.ASSIGNED,
            started_at__lt=now - RECLAIM_AFTER
        ).order_by("started_at").first()
    if j:
        old_agent = j.assigned_agent
        j.assigned_agent = agent_id
        j.save(update_fields=["assigned_agent", "updated_at"])
        plog.warn(None, phase="agent", event="pull.reclaim",
                  message=f"Reclaim ASSIGNED job from '{old_agent}'",
                  job_id=j.id, doc_url=j.doc_url,
                  trace_id=(j.trace_id or None),
                  data={"agent_id": agent_id})
        return _job_payload(j)

    # 3) Обычные QUEUED
    j = Job.objects.filter(status=Job.Status.QUEUED) \
                   .order_by("-priority", "created_at").first()
    if not j:
        return JsonResponse({"ok": True, "job": None})

    j.status = Job.Status.ASSIGNED
    j.assigned_agent = agent_id
    j.started_at = now
    j.attempts += 1
    j.save(update_fields=["status", "assigned_agent", "started_at", "attempts", "updated_at"])

    plog.info(None, phase="agent", event="pull.assigned_new",
              message="Assigned QUEUED to agent",
              job_id=j.id, doc_url=j.doc_url,
              trace_id=(j.trace_id or None),
              data={"agent_id": agent_id})
    return _job_payload(j)

@csrf_exempt
@require_POST
def docs_next(request):
    data = json.loads(request.body or "{}")
    url = (data.get("url") or "").strip()
    if not url:
        return JsonResponse({"ok": True, "job": None})

    key    = make_doc_key(url)
    bucket = _user_bucket(url)

    # 1) Точное совпадение среди QUEUED
    job = (Job.objects
           .filter(status=Job.Status.QUEUED, doc_key=key)
           .order_by("-priority", "created_at")
           .first())

    # 2) Точное среди ASSIGNED/IN_PROGRESS
    if job is None:
        job = (Job.objects
               .filter(status__in=[Job.Status.ASSIGNED, Job.Status.IN_PROGRESS], doc_key=key)
               .order_by("-priority", "created_at")
               .first())

    # 3) Фолбэк по user-bucket (разные формы URL одного файла)
    if job is None and bucket:
        job = (Job.objects
               .filter(status__in=[Job.Status.QUEUED, Job.Status.ASSIGNED, Job.Status.IN_PROGRESS],
                       doc_key__contains=bucket)
               .order_by("-priority", "created_at")
               .first())

    if not job:
        plog.debug(None, phase="docs", event="next.none")
        return JsonResponse({"ok": True, "job": None})

    # Переводим QUEUED → IN_PROGRESS, чтобы не «моргало»
    if job.status == Job.Status.QUEUED:
        job.status = Job.Status.IN_PROGRESS
        job.save(update_fields=["status", "updated_at"])

    # ops → blocks (панель такое уже ест)
    anchor_text = _payload_anchor_text(job.payload)
    blocks = (job.payload or {}).get("blocks") or _ops_to_blocks(job.payload)
    payload_out = {"blocks": blocks}
    if anchor_text:
        payload_out["target"] = {"marker": anchor_text}

    plog.info(
        None, phase="docs", event="next.found",
        job_id=job.id, doc_url=job.doc_url,
        trace_id=(job.trace_id or None)
    )

    return JsonResponse({
        "ok": True,
        "job": {
            "id": str(job.id),
            "payload": payload_out,
            "traceId": (str(job.trace_id) if job.trace_id else None),  # ← добавить
        }
    })

@csrf_exempt
@require_POST
def job_complete(request, job_id):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")

    ok = bool(data.get("ok"))
    message = (data.get("message") or "")[:2000]
    # опционально: метрики, счетчики, длительность и т.д.

    try:
        j = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return HttpResponseBadRequest("job not found")

    j.status = Job.Status.DONE if ok else Job.Status.FAILED
    j.last_error = "" if ok else (message or "failed")
    j.finished_at = timezone.now()
    j.save(update_fields=["status","last_error","finished_at","updated_at"])
    if ok:
        plog.info(None, phase="queue", event="complete.ok",
                  job_id=j.id, doc_url=j.doc_url,
                  trace_id=(j.trace_id or None), message=message or "")
    else:
        plog.error(None, phase="queue", event="complete.failed",
                   job_id=j.id, doc_url=j.doc_url, trace_id=(j.trace_id or None),
                   message=message or "failed")
    return JsonResponse({"ok": True})

@require_GET
def job_detail(request, job_id: UUID):
    j = get_object_or_404(Job, id=job_id)
    return JsonResponse({
        "id": str(j.id),
        "status": j.status,
        "priority": j.priority,
        "docUrl": j.doc_url,
        "payload": j.payload,
        "assignedAgent": j.assigned_agent,
        "attempts": j.attempts,
        "lastError": j.last_error,
        "createdAt": j.created_at.isoformat(),
        "updatedAt": j.updated_at.isoformat(),
        "startedAt": j.started_at.isoformat() if j.started_at else None,
        "finishedAt": j.finished_at.isoformat() if j.finished_at else None,
        "traceId": str(j.trace_id) if j.trace_id else None,
    })

@csrf_exempt
@require_POST
def reset_stale(request):
    mins = int((json.loads(request.body or b"{}") or {}).get("minutes", 5))
    n = timezone.now() - timedelta(minutes=mins)
    c = Job.objects.filter(status=Job.Status.ASSIGNED, started_at__lt=n) \
                   .update(status=Job.Status.QUEUED, assigned_agent="")
    plog.warn(None, phase="queue", event="reset_stale",
              message=f"Reset stale ASSIGNED → QUEUED: {c}",
              data={"minutes": mins})
    return JsonResponse({"ok": True, "reset": c, "minutes": mins})