# /Users/sergei/PycharmProjects/ai_app/macroops_app/service.py

from .compiler import compile_docops_to_addin_job
import uuid
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from office_addin.utils import group_for_email
from logs_app import utils as plog
from .addin_payload import build_payload_from_job
import json
import logging
from typing import Any, Dict
from django.conf import settings
import base64

log = logging.getLogger(__name__)

try:
    import requests
except Exception:
    requests = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _queue_base() -> str:
    base = getattr(settings, "QUEUE_API_BASE", "").strip().rstrip("/")
    return base


def _queue_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "1",
    }


def snapshot_for_log(job: dict, *, max_ops: int = 12, max_chars_per_op: int = 160) -> dict:
    ops = list(job.get("ops") or [])
    types = {}
    for op in ops:
        t = (op or {}).get("op", "?")
        types[t] = types.get(t, 0) + 1

    samples = []
    for i, op in enumerate(ops[:max_ops]):
        item = {"i": i, "op": op.get("op")}
        if "text" in op and isinstance(op["text"], str):
            txt = op["text"]
            if len(txt) > max_chars_per_op:
                txt = txt[:max_chars_per_op] + "…"
            item["text"] = txt

        for k in ("style", "level", "ordered"):
            if k in op:
                item[k] = op[k]

        if op.get("op") == "docx.insert":
            b64 = (op.get("base64") or "")
            b64_len = len(b64)
            sig = None
            try:
                raw = base64.b64decode(b64.encode("ascii")) if b64 else b""
                sig = raw[:2].hex() if raw else None
            except Exception:
                sig = None

            item["base64_len"] = b64_len
            item["zip_sig"] = sig
            if "fileName" in op:
                item["fileName"] = op["fileName"]
            if "mimeType" in op:
                item["mimeType"] = op["mimeType"]
            if "location" in op:
                item["location"] = op["location"]

        samples.append(item)

    return {
        "job_id": job.get("id"),
        "kind": job.get("kind"),
        "version": job.get("version"),
        "ops_count": len(ops),
        "ops_types": types,
        "anchor": job.get("anchor"),
        "meta_keys": sorted((job.get("meta") or {}).keys()),
        "options_keys": sorted((job.get("options") or {}).keys()),
        "samples": samples,
    }


# ============================================================================
# LOW-LEVEL DELIVERY FUNCTIONS
# ============================================================================

def _send_via_websocket(email: str, client_payload: dict, *, user=None, trace_id=None, doc_url: str = ""):
    """Отправка готового client_payload через WebSocket."""
    group = group_for_email(email)
    layer = get_channel_layer()

    async_to_sync(layer.group_send)(
        group,
        client_payload  # уже готовый {"type":"addin.block", "blocks":[...], ...}
    )

    plog.info(user, phase="ws", event="sent",
              message=f"WS job sent ops={len(client_payload.get('blocks') or [])}",
              trace_id=trace_id, email=email, via="ws",
              job_id=uuid.UUID(client_payload["jobId"]) if client_payload.get("jobId") else None,
              doc_url=client_payload.get("docUrl") or doc_url,
              anchor_text="")  # anchor уже внутри blocks


def _enqueue_client_payload(client_payload: dict, *, doc_url: str, priority: int = 10,
                            trace_id: str | None = None, email: str | None = None) -> str:
    """
    Кладёт готовый client_payload (addin.block) в очередь.
    Работает как локально (через Django ORM), так и через API (если задан QUEUE_API_BASE).
    """
    body = {
        "docUrl": (doc_url or "").strip(),
        "priority": int(priority or 10),
        "agentId": getattr(settings, "ADDIN_AGENT_ID", "addin-auto"),
        "role": getattr(settings, "ADDIN_AGENT_ROLE", "addin"),
        "payload": client_payload,  # ← ВАЖНО: кладём готовый addin.block
    }

    if trace_id:
        body["traceId"] = str(trace_id)

    base = _queue_base()

    # Попытка отправить через API (если настроен)
    if base and requests is not None:
        url = f"{base}/api/jobs/enqueue"
        try:
            resp = requests.post(url, headers=_queue_headers(), data=json.dumps(body), timeout=15)
            resp.raise_for_status()
            jd = resp.json()
            job_id = str(jd.get("jobId") or jd.get("id") or "")

            if not job_id:
                raise RuntimeError(f"enqueue returned no jobId: {jd}")

            plog.info(None, phase="queue", event="enqueued.api",
                      message=f"Job enqueued via API",
                      trace_id=trace_id, email=email, via="queue",
                      job_id=uuid.UUID(job_id) if job_id else None,
                      doc_url=doc_url)

            return job_id
        except Exception as e:
            plog.warn(None, phase="queue", event="enqueue.api.failed",
                      message=f"API enqueue failed: {e}, falling back to local",
                      trace_id=trace_id, email=email)

    # Локальный fallback через Django ORM
    from docops_queue.models import Job as QJob

    j = QJob.objects.create(
        doc_url=body["docUrl"],
        payload=client_payload,  # ← готовый addin.block
        priority=body["priority"],
        trace_id=uuid.UUID(trace_id) if trace_id else None,
    )

    plog.info(None, phase="queue", event="enqueued.local",
              message=f"Job enqueued locally",
              trace_id=trace_id, email=email, via="queue",
              job_id=j.id,
              doc_url=doc_url)

    return str(j.id)


# ============================================================================
# HIGH-LEVEL: UNIFIED DELIVERY
# ============================================================================

def deliver_addin_job(via: str, *, email: str, job: dict, doc_url: str,
                      priority: int = 10, user=None, trace_id=None) -> str:
    """
    ЕДИНАЯ ТОЧКА формирования и доставки addin.block payload.

    Шаги:
    1. Формирует ГОТОВЫЙ client_payload (addin.block) из job — ОДИН РАЗ
    2. В зависимости от via отправляет его:
       - "ws" → WebSocket в локальную панель
       - "queue" → очередь на Windows-сервер (или локально)

    Returns:
        jobId (str)
    """
    meta = (job.get("meta") or {})

    # Резолвим trace_id и job_id
    if not trace_id:
        trace_id = meta.get("trace_id") or meta.get("traceId")

    job_id = meta.get("job_id") or meta.get("jobId") or str(uuid.uuid4())

    # ========================================================================
    # КЛЮЧЕВОЙ МОМЕНТ: формируем client_payload ОДИН РАЗ для обоих каналов
    # ========================================================================
    client_payload = build_payload_from_job(
        job,
        job_id=job_id,
        trace_id=trace_id,
        doc_url=doc_url,
    )

    # Логируем снимок payload (для отладки)
    try:
        snap = snapshot_for_log(job, max_ops=8, max_chars_per_op=140)
        plog.debug(user, phase="deliver", event="payload.snapshot",
                   message=f"Delivery via {via}",
                   trace_id=trace_id, email=email, via=via,
                   job_id=uuid.UUID(str(job_id)) if job_id else None,
                   doc_url=doc_url,
                   data=snap)
    except Exception as e:
        plog.warn(user, phase="deliver", event="payload.snapshot.failed",
                  message=str(e), trace_id=trace_id, email=email, via=via)

    # ========================================================================
    # ДОСТАВКА: два канала используют ОДИН И ТОТ ЖЕ client_payload
    # ========================================================================

    if via == "ws":
        # Канал 1: WebSocket в локальную панель
        _send_via_websocket(email, client_payload, user=user, trace_id=trace_id, doc_url=doc_url)

        plog.info(user, phase="ws", event="delivered",
                  message=f"Job delivered via WebSocket, ops={len(client_payload.get('blocks') or [])}",
                  trace_id=trace_id, email=email, via="ws",
                  job_id=uuid.UUID(client_payload["jobId"]) if client_payload.get("jobId") else None,
                  doc_url=doc_url)

        return str(client_payload.get("jobId") or job_id)

    elif via == "queue":
        # Канал 2: Очередь на Windows-сервер (или локально)
        returned_job_id = _enqueue_client_payload(
            client_payload,
            doc_url=doc_url,
            priority=priority,
            trace_id=trace_id,
            email=email,
        )

        plog.info(user, phase="queue", event="delivered",
                  message=f"Job delivered via queue, ops={len(client_payload.get('blocks') or [])}",
                  trace_id=trace_id, email=email, via="queue",
                  job_id=uuid.UUID(returned_job_id) if returned_job_id else None,
                  doc_url=doc_url)

        return returned_job_id

    else:
        raise ValueError(f"Unknown delivery via={via}")


# ============================================================================
# LEGACY COMPATIBILITY (если где-то ещё используется)
# ============================================================================

def push_addin_job_via_ws(email: str, job: dict, doc_url: str | None = None,
                          *, user=None, trace_id=None) -> int:
    """
    DEPRECATED: используйте deliver_addin_job(via="ws", ...) вместо этого.
    Оставлено для обратной совместимости.
    """
    job_id = deliver_addin_job(
        via="ws",
        email=email,
        job=job,
        doc_url=doc_url or "",
        user=user,
        trace_id=trace_id,
    )

    # Возвращаем количество ops (для совместимости со старым API)
    ops_count = len((job.get("ops") or []))
    return ops_count

def enqueue_addin_job(*, email: str | None = None, job: dict, doc_url: str,
                      priority: int = 10, trace_id: str | None = None,
                      client_payload: dict | None = None) -> str:
    """
    LEGACY WRAPPER: для совместимости с blocks_app.views.

    Если client_payload задан — кладём его как payload (это уже {type:'addin.block', ...}).
    Иначе — формируем через build_payload_from_job.
    """
    if client_payload is None:
        # Формируем client_payload из job
        meta = (job.get("meta") or {})
        if not trace_id:
            trace_id = meta.get("trace_id") or meta.get("traceId")

        job_id = meta.get("job_id") or meta.get("jobId") or str(uuid.uuid4())

        client_payload = build_payload_from_job(
            job,
            job_id=job_id,
            trace_id=trace_id,
            doc_url=doc_url,
        )

    # Используем внутреннюю функцию для постановки в очередь
    return _enqueue_client_payload(
        client_payload,
        doc_url=doc_url,
        priority=priority,
        trace_id=trace_id,
        email=email,
    )


def docops_to_addin_job(docops: dict, meta: dict | None = None, anchor: dict | None = None) -> dict:
    """Обёртка для compile_docops_to_addin_job."""
    from .compiler import compile_docops_to_addin_job
    return compile_docops_to_addin_job(docops, anchor=anchor, meta=meta)