from __future__ import annotations

import logging
import os
import re
from types import SimpleNamespace

from django.utils import timezone

from policy_app.models import TypicalSection

from .docx_comments import (
    DocxCommentError,
    count_comments,
    extract_char_runs,
    extract_document_text,
    extract_notes,
    extract_paragraphs,
    extract_ref_fields,
    extract_sections,
    extract_tab_offsets,
    extract_table_cells,
    insert_comments,
    materialize_symbols,
    strip_comments,
    update_broken_ref_fields,
)
from .docx_layout import extract_line_end_spaces
from .models import Performer, PerformerReportUpload, ProjectRegistrationProduct, ReportCheckRule, ReportMacro

log = logging.getLogger(__name__)

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
        rules = list(ReportCheckRule.objects.order_by("position", "id"))
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
    if not matched:
        return 0
    macro_matched = [
        rule
        for rule in matched
        if getattr(rule, "check_type", "") == ReportCheckRule.CheckType.MACRO
    ]
    chosen = macro_matched or matched
    return min(int(getattr(rule, "finding_threshold", 0) or 0) for rule in chosen)


def list_macros_for_upload(upload: PerformerReportUpload) -> list[ReportMacro]:
    rules = (
        ReportCheckRule.objects
        .filter(check_type=ReportCheckRule.CheckType.MACRO)
        .prefetch_related("macros")
        .order_by("position", "id")
    )
    seen: set[int] = set()
    macros: list[ReportMacro] = []
    for rule in matching_check_rules(upload, rules):
        for macro in rule.macros.all().order_by("position", "id"):
            if macro.pk in seen:
                continue
            seen.add(macro.pk)
            macros.append(macro)
    return macros


def matching_macro_rules_clear_comments(upload: PerformerReportUpload) -> bool:
    rules = (
        ReportCheckRule.objects
        .filter(check_type=ReportCheckRule.CheckType.MACRO)
        .order_by("position", "id")
    )
    return any(rule.clear_comments for rule in matching_check_rules(upload, rules))


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


def apply_report_macro_checks(upload: PerformerReportUpload, file_bytes: bytes) -> bytes:
    macros = list_macros_for_upload(upload)
    if not macros:
        return file_bytes
    ext = os.path.splitext(upload.file_name or "")[1].lower()
    if ext != ".docx":
        return file_bytes

    upload.check_status = PerformerReportUpload.CheckStatus.RUNNING
    upload.check_error = ""
    upload.check_finding_count = 0
    upload.save(update_fields=["check_status", "check_error", "check_finding_count"])

    if matching_macro_rules_clear_comments(upload):
        try:
            file_bytes = strip_comments(file_bytes)
        except DocxCommentError as exc:
            store_report_check_status(upload, PerformerReportUpload.CheckStatus.ERROR, 0, str(exc))
            return file_bytes

    source_bytes = file_bytes
    try:
        file_bytes = materialize_symbols(file_bytes)
    except Exception:
        log.exception("Failed to materialize Word symbols for upload %s", upload.pk)
        file_bytes = source_bytes

    try:
        file_bytes = update_broken_ref_fields(file_bytes)
    except Exception:
        log.exception("Failed to update broken REF fields for upload %s", upload.pk)

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
        line_end_spaces = extract_line_end_spaces(file_bytes)
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
    for macro in macros:
        try:
            for item in run_macro(macro, _build_ctx(upload, text, macro, line_end_spaces, notes, paragraphs, table_cells, ref_fields, sections, tab_offsets, char_runs)):
                item["author"] = macro.name
                findings.append(item)
        except Exception as exc:
            log.exception("Report macro %s failed for upload %s", macro.pk, upload.pk)
            errors.append(f"{macro.name}: {exc}")

    result = source_bytes
    if findings:
        try:
            result = insert_comments(file_bytes, findings)
        except Exception as exc:
            log.exception("Failed to insert report comments for upload %s", upload.pk)
            errors.append(f"Комментарии: {exc}")
            result = source_bytes

    if errors and not findings:
        status = PerformerReportUpload.CheckStatus.ERROR
    else:
        status = PerformerReportUpload.CheckStatus.DONE
    finding_count = len(findings)
    if status == PerformerReportUpload.CheckStatus.DONE:
        try:
            finding_count = count_comments(result)
        except DocxCommentError as exc:
            errors.append(f"Не удалось посчитать комментарии: {exc}")
            status = PerformerReportUpload.CheckStatus.ERROR
    store_report_check_status(upload, status, finding_count, "\n".join(errors))
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


def store_report_check_status(
    upload: PerformerReportUpload,
    status: str,
    finding_count: int,
    error: str,
) -> None:
    upload.check_status = status
    upload.check_finding_count = finding_count
    upload.check_error = error or ""
    upload.checked_at = timezone.now()
    upload.save(update_fields=["check_status", "check_finding_count", "check_error", "checked_at"])
