import json, re
from typing import Optional, Dict, Any

_FENCE_RE = re.compile(
    r"^\s*```(?:docops|json)?\s*(?P<json>\{.*\})\s*```",
    re.IGNORECASE | re.DOTALL
)

def _extract_first_json_object(text: str) -> Optional[str]:
    """Находит первый {...}-объект с балансом скобок в тексте."""
    if not text:
        return None
    i = text.find("{")
    if i < 0:
        return None
    depth = 0
    for j, ch in enumerate(text[i:], start=i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j+1]
    return None

def _try_json(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None

def try_extract_docops_json(answer: str) -> Optional[Dict[str, Any]]:
    """
    Пытается вытащить объект DocOps:
      {"type":"DocOps","version":"v1","ops":[...], "options":{...}}
    Возвращает dict или None.
    Поддерживает:
    - fenced-блоки ```docops / ```json где угодно
    - «сырой» JSON в тексте (первый сбалансированный {...})
    - строковый литерал JSON (экранированный)
    Сохраняет поле options без изменений, если оно есть.
    """
    if not answer:
        return None

    s = answer

    # 1) fenced-блок
    m = _FENCE_RE.search(s)
    if m:
        body = (m.group("body") or "").strip()
        obj = _try_json(body)
        if isinstance(obj, dict):
            # допускаем обёртку {"program": {...}} или {"docops": {...}}
            cand = obj.get("program") or obj.get("docops") or obj
            if isinstance(cand, dict):
                if (cand.get("type") == "DocOps"
                    and cand.get("version") in ("v1", "1")
                    and isinstance(cand.get("ops"), list)):
                    # options сохраняем как есть (если есть)
                    if "options" not in cand:
                        # не навязываем пустой dict — просто возвращаем как есть
                        pass
                    return cand

    # 2) если прислали JSON как строковый литерал
    raw = s.strip()
    if raw.startswith('"') and raw.endswith('"') and '\\"type\\":\\"DocOps\\"' in raw:
        try:
            raw = json.loads(raw)  # разворачиваем строку в json-текст
        except Exception:
            pass

    # 3) первый сбалансированный {...}
    snippet = _extract_first_json_object(raw)
    if not snippet:
        return None
    obj = _try_json(snippet)
    if not isinstance(obj, dict):
        return None

    cand = obj.get("program") or obj.get("docops") or obj
    if not isinstance(cand, dict):
        return None

    if (cand.get("type") == "DocOps"
        and cand.get("version") in ("v1", "1")
        and isinstance(cand.get("ops"), list)):
        return cand

    return None