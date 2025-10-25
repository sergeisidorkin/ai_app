# /Users/sergei/PycharmProjects/ai_app/macroops_app/service.py
from .compiler import compile_docops_to_addin_job

import uuid
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from office_addin.utils import group_for_email
from logs_app import utils as plog

import json
import logging
from typing import Any, Dict
from django.conf import settings

log = logging.getLogger(__name__)

try:
    import requests
except Exception:
    requests = None

def _queue_base() -> str:
    base = getattr(settings, "QUEUE_API_BASE", "").strip().rstrip("/")
    return base

def _queue_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        # ngrok хедер, чтобы прокси не показывала баннер
        "ngrok-skip-browser-warning": "1",
    }

def _job_to_queue_payload(job: dict) -> dict:
    """
    Приводим addin.job к payload для очереди:
      {"ops":[...], "anchor":{...}} — по сути то, что потом заберёт add-in.
    """
    ops = list((job or {}).get("ops") or [])
    anchor = ((job or {}).get("anchor") or None)
    payload: dict[str, Any] = {"ops": ops}
    if anchor:
        payload["anchor"] = anchor
    return payload






# --- Компактный «снимок» задания для логов ---
def snapshot_for_log(job: dict, *, max_ops: int = 12, max_chars_per_op: int = 160) -> dict:
    ops = list(job.get("ops") or [])
    # частоты типов опов
    types = {}
    for op in ops:
        t = (op or {}).get("op", "?")
        types[t] = types.get(t, 0) + 1

    # примеры первых опов (обрезаем длинные тексты)
    samples = []
    for i, op in enumerate(ops[:max_ops]):
        item = {"i": i, "op": op.get("op")}
        if "text" in op and isinstance(op["text"], str):
            txt = op["text"]
            if len(txt) > max_chars_per_op:
                txt = txt[:max_chars_per_op] + "…"
            item["text"] = txt
        # немного контекста полезно:
        for k in ("style", "level", "ordered"):
            if k in op:
                item[k] = op[k]
        samples.append(item)

    return {
        "job_id": job.get("id"),
        "kind": job.get("kind"),
        "version": job.get("version"),
        "ops_count": len(ops),
        "ops_types": types,
        "anchor": job.get("anchor"),
        "meta_keys": sorted((job.get("meta") or {}).keys()),
        "samples": samples,
    }

def docops_to_addin_job(docops: dict, meta: dict | None = None, anchor: dict | None = None) -> dict:
    from .compiler import compile_docops_to_addin_job
    return compile_docops_to_addin_job(docops, anchor=anchor, meta=meta)


def push_addin_job_via_ws(email: str, job: dict, doc_url: str | None = None, *, user=None, trace_id=None) -> int:
    # ← добавлены именованные user/trace_id
    try:
        snap = snapshot_for_log(job, max_ops=8, max_chars_per_op=140)
        plog.debug(user, phase="ws", event="payload",
                   message="WS payload snapshot",
                   trace_id=trace_id, email=email, via="ws",
                   job_id=uuid.UUID(job["id"]) if job.get("id") else None,
                   doc_url=doc_url, anchor_text=(job.get("anchor") or {}).get("text",""),
                   data=snap)
    except Exception as e:
        plog.warn(user, phase="ws", event="payload.snapshot.failed",
                  message=str(e), trace_id=trace_id, email=email, via="ws")

    async_to_sync(get_channel_layer().group_send)(
        group_for_email(email),
        {"type": "addin.job", "job": job, "docUrl": doc_url},
    )

    plog.info(user, phase="ws", event="sent",
              message=f"WS job sent ops={len(job.get('ops',[]))}",
              trace_id=trace_id, email=email, via="ws",
              job_id=uuid.UUID(job["id"]) if job.get("id") else None,
              doc_url=doc_url, anchor_text=(job.get("anchor") or {}).get("text",""))
    return len(job.get("ops", []))

def _payload_from_job(job: dict) -> dict:
    payload = {
        "id": job.get("id") or str(uuid.uuid4()),
        "kind": job.get("kind", "addin.job"),
        "version": job.get("version", "v1"),
        "ops": job.get("ops", []),
        "meta": job.get("meta", {}),
    }
    if job.get("anchor"):
        payload["anchor"] = job["anchor"]
    return payload

def enqueue_addin_job(*, email: str | None = None, job: dict, doc_url: str,
                      priority: int = 10, trace_id: str | None = None) -> str:
    """
    Ставит задание в внешнюю/локальную очередь docops_queue в формате /api/jobs/enqueue.
    Возвращает jobId (строкой). Бросает исключение при сетевых/иных ошибках.
    """
    # 1) Собираем тело запроса
    body = {
        "docUrl": (doc_url or "").strip(),
        "priority": int(priority or 10),
        "agentId": getattr(settings, "ADDIN_AGENT_ID", "addin-auto"),
        "role": getattr(settings, "ADDIN_AGENT_ROLE", "addin"),
        "payload": _job_to_queue_payload(job),
    }

    if not trace_id:
        trace_id = (job.get("meta") or {}).get("trace_id") or (job.get("meta") or {}).get("traceId")
    if trace_id:
        body["traceId"] = str(trace_id)

    # 2) Если задан внешний BASE — шлём HTTP
    base = _queue_base()
    if base and requests is not None:
        url = f"{base}/api/jobs/enqueue"
        try:
            resp = requests.post(url, headers=_queue_headers(), data=json.dumps(body), timeout=15)
            resp.raise_for_status()
            jd = resp.json()
            job_id = str(jd.get("jobId") or jd.get("id") or "")
            if not job_id:
                raise RuntimeError(f"enqueue returned no jobId: {jd}")
            return job_id
        except Exception as e:
            # логируем и пробрасываем — пусть верхний уровень отобразит messages.error/лог
            log.exception("Queue enqueue HTTP failed: %s", e)
            raise

    # 3) Фолбэк (локально) — пишем в свою БД docops_queue.Job напрямую
    try:
        from docops_queue.models import Job as QJob
        j = QJob.objects.create(doc_url=body["docUrl"], payload=body["payload"], priority=body["priority"])
        return str(j.id)
    except Exception as e:
        log.exception("Queue enqueue local fallback failed: %s", e)
        raise





def deliver_addin_job(via: str, *, email: str, job: dict, doc_url: str, priority: int = 10, user=None, trace_id=None):
    if via == "queue":
        payload = _payload_from_job(job)

        # лог «что именно положили в очередь»
        try:
            snap = snapshot_for_log(payload, max_ops=8, max_chars_per_op=140)
            plog.debug(
                user, phase="queue", event="payload",
                message="Queue payload snapshot",
                trace_id=trace_id, email=email, via="queue",
                job_id=uuid.UUID(str(payload.get("id"))) if payload.get("id") else None,
                doc_url=doc_url, anchor_text=(payload.get("anchor") or {}).get("text", ""),
                data=snap,
            )
        except Exception as e:
            plog.warn(user, phase="queue", event="payload.snapshot.failed",
                      message=str(e), trace_id=trace_id, email=email, via="queue")

        job_id = enqueue_addin_job(email=email, job=job, doc_url=doc_url, priority=priority, trace_id=trace_id,)

        plog.info(
            user, phase="queue", event="enqueued",
            message="Job enqueued",
            trace_id=trace_id, email=email, via="queue",
            job_id=uuid.UUID(str(job_id)) if job_id else None,
            doc_url=doc_url, anchor_text=(payload.get("anchor") or {}).get("text", ""),
            data={"ops": len(payload.get("ops", []))},
        )
        return job_id
    elif via == "ws":
        return push_addin_job_via_ws(email=email, job=job, doc_url=doc_url, user=user, trace_id=trace_id)
    else:
        raise ValueError(f"Unknown delivery via={via}")