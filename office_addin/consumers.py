# /office_addin/consumers.py
import re, urllib.parse, logging, uuid
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from asgiref.sync import sync_to_async
from uuid import uuid4
from django.contrib.auth.models import AnonymousUser

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

class AddinConsumer(AsyncJsonWebsocketConsumer):
    async def _plog_info(self, *args, **kwargs):
        # ленивый импорт, чтобы не дёргать модели до setup()
        from logs_app import utils as plog
        return await sync_to_async(plog.info, thread_sensitive=True)(*args, **kwargs)

    async def connect(self):
        # ОБЯЗАТЕЛЬНО сохраняем self.user
        self.user = self.scope.get("user") or AnonymousUser()

        raw = (self.scope.get("url_route", {}) or {}).get("kwargs", {}).get("email") or ""
        self.email = raw
        self.group_name = group_for_email(raw)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        try:
            uid = getattr(self.user, "id", None)
            if uid:
                cache.set(f"addin:last_email:{uid}", raw, 3600)
        except Exception:
            pass

        await self.send_json({"type": "hello", "group": self.group_name})
        log.warning("WS connected: group=%s chan=%s", self.group_name, self.channel_name)

    async def disconnect(self, code):
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            pass

    async def ws_addin_block(self, event):
        return await self.addin_block(event)

    async def ws_addin_job(self, event):
        return await self.addin_job(event)

    async def addin_block(self, event):
        """
        Нормализуем разные варианты payload и пишем компактный лог в plog.
        Поддерживает:
          - {"type":"addin.block","blocks":[...], "docUrl": "...", "jobId":"...", "traceId":"..."}
          - {"type":"addin.block","block": {...}}                       (один op)
          - fallback: если вместо blocks/block пришли job/ops → отдаём через _emit_as_addin_block
        """
        try:
            # 1) ops
            if isinstance(event.get("blocks"), list):
                blocks = list(event.get("blocks") or [])
            elif event.get("block"):
                blocks = [event.get("block")]
            else:
                return await self._emit_as_addin_block(event=event)

            # 2) поля
            doc_url  = event.get("docUrl") or ""
            job_id   = (event.get("jobId") or "") or ""
            trace_id = (event.get("traceId") or "") or ""

            # 2a) добор из cache, если пусто
            try:
                if not trace_id:
                    from django.core.cache import cache
                    trace_id = cache.get(f"ws:last_trace:{self.group_name}") or ""
                if not job_id:
                    from django.core.cache import cache
                    job_id = cache.get(f"ws:last_job:{self.group_name}") or ""
            except Exception:
                pass

            # 3) клиентский payload
            payload = {"type": "addin.block", "blocks": blocks, "docUrl": doc_url}
            if job_id:   payload["jobId"] = job_id
            if trace_id: payload["traceId"] = trace_id
            await self.send_json(payload)

            # 4) лог
            try:
                user = getattr(self.scope, "user", None)
                if not getattr(user, "is_authenticated", False):
                    user = None
                job_uuid = None
                try:
                    if job_id:
                        job_uuid = uuid.UUID(str(job_id))
                except Exception:
                    job_uuid = None
                blocks = event.get("blocks") or []
                trace_id = event.get("traceId") or event.get("trace_id") or str(uuid4())
                await self._plog_info(
                    user, phase="ws", event="emit.addin.block",
                    message=f"ops={len(blocks)}",
                    job_id=job_uuid,
                    trace_id=trace_id,
                    data={
                        "doc_url": bool(doc_url),
                        "ops_preview": [(o.get("op") or o.get("kind") or o.get("type")) for o in blocks[:10]],
                        "client_email": self.email,
                        "ws_channel": self.channel_name,
                    }
                )
            except Exception as e:
                log.exception("WS OUT addin.block log failed: %s", e)

        except Exception as e:
            log.exception("addin_block failed: %s", e)


    async def paragraph(self, event):
        # Старые события {"type":"paragraph", ...} — игнорируем
        log.warning("WS ignore legacy 'paragraph' event: %s", event)
        return

    def _to_legacy(self, block: dict) -> dict | None:
        kind = block.get("kind") or block.get("op")
        if kind == "paragraph.insert":
            style = (block.get("styleBuiltIn") or "").lower()
            if style in ("listbullet", "listnumber"):
                return None
            return {"type": "paragraph", "text": block.get("text") or ""}
        return None

    async def addin_job(self, event):
        job = event.get("job") or {}
        ops = list(job.get("ops") or [])

        # якорь первым абзацем
        anchor_text = ""
        try:
            anchor = job.get("anchor") or {}
            anchor_text = (anchor.get("text") or "").strip()
        except Exception:
            anchor_text = ""
        if anchor_text:
            ops = [{"op": "paragraph.insert", "text": anchor_text}] + ops

        # IDs для трассы
        job_id = str(event.get("jobId") or (job.get("meta") or {}).get("job_id") or uuid.uuid4())
        trace_id = (job.get("meta") or {}).get("trace_id") or event.get("trace_id") or ""

        payload = {
            "type": "addin.block",
            "jobId": job_id,
            "traceId": str(trace_id) if trace_id else "",
            "blocks": ops,
            "docUrl": event.get("docUrl") or (job.get("meta") or {}).get("doc_url") or ""
        }

        await self.send_json(payload)

        # компактный лог отправки в панель
        try:
            user = getattr(self.scope, "user", None)
            if not getattr(user, "is_authenticated", False):
                user = None
            from uuid import UUID
            await self._plog_info(
                user, phase="ws", event="emit.addin.block",
                message=f"ops={len(ops)}",
                trace_id=trace_id or None,
                job_id=(UUID(job_id) if len(str(job_id)) == 36 else None),
                data={
                    "doc_url": bool(payload["docUrl"]),
                    "ops_preview": [(o.get("op") or o.get("kind") or o.get("type")) for o in ops[:10]],
                    "client_email": self.email,
                    "ws_channel": self.channel_name,
                }
            )
        except Exception as e:
            log.exception("WS OUT addin.block log failed: %s", e)

    async def receive_json(self, content, **kwargs):
        from django.contrib.auth.models import AnonymousUser
        user = getattr(self, "user", None) or self.scope.get("user") or AnonymousUser()
        if content.get("type") == "addin.ack":
            user = getattr(self.scope, "user", None)
            if not getattr(user, "is_authenticated", False):
                user = None
            job_id = content.get("jobId")
            trace_id = content.get("TraceId") or content.get("traceId") or None
            applied = int(content.get("appliedOps") or 0)

            job_uuid = None
            try:
                if job_id:
                    job_uuid = uuid.UUID(str(job_id))
            except Exception:
                job_uuid = None
        msg_type = content.get("type")
        trace_id = content.get("traceId") or content.get("trace_id") or str(uuid4())
        if msg_type == "addin.ack":
            await self._plog_info(
                self.user, "ack", "addin.applied",
                applied_ops=content.get("appliedOps"),
                anchor_found=content.get("anchorFound"),
                selection_moved=content.get("selectionMoved"),
                ws_channel=self.channel_name,
                trace_id=trace_id,
            )

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
                  or "")
        trace_id = (event.get("traceId")
                    or (job.get("meta") or {}).get("trace_id")
                    or "")

        payload = {"type": "addin.block", "blocks": ops, "docUrl": doc_url}
        if job_id:   payload["jobId"] = job_id
        if trace_id: payload["traceId"] = trace_id

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
                    "ops_preview": [(o.get("op") or o.get("kind") or o.get("type")) for o in ops[:10]],  # <-- ops!
                    "client_email": self.email,
                    "ws_channel": self.channel_name,
                }
            )
        except Exception as e:
            log.exception("WS OUT addin.block log failed: %s", e)