from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from types import SimpleNamespace

from django.db import connection
from django.utils import timezone

from policy_app.models import TypicalSection

from .docx_comments import (
    DocxCommentError,
    count_comments,
    count_comments_by_author,
    extract_char_runs,
    extract_document_text,
    extract_notes,
    extract_paragraphs,
    extract_ref_fields,
    extract_sections,
    extract_tab_offsets,
    extract_table_cells,
    insert_comments,
    strip_comments,
)
from .docx_layout import extract_line_end_spaces
from .models import (
    Performer,
    PerformerReportUpload,
    ProjectRegistrationProduct,
    ReportCheckRule,
    ReportMacro,
    report_line_participates,
)

log = logging.getLogger(__name__)


class ReportCheckAborted(Exception):
    """This process no longer owns the check and must not write its file."""

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "chr": chr,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class MacroRunError(RuntimeError):
    """A single macro failed while checking a report."""


def matching_check_rules(upload, rules=None) -> list[ReportCheckRule]:
    if rules is None:
        rules = list(
            ReportCheckRule.objects.prefetch_related("lines__macro").order_by("position", "id")
        )
    else:
        rules = list(rules)
    product_ids = _registration_product_ids(upload)
    section_ids = _upload_section_ids(upload)
    section_expertise = _section_expertise_map(section_ids)
    if upload.is_full_report:
        return [
            rule
            for rule in rules
            if rule.is_full_report
            and (not rule.product_id or rule.product_id in product_ids)
        ]
    return [
        rule
        for rule in rules
        if _rule_matches_upload(rule, upload, product_ids, section_ids, section_expertise)
    ]


def report_acceptance_threshold(upload, rules=None) -> int:
    if not upload or not getattr(upload, "pk", None):
        return 0
    matched = matching_check_rules(upload, rules)
    sums = [
        rule
        for rule in matched
        if getattr(rule, "completion_mode", "") != ReportCheckRule.CompletionMode.PER_ITEM
    ]
    chosen = sums or matched
    if not chosen:
        return 0
    return min(int(getattr(rule, "finding_threshold", 0) or 0) for rule in chosen)


def _line_is_kind(line, kind: str) -> bool:
    return getattr(line, "check_type", "") == kind and getattr(line, "macro_id", None)


def list_macros_for_upload(upload: PerformerReportUpload) -> list[ReportMacro]:
    rules = (
        ReportCheckRule.objects
        .prefetch_related("lines__macro")
        .order_by("position", "id")
    )
    seen: set[int] = set()
    macros: list[ReportMacro] = []
    for rule in matching_check_rules(upload, rules):
        lines = sorted(rule.lines.all(), key=lambda item: (item.position, item.pk))
        for line in lines:
            if not report_line_participates(line):
                continue
            if not _line_is_kind(line, ReportCheckRule.CheckType.MACRO):
                continue
            macro = line.macro
            if macro.pk in seen:
                continue
            seen.add(macro.pk)
            macros.append(macro)
    return macros


def matching_macro_rules_clear_comments(upload: PerformerReportUpload) -> bool:
    rules = (
        ReportCheckRule.objects
        .prefetch_related("lines")
        .order_by("position", "id")
    )
    for rule in matching_check_rules(upload, rules):
        if not rule.clear_comments:
            continue
        if any(
            report_line_participates(line) and _line_is_kind(line, ReportCheckRule.CheckType.MACRO)
            for line in rule.lines.all()
        ):
            return True
    return False


def _rule_matches_upload(rule, upload, product_ids, section_ids, section_expertise) -> bool:
    if rule.product_id and rule.product_id not in product_ids:
        return False
    if rule.is_full_report:
        return bool(upload.is_full_report)
    if upload.is_full_report:
        return False
    if rule.section_id:
        if rule.section_id not in section_ids:
            return False
        if rule.expertise_dir_id and section_expertise.get(rule.section_id) != rule.expertise_dir_id:
            return False
        return True
    if rule.expertise_dir_id:
        return any(
            section_expertise.get(section_id) == rule.expertise_dir_id
            for section_id in section_ids
        )
    return True


def _claim_report_check_if_unbound(upload: PerformerReportUpload) -> None:
    """Own a synchronous check before it becomes visible as running.

    Recovery treats a running check with an empty heartbeat as abandoned and
    starts a second process. That process strips comments, then loses the race
    and used to overwrite the finished file with the stripped document.
    """
    token = getattr(_report_check_claim, "token", "") or ""
    upload_id = getattr(_report_check_claim, "upload_id", None)
    if token and upload_id == upload.pk:
        return
    token = uuid.uuid4().hex
    now = timezone.now()
    attempts = max(int(upload.check_attempts or 0), 1)
    updated = PerformerReportUpload.objects.filter(pk=upload.pk, check_claim="").update(
        check_claim=token,
        check_heartbeat_at=now,
        check_status=PerformerReportUpload.CheckStatus.RUNNING,
        check_error="",
        check_finding_count=0,
        check_attempts=attempts,
        check_macro_index=0,
        check_macro_total=0,
        check_macro_name="",
    )
    if not updated:
        raise ReportCheckAborted()
    bind_report_check_claim(upload.pk, token)
    upload.check_claim = token
    upload.check_heartbeat_at = now
    upload.check_attempts = attempts
    upload.check_status = PerformerReportUpload.CheckStatus.RUNNING
    upload.check_macro_index = 0
    upload.check_macro_total = 0
    upload.check_macro_name = ""


def _require_report_check_owner(upload: PerformerReportUpload) -> None:
    if not touch_report_check_heartbeat(upload):
        raise ReportCheckAborted()


def apply_report_macro_checks(upload: PerformerReportUpload, file_bytes: bytes) -> bytes:
    macros = list_macros_for_upload(upload)
    if not macros:
        return file_bytes
    ext = os.path.splitext(upload.file_name or "")[1].lower()
    if ext != ".docx":
        return file_bytes
    _claim_report_check_if_unbound(upload)
    _require_report_check_owner(upload)

    upload.check_status = PerformerReportUpload.CheckStatus.RUNNING
    upload.check_error = ""
    upload.check_finding_count = 0
    upload.save(update_fields=["check_status", "check_error", "check_finding_count"])
    total = len(macros)
    _publish_check_progress(upload, 0, total, "Подготовка документа")

    if matching_macro_rules_clear_comments(upload):
        try:
            file_bytes = strip_comments(file_bytes)
        except DocxCommentError as exc:
            store_report_check_status(upload, PerformerReportUpload.CheckStatus.ERROR, 0, str(exc))
            return file_bytes

    # Analysis and rendering must use the same immutable coordinate system.
    # Materialising w:sym or rewriting REF results in the output used to alter
    # report text; comment-only checks intentionally never do that.
    source_bytes = file_bytes

    try:
        text, _spans = extract_document_text(file_bytes)
    except DocxCommentError as exc:
        store_report_check_status(upload, PerformerReportUpload.CheckStatus.ERROR, 0, str(exc))
        return file_bytes
    except Exception as exc:
        log.exception("Failed to read report docx for upload %s", upload.pk)
        store_report_check_status(
            upload,
            PerformerReportUpload.CheckStatus.ERROR,
            0,
            f"Не удалось прочитать docx: {exc}",
        )
        return file_bytes

    try:
        line_end_spaces = extract_line_end_spaces(
            file_bytes,
            progress=_layout_progress(upload, total),
        )
    except ReportCheckAborted:
        raise
    except Exception:
        log.exception("Failed to estimate visual line wraps for upload %s", upload.pk)
        line_end_spaces = frozenset()

    try:
        tab_offsets = extract_tab_offsets(file_bytes)
    except Exception:
        log.exception("Failed to read tab positions for upload %s", upload.pk)
        tab_offsets = frozenset()

    try:
        notes = extract_notes(file_bytes)
    except Exception:
        log.exception("Failed to read footnotes for upload %s", upload.pk)
        notes = []

    try:
        paragraphs = extract_paragraphs(file_bytes)
    except Exception:
        log.exception("Failed to read paragraphs for upload %s", upload.pk)
        paragraphs = []

    try:
        char_runs = extract_char_runs(file_bytes)
    except Exception:
        log.exception("Failed to read character styles for upload %s", upload.pk)
        char_runs = []

    try:
        table_cells = extract_table_cells(file_bytes)
    except Exception:
        log.exception("Failed to read table cells for upload %s", upload.pk)
        table_cells = []

    try:
        ref_fields = extract_ref_fields(file_bytes)
    except Exception:
        log.exception("Failed to read REF fields for upload %s", upload.pk)
        ref_fields = []

    try:
        sections = extract_sections(file_bytes)
    except Exception:
        log.exception("Failed to read sections for upload %s", upload.pk)
        sections = []

    findings: list[dict] = []
    errors: list[str] = []
    for index, macro in enumerate(macros, start=1):
        label = macro.display_label
        if not store_report_macro_progress(upload, index, total, label):
            raise ReportCheckAborted()
        try:
            for item in run_macro(macro, _build_ctx(upload, text, macro, line_end_spaces, notes, paragraphs, table_cells, ref_fields, sections, tab_offsets, char_runs)):
                item["author"] = label
                findings.append(item)
        except Exception as exc:
            log.exception("Report macro %s failed for upload %s", macro.pk, upload.pk)
            errors.append(f"{macro.name}: {exc}")

    result = source_bytes
    unplaced: list[str] = []
    if findings:
        _publish_check_progress(upload, total, total, "Примечания")
        try:
            result = insert_comments(
                source_bytes,
                findings,
                unplaced=unplaced,
                progress=lambda: touch_report_check_heartbeat(upload),
            )
        except Exception as exc:
            log.exception("Failed to insert report comments for upload %s", upload.pk)
            errors.append(f"Комментарии: {exc}")
            result = source_bytes
        else:
            errors.extend(unplaced)
    _require_report_check_owner(upload)

    if errors and not findings:
        status = PerformerReportUpload.CheckStatus.ERROR
    else:
        status = PerformerReportUpload.CheckStatus.DONE
    finding_count = len(findings)
    by_author: dict[str, int] = {}
    if status == PerformerReportUpload.CheckStatus.DONE:
        try:
            finding_count, by_author = recount_report_findings(result)
        except DocxCommentError as exc:
            errors.append(f"Не удалось посчитать комментарии: {exc}")
            status = PerformerReportUpload.CheckStatus.ERROR
            finding_count = 0
            by_author = {}
    store_report_check_status(upload, status, finding_count, "\n".join(errors), by_author)
    return result


def run_macro(macro: ReportMacro, ctx) -> list[dict]:
    namespace = {"__builtins__": SAFE_BUILTINS, "re": re}
    try:
        exec(macro.code or "", namespace, namespace)
    except Exception as exc:
        raise MacroRunError(f"Ошибка компиляции макроса «{macro.name}»: {exc}") from exc
    check = namespace.get("check")
    if not callable(check):
        raise MacroRunError(f"Макрос «{macro.name}» должен определять функцию check(ctx).")
    try:
        raw = check(ctx)
    except Exception as exc:
        raise MacroRunError(f"Ошибка выполнения макроса «{macro.name}»: {exc}") from exc
    return _normalize_findings(raw, len(getattr(ctx, "text", "") or ""))


def _normalize_findings(raw, text_len: int) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise MacroRunError("check() должен вернуть список находок.")
    findings = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        note_id = str(item.get("note_id") or "").strip()
        if not message:
            continue
        if note_id:
            finding = {"start": 0, "end": 1, "message": message, "note_id": note_id}
            note_kind = str(item.get("note_kind") or "").strip()
            if note_kind:
                finding["note_kind"] = note_kind
            links = _normalize_links(item)
            if links:
                finding["links"] = links
            findings.append(finding)
            continue
        try:
            start = int(item.get("start"))
            end = int(item.get("end"))
        except (TypeError, ValueError):
            continue
        if start < 0 or end > text_len or start >= end:
            continue
        finding = {"start": start, "end": end, "message": message}
        links = _normalize_links(item)
        if links:
            finding["links"] = links
        findings.append(finding)
    return findings


def _normalize_links(item: dict) -> list[dict]:
    links = []
    raw = item.get("links")
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            url = str(entry.get("url") or "").strip()
            if text and url:
                links.append({"text": text, "url": url})
    text = str(item.get("link_text") or "").strip()
    url = str(item.get("link_url") or "").strip()
    if text and url:
        links.append({"text": text, "url": url})
    return links


def _build_ctx(upload: PerformerReportUpload, text: str, macro: ReportMacro, line_end_spaces=(), notes=None, paragraphs=None, table_cells=None, ref_fields=None, sections=None, tab_offsets=None, char_runs=None):
    from django.conf import settings

    registration = getattr(upload, "registration", None)
    performer = getattr(upload, "performer", None)
    section = getattr(performer, "typical_section", None) if performer else None
    product = getattr(registration, "type", None) if registration else None
    return SimpleNamespace(
        text=text or "",
        line_end_spaces=frozenset(line_end_spaces or ()),
        notes=list(notes or ()),
        paragraphs=list(paragraphs or ()),
        char_runs=list(char_runs or ()),
        table_cells=list(table_cells or ()),
        ref_fields=list(ref_fields or ()),
        sections=list(sections or ()),
        tab_offsets=frozenset(tab_offsets or ()),
        nextcloud_base_url=(getattr(settings, "NEXTCLOUD_BASE_URL", "") or "").strip(),
        file_name=upload.file_name or "",
        product_name=getattr(product, "short_name", "") or "",
        section_code=getattr(section, "code", "") or "",
        executor=upload.executor or "",
        asset_name=upload.asset_name or "",
        macro_name=macro.name,
    )


def _registration_product_ids(upload: PerformerReportUpload) -> set[int]:
    registration = getattr(upload, "registration", None)
    if registration is None:
        return set()
    ids = set()
    if getattr(registration, "type_id", None):
        ids.add(registration.type_id)
    ids.update(
        ProjectRegistrationProduct.objects
        .filter(registration_id=registration.pk)
        .values_list("product_id", flat=True)
    )
    return {item for item in ids if item}


def _upload_section_ids(upload: PerformerReportUpload) -> set[int]:
    if upload.performer_id and not upload.is_all_sections and not upload.is_full_report:
        section_id = getattr(getattr(upload, "performer", None), "typical_section_id", None)
        return {section_id} if section_id else set()
    qs = Performer.objects.filter(registration_id=upload.registration_id)
    if upload.asset_name:
        qs = qs.filter(asset_name=upload.asset_name)
    if upload.is_all_sections and not upload.is_full_report:
        qs = qs.filter(executor=upload.executor or "")
    return set(
        qs.exclude(typical_section_id=None).values_list("typical_section_id", flat=True)
    )


def _section_expertise_map(section_ids) -> dict[int, int | None]:
    if not section_ids:
        return {}
    return dict(
        TypicalSection.objects.filter(pk__in=section_ids).values_list("id", "expertise_dir_id")
    )


_report_check_claim = threading.local()


def bind_report_check_claim(upload_id, token: str) -> None:
    _report_check_claim.upload_id = upload_id
    _report_check_claim.token = token or ""


def clear_report_check_claim() -> None:
    _report_check_claim.upload_id = None
    _report_check_claim.token = ""


def touch_report_check_heartbeat(upload) -> bool:
    """Refresh the lease. False when this thread no longer owns the check."""
    token = getattr(_report_check_claim, "token", "") or ""
    upload_id = getattr(_report_check_claim, "upload_id", None)
    if not token or upload_id != getattr(upload, "pk", None):
        return True
    if connection.connection is not None and not connection.is_usable():
        connection.close()
    updated = PerformerReportUpload.objects.filter(
        pk=upload.pk,
        check_claim=token,
        check_status=PerformerReportUpload.CheckStatus.RUNNING,
    ).update(check_heartbeat_at=timezone.now())
    return bool(updated)


def report_check_claim_lost(upload) -> bool:
    """True when this thread no longer owns the background report check."""
    token = getattr(_report_check_claim, "token", "") or ""
    upload_id = getattr(_report_check_claim, "upload_id", None)
    if not token or upload_id != getattr(upload, "pk", None):
        return False
    return not PerformerReportUpload.objects.filter(pk=upload.pk, check_claim=token).exists()


def recount_report_findings(file_bytes: bytes) -> tuple[int, dict[str, int]]:
    """Count comments in the finished docx, including a breakdown by author."""
    if not file_bytes:
        return 0, {}
    total = count_comments(file_bytes)
    return total, count_comments_by_author(file_bytes)


def store_report_check_status(
    upload: PerformerReportUpload,
    status: str,
    finding_count: int,
    error: str,
    by_author: dict | None = None,
) -> bool:
    if report_check_claim_lost(upload):
        return False
    upload.check_status = status
    upload.check_finding_count = finding_count
    upload.check_error = error or ""
    upload.checked_at = timezone.now()
    upload.check_macro_index = 0
    upload.check_macro_total = 0
    upload.check_macro_name = ""
    upload.check_finding_by_author = by_author or {}
    upload.check_finding_correction = None
    upload.status_changed_at = upload.checked_at
    upload.save(update_fields=[
        "check_status",
        "check_finding_count",
        "check_error",
        "checked_at",
        "check_macro_index",
        "check_macro_total",
        "check_macro_name",
        "check_finding_by_author",
        "check_finding_correction",
        "status_changed_at",
    ])
    if status == PerformerReportUpload.CheckStatus.DONE:
        from .report_review import sync_review_after_check

        sync_review_after_check(upload)
    return True


def _publish_check_progress(upload, index: int, total: int, name: str) -> None:
    if not store_report_macro_progress(upload, index, total, name):
        raise ReportCheckAborted()


def _layout_progress(upload, total: int):
    """Доля разобранных абзацев. Запись в базу не чаще нескольких раз в секунду."""
    state = {"mark": 0.0, "label": ""}

    def report(done: int, count: int) -> None:
        percent = 0 if not count else (int(done) * 100) // int(count)
        label = f"Подготовка документа {percent}%"
        now = time.monotonic()
        finished = count and int(done) >= int(count)
        if label == state["label"]:
            return
        if not finished and state["mark"] and now - state["mark"] < 0.4:
            return
        state["mark"] = now
        state["label"] = label
        _publish_check_progress(upload, 0, total, label)

    return report


def store_report_macro_progress(upload, index: int, total: int, name: str) -> bool:
    """Записать текущий макрос. False, если эта проверка уже не принадлежит потоку."""
    token = getattr(_report_check_claim, "token", "") or ""
    upload_id = getattr(_report_check_claim, "upload_id", None)
    if not token or upload_id != getattr(upload, "pk", None):
        return True
    if connection.connection is not None and not connection.is_usable():
        connection.close()
    label = (name or "")[:255]
    updated = PerformerReportUpload.objects.filter(
        pk=upload.pk,
        check_claim=token,
        check_status=PerformerReportUpload.CheckStatus.RUNNING,
    ).update(
        check_heartbeat_at=timezone.now(),
        check_macro_index=index,
        check_macro_total=total,
        check_macro_name=label,
    )
    if not updated:
        return False
    upload.check_macro_index = index
    upload.check_macro_total = total
    upload.check_macro_name = label
    return True
