from __future__ import annotations
import uuid as _uuid
from typing import Any
from .models import LogEvent

# --- публичное API ---
def new_trace_id() -> _uuid.UUID:
    return _uuid.uuid4()

def info(user, phase: str, event: str, message: str = "", **kwargs) -> LogEvent:
    return log_event(user, level="INFO", phase=phase, event=event, message=message, **kwargs)

def warn(user, phase: str, event: str, message: str = "", **kwargs) -> LogEvent:
    return log_event(user, level="WARN", phase=phase, event=event, message=message, **kwargs)

def error(user, phase: str, event: str, message: str = "", **kwargs) -> LogEvent:
    return log_event(user, level="ERROR", phase=phase, event=event, message=message, **kwargs)

def debug(user, phase: str, event: str, message: str = "", **kwargs) -> LogEvent:
    return log_event(user, level="DEBUG", phase=phase, event=event, message=message, **kwargs)

def bind(user=None, **ctx):
    """Вернёт объект с методами info/warn/error/debug, которые доклеивают контекст."""
    class _Bound:
        def info(self, **k):  return info(user, **{**ctx, **k})
        def warn(self, **k):  return warn(user, **{**ctx, **k})
        def error(self, **k): return error(user, **{**ctx, **k})
        def debug(self, **k): return debug(user, **{**ctx, **k})
    return _Bound()

# --- внутренняя утилита ---
def _coerce_uuid(v) -> _uuid.UUID | None:
    if not v:
        return None
    if isinstance(v, _uuid.UUID):
        return v
    try:
        return _uuid.UUID(str(v))
    except Exception:
        return None

def _mk_payload(user, **kwargs) -> dict[str, Any]:
    # Нормализуем camelCase -> snake_case
    if "traceId" in kwargs and "trace_id" not in kwargs:
        kwargs["trace_id"] = kwargs.pop("traceId")
    if "jobId" in kwargs and "job_id" not in kwargs:
        kwargs["job_id"] = kwargs.pop("jobId")
    if "docUrl" in kwargs and "doc_url" not in kwargs:
        kwargs["doc_url"] = kwargs.pop("docUrl")

    allowed = {
        "email", "trace_id", "request_id", "job_id", "via",
        "project_code6", "company", "section", "anchor_text",
        "data", "doc_url"
    }
    payload = {k: kwargs.get(k) for k in allowed if k in kwargs}

    # Подхватим пользователя/почту, если передан request.user
    payload["user"] = user if getattr(user, "is_authenticated", False) else None
    if not payload.get("email") and getattr(user, "email", None):
        payload["email"] = user.email

    # Обязательно гарантируем trace_id
    t = _coerce_uuid(payload.get("trace_id"))
    if not t:
        t = new_trace_id()
    payload["trace_id"] = t

    # Приводим UUID-поля к UUID (или None)
    for key in ("job_id", "request_id"):
        if key in payload:
            payload[key] = _coerce_uuid(payload.get(key))

    return payload

def log_event(user, *, level: str, phase: str, event: str, message: str = "", **kwargs) -> LogEvent:
    payload = _mk_payload(user, **kwargs)
    return LogEvent.objects.create(level=level, phase=phase, event=event, message=message, **payload)
