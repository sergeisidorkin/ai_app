import re
import yaml
from dataclasses import dataclass
from typing import Dict, Any, List
from .ir import DocProgram, DocOp
from typing import Optional

@dataclass
class Ruleset:
    version: str
    styles: Dict[str, List[str]]  # Canonical -> [aliases]
    phrases: Dict[str, List[str]] # intent -> [regex patterns]

def load_ruleset(path: str) -> Ruleset:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Ruleset(
        version=str(data.get("version", "1")),
        styles=data.get("styles", {}),
        phrases=data.get("phrases", {}),
    )

def alias_to_canonical_style(human_name: str, rules: Ruleset) -> str | None:
    norm = human_name.strip().lower()
    for canon, aliases in rules.styles.items():
        # canon может тоже встречаться в тексте
        names = [canon] + (aliases or [])
        for n in names:
            if norm == str(n).strip().lower():
                return canon
    return None

def _styles_mapping_from_rules(rules) -> dict:
    """
    Достаём карту style_aliases из чего угодно:
    - Ruleset со свойством .style_aliases
    - Ruleset с .data["style_aliases"] или .data["aliases"]["styles"]
    - просто dict
    Ключи приводим к lower().
    """
    mapping = {}
    try:
        if hasattr(rules, "style_aliases") and getattr(rules, "style_aliases"):
            mapping = rules.style_aliases
        elif hasattr(rules, "data") and rules.data:
            data = rules.data or {}
            mapping = (data.get("style_aliases")
                       or (data.get("aliases") or {}).get("styles")
                       or {})
        elif isinstance(rules, dict):
            mapping = (rules.get("style_aliases")
                       or (rules.get("aliases") or {}).get("styles")
                       or {})
    except Exception:
        mapping = {}
    # нормализуем ключи
    return {str(k).strip().lower(): v for k, v in (mapping or {}).items()}

def resolve_style(human: str, rules) -> tuple[Optional[str], Optional[str]]:
    mapping = _styles_mapping_from_rules(rules)
    meta = mapping.get(human.strip().lower())
    if isinstance(meta, dict):
        return meta.get("canonical"), meta.get("style_id")

    # эвристики
    low = human.strip().lower()
    if "маркирован" in low or "bullet" in low:
        return "ListBullet", None
    if "нумерован" in low or "number" in low:
        return "ListNumber", None
    return None, None

# Очень простой распознаватель интентов для Фазы 1
def nl_to_ir(nl_text: str, rules: Ruleset) -> DocProgram:
    text = nl_text.strip()
    prog = DocProgram()

    # общая выемка: ... в стиле "XXX" / как «XXX»
    STYLE_CLAUSE = r'(?:стил[еия]\s+|как\s+|в\s+стиле\s+)'
    QUOTED_NAME  = r'[«"“]?([^»"”]+)[»"”]?'

    def _extract_style(s: str) -> str | None:
        m = re.search(STYLE_CLAUSE + QUOTED_NAME, s, flags=re.I)
        return m.group(1).strip() if m else None

    text = nl_text.strip()

    # 1) Универсальное извлечение: "в стиле|стиле|как" + «кавычки»
    m_style = re.search(r'(?:в\s+стиле|стил[еия]|как)\s+[«"“]?([^»"”]+)[»"”]?', text, flags=re.I)
    if m_style:
        human_style = m_style.group(1).strip()  # ← подсказка

        canon, style_id = resolve_style(human_style, rules)
        if canon:
            prog = DocProgram()
            prog.ops.append(DocOp(
                op="paragraph.insert",
                style=canon,
                style_id=style_id,  # ← прокидываем
                style_name_hint=human_style,
            ))
            return prog

    # 1a) Фоллбек: упоминание вида списка БЕЗ управляющего глагола → применяем стиль к абзацу
    if re.search(r'\bмаркированн\w*\s+список\b', text, flags=re.I) and not re.search(
            r'\b(начни|создай|включи|переключи)\b', text, flags=re.I):
        prog = DocProgram()
        prog.ops.append(DocOp(op="paragraph.insert", style="ListBullet", style_name_hint="Маркированный список"))
        return prog

    if re.search(r'\bнумерованн\w*\s+список\b', text, flags=re.I) and not re.search(
            r'\b(начни|создай|включи|переключи)\b', text, flags=re.I):
        prog = DocProgram()
        prog.ops.append(DocOp(op="paragraph.insert", style="ListNumber", style_name_hint="Нумерованный список"))
        return prog

    # 2) Явный старт списка (требуем управляющий глагол)
    if re.search(r'\b(начни|создай|включи|переключи)\b.*\bмаркированн\w*\s+список\b', text, flags=re.I):
        prog = DocProgram(); prog.ops.append(DocOp(op="list.start", list_type="ListBullet")); return prog
    if re.search(r'\b(начни|создай|включи|переключи)\b.*\bнумерованн\w*\s+список\b', text, flags=re.I):
        prog = DocProgram(); prog.ops.append(DocOp(op="list.start", list_type="ListNumber")); return prog

    # 3) Пункт списка
    m = re.search(r'(?:пункт|item|bullet)\s*[:\-–]\s*(.+)$', text, flags=re.I)
    if m:
        prog.ops.append(DocOp(op="list.item", text=m.group(1).strip()))
        return prog

    # 4) Завершить список
    if re.search(r'(?:заверш[иь]|законч[иь]).*список', text, flags=re.I):
        prog.ops.append(DocOp(op="list.end"))
        return prog

    # 5) Дефолт: пустой абзац
    prog.ops.append(DocOp(op="paragraph.insert"))
    return prog

def normalize_ir(prog: DocProgram, rules: Ruleset) -> DocProgram:
    """
    Проставляет канонические стили/ID по человекочитаемым названиям,
    добивает недостающие поля list_type и пр.
    Не меняет семантику, только приводит к канону.
    """
    new_ops: list[DocOp] = []

    for op in prog.ops:
        o = DocOp(
            op=op.op,
            text=op.text,
            style=op.style,
            style_id=op.style_id,
            style_name_hint=op.style_name_hint,
            list_type=op.list_type,
        )

        # paragraph.* — подтянуть style по подсказке
        if o.op in ("paragraph.insert", "paragraph.apply_style"):
            if (not o.style) and o.style_name_hint:
                canon, sid = resolve_style(o.style_name_hint, rules)
                if canon: o.style = canon
                if sid:   o.style_id = sid

        # list.start — если нет типа списка, попробуем вывести из подсказки
        if o.op == "list.start":
            if not o.list_type and o.style_name_hint:
                canon, _sid = resolve_style(o.style_name_hint, rules)
                if canon in ("ListBullet", "ListNumber"):
                    o.list_type = canon

        new_ops.append(o)

    return DocProgram(ops=new_ops, version=prog.version)