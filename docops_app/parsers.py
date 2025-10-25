import json, re
from typing import Optional, Dict, Any

_FENCE_RE = re.compile(
    r"^\s*```(?:docops|json)?\s*(?P<json>\{.*\})\s*```",
    re.IGNORECASE | re.DOTALL
)

def _strip_fences(s: str) -> str:
    m = _FENCE_RE.search(s or "")
    return (m.group("json") if m else s or "").strip()

def try_extract_docops_json(answer: str) -> Optional[Dict[str, Any]]:
    """
    Пытается вытащить из строки ответ LLM объект DocOps:
    {"type":"DocOps","version":"v1","ops":[...]}
    Возвращает dict или None.
    """
    raw = _strip_fences(answer)
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if (obj.get("type") == "DocOps"
        and obj.get("version") in ("v1", "1")
        and isinstance(obj.get("ops"), list)):
        return obj
    return None