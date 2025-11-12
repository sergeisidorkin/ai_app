# /office_addin/consumers.py
import re
import urllib.parse
import logging
import uuid
from uuid import uuid4

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

log = logging.getLogger(__name__)

try:
    from office_addin.utils import group_for_email as _group_for_email
except Exception:
    _group_for_email = None

def group_for_email(email: str) -> str:
    if _group_for_email:
        return _group_for_email(email)
    e = (email or "").strip().lower()
    try:
        e = urllib.parse.unquote(e)
    except Exception:
        pass
    e = e.replace("@", ".")
    safe = re.sub(r"[^0-9a-zA-Z_.-]+", "-", e)
    return f"user_{safe}"[:90]

# ----------------------------- helpers --------------------------------- #

# def _op_name(op: dict) -> str:
#     if not isinstance(op, dict):
#         return ""
#     return (op.get("op")
#             or op.get("kind")
#             or op.get("type")
#             or "").strip()

# def _strip_job_marker_tail(ops: list[dict]) -> tuple[list[dict], int]:
#     """Remove any existing job.marker.tail ops; return (filtered_ops, removed_count)."""
#     filtered = []
#     removed = 0
#     for o in ops or []:
#         if _op_name(o) == "job.marker.tail":
#             removed += 1
#             continue
#         filtered.append(o)
#     return filtered, removed

# def _ensure_trailing_block_op(ops: list[dict], job_id: str | None) -> tuple[list[dict], bool, int]:
#     """
#     Ensure exactly one trailing {"op":"job.marker.tail","jobId":job_id} when job_id is present.
#     Returns: (ops_updated, appended_bool, removed_count)
#     """
#     if not isinstance(ops, list):
#         ops = list(ops or [])
#     ops, removed = _strip_job_marker_tail(ops)
#     appended = False
#     if job_id:
#         ops.append({"op": "job.marker.tail", "jobId": str(job_id)})
#         appended = True
#     return ops, appended, removed

# def _ops_preview(ops: list[dict], limit: int = 10) -> list[str]:
#     return [(_op_name(o) or None) for o in (ops or [])[:max(1, limit)]]

# ----------------------------------------------------------------------- #

class AddinConsumer(AsyncJsonWebsocketConsumer):
    async def _plog_info(self, *args, **kwargs):
        from logs_app import utils as plog
        return await sync_to_async(plog.info, thread_sensitive=True)(*args, **kwargs)

    async def connect(self):
        self.user = self.scope.get("user") or AnonymousUser()
        raw = (self.scope.get("url_route", {}) or {}).get("kwargs", {}).get("email") or ""
        self.email = raw
        self.group_name = group_for_email(raw)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello", "group": self.group_name})

    async def addin_block(self, event):
        # ⚠️ event уже содержит финальный клиентский payload: type=addin.block, blocks/block, jobId/traceId, docUrl
        try:
            await self.send_json(event)
            # (опционально короткий лог без приватных хелперов)
            try:
                user = getattr(self.scope, "user", None)
                if not getattr(user, "is_authenticated", False):
                    user = None
                await self._plog_info(
                    user, phase="ws", event="emit.addin.block",
                    message=f"ops={len(event.get('blocks') or [event.get('block')] or [])}",
                    trace_id=(event.get("traceId") or None),
                    data={
                        "doc_url": bool(event.get("docUrl")),
                        "client_email": self.email,
                        "ws_channel": self.channel_name,
                    }
                )
            except Exception:
                pass
        except Exception as e:
            log.exception("addin_block forward failed: %s", e)

    # Для совместимости: если придёт старое событие с type="addin.job" — просто пробросим как есть
    async def addin_job(self, event):
        await self.send_json(event)  # временно; после миграции можно удалить хэндлер целиком

# class AddinConsumer(AsyncJsonWebsocketConsumer):
#     async def _plog_info(self, *args, **kwargs):
#         # ленивый импорт, чтобы не дёргать модели до setup()
#         from logs_app import utils as plog
#         return await sync_to_async(plog.info, thread_sensitive=True)(*args, **kwargs)
#
#     async def connect(self):
#         # ОБЯЗАТЕЛЬНО сохраняем self.user
#         self.user = self.scope.get("user") or AnonymousUser()
#
#         raw = (self.scope.get("url_route", {}) or {}).get("kwargs", {}).get("email") or ""
#         self.email = raw
#         self.group_name = group_for_email(raw)
#
#         await self.channel_layer.group_add(self.group_name, self.channel_name)
#         await self.accept()
#         try:
#             uid = getattr(self.user, "id", None)
#             if uid:
#                 cache.set(f"addin:last_email:{uid}", raw, 3600)
#         except Exception:
#             pass
#
#         await self.send_json({"type": "hello", "group": self.group_name})
#         log.warning("WS connected: group=%s chan=%s", self.group_name, self.channel_name)
#
#     async def disconnect(self, code):
#         try:
#             await self.channel_layer.group_discard(self.group_name, self.channel_name)
#         except Exception:
#             pass
#
#     # Aliases from channel layer
#     async def ws_addin_block(self, event):
#         return await self.addin_block(event)
#
#     async def ws_addin_job(self, event):
#         return await self.addin_job(event)
#
#     # --------------------------- main handlers --------------------------- #
#
#     async def addin_block(self, event):
#         """
#         Нормализуем разные варианты payload и пишем компактный лог в plog.
#         Поддерживает:
#           - {"type":"addin.block","blocks":[...], "docUrl": "...", "jobId":"...", "traceId":"..."}
#           - {"type":"addin.block","block": {...}}                       (один op)
#           - fallback: если вместо blocks/block пришли job/ops → отдаём через _emit_as_addin_block
#
#         Новая логика компилятора:
#           - если есть jobId → гарантируем финальную op {"op":"job.marker.tail","jobId":...}
#           - удаляем любые встреченные ранее "job.marker.tail" в середине ops
#         """
#         try:
#             # 1) ops
#             if isinstance(event.get("blocks"), list):
#                 blocks = list(event.get("blocks") or [])
#             elif event.get("block"):
#                 blocks = [event.get("block")]
#             else:
#                 return await self._emit_as_addin_block(event=event)
#
#             # 2) поля
#             doc_url = event.get("docUrl") or ""
#             job_id = (event.get("jobId") or "") or ""
#             trace_id = (event.get("traceId") or "") or ""
#
#             # 2a) добор из cache, если пусто
#             try:
#                 if not trace_id:
#                     trace_id = cache.get(f"ws:last_trace:{self.group_name}") or ""
#                 if not job_id:
#                     job_id = cache.get(f"ws:last_job:{self.group_name}") or ""
#             except Exception:
#                 pass
#
#             # 2b) компилятор: вставляем завершающий <BLOCK:…> как op
#             blocks, appended, removed = _ensure_trailing_block_op(blocks, job_id)
#
#             # 2c) обновим cache для последующих пакетов
#             try:
#                 if job_id:
#                     cache.set(f"ws:last_job:{self.group_name}", job_id, 900)
#                 if trace_id:
#                     cache.set(f"ws:last_trace:{self.group_name}", trace_id, 900)
#             except Exception:
#                 pass
#
#             # 3) клиентский payload
#             payload = {"type": "addin.block", "blocks": blocks, "docUrl": doc_url}
#             if job_id:
#                 payload["jobId"] = job_id
#             if trace_id:
#                 payload["traceId"] = trace_id
#
#             await self.send_json(payload)
#
#             # 4) логи
#             try:
#                 user = getattr(self.scope, "user", None)
#                 if not getattr(user, "is_authenticated", False):
#                     user = None
#                 job_uuid = None
#                 try:
#                     if job_id:
#                         job_uuid = uuid.UUID(str(job_id))
#                 except Exception:
#                     job_uuid = None
#
#                 await self._plog_info(
#                     user, phase="ws", event="emit.addin.block.payload.full",
#                     message=f"Full payload: {len(blocks)} ops",
#                     job_id=job_uuid,
#                     trace_id=(trace_id or None),
#                     data={
#                         "doc_url": doc_url,
#                         "job_id": job_id,
#                         "trace_id": trace_id,
#                         "ops": [
#                             {
#                                 "index": i,
#                                 "op": _op_name(op),
#                                 "text": (op.get("text") or op.get("caption") or "")[:100],
#                                 "location": op.get("location"),
#                                 "fileName": op.get("fileName"),
#                                 "base64_len": len(op.get("base64", "")),
#                                 "has_base64": bool(op.get("base64")),
#                             }
#                             for i, op in enumerate(blocks)
#                         ],
#                         "compiler": {
#                             "job_marker_tail": {"appended": appended, "removed_dups": removed}
#                         }
#                     }
#                 )
#                 await self._plog_info(
#                     user, phase="ws", event="emit.addin.block",
#                     message=f"ops={len(blocks)}",
#                     job_id=job_uuid,
#                     trace_id=(trace_id or None),
#                     data={
#                         "doc_url": bool(doc_url),
#                         "ops_preview": _ops_preview(blocks, 10),
#                         "client_email": self.email,
#                         "ws_channel": self.channel_name,
#                     }
#                 )
#             except Exception as e:
#                 log.exception("WS OUT addin.block log failed: %s", e)
#
#         except Exception as e:
#             log.exception("addin_block failed: %s", e)
#
#     async def paragraph(self, event):
#         # Старые события {"type":"paragraph", ...} — игнорируем
#         log.warning("WS ignore legacy 'paragraph' event: %s", event)
#         return
#
#     def _to_legacy(self, block: dict) -> dict | None:
#         kind = block.get("kind") or block.get("op")
#         if kind == "paragraph.insert":
#             style = (block.get("styleBuiltIn") or "").lower()
#             if style in ("listbullet", "listnumber"):
#                 return None
#             return {"type": "paragraph", "text": block.get("text") or ""}
#         return None
#
#     async def addin_job(self, event):
#         job = event.get("job") or {}
#         ops = list(job.get("ops") or [])
#
#         # поднимаем IDs СРАЗУ, чтобы можно было использовать в ops
#         from uuid import uuid4, UUID
#         job_id = str(event.get("jobId") or (job.get("meta") or {}).get("job_id") or uuid4())
#         trace_id = (job.get("meta") or {}).get("trace_id") or event.get("trace_id") or ""
#
#         # якорь первым абзацем (как и раньше)
#         anchor_text = ""
#         try:
#             anchor = job.get("anchor") or {}
#             anchor_text = (anchor.get("text") or "").strip()
#         except Exception:
#             anchor_text = ""
#         if anchor_text:
#             ops = [{"op": "paragraph.insert", "text": anchor_text}] + ops
#
#         # ХВОСТ С JOB-ID ВСЕГДА ПОСЛЕДНИМ
#         ops.append({"op": "job.marker.tail", "jobId": job_id})
#
#         payload = {
#             "type": "addin.block",
#             "jobId": job_id,
#             "traceId": str(trace_id) if trace_id else "",
#             "blocks": ops,
#             "docUrl": event.get("docUrl") or (job.get("meta") or {}).get("doc_url") or ""
#         }
#
#         await self.send_json(payload)
#
#         # логирование (как было)
#         try:
#             user = getattr(self.scope, "user", None)
#             if not getattr(user, "is_authenticated", False):
#                 user = None
#             await self._plog_info(
#                 user, phase="ws", event="emit.addin.block.payload.full",
#                 message=f"Full payload: {len(ops)} ops",
#                 trace_id=trace_id or None,
#                 job_id=(UUID(job_id) if len(str(job_id)) == 36 else None),
#                 data={
#                     "doc_url": payload["docUrl"],
#                     "job_id": job_id,
#                     "trace_id": trace_id,
#                     "ops": [
#                         {
#                             "index": i,
#                             "op": op.get("op") or op.get("kind") or op.get("type"),
#                             "text": (op.get("text") or "")[:100],
#                             "location": op.get("location"),
#                             "fileName": op.get("fileName"),
#                             "base64_len": len(op.get("base64", "")),
#                             "has_base64": bool(op.get("base64")),
#                             "jobId": op.get("jobId"),
#                         }
#                         for i, op in enumerate(ops)
#                     ]
#                 }
#             )
#             await self._plog_info(
#                 user, phase="ws", event="emit.addin.block",
#                 message=f"ops={len(ops)}",
#                 trace_id=trace_id or None,
#                 job_id=(UUID(job_id) if len(str(job_id)) == 36 else None),
#                 data={
#                     "doc_url": bool(payload["docUrl"]),
#                     "ops_preview": [(o.get("op") or o.get("kind") or o.get("type")) for o in ops[:10]],
#                     "client_email": self.email,
#                     "ws_channel": self.channel_name,
#                 }
#             )
#         except Exception as e:
#             log.exception("WS OUT addin.block log failed: %s", e)

    async def receive_json(self, content, **kwargs):
        from django.contrib.auth.models import AnonymousUser
        from uuid import UUID, uuid4

        # безопасно получаем пользователя (если неавторизован — None)
        user = getattr(self, "user", None) or self.scope.get("user") or AnonymousUser()
        if not getattr(user, "is_authenticated", False):
            user_for_log = None
        else:
            user_for_log = user

        # тип сообщения
        msg_type = str((content or {}).get("type") or "")

        # trace_id из нескольких возможных ключей
        trace_id = (
                content.get("traceId")
                or content.get("TraceId")
                or content.get("trace_id")
                or str(uuid4())
        )

        if msg_type == "addin.ack":
            job_id = str(content.get("jobId") or "")
            applied = int(content.get("appliedOps") or 0)
            anchor_found = bool(content.get("anchorFound"))
            selection_moved = bool(content.get("selectionMoved"))

            # uuid для plog (если job_id валидный UUID)
            job_uuid = None
            try:
                if job_id and len(job_id) == 36:
                    job_uuid = UUID(job_id)
            except Exception:
                job_uuid = None

            # логируем ACK
            try:
                await self._plog_info(
                    user_for_log,
                    phase="ack",
                    event="addin.applied",
                    message=f"applied={applied}",
                    job_id=job_uuid,
                    trace_id=trace_id,
                    data={
                        "applied_ops": applied,
                        "anchor_found": anchor_found,
                        "selection_moved": selection_moved,
                        "ws_channel": self.channel_name,
                    },
                )
            except Exception as e:
                log.exception("ACK log failed: %s", e)

            # обновим кеш для последующих пакетов без id
            try:
                if job_id:
                    cache.set(f"ws:last_job:{self.group_name}", job_id, 900)
                if trace_id:
                    cache.set(f"ws:last_trace:{self.group_name}", trace_id, 900)
            except Exception:
                pass

            return  # ACK обработан

        # Прочие типы — мягко логируем как неизвестные (не критично)
        try:
            await self._plog_info(
                user_for_log,
                phase="ws",
                event="recv.unknown",
                message=f"type={msg_type}",
                trace_id=trace_id or None,
                data={"raw": content},
            )
        except Exception:
            pass

    # --------------------------- fallback path --------------------------- #

    async def _emit_as_addin_block(self, *, event: dict):
        job = event.get("job") or {}
        ops = list(job.get("ops") or event.get("ops") or [])
        atext = ((job.get("anchor") or {}).get("text") or "").strip() if isinstance(job, dict) else ""
        if atext:
            ops = [{"op": "paragraph.insert", "text": atext}] + ops

        doc_url = (event.get("docUrl")
                   or (job.get("meta") or {}).get("doc_url")
                   or (job.get("meta") or {}).get("docUrl")
                   or "")

        job_id = (event.get("jobId")
                  or (job.get("meta") or {}).get("job_id")
                  or str(uuid4()))
        trace_id = (event.get("traceId")
                    or (job.get("meta") or {}).get("trace_id")
                    or "")

        # добавляем хвост
        ops.append({"op": "job.marker.tail", "jobId": str(job_id)})

        payload = {"type": "addin.block", "blocks": ops, "docUrl": doc_url, "jobId": str(job_id),
                   "traceId": str(trace_id)}
        await self.send_json(payload)

        try:
            user = getattr(self.scope, "user", None)
            if not getattr(user, "is_authenticated", False):
                user = None
            await self._plog_info(
                user, phase="ws", event="emit.addin.block",
                message=f"ops={len(ops)}",
                trace_id=(trace_id or None),
                data={
                    "doc_url": bool(doc_url),
                    "ops_preview": [(o.get("op") or o.get("kind") or o.get("type")) for o in ops[:10]],
                    "client_email": self.email,
                    "ws_channel": self.channel_name,
                }
            )
        except Exception as e:
            log.exception("WS OUT addin.block log failed: %s", e)