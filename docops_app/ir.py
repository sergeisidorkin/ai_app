# docops_app/ir.py
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, Any, Union

# Набор операций DocOps
DocOpName = Literal[
    "paragraph.insert",
    "paragraph.apply_style",
    "list.start",
    "list.item",
    "list.end",
    "table.start",
    "table.row",
    "table.cell",
    "table.end",
    "footnote.add",
    "caption.add",
    "image.insert",
    "docx.insert",
]

@dataclass
class DocOp:
    op: DocOpName
    # общие стилевые поля
    style: Optional[str] = None
    style_id: Optional[str] = None
    style_name_hint: Optional[str] = None
    text: Optional[str] = None

    # списки
    list_type: Optional[Literal["ListBullet","ListNumber"]] = None

    # таблицы
    cols: Optional[int] = None
    table_style: Optional[str] = None
    header: Optional[bool] = None

    # подписи (caption.add) ---
    target: Optional[Literal["table", "figure"]] = None      # влияет на дефолтную метку
    label: Optional[str] = None                              # «Таблица» / «Рисунок» и т.п.
    placement: Optional[Literal["above", "below"]] = None    # расположение подписи
    chapter_level: Optional[int] = None                      # 0/None=глобально; 1..=сброс по уровню

    # картинки (image.insert) ---
    base64: Optional[str] = None
    content_type: Optional[str] = None
    width_mm: Optional[Union[int, float]] = None
    height_mm: Optional[Union[int, float]] = None

    # поддержка docx.insert
    location: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"op": self.op}

        # общие/стили
        if self.style is not None: d["style"] = self.style
        if self.style_id is not None: d["style_id"] = self.style_id
        if self.style_name_hint is not None: d["style_name_hint"] = self.style_name_hint
        if self.text is not None: d["text"] = self.text

        # списки
        if self.list_type is not None: d["list_type"] = self.list_type

        # таблицы
        if self.cols is not None: d["cols"] = self.cols
        if self.table_style is not None: d["table_style"] = self.table_style
        if self.header is not None: d["header"] = self.header

        # caption.add
        if self.target is not None: d["target"] = self.target
        if self.label is not None: d["label"] = self.label
        if self.placement is not None: d["placement"] = self.placement
        if self.chapter_level is not None: d["chapterLevel"] = self.chapter_level  # camelCase наружу

        # image.insert
        if self.base64 is not None: d["base64"] = self.base64
        if self.content_type is not None: d["contentType"] = self.content_type    # camelCase
        if self.width_mm is not None: d["widthMm"] = self.width_mm
        if self.height_mm is not None: d["heightMm"] = self.height_mm

        # docx.insert
        if self.location is not None: d["location"] = self.location
        if self.file_name is not None: d["fileName"] = self.file_name
        if self.mime_type is not None: d["mimeType"] = self.mime_type

        return d

@dataclass
class DocProgram:
    type: Literal["DocOps"] = "DocOps"
    version: str = "v1"
    ops: List[DocOp] = field(default_factory=list)
    options: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "type": self.type,
            "version": self.version,
            "ops": [op.to_dict() for op in self.ops],
        }
        if self.options:
            out["options"] = self.options
        return out

# Минимальная валидация без внешних либ
class IRValidationError(ValueError):
    pass

def validate_ir(prog: DocProgram) -> None:
    if prog.type != "DocOps":
        raise IRValidationError("prog.type должен быть 'DocOps'")
    if not prog.version.startswith("v1"):
        raise IRValidationError("Поддерживается только DocOps v1 на этой фазе")
    for idx, op in enumerate(prog.ops):
        if op.op == "paragraph.insert":
            pass
        elif op.op == "paragraph.apply_style":
            if not op.style:
                raise IRValidationError(f"op[{idx}] paragraph.apply_style требует style")
        elif op.op == "list.start":
            if op.list_type not in ("ListBullet", "ListNumber") and not op.style:
                raise IRValidationError(f"op[{idx}] list.start требует list_type=ListBullet|ListNumber или style")
        elif op.op in ("list.item", "list.end"):
            pass
        elif op.op == "table.start":
            if op.cols is not None and (not isinstance(op.cols, int) or op.cols <= 0):
                raise IRValidationError(f"op[{idx}] table.start: cols должен быть положительным целым")
        elif op.op == "table.row":
            pass
        elif op.op == "table.cell":
            pass
        elif op.op == "table.end":
            pass
        elif op.op == "footnote.add":
            if not (op.text and isinstance(op.text, str)):
                raise IRValidationError(f"op[{idx}] footnote.add требует text")

        # caption.add
        elif op.op == "caption.add":
            if not (op.text and isinstance(op.text, str)):
                raise IRValidationError(f"op[{idx}] caption.add требует text")
            if op.placement is not None and op.placement not in ("above", "below"):
                raise IRValidationError(f"op[{idx}] caption.add: placement должен быть 'above'|'below'")
            if op.target is not None and op.target not in ("table", "figure"):
                raise IRValidationError(f"op[{idx}] caption.add: target должен быть 'table'|'figure'")
            if op.chapter_level is not None:
                try:
                    cl = int(op.chapter_level)
                    if cl < 0:
                        raise ValueError()
                except Exception:
                    raise IRValidationError(f"op[{idx}] caption.add: chapterLevel должен быть целым ≥ 0")

        # image.insert
        elif op.op == "image.insert":
            if not (op.base64 and isinstance(op.base64, str)):
                raise IRValidationError(f"op[{idx}] image.insert требует base64")
            # content_type/width_mm/height_mm — опциональны

        # docx.insert
        elif op.op == "docx.insert":
            if not (op.base64 and isinstance(op.base64, str)):
                raise IRValidationError(f"op[{idx}] docx.insert требует base64")
            if op.location is not None and op.location not in ("after","before","replace","start","end"):
                raise IRValidationError(f"op[{idx}] docx.insert: неверный location")

        else:
            raise IRValidationError(f"op[{idx}] неизвестная операция {op.op}")

def docop_from_dict(d: Dict[str, Any]) -> DocOp:
    """Терпимый парсер одной операции."""
    op = d.get("op") or d.get("kind") or d.get("type")
    if not op:
        raise ValueError("DocOps: 'op' is required")

    style = d.get("styleBuiltIn") or d.get("style")
    style_id = d.get("styleId") or d.get("style_id")
    style_name_hint = d.get("styleName") or d.get("styleLocalName") or d.get("style_name_hint")
    list_type = d.get("listType") or d.get("list_type")

    cols = d.get("cols") or d.get("columns")
    try:
        cols = int(cols) if cols is not None else None
    except Exception:
        cols = None

    table_style = d.get("tableStyle") or d.get("table_style")
    header = d.get("header") or d.get("isHeader") or d.get("is_header")

    # caption.add
    target = d.get("target")
    label = d.get("label")
    placement = d.get("placement")
    chapter_level = d.get("chapterLevel") or d.get("chapter_level")
    try:
        chapter_level = int(chapter_level) if chapter_level is not None else None
    except Exception:
        chapter_level = None

    # image.insert
    base64_data = d.get("base64")
    content_type = d.get("contentType") or d.get("mime") or d.get("content_type")
    def _num(x):
        try:
            return float(x)
        except Exception:
            return None
    width_mm  = d.get("widthMm")  or d.get("width_mm")
    height_mm = d.get("heightMm") or d.get("height_mm")
    width_mm  = _num(width_mm)  if width_mm  is not None else None
    height_mm = _num(height_mm) if height_mm is not None else None

    # (docx.insert
    location  = d.get("location")
    file_name = d.get("fileName") or d.get("file_name")
    mime_type = d.get("mimeType") or d.get("mime_type")

    return DocOp(
        op=str(op),
        text=d.get("text"),
        style=style,
        style_id=style_id,
        style_name_hint=style_name_hint,
        list_type=list_type,
        cols=cols,
        table_style=table_style,
        header=bool(header) if header is not None else None,

        target=target,
        label=label,
        placement=placement,
        chapter_level=chapter_level,

        base64=base64_data,
        content_type=content_type,
        width_mm=width_mm,
        height_mm=height_mm,

        location=location,
        file_name=file_name,
        mime_type=mime_type,
    )

def program_from_dict(prog: Dict[str, Any]) -> DocProgram:
    """Собирает DocProgram из словаря {type:'DocOps', ops:[...] }."""
    if not isinstance(prog, dict) or "ops" not in prog:
        raise ValueError("DocOps program must contain 'ops'")
    ops = [docop_from_dict(x) for x in (prog.get("ops") or [])]
    return DocProgram(
        ops=ops,
        version=prog.get("version", "v1"),
        options=prog.get("options") or None,
    )