# macroops_app/compiler.py
import os
import uuid
import tempfile
from django.conf import settings
from logs_app import utils as plog

from .chart_hydrator import build_chart_snippet_base64

ALLOWED = {
    "paragraph.insert",
    "list.start", "list.item", "list.end",
    "table.start", "table.row", "table.cell", "table.end",
    "footnote.add",
    "docx.insert",
    "caption.add",
    "image.insert",
}

def _trace_from_meta(meta: dict | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    return meta.get("trace_id") or meta.get("traceId") or None

def _email_from_meta(meta: dict | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    return (meta.get("email") or None)

def _request_from_meta(meta: dict | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    return (meta.get("request_id")
            or meta.get("requestId")
            or meta.get("job_id")
            or meta.get("jobId")
            or None)

def _project_code6_from_meta(meta: dict | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    # часто прилетает как code6 или project_code6
    return (meta.get("project_code6")
            or meta.get("code6")
            or None)

def _log_ctx_from_meta(meta: dict | None) -> dict:
    trace_id = _trace_from_meta(meta)
    email = _email_from_meta(meta)
    request_id = _request_from_meta(meta)
    project_code6 = _project_code6_from_meta(meta)
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "project_code6": project_code6,
        "email": email,
    }

def _wants_docx(meta: dict | None, docops: dict) -> bool:
    m = meta or {}
    if bool(m.get("useDocxInsert")):
        return True
    opts = (docops.get("options") or {}) if isinstance(docops, dict) else {}
    if (opts.get("render") or "").lower() == "docx":
        return True
    return False

def _ops_support_docx_build(ops_in: list[dict]) -> tuple[bool, str | None]:
    allowed_for_build = {
        "paragraph.insert",
        "list.start", "list.item", "list.end",
        "table.start", "table.row", "table.cell", "table.end",
        "footnote.add",
        "caption.add",
        "image.insert",
    }
    for op in ops_in:
        if not isinstance(op, dict):
            return False, "not_a_dict"
        k = op.get("op")
        if k not in allowed_for_build:
            return False, k or "unknown"
    return True, None

def _interleave_footnotes_apply_ops(
    ops: list[dict],
    *,
    marker: str = "&SRC&",
    scope: str = "last",
    trace_id: str | None = None,
    email: str | None = None,
) -> list[dict]:
    """
    После КАЖДОГО {"op":"docx.insert"} вставляем footnotes.apply-embedded,
    но если сразу после вставки идёт {"op":"caption.add"}, то сноски ставим ПОСЛЕ подписи.
    """
    if not isinstance(ops, list) or not ops:
        return ops

    new_ops: list[dict] = []
    i = 0
    injected = 0

    while i < len(ops):
        op = ops[i]
        if isinstance(op, dict) and op.get("op") == "docx.insert":
            new_ops.append(op)
            # lookahead: если дальше caption.add — переносим footnotes за него
            j = i + 1
            if j < len(ops) and isinstance(ops[j], dict) and ops[j].get("op") == "caption.add":
                new_ops.append(ops[j])  # подпись рядом с диаграммой
                i = j  # перепрыгнули caption
            # теперь — footnotes.apply-embedded
            new_ops.append({
                "op": "footnotes.apply-embedded",
                "marker": marker,
                "scope": scope,
            })
            injected += 1
        else:
            new_ops.append(op)
        i += 1

    if injected:
        try:
            plog.debug(
                None, phase="compile", event="footnotes.apply.injected",
                message=f"added {injected} footnotes.apply-embedded op(s) (after caption when present)",
                trace_id=trace_id, email=email,
                data={"ops_out": len(new_ops), "marker": marker, "scope": scope},
            )
        except Exception:
            pass

    return new_ops

def _expand_inline_chart_ops(ops: list[dict], *, log_ctx: dict | None = None) -> tuple[list[dict], list[dict]]:
    """
    Находит в ops инлайновые диаграммы и заменяет их на docx.insert.
    Возвращает (prepend_docx_inserts, ops_without_inline_charts).
    Поддерживаем:
      - {"op":"chart-snippet", "template":"...", "data":{...}, "location":"anchor:< HRM-01 >"}
      - {"op":"chart.insert",  ...}
      - {"op":"chart",         ...}
    """
    if not isinstance(ops, list) or not ops:
        return [], ops

    docx_inserts: list[dict] = []
    rest: list[dict] = []

    for idx, o in enumerate(ops):
        try:
            if not isinstance(o, dict):
                rest.append(o); continue
            op_name = (o.get("op") or o.get("kind") or o.get("type") or "").strip().lower()
            if op_name not in {"chart-snippet", "chart.insert", "chart"}:
                rest.append(o); continue

            template = (o.get("template") or "").strip()
            if not template:
                raise ValueError("inline chart: missing template")
            data = o.get("data") or {}
            location = (o.get("location") or "after")

            b64 = build_chart_snippet_base64(template=str(template), data=data, log_ctx=log_ctx)

            # Валидация: это .docx (ZIP 'PK' → base64 'UEs')
            if not b64 or not isinstance(b64, str):
                raise ValueError("inline chart: empty base64")
            try:
                import base64 as _b64
                raw = _b64.b64decode(b64.encode("ascii"))
                if not (len(raw) >= 2 and raw[0:2] == b"PK"):
                    raise ValueError("inline chart: not a ZIP/docx payload")
            except Exception as ve:
                raise ValueError(str(ve))

            file_name = f"chart-{template}-{uuid.uuid4().hex[:8]}.docx"
            docx_inserts.append({
                "op": "docx.insert",
                "base64": b64,
                "location": location,
                "fileName": file_name,
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            })

            try:
                plog.info(None, phase="compile", event="chart.inline.expanded",
                          message="inline chart op → docx.insert",
                          data={"template": template, "idx": idx}, **(log_ctx or {}))
            except Exception:
                pass

        except Exception as e:
            rest.append(o)  # сохраняем исходный op, чтобы не потерять контент
            try:
                plog.error(None, phase="compile", event="chart.inline.fail",
                           message=str(e), data={"idx": idx}, **(log_ctx or {}))
            except Exception:
                pass

    return docx_inserts, rest

def _expand_chart_assets_to_ops(options: dict, *, log_ctx: dict | None = None) -> list[dict]:
    """
    options.assets[kind=chart-snippet] -> список {"op":"docx.insert",...}
    Добавлено:
      • подробное логирование
      • валидация base64 как ZIP/docx
      • fallback: если гидрация упала — генерируем плейсхолдер .docx с текстом ошибки (чтобы визуально понять причину)
    """
    ops: list[dict] = []
    if not isinstance(options, dict):
        return ops

    assets = options.get("assets") or []
    try:
        plog.info(None, phase="compile", event="assets.scan",
                  message="scan options.assets",
                  data={"count": len(assets)}, **(log_ctx or {}))
    except Exception:
        pass

    if not isinstance(assets, list) or not assets:
        return ops

    for idx, a in enumerate(assets):
        try:
            if not isinstance(a, dict):
                continue
            kind = (a.get("kind") or "").lower().strip()
            if kind != "chart-snippet":
                try:
                    plog.debug(None, phase="compile", event="asset.skip",
                               message="non-chart asset kind",
                               data={"i": idx, "kind": kind}, **(log_ctx or {}))
                except Exception:
                    pass
                continue

            template = (a.get("template") or "").strip()
            loc = (a.get("location") or "after")
            data = a.get("data") or {}

            try:
                plog.info(None, phase="compile", event="chart.asset.try",
                          message="hydrate chart",
                          data={"i": idx, "template": template, "has_data": bool(data)},
                          **(log_ctx or {}))
            except Exception:
                pass

            if not template:
                raise ValueError("asset chart: missing template")

            b64 = build_chart_snippet_base64(template=str(template), data=data, log_ctx=log_ctx)

            # validate ZIP 'PK'
            if not b64 or not isinstance(b64, str):
                raise ValueError("asset chart: empty base64")
            import base64 as _b64
            raw = _b64.b64decode(b64.encode("ascii"))
            if not (len(raw) >= 2 and raw[0:2] == b"PK"):
                raise ValueError("asset chart: not a ZIP/docx payload")

            file_name = f"chart-{template}-{uuid.uuid4().hex[:8]}.docx"
            ops.append({
                "op": "docx.insert",
                "base64": b64,
                "location": loc,
                "fileName": file_name,
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            })

            try:
                plog.info(None, phase="compile", event="chart.asset.ok",
                          message="chart asset → docx.insert",
                          data={"i": idx, "template": template, "base64_len": len(b64)},
                          **(log_ctx or {}))
            except Exception:
                pass

        except Exception as e:
            # Логируем первопричину
            try:
                plog.error(None, phase="compile", event="chart.asset.fail",
                           message=str(e),
                           data={"i": idx, "asset": a},
                           **(log_ctx or {}))
            except Exception:
                pass
            # Плейсхолдер: не даём пайплайну «незаметно» схлопнуть всё в одиночный .docx без диаграммы
            try:
                from .docx_builder import build_docx_from_ops
                placeholder_ops = [{
                    "op": "paragraph.insert",
                    "text": f"⚠ Не удалось собрать диаграмму '{(a or {}).get('template') or ''}': {e}"
                }]
                ph_b64 = build_docx_from_ops(placeholder_ops, log_ctx=log_ctx)
                ops.append({
                    "op": "docx.insert",
                    "base64": ph_b64,
                    "location": (a.get("location") or "after"),
                    "fileName": f"chart-error-{uuid.uuid4().hex[:6]}.docx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                })
                try:
                    plog.warn(None, phase="compile", event="chart.asset.placeholder",
                              message="placeholder docx inserted",
                              data={"i": idx}, **(log_ctx or {}))
                except Exception:
                    pass
            except Exception as e2:
                # если даже плейсхолдер не собрался — просто продолжаем, но это будет видно в логах
                try:
                    plog.error(None, phase="compile", event="chart.placeholder.fail",
                               message=str(e2), data={"i": idx}, **(log_ctx or {}))
                except Exception:
                    pass

    if not ops:
        try:
            plog.warn(None, phase="compile", event="chart.assets.none",
                      message="no chart ops produced from assets",
                      data={"assets_count": len(assets)}, **(log_ctx or {}))
        except Exception:
            pass

    return ops

# --- inline charts expander (safe) ---
def _expand_inline_chart_ops(ops: list[dict], *, log_ctx: dict | None = None) -> tuple[list[dict], list[dict]]:
    """
    Находит в ops инлайновые диаграммы и заменяет их на docx.insert.
    Возвращает (prepend_docx_inserts, ops_without_inline_charts).
    Поддерживаем:
      - {"op":"chart-snippet", "template":"...", "data":{...}, "location":"anchor:< HRM-01 >"}
      - {"op":"chart.insert",  ...}
      - {"op":"chart",         ...}
    """
    if not isinstance(ops, list) or not ops:
        return [], ops

    docx_inserts: list[dict] = []
    rest: list[dict] = []

    for idx, o in enumerate(ops):
        try:
            if not isinstance(o, dict):
                rest.append(o); continue
            op_name = (o.get("op") or o.get("kind") or o.get("type") or "").strip().lower()
            if op_name not in {"chart-snippet", "chart.insert", "chart"}:
                rest.append(o); continue

            template = (o.get("template") or "").strip()
            if not template:
                raise ValueError("inline chart: missing template")

            data = o.get("data") or {}
            location = (o.get("location") or "after")

            b64 = build_chart_snippet_base64(template=str(template), data=data, log_ctx=log_ctx)

            # Валидация .docx (ZIP 'PK')
            if not b64 or not isinstance(b64, str):
                raise ValueError("inline chart: empty base64")
            import base64 as _b64
            raw = _b64.b64decode(b64.encode("ascii"))
            if not (len(raw) >= 2 and raw[0:2] == b"PK"):
                raise ValueError("inline chart: not a ZIP/docx payload")

            file_name = f"chart-{template}-{uuid.uuid4().hex[:8]}.docx"
            docx_inserts.append({
                "op": "docx.insert",
                "base64": b64,
                "location": location,
                "fileName": file_name,
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            })

            try:
                plog.info(None, phase="compile", event="chart.inline.expanded",
                          message="inline chart op → docx.insert",
                          data={"template": template, "idx": idx}, **(log_ctx or {}))
            except Exception:
                pass

        except Exception as e:
            rest.append(o)  # не теряем контент
            try:
                plog.error(None, phase="compile", event="chart.inline.fail",
                           message=str(e), data={"idx": idx, "op": o}, **(log_ctx or {}))
            except Exception:
                pass

    return docx_inserts, rest

def compile_docops_to_addin_job(docops: dict, anchor: dict | None = None, meta: dict | None = None) -> dict:
    if not isinstance(docops, dict) or docops.get("type") != "DocOps" or docops.get("version") != "v1":
        raise ValueError("invalid DocOps")

    trace_id = _trace_from_meta(meta)
    email    = _email_from_meta(meta)
    log_ctx  = _log_ctx_from_meta(meta)

    ops_in = list(docops.get("ops") or [])
    try:
        plog.debug(
            None, phase="compile", event="start",
            message="compile_docops_to_addin_job",
            trace_id=trace_id, email=email,
            data={
                "ops_in": len(ops_in),
                "first_ops": [(o.get("op"), (o.get("text") or "")[:80]) for o in ops_in[:6]],
            },
        )
    except Exception:
        pass

    # Фильтруем допустимые опы
    filtered_ops: list[dict] = [o for o in ops_in if isinstance(o, dict) and o.get("op") in ALLOWED]
    if not filtered_ops:
        raise ValueError("DocOps has no supported ops")

    try:
        plog.debug(
            None, phase="compile", event="ops.filtered",
            message=f"ops_in={len(ops_in)} → ops_kept={len(filtered_ops)}",
            trace_id=trace_id, email=email,
            data={"types": [op.get("op") for op in filtered_ops[:12]]},
        )
    except Exception:
        pass

    options = (docops.get("options") or {})
    use_docx_requested = _wants_docx(meta, docops)

    # Есть ли в принципе chart-ассеты в raw (независимо от успеха гидрации)?
    assets = options.get("assets") or []
    assets_present = any(
        isinstance(a, dict) and (a.get("kind") or "").lower().strip() == "chart-snippet"
        for a in (assets if isinstance(assets, list) else [])
    )

    # 1) Диаграммы из ассетов → docx.insert (в начало)
    chart_ops: list[dict] = []
    try:
        chart_ops = _expand_chart_assets_to_ops(options, log_ctx=log_ctx)
        try:
            plog.info(None, phase="compile", event="charts.front",
                      message="charts prepared",
                      trace_id=trace_id, email=email,
                      data={"requested_assets": int(assets_present), "chart_ops": len(chart_ops)})
        except Exception:
            pass
    except Exception as e:
        try:
            plog.warn(None, phase="compile", event="chart.assets.error",
                      message=str(e), trace_id=trace_id, email=email)
        except Exception:
            pass

    # 2) Контентные опы
    content_ops = list(filtered_ops)

    # 2а) Если есть диаграммы — подписи оставляем как caption.add и ставим их СРАЗУ ПОСЛЕ диаграмм
    if chart_ops:
        caption_ops: list[dict] = []
        rest_ops: list[dict] = []
        for op in content_ops:
            if isinstance(op, dict) and op.get("op") == "caption.add":
                caption_ops.append(op)
            else:
                rest_ops.append(op)
        # порядок: [диаграммы] + [подписи] + остальной контент
        content_ops = caption_ops + rest_ops
        try:
            plog.info(None, phase="compile", event="caption.inlined",
                      message="caption kept as caption.add after charts",
                      trace_id=trace_id, email=email,
                      data={"captions": len(caption_ops)})
        except Exception:
            pass

    # Итог без footnotes
    ops_out: list[dict] = list(chart_ops) + list(content_ops)

    # 3) Коллапс в один .docx допускаем ТОЛЬКО когда:
    #    • явно просили render=docx И
    #    • в ops_out ещё НЕТ docx.insert И
    #    • И НЕ было запрошено ни одного chart-ассета (assets_present == False)
    try:
        has_docx_insert = any(isinstance(o, dict) and o.get("op") == "docx.insert" for o in ops_out)
        plog.debug(None, phase="compile", event="docx.mode.check",
                   message="pre-collapse check",
                   trace_id=trace_id, email=email,
                   data={"use_docx_requested": bool(use_docx_requested),
                         "has_docx_insert": bool(has_docx_insert),
                         "assets_present": bool(assets_present),
                         "ops_out": len(ops_out)})
    except Exception:
        pass

    if use_docx_requested and (not has_docx_insert) and (not assets_present):
        try:
            from .docx_builder import build_docx_from_ops
            b64 = build_docx_from_ops(ops_out, log_ctx=log_ctx)

            try:
                import base64 as _b64
                raw = _b64.b64decode(b64.encode("ascii"))
                sig = raw[:2].hex()
                plog.info(None, phase="compile", event="docx.build.ok",
                          message="built .docx from ops (paragraphs/lists/tables/footnotes)",
                          trace_id=trace_id, email=email,
                          data={"ops_source": len(ops_out), "base64_len": len(b64), "zip_sig": sig})
            except Exception:
                pass

            file_name = f"docops-snippet-{(trace_id or uuid.uuid4())}.docx"
            ops_out = [{
                "op": "docx.insert",
                "base64": b64,
                "location": "after",
                "fileName": file_name,
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }]

            plog.info(None, phase="compile", event="docx.insert.enabled",
                      message="ops collapsed to single docx.insert",
                      trace_id=trace_id, email=email,
                      data={"ops_out": 1, "fileName": file_name})
        except Exception as e:
            plog.error(None, phase="compile", event="docx.build.error",
                       message=str(e), trace_id=trace_id, email=email,
                       data={"fallback": "raw_ops"})

    # 4) Применяем anchor к ПЕРВОМУ docx.insert (если он пришёл из контекста блока)
    def _apply_anchor_to_first_insert(ops_list: list[dict], anchor_dict: dict | None) -> None:
        if not isinstance(anchor_dict, dict):
            return
        a_text = str((anchor_dict.get("text") or "")).strip()
        if not a_text:
            return
        for i, o in enumerate(ops_list):
            if isinstance(o, dict) and o.get("op") == "docx.insert":
                o["location"] = f"anchor:{a_text}"
                plog.info(None, phase="compile", event="anchor.applied.to.insert",
                          trace_id=trace_id, email=email, data={"index": i, "text": a_text})
                break

    if anchor:
        _apply_anchor_to_first_insert(ops_out, anchor)

    # 5) После КАЖДОГО docx.insert → footnotes.apply-embedded (scope=last)
    marker = (options.get("footnotesMarker") or "&SRC&") if isinstance(options, dict) else "&SRC&"
    ops_out = _interleave_footnotes_apply_ops(
        ops_out, marker=marker, scope="last", trace_id=trace_id, email=email
    )

    job = {
        "kind": "addin.job",
        "version": "v1",
        "id": str(uuid.uuid4()),
        "ops": ops_out,
        "options": options,
    }
    if anchor:
        job["anchor"] = anchor
    if meta:
        job["meta"] = meta

    try:
        plog.debug(None, phase="compile", event="job.ready",
                   message="addin.job compiled",
                   trace_id=trace_id, email=email,
                   data={"ops_out": len(ops_out),
                         "has_anchor": bool(anchor),
                         "ops_types": {o.get('op'): 1 for o in ops_out if isinstance(o, dict)}})
    except Exception:
        pass

    return job