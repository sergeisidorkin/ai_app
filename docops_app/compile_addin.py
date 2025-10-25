from typing import Dict, Any, List
from .ir import DocProgram, DocOp

STYLE_NAME_TO_ID = {
    "маркированный список": "a",
}

def _style_id_for(style_name_hint: str | None, built_in: str | None) -> str | None:
    if style_name_hint:
        sid = STYLE_NAME_TO_ID.get(style_name_hint.strip().lower())
        if sid:
            return sid
    if (built_in or "").strip().lower() == "listbullet":
        return "a"
    return None

def op_to_block(op: DocOp) -> dict:
    if op.op == "paragraph.insert":
        text = op.text or ""

        # базовый блок
        block = {
            "kind": "paragraph.insert",
            "text": text,
            "styleBuiltIn": op.style or None,                 # "ListBullet" и т.п.
            "styleName": getattr(op, "style_name_hint", None),# ← фронт читает styleName
            "styleNameHint": getattr(op, "style_name_hint", None),
        }

        # проставим styleId, если известно
        style_id = getattr(op, "style_id", None) or _style_id_for(
            getattr(op, "style_name_hint", None), op.style
        )
        if style_id:
            block["styleId"] = style_id

        # NBSP снимать не будем — фронт сам вставит пустой <w:p> без <w:r>
        return block

    if op.op == "paragraph.apply_style":
        return {
            "kind": "paragraph.apply_style",
            "styleBuiltIn": op.style,
            "styleName": getattr(op, "style_name_hint", None),
            "styleNameHint": getattr(op, "style_name_hint", None),
            # styleId тут обычно не нужен
        }

    if op.op == "list.start":
        style_name = getattr(op, "style_name_hint", None)
        style_id = getattr(op, "style_id", None) or _style_id_for(style_name, None)
        block = {"kind": "list.start"}
        if style_name:
            block["styleName"] = style_name
            block["styleNameHint"] = style_name
        if style_id:
            block["styleId"] = style_id
        return block

    if op.op == "list.item":
        return {
            "kind": "list.item",
            "text": op.text or "",
        }

    if op.op == "list.end":
        return { "kind": "list.end" }

    raise ValueError(f"Неизвестная операция: {op.op}")

def compile_to_addin_blocks(program: DocProgram) -> List[Dict[str, Any]]:
    return [op_to_block(op) for op in program.ops]