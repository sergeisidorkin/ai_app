from __future__ import annotations

import logging
import os
import re
from types import SimpleNamespace

from django.utils import timezone

from .docx_comments import DocxCommentError, extract_document_text, insert_comments
from .models import Performer, PerformerReportUpload, ProjectRegistrationProduct, ReportCheckRule, ReportMacro

log = logging.getLogger(__name__)

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
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
    product_ids = _registration_product_ids(upload)
    section_ids = _upload_section_ids(upload)
    return [
        rule
        for rule in rules
        if _rule_matches_upload(rule, upload, product_ids, section_ids)
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


def _rule_matches_upload(rule, upload, product_ids, section_ids) -> bool:
    if rule.product_id and rule.product_id not in product_ids:
        return False
    if rule.is_full_report:
        return bool(upload.is_full_report)
    if upload.is_full_report:
        return False
    if rule.section_id:
        return rule.section_id in section_ids
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

    try:
        text, _spans = extract_document_text(file_bytes)
    except DocxCommentError as exc:
        _store_status(upload, PerformerReportUpload.CheckStatus.ERROR, 0, str(exc))
        return file_bytes
    except Exception as exc:
        log.exception("Failed to read report docx for upload %s", upload.pk)
        _store_status(upload, PerformerReportUpload.CheckStatus.ERROR, 0, f"Не удалось прочитать docx: {exc}")
        return file_bytes

    findings: list[dict] = []
    errors: list[str] = []
    for macro in macros:
        try:
            for item in run_macro(macro, _build_ctx(upload, text, macro)):
                item["author"] = macro.name
                findings.append(item)
        except Exception as exc:
            log.exception("Report macro %s failed for upload %s", macro.pk, upload.pk)
            errors.append(f"{macro.name}: {exc}")

    result = file_bytes
    if findings:
        try:
            result = insert_comments(file_bytes, findings)
        except Exception as exc:
            log.exception("Failed to insert report comments for upload %s", upload.pk)
            errors.append(f"Комментарии: {exc}")
            result = file_bytes

    if errors and not findings:
        status = PerformerReportUpload.CheckStatus.ERROR
    else:
        status = PerformerReportUpload.CheckStatus.DONE
    _store_status(upload, status, len(findings), "\n".join(errors))
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
        try:
            start = int(item.get("start"))
            end = int(item.get("end"))
        except (TypeError, ValueError):
            continue
        message = str(item.get("message") or "").strip()
        if not message or start < 0 or end > text_len or start >= end:
            continue
        findings.append({"start": start, "end": end, "message": message})
    return findings


def _build_ctx(upload: PerformerReportUpload, text: str, macro: ReportMacro):
    registration = getattr(upload, "registration", None)
    performer = getattr(upload, "performer", None)
    section = getattr(performer, "typical_section", None) if performer else None
    product = getattr(registration, "type", None) if registration else None
    return SimpleNamespace(
        text=text or "",
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


def _store_status(upload: PerformerReportUpload, status: str, finding_count: int, error: str) -> None:
    upload.check_status = status
    upload.check_finding_count = finding_count
    upload.check_error = error or ""
    upload.checked_at = timezone.now()
    upload.save(update_fields=["check_status", "check_finding_count", "check_error", "checked_at"])
