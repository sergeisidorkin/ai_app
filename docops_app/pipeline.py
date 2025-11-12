# docops_app/pipeline.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from .parsers import try_extract_docops_json
from .structured import extract_docops_control, synthesize_docops_from_text
from .ir import program_from_dict, DocProgram, validate_ir
from .compile_addin import compile_to_addin_blocks
from .normalize import load_ruleset, resolve_style

# NEW: централизованный логгер
from logs_app import utils as plog

_RULESET_PATH = "docops_app/rulesets/base.ru.yml"


def _normalize_program_styles(prog: DocProgram, rules) -> Tuple[DocProgram, bool]:
    changed = False
    for op in prog.ops:
        if op.op == "paragraph.insert":
            human = getattr(op, "style_name_hint", None)
            if human:
                canon, style_id = resolve_style(human, rules)
                if canon and op.style != canon:
                    op.style = canon
                    changed = True
                if style_id and op.style_id != style_id:
                    op.style_id = style_id
                    changed = True

        if op.op == "list.start":
            human = getattr(op, "style_name_hint", None)
            if human:
                canon, style_id = resolve_style(human, rules)
                if (not getattr(op, "list_type", None)) and canon in ("ListBullet", "ListNumber"):
                    op.list_type = canon
                    changed = True
                if style_id and op.style_id != style_id:
                    op.style_id = style_id
                    changed = True
    return prog, changed


def _validate_safe(prog: DocProgram) -> Tuple[bool, Optional[str]]:
    try:
        validate_ir(prog)
        return True, None
    except Exception as e:
        return False, str(e)


def _should_skip_blocks(prog: DocProgram) -> bool:
    """
    Для render=docx не собираем add-in blocks превью, чтобы не падать на незнакомых опах
    (table.* и т.п.). Далее по цепочке всё равно пойдём через macroops → docx.insert.
    """
    try:
        return bool((prog.options or {}).get("render", "").lower() == "docx")
    except Exception:
        return False


def _ops_preview(ops: list[dict[str, Any]] | list) -> list[str]:
    """Короткая сводка по операциям/блокам для логов: ['paragraph.insert','list.start',...]"""
    out: list[str] = []
    try:
        for o in (ops or [])[:20]:
            k = None
            if isinstance(o, dict):
                k = o.get("op") or o.get("kind") or o.get("type")
            else:
                # объект DocOp
                k = getattr(o, "op", None) or getattr(o, "kind", None) or getattr(o, "type", None)
            out.append(str(k or "?"))
    except Exception:
        pass
    return out


def process_answer_through_pipeline(
    answer: str,
    *,
    user=None,
    trace_id=None,
    request_id=None,
    project_code6: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Унифицированный пайплайн DocOps + подробное логирование.
    """

    def log(lev: str, phase: str, event: str, message: str = "", **data):
        fn = getattr(plog, lev, plog.info)
        try:
            fn(
                user,
                phase=phase,
                event=event,
                message=message,
                trace_id=trace_id,
                request_id=request_id,
                project_code6=(project_code6 or ""),
                **data,
            )
        except Exception:
            # Логи не должны ломать пайплайн
            pass

    rules = load_ruleset(_RULESET_PATH)

    log("info", "docops", "start", message=f"answer_len={len(answer or '')}")

    try:
        # ── 1) Raw DocOps прямо в ответе ──────────────────────────────────────
        raw = None
        try:
            raw = try_extract_docops_json(answer)
        except Exception as e:
            log("error", "docops.parse", "raw_parser.error", message=str(e))
            raw = None

        if raw:
            ops_cnt = len(raw.get("ops") or [])
            log(
                "info",
                "docops.parse",
                "raw_docops.detected",
                data={"ops": ops_cnt, "ops_preview": _ops_preview(raw.get("ops"))},
            )

            prog = program_from_dict(raw)
            try:
                if getattr(prog, "options", None) and (prog.options or {}).get("render") == "docx":
                    log("info", "docops.options", "render.docx", message="flag seen in raw")
            except Exception:
                pass

            prog, norm_changed = _normalize_program_styles(prog, rules)
            if norm_changed:
                log("info", "docops.normalize", "styles.updated")

            ok, err = _validate_safe(prog)
            if not ok:
                # invalid: без блоков, возвращаем ошибку
                result = {
                    "kind": "docops",
                    "program": prog.to_dict(),
                    "docops": {
                        "type": "DocOps",
                        "version": prog.version,
                        "ops": [o.to_dict() for o in prog.ops],
                    },
                    "blocks": [],
                    "normalized": bool(norm_changed),
                    "source": "raw_docops",
                    "valid": False,
                    "error": err,
                }
                log("info", "docops", "done", data={"valid": False, "source": "raw_docops"})
                return result

            # ok == True
            if _should_skip_blocks(prog):
                blocks: list[dict] = []
                log("info", "docops.compile", "skipped", message="skip addin blocks for render=docx")
            else:
                blocks = compile_to_addin_blocks(prog)
                log(
                    "info",
                    "docops.compile",
                    "blocks",
                    data={"count": len(blocks), "kinds": _ops_preview(blocks)},
                )

            result = {
                "kind": "docops",
                "program": prog.to_dict(),
                "docops": {
                    "type": "DocOps",
                    "version": prog.version,
                    "ops": [o.to_dict() for o in prog.ops],
                },
                "blocks": blocks,
                "normalized": bool(norm_changed),
                "source": "raw_docops",
                "valid": True,
            }
            log("info", "docops", "done", data={"valid": True, "source": "raw_docops", "blocks": len(blocks)})
            return result

        # ── 2) JSON program внутри текста (толерантный парсер) ───────────────
        ctrl = extract_docops_control(answer)
        if ctrl and ctrl.get("program"):
            ops_cnt = len((ctrl["program"] or {}).get("ops") or [])
            log(
                "info",
                "docops.parse",
                "json_in_text.detected",
                data={
                    "ops": ops_cnt,
                    "ops_preview": _ops_preview((ctrl["program"] or {}).get("ops")),
                },
            )

            prog = program_from_dict(ctrl["program"])
            try:
                if getattr(prog, "options", None) and (prog.options or {}).get("render") == "docx":
                    log("info", "docops.options", "render.docx", message="flag seen in text")
            except Exception:
                pass

            prog, norm_changed = _normalize_program_styles(prog, rules)
            if norm_changed:
                log("info", "docops.normalize", "styles.updated")

            ok, err = _validate_safe(prog)
            if not ok:
                result = {
                    "kind": "docops",
                    "program": prog.to_dict(),
                    "docops": {
                        "type": "DocOps",
                        "version": prog.version,
                        "ops": [o.to_dict() for o in prog.ops],
                    },
                    "blocks": [],
                    "normalized": bool(norm_changed),
                    "source": "json_in_text",
                    "valid": False,
                    "error": err,
                }
                log("info", "docops", "done", data={"valid": False, "source": "json_in_text"})
                return result

            if _should_skip_blocks(prog):
                blocks: list[dict] = []
                log("info", "docops.compile", "skipped", message="skip addin blocks for render=docx")
            else:
                blocks = compile_to_addin_blocks(prog)
                log(
                    "info",
                    "docops.compile",
                    "blocks",
                    data={"count": len(blocks), "kinds": _ops_preview(blocks)},
                )

            result = {
                "kind": "docops",
                "program": prog.to_dict(),
                "docops": {
                    "type": "DocOps",
                    "version": prog.version,
                    "ops": [o.to_dict() for o in prog.ops],
                },
                "blocks": blocks,
                "normalized": bool(norm_changed),
                "source": "json_in_text",
                "valid": True,
            }
            log("info", "docops", "done", data={"valid": True, "source": "json_in_text", "blocks": len(blocks)})
            return result

        # ── 3) Синтез из plain-text ─────────────────────────────────────────
        synthesized = synthesize_docops_from_text(answer)
        if not synthesized:
            log("warn", "docops.parse", "empty", message="no docops nor synthesized text")
            prog = program_from_dict({"type": "DocOps", "version": "v1", "ops": []})
            result = {
                "kind": "empty",
                "program": prog.to_dict(),
                "docops": {"type": "DocOps", "version": "v1", "ops": []},
                "blocks": [],
                "normalized": False,
                "source": "plain_text_empty",
                "valid": False,
                "error": "empty",
            }
            log("info", "docops", "done", data={"valid": False, "source": "plain_text_empty"})
            return result

        log(
            "info",
            "docops.parse",
            "synthesized",
            data={"ops": len(synthesized.get("ops") or []), "ops_preview": _ops_preview(synthesized.get("ops"))},
        )

        prog = program_from_dict(synthesized)
        log(
            "debug",
            "docops.program",
            "from_synthesized",
            data={"ops": len(prog.ops), "ops_preview": _ops_preview(prog.ops)},
        )

        prog, norm_changed = _normalize_program_styles(prog, rules)
        if norm_changed:
            log("info", "docops.normalize", "styles.updated")

        ok, err = _validate_safe(prog)
        if not ok:
            result = {
                "kind": "docops",
                "program": prog.to_dict(),
                "docops": {
                    "type": "DocOps",
                    "version": prog.version,
                    "ops": [o.to_dict() for o in prog.ops],
                },
                "blocks": [],
                "normalized": bool(norm_changed),
                "source": "synthesized",
                "valid": False,
                "error": err,
            }
            log("info", "docops", "done", data={"valid": False, "source": "synthesized"})
            return result

        if _should_skip_blocks(prog):
            blocks: list[dict] = []
            log("info", "docops.compile", "skipped", message="skip addin blocks for render=docx")
        else:
            blocks = compile_to_addin_blocks(prog)
            log(
                "info",
                "docops.compile",
                "blocks",
                data={"count": len(blocks), "kinds": _ops_preview(blocks)},
            )

        result = {
            "kind": "docops",
            "program": prog.to_dict(),
            "docops": {
                "type": "DocOps",
                "version": prog.version,
                "ops": [o.to_dict() for o in prog.ops],
            },
            "blocks": blocks,
            "normalized": bool(norm_changed),
            "source": "synthesized",
            "valid": True,
        }
        log("info", "docops", "done", data={"valid": True, "source": "synthesized", "blocks": len(blocks)})
        return result

    except Exception as e:
        # Неожиданная ошибка самого пайплайна
        log("error", "docops", "exception", message=str(e))
        # Зафиксируем как invalid
        try:
            prog = program_from_dict({"type": "DocOps", "version": "v1", "ops": []})
        except Exception:
            prog = DocProgram()
        result = {
            "kind": "error",
            "program": prog.to_dict(),
            "docops": {"type": "DocOps", "version": "v1", "ops": []},
            "blocks": [],
            "normalized": False,
            "source": "exception",
            "valid": False,
            "error": str(e),
        }
        log("info", "docops", "done", data={"valid": False, "source": "exception"})
        return result