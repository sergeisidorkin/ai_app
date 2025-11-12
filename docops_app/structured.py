# /Users/sergei/PycharmProjects/ai_app/docops_app/structured.py
from __future__ import annotations
import json, re
from typing import Any, Dict, Optional, List

_FENCE = re.compile(
    r"```(?:docops|json)\s*?\n(?P<body>\{[\s\S]*?\})\s*?\n```",
    re.IGNORECASE,
)

def _try_json(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _extract_first_json_object(text: str) -> Optional[str]:
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

def extract_docops_control(text: str) -> Optional[Dict[str, Any]]:
    """Пытается найти JSON DocOps в ответе модели (в fenced-блоке или «сырым» JSON)."""
    if not text:
        return None
    m = _FENCE.search(text)
    if m:
        body = (m.group("body") or "").strip()
        data = _try_json(body)
        if isinstance(data, dict):
            if data.get("type") == "DocOps" or "ops" in data:
                return {"program": {
                    "type": "DocOps",
                    "version": data.get("version", "v1"),
                    "ops": data.get("ops", []),
                    "options": data.get("options") or {}
                }}
            if isinstance(data.get("docops"), dict):
                d = data["docops"]
                return {"program": {
                    "type": "DocOps",
                    "version": d.get("version", "v1"),
                    "ops": d.get("ops", []),
                    "options": d.get("options") or {}
                }}

    raw = _extract_first_json_object(text)
    data = _try_json(raw) if raw else None
    if isinstance(data, dict):
        if data.get("type") == "DocOps" or "ops" in data:
            return {"program": {
                "type": "DocOps",
                "version": data.get("version", "v1"),
                "ops": data.get("ops", []),
                "options": data.get("options") or {}
            }}
        if isinstance(data.get("docops"), dict):
            d = data["docops"]
            return {"program": {
                "type": "DocOps",
                "version": d.get("version", "v1"),
                "ops": d.get("ops", []),
                "options": d.get("options") or {}
            }}

    return None

# ── ВАЖНО: синтезируем список из «- ...» / «• ...» внутри обычного текста
def _decode_escapes(t: str) -> str:
    if not t:
        return ""
    def once(s: str) -> str:
        return (s.replace("\\r\\n","\n")
                 .replace("\\r","\n")
                 .replace("\\n","\n")
                 .replace("\\t","\t"))
    prev = None
    while prev != t and "\\n" in t or "\\t" in t or "\\r" in t:
        prev, t = t, once(t)
    # убираем markdown-разрывы "  \n"
    t = re.sub(r"[ \t]+(?:\n|\\n)", "\n", t)
    return t

def synthesize_docops_from_text(text: str, bullet_style_name: str = "Маркированный список") -> Optional[Dict[str, Any]]:
    """
    Вариант B: если модель НЕ прислала DocOps, но в тексте есть пункты "- ..." / "• ...",
    делаем DocOps-программу: paragraph.insert + list.start/item/end со styleName.
    """
    t = _decode_escapes(text or "").strip()
    if not t:
        return None

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    ops: List[Dict[str, Any]] = []
    bullet_re = re.compile(r"^\s*([-–—•\*])\s+(.*\S)\s*$")

    found_any_list = False

    for para in paragraphs:
        lines = para.split("\n")
        # сколько строк в параграфе похожи на пункты
        matches = [bullet_re.match(ln) for ln in lines]
        cnt = sum(1 for m in matches if m)

        if cnt >= 2:
            # считаем параграф списком
            found_any_list = True
            ops.append({"op": "list.start", "listType": "ListBullet", "styleName": bullet_style_name})
            for m in matches:
                if m:
                    ops.append({"op": "list.item", "text": m.group(2)})
            ops.append({"op": "list.end"})
        elif cnt == 1 and len(lines) == 1:
            # одиночный пункт — тоже как список
            found_any_list = True
            ops.append({"op": "list.start", "listType": "ListBullet", "styleName": bullet_style_name})
            m = matches[0]
            ops.append({"op": "list.item", "text": m.group(2) if m else lines[0].lstrip("-•*—– ").strip()})
            ops.append({"op": "list.end"})
        else:
            # обычный абзац
            ops.append({"op": "paragraph.insert", "text": para})

    if not ops:
        return None

    return {"type": "DocOps", "version": "v1", "ops": ops}