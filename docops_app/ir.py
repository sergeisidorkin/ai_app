from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, Any


DocOpName = Literal[
    "paragraph.insert",
    "paragraph.apply_style",
    "list.start",
    "list.item",
    "list.end",
]

DocOpName = Literal["paragraph.insert","paragraph.apply_style","list.start","list.item","list.end"]

@dataclass
class DocOp:
    op: DocOpName
    style: Optional[str] = None               # Canonical: ListBullet / ListNumber / …
    style_id: Optional[str] = None            # ВАЖНО: ID стиля из шаблона ("a")
    style_name_hint: Optional[str] = None     # Как сказал пользователь
    text: Optional[str] = None
    list_type: Optional[Literal["ListBullet","ListNumber"]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"op": self.op}
        if self.style is not None: d["style"] = self.style
        if self.style_id is not None: d["style_id"] = self.style_id
        if self.style_name_hint is not None: d["style_name_hint"] = self.style_name_hint
        if self.text is not None: d["text"] = self.text
        if self.list_type is not None: d["list_type"] = self.list_type
        return d

@dataclass
class DocProgram:
    type: Literal["DocOps"] = "DocOps"
    version: str = "v1"
    ops: List[DocOp] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "ops": [op.to_dict() for op in self.ops],
        }

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
            # параграф может иметь текст и/или style
            pass
        elif op.op == "paragraph.apply_style":
            if not op.style:
                raise IRValidationError(f"op[{idx}] paragraph.apply_style требует style")
        elif op.op == "list.start":
            if op.list_type not in ("ListBullet", "ListNumber"):
                raise IRValidationError(f"op[{idx}] list.start требует list_type=ListBullet|ListNumber")
        elif op.op in ("list.item", "list.end"):
            pass
        else:
            raise IRValidationError(f"op[{idx}] неизвестная операция {op.op}")

def docop_from_dict(d: Dict[str, Any]) -> DocOp:
    """Терпимый парсер одной операции."""
    op = d.get("op") or d.get("kind") or d.get("type")
    if not op:
        raise ValueError("DocOps: 'op' is required")

    # Унифицируем имена полей для стилевых атрибутов
    style = d.get("styleBuiltIn") or d.get("style")  # 'ListBullet' и т.п.
    style_id = d.get("styleId") or d.get("style_id")
    style_name_hint = d.get("styleName") or d.get("styleLocalName") or d.get("style_name_hint")

    return DocOp(
        op=str(op),
        text=d.get("text"),
        style=style,
        style_id=style_id,
        style_name_hint=style_name_hint,
        list_type=d.get("listType") or d.get("list_type"),
    )

def program_from_dict(prog: Dict[str, Any]) -> DocProgram:
    """Собирает DocProgram из словаря {type:'DocOps', ops:[...] }."""
    if not isinstance(prog, dict) or "ops" not in prog:
        raise ValueError("DocOps program must contain 'ops'")
    ops = [docop_from_dict(x) for x in (prog.get("ops") or [])]
    return DocProgram(ops=ops, version=prog.get("version", "v1"))