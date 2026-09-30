from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import timedelta
from itertools import groupby
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import F, Q
from django.db.models.functions import Trim
from django.utils import timezone

from checklists_app.models import ProjectWorkspace
from core.cloud_paths import join_cloud_path
from core.cloud_storage import (
    CloudStorageNotReadyError,
    create_folder as cloud_create_folder,
    delete_file as cloud_delete_file,
    download_file as cloud_download_file,
    get_any_connected_service_user,
    is_nextcloud_primary,
    publish_resource as cloud_publish_resource,
    upload_file as cloud_upload_file,
)
from yandexdisk_app.workspace import _resolve_workspace_folder_name, _sanitize

from .models import (
    Performer,
    PerformerReportUpload,
    RegistrationWorkspaceFolder,
    ReportCheckRule,
    ReportMacro,
    WorkVolume,
    report_line_participates,
)
from .report_macro_runner import matching_check_rules, report_acceptance_threshold

logger = logging.getLogger(__name__)


def _reconnect_after_storage_io():
    _close_background_db_connections()


def _close_background_db_connections():
    from django.db import connection

    if connection.in_atomic_block:
        return
    close_old_connections()


class ReportUploadError(Exception):
    """Controlled error shown to the user when a report cannot be uploaded."""


def _plural_count(n: int, one: str, few: str, many: str) -> str:
    mod10 = n % 10
    mod100 = n % 100
    if mod10 == 1 and mod100 != 11:
        word = one
    elif 2 <= mod10 <= 4 and (mod100 < 12 or mod100 > 14):
        word = few
    else:
        word = many
    return f"{n} {word}"


def plural_sections(n: int) -> str:
    return _plural_count(n, "раздел", "раздела", "разделов")


def plural_macros(n: int) -> str:
    return _plural_count(n, "макрос", "макроса", "макросов")


def plural_skills(n: int) -> str:
    return _plural_count(n, "навык", "навыка", "навыков")


def _course_count_label(items, plural) -> str:
    """«N слово XXXX, …»: группы по курсу в порядке первого появления."""
    ordered = sorted(
        items or [],
        key=lambda item: (int(getattr(item, "position", 0) or 0), int(getattr(item, "id", 0) or 0)),
    )
    counts = {}
    for item in ordered:
        course = str(getattr(item, "course", "") or "").strip()
        counts[course] = counts.get(course, 0) + 1
    parts = []
    for course, n in counts.items():
        label = plural(n)
        parts.append(f"{label} {course}" if course else label)
    return ", ".join(parts)


def format_macro_check_label(macros) -> str:
    """Сводка выбранных макросов: «N макрос** XXXX, …» по полю Курс."""
    return _course_count_label(macros, plural_macros)


def format_skill_check_label(skills) -> str:
    """Сводка выбранных навыков: «N навык** XXXX, …» по полю Курс."""
    return _course_count_label(skills, plural_skills)


def format_check_composition_label(lines) -> str:
    """Состав запуска: счётчики макросов и навыков по курсу."""
    macros = []
    skills = []
    for line in lines or []:
        if not report_line_participates(line):
            continue
        macro = getattr(line, "macro", None)
        if macro is None:
            continue
        kind = (getattr(line, "check_type", None) or getattr(macro, "check_kind", "") or "").strip()
        if kind == "skill":
            skills.append(macro)
        else:
            macros.append(macro)
    return ", ".join(
        part for part in (
            format_macro_check_label(macros),
            format_skill_check_label(skills),
        ) if part
    )


def typical_section_short(section) -> str:
    if not section:
        return ""
    code = getattr(section, "code", "") or ""
    short_name_ru = getattr(section, "short_name_ru", "") or ""
    return " ".join(part for part in (code, short_name_ru) if part).strip()


def short_fio(value: str) -> str:
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


def short_fio_no_dots(value: str) -> str:
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(part[0] for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


FULL_REPORT_LABEL = "Весь отчет"
LOCAL_REPORT_PATH_PREFIX = "local:"
REPORT_ASSET_FOLDER_NAME_MAX_LEN = 50
EMPTY_REPORT_ASSET_FOLDER_LABEL = "без_актива"
REPORT_SECTION_ACCOUNTING_TYPE = "Раздел"
_ASSET_FOLDER_IN_PATH_RE = re.compile(r"(?:^|/)A[1-9]\d* ")
_ASSET_CODE_IN_FILENAME_RE = re.compile(r"_A[1-9]\d*_")


def report_group_key(registration_id, executor, asset_name=None) -> str:
    return f"{registration_id}\x1f{executor or ''}\x1f{asset_name or ''}"


def full_report_group_key(registration_id, asset_name) -> str:
    return f"{registration_id}\x1f{asset_name or ''}"


def get_effective_workspace_folders(user):
    user_qs = RegistrationWorkspaceFolder.objects.filter(user=user).order_by("position")
    if user_qs.exists():
        return user_qs
    return RegistrationWorkspaceFolder.objects.filter(user__isnull=True).order_by("position")


def resolve_workspace_folder_relpath(rows, project, role: str) -> str:
    parent = {1: "", 2: "", 3: ""}
    target_role = (role or "").strip()
    if not target_role:
        return ""
    for item in rows:
        if isinstance(item, dict):
            level = int(item.get("level") or 1)
            name = item.get("name") or ""
            item_role = (item.get("role") or "").strip()
        else:
            level = int(item[0]) if len(item) > 0 else 1
            name = item[1] if len(item) > 1 else ""
            item_role = (item[2] if len(item) > 2 else "") or ""
            item_role = str(item_role).strip()
        sanitized = _resolve_workspace_folder_name(name, project)
        if level == 1:
            parent[1] = sanitized
            parent[2] = ""
            parent[3] = ""
            path = sanitized
        elif level == 2:
            parent[2] = sanitized
            parent[3] = ""
            path = f"{parent[1]}/{sanitized}" if parent[1] else sanitized
        else:
            base = f"{parent[1]}/{parent[2]}" if parent[1] and parent[2] else (parent[2] or parent[1])
            path = f"{base}/{sanitized}" if base else sanitized
        if item_role == target_role:
            return path
    return ""


def resolve_reports_folder_path(project, user) -> str:
    workspace = (
        ProjectWorkspace.objects.filter(project=project)
        .only("disk_path")
        .first()
    )
    if not workspace or not (workspace.disk_path or "").strip():
        raise ReportUploadError("Для проекта не создано рабочее пространство.")

    folders = get_effective_workspace_folders(user)
    rows = list(folders.values("level", "name", "role"))
    relpath = resolve_workspace_folder_relpath(
        rows,
        project,
        RegistrationWorkspaceFolder.ROLE_REPORTS,
    )
    if not relpath:
        raise ReportUploadError(
            "В шаблоне рабочего пространства не назначена папка с ролью «Отчеты»."
        )
    return join_cloud_path(workspace.disk_path, relpath)


def ordered_work_volume_asset_names(project) -> list[str]:
    return [
        (name or "")
        for name in (
            WorkVolume.objects.filter(project=project)
            .order_by("position", "id")
            .values_list("asset_name", flat=True)
        )
    ]


def ordered_report_asset_names(project) -> list[str]:
    work_names = ordered_work_volume_asset_names(project)
    if work_names:
        return work_names

    performers = list(
        Performer.objects.filter(registration=project)
        .order_by("position", "pk")
        .values("asset_name", "position", "pk")
    )
    first_seen = {}
    for row in performers:
        name = row["asset_name"] or ""
        if name in first_seen:
            continue
        first_seen[name] = (row["position"] or 0, row["pk"] or 0)
    return [name for name, _rank in sorted(first_seen.items(), key=lambda item: item[1])]


def report_asset_code(project, asset_name="") -> str:
    names = ordered_report_asset_names(project)
    value = asset_name or ""
    if value not in names:
        names = [*names, value]
    if len(names) <= 1:
        return ""
    return f"A{names.index(value) + 1}"


def _report_asset_display_name(asset_name: str) -> str:
    text = _sanitize(asset_name or "") or EMPTY_REPORT_ASSET_FOLDER_LABEL
    if len(text) <= REPORT_ASSET_FOLDER_NAME_MAX_LEN:
        return text
    return text[:REPORT_ASSET_FOLDER_NAME_MAX_LEN].rstrip(" .") or EMPTY_REPORT_ASSET_FOLDER_LABEL


def build_report_asset_folder_name(asset_code: str, asset_name="") -> str:
    code = (asset_code or "").strip()
    if not code:
        return ""
    return f"{code} {_report_asset_display_name(asset_name)}"


def work_volume_asset_code(work_item) -> str:
    if work_item is None or not getattr(work_item, "project_id", None):
        return ""
    items = list(
        WorkVolume.objects.filter(project_id=work_item.project_id).order_by("position", "id")
    )
    if len(items) <= 1:
        return "A0"
    for index, item in enumerate(items, start=1):
        if item.pk == work_item.pk:
            return f"A{index}"
    return "A0"


def next_work_volume_asset_code(project) -> str:
    if project is None:
        return ""
    count = WorkVolume.objects.filter(project=project).count()
    if count == 0:
        return "A0"
    return f"A{count + 1}"


def stored_report_has_asset_folder(cloud_path="", file_name="") -> bool:
    if _ASSET_CODE_IN_FILENAME_RE.search(file_name or ""):
        return True
    normalized = str(cloud_path or "").replace("\\", "/")
    return bool(_ASSET_FOLDER_IN_PATH_RE.search(normalized))


def report_folder_locked_asset_keys(project_ids) -> set[tuple[int, str]]:
    ids = [project_id for project_id in project_ids if project_id]
    if not ids:
        return set()
    locked = set()
    for registration_id, asset_name, cloud_path, file_name in (
        PerformerReportUpload.objects.filter(registration_id__in=ids)
        .values_list("registration_id", "asset_name", "cloud_path", "file_name")
    ):
        if stored_report_has_asset_folder(cloud_path, file_name):
            locked.add((registration_id, asset_name or ""))
    return locked


def work_item_report_folder_locked(work_item) -> bool:
    if work_item is None or not getattr(work_item, "project_id", None):
        return False
    asset = (work_item.asset_name or "").strip()
    return (work_item.project_id, asset) in report_folder_locked_asset_keys([work_item.project_id])


def report_upload_locked_asset_keys(project_ids) -> set[tuple[int, str]]:
    ids = [project_id for project_id in project_ids if project_id]
    if not ids:
        return set()
    locked = set()
    for registration_id, asset_name in (
        PerformerReportUpload.objects.filter(registration_id__in=ids)
        .values_list("registration_id", "asset_name")
    ):
        locked.add((registration_id, (asset_name or "").strip()))
    return locked


def work_items_with_report_uploads(work_items) -> set[int]:
    """Work items whose project asset, or a performer deletion would remove, has an upload."""
    items = [item for item in work_items if getattr(item, "project_id", None) and getattr(item, "pk", None)]
    if not items:
        return set()
    project_ids = {item.project_id for item in items}
    upload_keys = report_upload_locked_asset_keys(project_ids)
    work_ids = [item.pk for item in items]
    linked_ids = set(
        PerformerReportUpload.objects.filter(performer__work_item_id__in=work_ids)
        .values_list("performer__work_item_id", flat=True)
    )
    legacy_keys = set()
    for registration_id, asset_name in (
        PerformerReportUpload.objects.filter(
            registration_id__in=project_ids,
            performer__isnull=False,
            performer__work_item__isnull=True,
        ).values_list("registration_id", "performer__asset_name")
    ):
        legacy_keys.add((registration_id, (asset_name or "").strip()))
    locked = set()
    for item in items:
        asset = (item.asset_name or "").strip()
        if (
            (item.project_id, asset) in upload_keys
            or item.pk in linked_ids
            or (item.project_id, asset) in legacy_keys
        ):
            locked.add(item.pk)
    return locked


def work_item_has_report_uploads(work_item) -> bool:
    if work_item is None or not getattr(work_item, "pk", None):
        return False
    return work_item.pk in work_items_with_report_uploads([work_item])


def report_section_locked_asset_keys(project_ids) -> set[tuple[int, str]]:
    ids = [project_id for project_id in project_ids if project_id]
    if not ids:
        return set()
    locked = set()
    for registration_id, asset_name, file_name, cloud_path in (
        PerformerReportUpload.objects.filter(registration_id__in=ids)
        .values_list("registration_id", "asset_name", "file_name", "cloud_path")
    ):
        if file_name or cloud_path:
            locked.add((registration_id, asset_name or ""))
    return locked


def performer_report_section_locked(performer) -> bool:
    if performer is None or not getattr(performer, "registration_id", None):
        return False
    if not is_report_section_accounting(getattr(performer, "typical_section", None)):
        return False
    key = (performer.registration_id, getattr(performer, "asset_name", "") or "")
    return key in report_section_locked_asset_keys([performer.registration_id])


def performer_has_report_uploads(performer) -> bool:
    performer_id = getattr(performer, "pk", None)
    if not performer_id:
        return False
    return PerformerReportUpload.objects.filter(performer_id=performer_id).exists()


def annotate_performers_report_section_lock(performers):
    items = list(performers)
    locked = report_section_locked_asset_keys(
        {getattr(item, "registration_id", None) for item in items}
    )
    performer_ids = [item.pk for item in items if getattr(item, "pk", None)]
    uploads = set()
    if performer_ids:
        uploads = set(
            PerformerReportUpload.objects.filter(performer_id__in=performer_ids)
            .values_list("performer_id", flat=True)
        )
    for item in items:
        item.report_section_locked = (
            is_report_section_accounting(getattr(item, "typical_section", None))
            and (item.registration_id, item.asset_name or "") in locked
        )
        item.report_upload_locked = item.pk in uploads
    return items


def annotate_performers_section_codes(performers):
    items = list(performers)
    grouped = {}
    for item in items:
        grouped.setdefault((item.registration_id, item.asset_name or ""), []).append(item)
    for group in grouped.values():
        ordered = sorted(group, key=lambda performer: (performer.position or 0, performer.pk or 0))
        index = 0
        for item in ordered:
            if is_report_section_accounting(getattr(item, "typical_section", None)):
                index += 1
                item.section_code = format_report_version(index)
            else:
                item.section_code = ""
    return items


def performer_section_code_ids_by_asset(performers=None) -> dict:
    items = list(
        performers
        if performers is not None
        else (
            Performer.objects
            .select_related("typical_section")
            .order_by("registration_id", "position", "id")
        )
    )
    grouped = {}
    for item in items:
        if not is_report_section_accounting(getattr(item, "typical_section", None)):
            continue
        grouped.setdefault(str(item.registration_id), {}).setdefault(item.asset_name or "", []).append(item.pk)
    return grouped


def locked_report_section_sequences(items) -> dict[tuple[int, str], list[int]]:
    locked = report_section_locked_asset_keys(
        {item.get("registration_id") for item in items}
    )
    sequences = {}
    for item in items:
        accounting = str(item.get("accounting_type") or "").strip()
        if accounting != REPORT_SECTION_ACCOUNTING_TYPE:
            continue
        key = (item.get("registration_id"), item.get("asset_name") or "")
        if key not in locked:
            continue
        sequences.setdefault(key, []).append(item["id"])
    return sequences


def annotate_work_volumes_for_projects_table(work_items):
    items = list(work_items)
    grouped = {}
    for item in items:
        grouped.setdefault(item.project_id, []).append(item)
    locked_keys = report_folder_locked_asset_keys(grouped.keys())
    upload_locked_ids = work_items_with_report_uploads(items)
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: (item.position or 0, item.pk or 0))
        if len(ordered) <= 1:
            for item in ordered:
                item.asset_code = "A0"
        else:
            for index, item in enumerate(ordered, start=1):
                item.asset_code = f"A{index}"
        for item in ordered:
            asset = (item.asset_name or "").strip()
            item.report_folder_locked = (item.project_id, asset) in locked_keys
            item.report_upload_locked = item.pk in upload_locked_ids
    return items


def format_report_version(version) -> str:
    return f"{int(version or 0):02d}"


def format_report_datetime(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")


REPORT_STATUS_IN_PROGRESS = "В работе"
REPORT_STATUS_UPLOADED = "Загружен"
REPORT_STATUS_SENT = "На проверке ИИ"
REPORT_STATUS_CHECKED = "Проверен ИИ"
REPORT_STATUS_ACCEPTED = "Сдан"
REPORT_STATUS_AGREED = "Согласован"


def report_findings_meet_threshold(finding_count, threshold) -> bool:
    findings = int(finding_count or 0)
    limit = int(threshold or 0)
    if findings < 0:
        findings = 0
    if limit < 0:
        limit = 0
    return findings < limit or (limit == 0 and findings == 0)


def _author_finding_count(upload, label: str, finding_counts=None) -> int:
    if finding_counts is not None:
        try:
            return int(finding_counts.get(label) or 0)
        except (TypeError, ValueError):
            return 0
    raw = getattr(upload, "check_finding_by_author", None) or {}
    if not isinstance(raw, dict):
        return 0
    try:
        return int(raw.get(label) or 0)
    except (TypeError, ValueError):
        return 0


def _lines_meet_thresholds(rule, upload, finding_counts=None) -> bool:
    lines = list(rule.lines.all()) if hasattr(rule, "lines") else []
    lines = [line for line in lines if report_line_participates(line)]
    if not lines:
        return False
    for line in lines:
        macro = getattr(line, "macro", None)
        label = macro.display_label if macro is not None else ""
        count = _author_finding_count(upload, label, finding_counts)
        if not report_findings_meet_threshold(count, getattr(line, "finding_threshold", 0)):
            return False
    return True


def report_launches_accepted(upload, check_rules=None, *, finding_counts=None, finding_total=None) -> bool:
    """«Сдан», только если каждый подошедший запуск проходит своё условие."""
    if finding_total is None:
        total = int(getattr(upload, "check_finding_count", 0) or 0)
    else:
        total = int(finding_total or 0)
    if not getattr(upload, "pk", None):
        return report_findings_meet_threshold(total, 0)
    matched = matching_check_rules(upload, check_rules)
    if not matched:
        return report_findings_meet_threshold(total, 0)
    for rule in matched:
        mode = getattr(rule, "completion_mode", "") or ReportCheckRule.CompletionMode.SUM
        sum_ok = report_findings_meet_threshold(total, getattr(rule, "finding_threshold", 0))
        if mode == ReportCheckRule.CompletionMode.PER_ITEM:
            if not _lines_meet_thresholds(rule, upload, finding_counts):
                return False
        elif mode == ReportCheckRule.CompletionMode.SUM_AND_PER_ITEM:
            if not (sum_ok and _lines_meet_thresholds(rule, upload, finding_counts)):
                return False
        elif not sum_ok:
            return False
    return True


def report_workflow_status(upload, threshold=None, check_rules=None) -> str:
    if not upload:
        return REPORT_STATUS_IN_PROGRESS
    has_file = bool(getattr(upload, "file_name", "") or getattr(upload, "cloud_path", ""))
    if not has_file:
        return REPORT_STATUS_IN_PROGRESS
    from .report_review import REVIEW_DONE, manual_status_label

    review_step = getattr(upload, "review_step", "") or ""
    if review_step == REVIEW_DONE:
        return REPORT_STATUS_AGREED
    manual_label = manual_status_label(review_step, getattr(upload, "review_phase", "") or "")
    if manual_label:
        return manual_label
    check_status = getattr(upload, "check_status", "") or ""
    if check_status == PerformerReportUpload.CheckStatus.DONE:
        findings = getattr(upload, "check_finding_count", 0)
        if getattr(upload, "pk", None):
            accepted = report_acceptance_for_status(upload, check_rules)
        else:
            if threshold is None:
                threshold = 0
            accepted = report_findings_meet_threshold(findings, threshold)
        if accepted:
            from .report_review import REVIEW_AI, passed_step_status, review_chain_for_upload

            chain = review_chain_for_upload(upload) if getattr(upload, "pk", None) else [REVIEW_AI]
            return passed_step_status(REVIEW_AI, chain)
        return REPORT_STATUS_CHECKED
    if getattr(upload, "sent_at", None):
        return REPORT_STATUS_SENT
    return REPORT_STATUS_UPLOADED


def format_grouped_count(value) -> str:
    """Группы разрядов через неразрывный пробел, начиная с четырёхзначных чисел."""
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount < 0:
        amount = 0
    return f"{amount:,}".replace(",", "\u00a0")


def report_finding_count_value(upload):
    if not upload or (getattr(upload, "check_status", "") or "") != PerformerReportUpload.CheckStatus.DONE:
        return None
    try:
        amount = int(getattr(upload, "check_finding_count", 0) or 0)
    except (TypeError, ValueError):
        amount = 0
    return amount if amount > 0 else 0


def format_report_finding_count(upload) -> str:
    amount = report_finding_count_value(upload)
    if amount is None:
        return "—"
    return format_grouped_count(amount)


class FindingCorrectionError(Exception):
    """Сохранение корректировки отклонено: числа нельзя увеличить выше расчёта."""

    def __init__(self, message, labels=None):
        super().__init__(message)
        self.labels = list(labels or [])


def calculated_finding_map(upload) -> dict[str, int]:
    """Ненулевые замечания автопроверки по подписи макроса или навыка."""
    raw = getattr(upload, "check_finding_by_author", None) or {} if upload else {}
    if not isinstance(raw, dict):
        return {}
    result = {}
    for author, count in raw.items():
        label = str(author or "").strip() or "Проверка"
        value = _finding_author_count(count)
        if value:
            result[label] = value
    return result


def _stored_finding_correction(upload) -> dict | None:
    raw = getattr(upload, "check_finding_correction", None) if upload else None
    if not isinstance(raw, dict) or not raw:
        return None
    return raw


def finding_correction_active(upload) -> bool:
    """Сохранённые числа отличаются от расчёта."""
    correction = _stored_finding_correction(upload)
    if not correction or not upload:
        return False
    calculated = calculated_finding_map(upload)
    if not calculated:
        return False
    for label, original in calculated.items():
        if label not in correction:
            return True
        try:
            value = int(correction.get(label))
        except (TypeError, ValueError):
            return True
        if value != original:
            return True
    return False


def effective_finding_map(upload, *, use_correction: bool) -> dict[str, int]:
    calculated = calculated_finding_map(upload)
    if not use_correction:
        return dict(calculated)
    correction = _stored_finding_correction(upload)
    if not correction:
        return dict(calculated)
    result = {}
    for label, original in calculated.items():
        if label not in correction:
            result[label] = original
            continue
        try:
            value = int(correction.get(label))
        except (TypeError, ValueError):
            value = original
        if value < 0:
            value = 0
        if value > original:
            value = original
        result[label] = value
    return result


def report_public_finding_count_value(upload):
    """Число в «Число замеч.» и «Корр.»: расчёт, пока правки нет."""
    calculated = report_finding_count_value(upload)
    if calculated is None:
        return None
    if not finding_correction_active(upload):
        return calculated
    return sum(effective_finding_map(upload, use_correction=True).values())


def format_report_public_finding_count(upload) -> str:
    amount = report_public_finding_count_value(upload)
    if amount is None:
        return "—"
    return format_grouped_count(amount)


_CORRECTION_MARK_STATUSES = {"Проверен ИИ", "Сдан ИИ", "Согласован ИИ"}


def mark_corrected_workflow_status(upload, status: str) -> str:
    if status not in _CORRECTION_MARK_STATUSES or not finding_correction_active(upload):
        return status
    return f"{status}*"


def upload_is_latest_version(upload) -> bool:
    """Актуальная версия слота: максимальный номер, не файл шага проверки."""
    if not upload or not getattr(upload, "pk", None) or getattr(upload, "step_revision", False):
        return False
    cached = getattr(upload, "_report_is_latest_version", None)
    if cached is not None:
        return bool(cached)
    latest_pk = (
        report_upload_slot_qs(upload)
        .filter(step_revision=False)
        .order_by("-version", "-pk")
        .values_list("pk", flat=True)
        .first()
    )
    upload._report_is_latest_version = latest_pk == upload.pk
    return upload._report_is_latest_version


def _mark_slot_latest_versions(uploads) -> None:
    latest = None
    latest_rank = None
    for upload in uploads or []:
        if upload is None or getattr(upload, "step_revision", False):
            if upload is not None:
                upload._report_is_latest_version = False
            continue
        rank = (int(getattr(upload, "version", 0) or 0), int(getattr(upload, "pk", 0) or 0))
        if latest is None or rank > latest_rank:
            latest = upload
            latest_rank = rank
    for upload in uploads or []:
        if upload is None or getattr(upload, "step_revision", False):
            continue
        upload._report_is_latest_version = upload is latest


def review_chain_is_adjustable(upload) -> bool:
    """Цепочку можно сдвинуть, пока следующий шаг не получил файл и не ушёл дальше."""
    from .models import ReportReviewEntry
    from .report_review import (
        MANUAL_REVIEW_CODES,
        REVIEW_AI,
        REVIEW_PHASE_REVIEW,
        REVIEW_PHASE_REWORK,
        _slot_upload_ids,
    )

    if not upload or not getattr(upload, "pk", None):
        return False
    entries = ReportReviewEntry.objects.filter(upload_id__in=_slot_upload_ids(upload))
    manual_open = 0
    for entry in entries:
        if entry.step == REVIEW_AI and entry.phase == REVIEW_PHASE_REWORK and not entry.settled:
            continue
        empty_file = not (entry.review_file_name or entry.review_cloud_path)
        if (
            entry.phase == REVIEW_PHASE_REVIEW
            and entry.step in MANUAL_REVIEW_CODES
            and not entry.settled
            and empty_file
        ):
            manual_open += 1
            continue
        return False
    return manual_open <= 1


def report_status_uses_correction(upload) -> bool:
    if not finding_correction_active(upload):
        return False
    if not upload_is_latest_version(upload):
        return False
    return review_chain_is_adjustable(upload)


def report_acceptance_for_status(upload, check_rules=None) -> bool:
    """Порог для статуса. Закреплённая цепочка актуальной версии не откатывается числами."""
    if (
        finding_correction_active(upload)
        and upload_is_latest_version(upload)
        and not review_chain_is_adjustable(upload)
    ):
        return True
    if report_status_uses_correction(upload):
        counts = effective_finding_map(upload, use_correction=True)
        return report_launches_accepted(
            upload,
            check_rules,
            finding_counts=counts,
            finding_total=sum(counts.values()),
        )
    return report_launches_accepted(upload, check_rules)


def report_acceptance_rule_payload(upload, check_rules=None) -> list[dict]:
    """Правила порога для живой проверки в модалке правки."""
    if not upload or not getattr(upload, "pk", None):
        return [{"mode": ReportCheckRule.CompletionMode.SUM, "sum_threshold": 0, "items": {}}]
    matched = matching_check_rules(upload, check_rules)
    if not matched:
        return [{"mode": ReportCheckRule.CompletionMode.SUM, "sum_threshold": 0, "items": {}}]
    item_modes = {
        ReportCheckRule.CompletionMode.PER_ITEM,
        ReportCheckRule.CompletionMode.SUM_AND_PER_ITEM,
    }
    sum_modes = {
        ReportCheckRule.CompletionMode.SUM,
        ReportCheckRule.CompletionMode.SUM_AND_PER_ITEM,
    }
    payload = []
    for rule in matched:
        mode = getattr(rule, "completion_mode", "") or ReportCheckRule.CompletionMode.SUM
        items = {}
        if mode in item_modes:
            lines = list(rule.lines.all()) if hasattr(rule, "lines") else []
            for line in lines:
                if not report_line_participates(line):
                    continue
                macro = getattr(line, "macro", None)
                label = macro.display_label if macro is not None else ""
                if not label:
                    continue
                items[label] = int(getattr(line, "finding_threshold", 0) or 0)
        payload.append({
            "mode": mode,
            "sum_threshold": int(getattr(rule, "finding_threshold", 0) or 0) if mode in sum_modes else None,
            "items": items,
        })
    return payload


def _parse_correction_count(raw):
    if isinstance(raw, bool) or isinstance(raw, float):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw or "").strip()
    if not text.isdigit():
        return None
    return int(text)


def apply_finding_correction(upload, submitted) -> None:
    """Сохранить уменьшение замечаний. Выше расчёта записать нельзя."""
    calculated = calculated_finding_map(upload)
    if not calculated:
        raise FindingCorrectionError("Нет рассчитанных замечаний.", [])
    if not isinstance(submitted, dict):
        raise FindingCorrectionError("Некорректные данные.", [])
    increased = []
    invalid = []
    cleaned = {}
    for label, original in calculated.items():
        if label not in submitted:
            cleaned[label] = original
            continue
        value = _parse_correction_count(submitted.get(label))
        if value is None or value < 0:
            invalid.append(label)
            continue
        if value > original:
            increased.append(label)
            continue
        cleaned[label] = value
    for label in submitted:
        if label not in calculated:
            invalid.append(str(label))
    if increased:
        raise FindingCorrectionError(
            "Число замечаний нельзя увеличить выше расчётного.",
            increased,
        )
    if invalid:
        raise FindingCorrectionError(
            "Укажите целое число от 0 до расчётного.",
            invalid,
        )
    if all(cleaned[label] == calculated[label] for label in calculated):
        upload.check_finding_correction = None
    else:
        upload.check_finding_correction = cleaned
    upload.save(update_fields=["check_finding_correction"])
    reconcile_review_after_correction(upload)


def reconcile_review_after_correction(upload) -> None:
    """Для актуальной версии повторить переход автопроверки по скорректированным числам."""
    from .models import ReportReviewEntry
    from .report_review import (
        REVIEW_AI,
        REVIEW_PHASE_REVIEW,
        REVIEW_PHASE_REWORK,
        manual_steps,
        review_chain_for_upload,
        _slot_upload_ids,
    )

    if not upload or (getattr(upload, "check_status", "") or "") != PerformerReportUpload.CheckStatus.DONE:
        return
    if not upload_is_latest_version(upload) or not review_chain_is_adjustable(upload):
        return
    if finding_correction_active(upload):
        counts = effective_finding_map(upload, use_correction=True)
        accepted = report_launches_accepted(
            upload,
            finding_counts=counts,
            finding_total=sum(counts.values()),
        )
    else:
        accepted = report_launches_accepted(upload)
    slot_ids = _slot_upload_ids(upload)
    if accepted:
        ReportReviewEntry.objects.filter(
            upload_id__in=slot_ids,
            step=REVIEW_AI,
            phase=REVIEW_PHASE_REWORK,
            settled=False,
        ).delete()
        steps = manual_steps(review_chain_for_upload(upload))
        if not steps:
            return
        if ReportReviewEntry.objects.filter(
            upload_id__in=slot_ids,
            phase=REVIEW_PHASE_REVIEW,
            settled=False,
        ).exists():
            return
        ReportReviewEntry.objects.create(
            upload=upload,
            step=steps[0],
            phase=REVIEW_PHASE_REVIEW,
        )
        return
    ReportReviewEntry.objects.filter(
        upload_id__in=slot_ids,
        phase=REVIEW_PHASE_REVIEW,
        settled=False,
        review_file_name="",
        review_cloud_path="",
    ).delete()
    if not ReportReviewEntry.objects.filter(
        upload_id__in=slot_ids,
        step=REVIEW_AI,
        phase=REVIEW_PHASE_REWORK,
        settled=False,
    ).exists():
        ReportReviewEntry.objects.create(
            upload=upload,
            step=REVIEW_AI,
            phase=REVIEW_PHASE_REWORK,
        )


_FINDING_AUTHOR_COURSE_RE = re.compile(r"^([A-Z]{4})-")
_FRAGMENT_CODES_CACHE = "\x00fragment-category-codes"
_FINDING_KIND_LABELS = {
    ReportMacro.CheckKind.MACRO: ReportMacro.CheckKind.MACRO.label,
    ReportMacro.CheckKind.SKILL: ReportMacro.CheckKind.SKILL.label,
}
_FINDING_UNMATCHED_POSITION = 10**9


def report_macro_catalog_index(macros=None) -> dict:
    """Подпись макроса или навыка → курс, вид и позиция в каталоге."""
    if macros is None:
        macros = ReportMacro.objects.all().only(
            "id",
            "course",
            "section",
            "part",
            "number",
            "name",
            "check_kind",
            "position",
        )
    index = {}
    for macro in macros:
        label = (macro.display_label or "").strip()
        if not label or label in index:
            continue
        index[label] = {
            "course": (getattr(macro, "course", "") or "").strip(),
            "kind": (getattr(macro, "check_kind", "") or "").strip(),
            "name": (getattr(macro, "name", "") or "").strip(),
            "position": int(getattr(macro, "position", 0) or 0),
            "id": int(getattr(macro, "pk", None) or getattr(macro, "id", 0) or 0),
        }
    return index


def _author_category_code(label: str) -> str:
    from .report_macro_code import TITLE_RE

    match = TITLE_RE.fullmatch(str(label or "").strip())
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}.{match.group(4)}"


def _fragment_validation_category_codes(catalog: dict) -> set[str]:
    """Коды категорий навыков в режиме «Фрагменты». Их авторы в модалке — «Навык»."""
    cached = catalog.get(_FRAGMENT_CODES_CACHE)
    if isinstance(cached, set):
        return cached
    from .report_chunk_skill_runner import ChunkSkillError, load_skill_manifest

    codes: set[str] = set()
    names = (
        ReportMacro.objects.filter(
            check_kind=ReportMacro.CheckKind.SKILL,
            processing_mode=ReportMacro.ProcessingMode.CHUNKS,
        )
        .exclude(skill_name="")
        .values_list("skill_name", flat=True)
        .distinct()
    )
    for name in names:
        try:
            manifest = load_skill_manifest(name) or {}
        except ChunkSkillError:
            continue
        for category in manifest.get("categories") or []:
            code = str(category.get("code") or "").strip()
            if code:
                codes.add(code)
    catalog[_FRAGMENT_CODES_CACHE] = codes
    return codes


def _finding_author_count(count) -> int:
    try:
        value = int(count or 0)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def report_finding_context(registration, executor, asset_name, section_label, version="") -> dict:
    """Подписи строки отчёта для шапки окна замечаний."""
    stage = ""
    product = ""
    name = ""
    if registration is not None:
        stage = str(getattr(registration, "short_uid", "") or "").strip()
        product = str(getattr(registration, "type_short_display", "") or "").strip()
        name = str(getattr(registration, "name", "") or "").strip()
    return {
        "stage": stage,
        "product": product,
        "name": name,
        "executor": short_fio(executor),
        "section": str(section_label or "").strip(),
        "asset": str(asset_name or "").strip(),
        "version": str(version or "").strip(),
    }


def report_upload_section_label(upload) -> str:
    if not upload:
        return ""
    if getattr(upload, "is_full_report", False):
        return FULL_REPORT_LABEL
    if getattr(upload, "is_all_sections", False):
        count = Performer.objects.filter(
            registration_id=upload.registration_id,
            executor=upload.executor or "",
            asset_name=upload.asset_name or "",
        ).count()
        return plural_sections(count)
    performer = getattr(upload, "performer", None)
    return typical_section_short(getattr(performer, "typical_section", None)) or "—"


def report_finding_thresholds(upload, check_rules=None) -> tuple[int | None, dict[int, int]]:
    """Порог суммы и пороги макросов/навыков из подошедших запусков.

    Порог суммы есть у режимов «сумма» и «сумма с контролем».
    Порог строки есть у режимов с контролем порога макроса или навыка.
    Ноль — установленное значение. Если режим порог не задаёт, значение отсутствует.
    """
    if not upload or not getattr(upload, "pk", None):
        return None, {}

    sum_modes = {
        ReportCheckRule.CompletionMode.SUM,
        ReportCheckRule.CompletionMode.SUM_AND_PER_ITEM,
    }
    item_modes = {
        ReportCheckRule.CompletionMode.PER_ITEM,
        ReportCheckRule.CompletionMode.SUM_AND_PER_ITEM,
    }
    sum_threshold = None
    by_macro: dict[int, int] = {}
    for rule in matching_check_rules(upload, check_rules):
        mode = getattr(rule, "completion_mode", "") or ReportCheckRule.CompletionMode.SUM
        if mode in sum_modes:
            value = int(getattr(rule, "finding_threshold", 0) or 0)
            sum_threshold = value if sum_threshold is None else min(sum_threshold, value)
        if mode not in item_modes:
            continue
        lines = list(rule.lines.all()) if hasattr(rule, "lines") else []
        for line in lines:
            if not report_line_participates(line):
                continue
            macro_id = getattr(line, "macro_id", None)
            if not macro_id:
                continue
            value = int(getattr(line, "finding_threshold", 0) or 0)
            current = by_macro.get(macro_id)
            by_macro[macro_id] = value if current is None else min(current, value)
    return sum_threshold, by_macro


def report_finding_groups(upload, catalog=None, check_rules=None, *, source="calculated") -> dict:
    """Итог и замечания по курсам: внутри курса — макросы и навыки с ненулевым числом."""
    done = bool(upload) and (
        (getattr(upload, "check_status", "") or "") == PerformerReportUpload.CheckStatus.DONE
    )
    use_corrected = source == "corrected" and finding_correction_active(upload)
    if use_corrected:
        counts = effective_finding_map(upload, use_correction=True)
        total = sum(counts.values()) if done else 0
        raw = counts
    else:
        total = int(getattr(upload, "check_finding_count", 0) or 0) if done else 0
        raw = getattr(upload, "check_finding_by_author", None) or {} if upload else {}
    if not isinstance(raw, dict):
        raw = {}
    counted = [
        (str(author or "").strip() or "Проверка", _finding_author_count(count))
        for author, count in raw.items()
    ]
    counted = [(label, count) for label, count in counted if count]
    if catalog is None and counted:
        catalog = report_macro_catalog_index()
    catalog = catalog or {}
    total_threshold, thresholds_by_macro = (
        report_finding_thresholds(upload, check_rules) if done else (None, {})
    )

    buckets: dict[str, list] = {}
    for label, count in counted:
        meta = catalog.get(label)
        if meta:
            course = meta["course"]
            kind = meta["kind"]
            item_name = meta.get("name") or label
            position = meta["position"]
            item_id = meta["id"]
        else:
            match = _FINDING_AUTHOR_COURSE_RE.match(label)
            course = match.group(1) if match else ""
            code = _author_category_code(label)
            kind = (
                ReportMacro.CheckKind.SKILL
                if code and code in _fragment_validation_category_codes(catalog)
                else ""
            )
            item_name = label
            position = _FINDING_UNMATCHED_POSITION
            item_id = 0
        buckets.setdefault(course, []).append({
            "label": label,
            "name": item_name,
            "kind": kind,
            "kind_label": _FINDING_KIND_LABELS.get(kind, "—"),
            "count": count,
            "_position": position,
            "_id": item_id,
        })

    courses = []
    for course, items in buckets.items():
        items.sort(key=lambda item: (-item["count"], item["_position"], item["_id"], item["label"]))
        courses.append({
            "course": course or "—",
            "total": sum(item["count"] for item in items),
            "_position": items[0]["_position"],
            "_id": items[0]["_id"],
            "items": [
                {
                    **{key: value for key, value in item.items() if not key.startswith("_")},
                    "threshold": thresholds_by_macro.get(item["_id"]),
                }
                for item in items
            ],
        })
    courses.sort(key=lambda item: (-item["total"], item["_position"], item["_id"], item["course"]))
    for course in courses:
        course.pop("_position", None)
        course.pop("_id", None)
    return {"total": total, "total_threshold": total_threshold, "courses": courses}


def report_finding_edit_payload(upload, groups, check_rules=None) -> dict:
    """Разбивка для модалки правки: «Замеч.» — расчёт, «Корр.» — сохранённое или то же число."""
    corrected = (
        effective_finding_map(upload, use_correction=True)
        if finding_correction_active(upload)
        else None
    )
    courses = []
    for course in groups.get("courses") or []:
        items = []
        corrected_total = 0
        for item in course.get("items") or []:
            value = item["count"] if corrected is None else int(corrected.get(item["label"], item["count"]))
            corrected_total += value
            items.append({**item, "corrected": value})
        courses.append({
            **course,
            "items": items,
            "corrected_total": corrected_total,
        })
    return {
        "total": groups.get("total") or 0,
        "corrected_total": sum(course["corrected_total"] for course in courses),
        "total_threshold": groups.get("total_threshold"),
        "courses": courses,
        "context": groups.get("context") or {},
        "rules": report_acceptance_rule_payload(upload, check_rules),
        "upload_id": getattr(upload, "pk", None) or "",
    }


REPORT_STATUS_DOT_CLASS = {
    REPORT_STATUS_IN_PROGRESS: "report-status--idle",
    REPORT_STATUS_UPLOADED: "report-status--uploaded",
    REPORT_STATUS_SENT: "report-status--sent",
    REPORT_STATUS_CHECKED: "report-status--checked",
    REPORT_STATUS_ACCEPTED: "report-status--accepted",
    REPORT_STATUS_AGREED: "report-status--accepted",
}


def report_workflow_status_class(status: str) -> str:
    known = REPORT_STATUS_DOT_CLASS.get(status or "")
    if known:
        return known
    if (status or "").startswith("Проверен"):
        return "report-status--checked"
    if (status or "").startswith("Сдан") or (status or "").startswith("Согласован"):
        return "report-status--accepted"
    if (status or "").startswith("На проверке"):
        return "report-status--sent"
    if (status or "").startswith("В работе после"):
        return "report-status--checked"
    return "report-status--idle"


def report_workflow_status_date(upload, status=None):
    status = status or report_workflow_status(upload)
    if (status or "").endswith("*"):
        status = status[:-1]
    if not upload or status == REPORT_STATUS_IN_PROGRESS:
        return None
    changed_at = getattr(upload, "status_changed_at", None)
    if changed_at and status not in (REPORT_STATUS_UPLOADED,):
        return changed_at
    if status == REPORT_STATUS_UPLOADED:
        return getattr(upload, "uploaded_at", None)
    if status == REPORT_STATUS_SENT or (status or "").startswith("На проверке"):
        return getattr(upload, "status_changed_at", None) or getattr(upload, "sent_at", None)
    if status == REPORT_STATUS_CHECKED or (status or "").startswith("Сдан") or (status or "").startswith("Согласован"):
        return getattr(upload, "checked_at", None) or getattr(upload, "sent_at", None)
    return None


def format_report_status_date(upload, status=None) -> str:
    return format_report_datetime(report_workflow_status_date(upload, status)) or "—"


def format_report_file_date(value=None) -> str:
    when = value or timezone.now()
    if timezone.is_aware(when):
        when = timezone.localtime(when)
    return when.strftime("%Y %m %d")


def _section_accounting_type(section) -> str:
    return str(getattr(section, "accounting_type", "") or "").strip()


def is_report_section_accounting(section) -> bool:
    return _section_accounting_type(section) == REPORT_SECTION_ACCOUNTING_TYPE


def _performer_section_code(performer) -> str:
    section = getattr(performer, "typical_section", None)
    return _sanitize(getattr(section, "code", "") or typical_section_short(section) or "раздел")


def grouped_report_performers(project, executor, asset_name="") -> list:
    if project is None or not getattr(project, "pk", None):
        return []
    return list(
        Performer.objects.filter(
            registration=project,
            executor=executor or "",
            asset_name=asset_name or "",
        )
        .select_related("typical_section")
        .order_by("position", "id")
    )


def asset_report_section_performers(project, asset_name="") -> list:
    if project is None or not getattr(project, "pk", None):
        return []
    return list(
        Performer.objects.filter(
            registration=project,
            asset_name=asset_name or "",
            typical_section__accounting_type=REPORT_SECTION_ACCOUNTING_TYPE,
        )
        .select_related("typical_section")
        .order_by("position", "id")
    )


def _resolve_filename_performer(registration, executor, section, performer, asset_name):
    if performer is not None:
        return performer, asset_name or getattr(performer, "asset_name", "") or ""
    if registration is None or not getattr(registration, "pk", None) or section is None:
        return None, asset_name or ""
    match = (
        Performer.objects.filter(
            registration=registration,
            executor=executor or "",
            typical_section=section,
        )
        .order_by("position", "id")
        .first()
    )
    if match is None:
        return None, asset_name or ""
    return match, asset_name or match.asset_name or ""


def report_section_number(
    project,
    asset_name="",
    *,
    performer=None,
    is_full_report=False,
    is_all_sections=False,
    grouped_performers=None,
    executor="",
) -> str:
    if is_full_report:
        return "00"
    rows = asset_report_section_performers(project, asset_name)
    index_by_id = {item.pk: idx for idx, item in enumerate(rows, start=1)}
    if is_all_sections:
        grouped = grouped_performers
        if grouped is None:
            grouped = grouped_report_performers(project, executor, asset_name)
        numbers = [index_by_id[item.pk] for item in grouped if item.pk in index_by_id]
        if not numbers:
            return ""
        return format_report_version(min(numbers))
    if performer is None:
        return ""
    if performer.pk in index_by_id:
        return format_report_version(index_by_id[performer.pk])
    return ""


def report_scope_label(
    *,
    section=None,
    is_full_report=False,
    is_all_sections=False,
    grouped_performers=None,
) -> str:
    if is_full_report:
        return "весь_отчет"
    if is_all_sections:
        codes = []
        for item in grouped_performers or []:
            code = _performer_section_code(item)
            if code:
                codes.append(code)
        return "-".join(codes) or "раздел"
    return _sanitize(getattr(section, "code", "") or typical_section_short(section) or "раздел")


def build_report_filename(
    registration,
    executor,
    *,
    section=None,
    is_all_sections=False,
    is_full_report=False,
    original_name="",
    version=0,
    asset_code="",
    asset_name="",
    performer=None,
    grouped_performers=None,
    section_number=None,
    scope=None,
    uploaded_at=None,
) -> str:
    ext = os.path.splitext(original_name or "")[1]
    short_uid = _sanitize(getattr(registration, "short_uid", "") or "")
    fio = _sanitize(short_fio_no_dots(executor))
    code = (asset_code or "").strip()
    performer, asset_name = _resolve_filename_performer(
        registration, executor, section, performer, asset_name,
    )
    if is_all_sections and grouped_performers is None:
        grouped_performers = grouped_report_performers(registration, executor, asset_name)
    if scope is None:
        scope = report_scope_label(
            section=section or getattr(performer, "typical_section", None),
            is_full_report=is_full_report,
            is_all_sections=is_all_sections,
            grouped_performers=grouped_performers,
        )
    if section_number is None:
        section_number = report_section_number(
            registration,
            asset_name,
            performer=performer,
            is_full_report=is_full_report,
            is_all_sections=is_all_sections,
            grouped_performers=grouped_performers,
            executor=executor,
        )
    numbered_scope = " ".join(part for part in (str(section_number or "").strip(), scope) if part)
    parts = [part for part in (short_uid, code, numbered_scope, fio) if part]
    stem = "_".join(parts) or "отчет"
    return f"{stem}_{format_report_version(version)}_{format_report_file_date(uploaded_at)}{ext}"


_REVIEW_RESULT_SUFFIX_RE = re.compile(r"_(?:ИИ|РН|КП|РП)\d+$|_(?:check|rn|kp|rp)$")


def _strip_review_result_suffix(stem: str) -> str:
    current = (stem or "").rstrip()
    while True:
        cleaned = _REVIEW_RESULT_SUFFIX_RE.sub("", current)
        if cleaned == current:
            return current or "отчет"
        current = cleaned.rstrip()


def build_review_result_filename(filename: str, step: str, cycle: int) -> str:
    """Имя файла результата: код проверяющего и его номер цикла, без чужого суффикса."""
    from .report_review import REVIEW_STEP_LABELS

    label = REVIEW_STEP_LABELS.get(step) or ""
    stem, ext = os.path.splitext(filename or "")
    stem = _strip_review_result_suffix(stem)
    suffix = f"_{label}{int(cycle)}" if label else ""
    return f"{stem}{suffix}{ext or '.docx'}"


def build_review_filename(filename: str, step: str, cycle: int = 1) -> str:
    return build_review_result_filename(filename, step, cycle)


def build_check_filename(filename: str, cycle: int = 1) -> str:
    from .report_review import REVIEW_AI

    return build_review_result_filename(filename, REVIEW_AI, cycle)


def next_review_result_cycle(upload, step: str) -> int:
    """Следующий номер цикла этого проверяющего в слоте отчёта. У каждого свой счётчик."""
    from .models import PerformerReportUpload, ReportReviewEntry
    from .report_review import REVIEW_STEP_LABELS, _slot_upload_ids

    label = REVIEW_STEP_LABELS.get(step) or ""
    if not label:
        return 1
    pattern = re.compile(rf"_{re.escape(label)}(\d+)$")
    slot_ids = _slot_upload_ids(upload) or [getattr(upload, "pk", None)]
    slot_ids = [item for item in slot_ids if item]
    names = []
    if slot_ids:
        names.extend(
            PerformerReportUpload.objects.filter(pk__in=slot_ids).values_list("check_file_name", flat=True)
        )
        names.extend(
            PerformerReportUpload.objects.filter(pk__in=slot_ids).values_list("review_file_name", flat=True)
        )
        names.extend(
            ReportReviewEntry.objects.filter(upload_id__in=slot_ids).values_list("review_file_name", flat=True)
        )
    found = 0
    for name in names:
        stem, _ext = os.path.splitext(name or "")
        match = pattern.search(stem)
        if match:
            found = max(found, int(match.group(1)))
    return found + 1


def index_report_uploads(uploads):
    by_full = {}
    by_all = {}
    by_performer = {}
    for upload in uploads:
        if upload.is_full_report:
            by_full.setdefault(
                full_report_group_key(upload.registration_id, upload.asset_name),
                [],
            ).append(upload)
        elif upload.is_all_sections:
            by_all.setdefault(
                report_group_key(upload.registration_id, upload.executor, upload.asset_name),
                [],
            ).append(upload)
        elif upload.performer_id:
            by_performer.setdefault(upload.performer_id, []).append(upload)
    return by_full, by_all, by_performer


def _report_sort_key(performer):
    return (
        performer.registration_id or 0,
        performer.asset_name or "",
        performer.executor or "",
        getattr(performer, "position", 0) or 0,
        performer.pk or 0,
    )


def _make_report_row(
    *,
    row_id,
    performer,
    performer_ids,
    registration,
    registration_id,
    executor,
    asset_name,
    section_label,
    group_key,
    upload,
    typical_section=None,
    is_all_sections=False,
    is_full_report=False,
    section_count=1,
    is_current=True,
    has_history=False,
    parent_row_id="",
    version_group="",
    version_display="",
    check_rules=None,
    catalog=None,
    review_entry=None,
):
    calculated_count_display = "—"
    corrected_count_display = "—"
    if review_entry is not None:
        from .report_review import entry_status

        workflow_status = entry_status(review_entry)
        upload = review_entry.upload
    else:
        workflow_status = report_workflow_status(upload, check_rules=check_rules)
        workflow_status = mark_corrected_workflow_status(upload, workflow_status)
    finding_groups = report_finding_groups(upload, catalog, check_rules)
    finding_context = report_finding_context(
        registration,
        executor,
        asset_name,
        section_label,
        version_display,
    )
    finding_groups["context"] = finding_context
    if review_entry is not None and (
        review_entry.review_file_name
        or review_entry.review_cloud_path
        or getattr(review_entry, "settled", False)
    ):
        finding_count_value = int(getattr(review_entry, "comment_count", 0) or 0)
        finding_count_display = format_grouped_count(finding_count_value)
        show_finding_info = False
    elif review_entry is not None:
        finding_count_value = None
        finding_count_display = "—"
        show_finding_info = False
    else:
        finding_count_value = report_public_finding_count_value(upload)
        calculated_value = report_finding_count_value(upload)
        finding_count_display = "—" if finding_count_value is None else format_grouped_count(finding_count_value)
        calculated_count_display = "—" if calculated_value is None else format_grouped_count(calculated_value)
        corrected_count_display = finding_count_display
        show_finding_info = bool(calculated_value)
    if show_finding_info:
        if finding_correction_active(upload):
            public_groups = report_finding_groups(upload, catalog, check_rules, source="corrected")
            public_groups["context"] = finding_context
        else:
            public_groups = finding_groups
        edit_groups = report_finding_edit_payload(upload, finding_groups, check_rules)
        edit_groups["context"] = finding_context
    else:
        public_groups = finding_groups
        edit_groups = {}
    return SimpleNamespace(
        row_id=row_id,
        performer=performer,
        performer_ids=performer_ids,
        registration=registration,
        registration_id=registration_id,
        executor=executor,
        asset_name=asset_name or "",
        is_all_sections=is_all_sections,
        is_full_report=is_full_report,
        section_label=section_label,
        section_count=section_count,
        group_key=group_key,
        upload=upload,
        typical_section=typical_section,
        row_kind="full" if is_full_report else ("all" if is_all_sections else "section"),
        is_current=is_current,
        has_history=has_history,
        parent_row_id=parent_row_id or "",
        version_group=version_group or row_id,
        version_display=(
            ""
            if (workflow_status or "").startswith("В работе после ")
            else (
                format_report_version(review_entry.upload.version)
                if review_entry is not None
                else (version_display or "")
            )
        ),
        workflow_status=workflow_status,
        workflow_status_class=report_workflow_status_class(workflow_status),
        status_date_display=(
            format_report_datetime(review_entry.created_at)
            if review_entry is not None
            else format_report_status_date(upload, workflow_status)
        ),
        review_entry=review_entry,
        finding_count_display=finding_count_display,
        calculated_count_display=calculated_count_display,
        corrected_count_display=corrected_count_display,
        finding_groups=public_groups,
        finding_groups_json=json.dumps(public_groups, ensure_ascii=False),
        calculated_groups_json=json.dumps(finding_groups, ensure_ascii=False),
        edit_groups_json=json.dumps(edit_groups, ensure_ascii=False) if edit_groups else "",
        show_finding_info=show_finding_info,
        finding_info_disabled=finding_count_display != "—" and not show_finding_info,
        show_version_download=bool(
            upload
            and (getattr(upload, "file_name", "") or "")
            and (
                (workflow_status or "").startswith(("Проверен", "Сдан", "Согласован"))
                or (
                    review_entry is not None
                    and (getattr(review_entry, "phase", "") or "") == "review"
                )
            )
        ),
        can_upload=False,
        can_send=False,
    )


def _sorted_slot_uploads(uploads):
    return sorted(list(uploads or []), key=lambda item: (item.version, item.pk or 0), reverse=True)


def _without_rework_waiting_for_remarks(entries):
    """«В работе после …» не показываем, пока замечания этого шага не отправлены."""
    pending_marks = [
        (entry.upload_id, entry.step, entry.pk)
        for entry in entries or []
        if getattr(entry, "remarks_notice_pending", False)
    ]
    if not pending_marks:
        return list(entries or [])
    visible = []
    for entry in entries or []:
        if (getattr(entry, "phase", "") or "") == "rework" and any(
            entry.upload_id == upload_id and entry.step == step and entry.pk > pending_pk
            for upload_id, step, pending_pk in pending_marks
        ):
            continue
        visible.append(entry)
    return visible


def _slot_timeline(uploads, entries):
    timeline = []
    for upload in uploads or []:
        if getattr(upload, "step_revision", False):
            continue
        timeline.append((getattr(upload, "uploaded_at", None), int(upload.pk or 0), 0, upload, None))
    for entry in entries or []:
        timeline.append((getattr(entry, "created_at", None), int(entry.pk or 0), 1, entry.upload, entry))
    timeline.sort(key=lambda item: (item[0] is not None, item[0] or timezone.now(), item[1], item[2]), reverse=True)
    return timeline


def _append_slot_rows(rows, *, row_id, uploads, entries=None, **kwargs):
    _mark_slot_latest_versions(uploads)
    if entries is None:
        from .models import ReportReviewEntry

        upload_ids = [item.pk for item in (uploads or []) if getattr(item, "pk", None)]
        entries = list(
            ReportReviewEntry.objects.filter(upload_id__in=upload_ids).select_related("basis_entry", "upload")
        ) if upload_ids else []
    entries = _without_rework_waiting_for_remarks(entries)
    timeline = _slot_timeline(uploads, entries)
    current = timeline[0] if timeline else None
    history = timeline[1:]
    rows.append(
        _make_report_row(
            row_id=row_id,
            upload=current[3] if current else None,
            review_entry=current[4] if current else None,
            is_current=True,
            has_history=bool(history),
            parent_row_id="",
            version_group=row_id,
            version_display=format_report_version(current[3].version) if current and current[3] else "",
            **kwargs,
        )
    )
    for older_upload_at, older_id, _kind, older_upload, older_entry in history:
        suffix = f"e{older_id}" if older_entry is not None else f"v{format_report_version(older_upload.version)}"
        rows.append(
            _make_report_row(
                row_id=f"{row_id}-{suffix}",
                upload=older_upload,
                review_entry=older_entry,
                is_current=False,
                has_history=False,
                parent_row_id=row_id,
                version_group=row_id,
                version_display=format_report_version(older_upload.version) if older_upload else "",
                **kwargs,
            )
        )


def build_report_submission_rows(performers, uploads=None):
    uploads = list(uploads or [])
    by_full, by_all, by_performer = index_report_uploads(uploads)
    check_rules = list(
        ReportCheckRule.objects.prefetch_related("lines__macro").order_by("position", "id")
    )
    catalog = report_macro_catalog_index()
    rows = []

    ordered = sorted(list(performers), key=_report_sort_key)
    for (registration_id, asset_name), asset_grouped in groupby(
        ordered,
        key=lambda performer: (performer.registration_id, performer.asset_name or ""),
    ):
        asset_list = list(asset_grouped)
        if not asset_list:
            continue
        first = asset_list[0]
        registration = first.registration
        manager_name = (getattr(registration, "project_manager", "") or "").strip()
        asset_key = full_report_group_key(registration_id, asset_name)
        _append_slot_rows(
            rows,
            row_id=f"full-{registration_id}-{asset_list[0].pk}",
            performer=None,
            performer_ids=[item.pk for item in asset_list],
            registration=registration,
            registration_id=registration_id,
            executor=manager_name,
            asset_name=asset_name,
            section_label=FULL_REPORT_LABEL,
            group_key=asset_key,
            uploads=by_full.get(asset_key),
            is_full_report=True,
            section_count=len(asset_list),
            check_rules=check_rules,
            catalog=catalog,
        )
        for executor, grouped in groupby(asset_list, key=lambda performer: performer.executor or ""):
            group_list = list(grouped)
            if not group_list:
                continue
            group_key = report_group_key(registration_id, executor, asset_name)
            if len(group_list) > 1:
                _append_slot_rows(
                    rows,
                    row_id=f"all-{registration_id}-{group_list[0].pk}",
                    performer=None,
                    performer_ids=[item.pk for item in group_list],
                    registration=registration,
                    registration_id=registration_id,
                    executor=executor,
                    asset_name=asset_name,
                    section_label=plural_sections(len(group_list)),
                    group_key=group_key,
                    uploads=by_all.get(group_key),
                    is_all_sections=True,
                    section_count=len(group_list),
                    check_rules=check_rules,
                    catalog=catalog,
                )
            for performer in group_list:
                _append_slot_rows(
                    rows,
                    row_id=f"p-{performer.pk}",
                    performer=performer,
                    performer_ids=[performer.pk],
                    registration=registration,
                    registration_id=registration_id,
                    executor=executor,
                    asset_name=performer.asset_name or "",
                    section_label=typical_section_short(performer.typical_section) or "—",
                    group_key=group_key,
                    uploads=by_performer.get(performer.pk),
                    typical_section=performer.typical_section,
                    check_rules=check_rules,
                    catalog=catalog,
                )
    return rows


def _cloud_upload_user(user):
    if is_nextcloud_primary():
        return user
    return get_any_connected_service_user()


def local_report_folder_enabled() -> bool:
    return bool(getattr(settings, "REPORT_CHECK_ALLOW_LOCAL_FOLDER", False))


def local_report_folder_placeholder() -> str:
    return str(Path.home() / "Desktop")


def encode_local_report_path(path: Path) -> str:
    return f"{LOCAL_REPORT_PATH_PREFIX}{path}"


def parse_local_report_path(cloud_path: str) -> str:
    raw = cloud_path or ""
    if not raw.startswith(LOCAL_REPORT_PATH_PREFIX):
        return ""
    return raw[len(LOCAL_REPORT_PATH_PREFIX):]


def is_local_report_path(cloud_path: str) -> bool:
    return bool(parse_local_report_path(cloud_path))


def _local_report_roots():
    roots = getattr(settings, "REPORT_CHECK_LOCAL_ROOTS", ()) or ()
    if not roots:
        roots = getattr(settings, "DSH_SORT_LOCAL_ROOTS", ()) or ()
    return roots


def _local_path_is_allowed(resolved: Path) -> bool:
    for raw in _local_report_roots():
        try:
            root = Path(raw).expanduser().resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _normalize_local_folder_text(raw_path) -> str:
    text = str(raw_path or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def resolve_local_report_folder(raw_path) -> Path:
    if not local_report_folder_enabled():
        raise ReportUploadError("Локальная папка на этом стенде выключена.")
    text = _normalize_local_folder_text(raw_path)
    if not text:
        raise ReportUploadError("Укажите путь к локальной папке.")
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError as exc:
        raise ReportUploadError(f"Не удалось прочитать путь: {exc}") from exc
    if resolved.exists() and not resolved.is_dir():
        raise ReportUploadError("Укажите путь к папке, а не к файлу.")
    if not _local_path_is_allowed(resolved):
        raise ReportUploadError(
            "Путь вне разрешённых корней локального тестирования. "
            "Укажите каталог внутри домашней папки пользователя или папки проекта."
        )
    if not resolved.is_dir():
        raise ReportUploadError(f"Папка не найдена: {resolved}")
    return resolved


def resolve_report_upload_source(request):
    source_kind = (request.POST.get("source_kind") or "cloud").strip() or "cloud"
    if source_kind not in {"cloud", "local"}:
        source_kind = "cloud"
    local_folder_path = ""
    if source_kind == "local":
        local_folder_path = str(resolve_local_report_folder(request.POST.get("local_folder_path") or ""))
    uploaded = request.FILES.get("file")
    if not uploaded:
        raise ReportUploadError("Файл не выбран.")
    return uploaded, local_folder_path


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def read_stored_report_bytes(cloud_path: str, *, file_name: str = "", user=None) -> tuple[str, bytes]:
    """Байты сохранённого файла отчёта или замечаний для вложения в письмо."""
    if is_local_report_path(cloud_path):
        file_bytes = read_local_report_bytes(cloud_path)
        if not file_bytes:
            raise ReportUploadError("Файл замечаний не найден.")
        filename = file_name or os.path.basename(parse_local_report_path(cloud_path) or "") or "remarks.docx"
        return filename, file_bytes
    if cloud_path:
        try:
            cloud_user = user if is_nextcloud_primary() else get_any_connected_service_user()
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not cloud_user:
            raise ReportUploadError("Не найдено подключённое облачное хранилище.")
        try:
            _mime, file_bytes = cloud_download_file(cloud_user, cloud_path)
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not file_bytes:
            raise ReportUploadError("Файл замечаний не найден.")
        filename = file_name or os.path.basename(cloud_path) or "remarks.docx"
        return filename, file_bytes
    raise ReportUploadError("Файл замечаний не найден.")


def read_local_report_bytes(cloud_path: str) -> bytes | None:
    if not local_report_folder_enabled():
        return None
    raw = parse_local_report_path(cloud_path)
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
    except OSError:
        return None
    if not path.is_file() or not _local_path_is_allowed(path):
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def report_upload_slot_qs(
    upload=None,
    *,
    project=None,
    executor="",
    asset_name="",
    performer=None,
    is_all_sections=False,
    is_full_report=False,
):
    if upload is not None:
        project = upload.registration
        executor = upload.executor
        asset_name = upload.asset_name
        performer = upload.performer
        is_all_sections = upload.is_all_sections
        is_full_report = upload.is_full_report
    is_full_report = bool(is_full_report)
    is_all_sections = bool(is_all_sections) and not is_full_report
    if is_full_report:
        return PerformerReportUpload.objects.filter(
            registration=project,
            asset_name=asset_name or "",
            is_full_report=True,
        )
    if is_all_sections:
        return PerformerReportUpload.objects.filter(
            registration=project,
            executor=executor or "",
            asset_name=asset_name or "",
            is_all_sections=True,
            is_full_report=False,
        )
    return PerformerReportUpload.objects.filter(
        performer=performer,
        is_all_sections=False,
        is_full_report=False,
    )


def previous_report_upload(upload):
    if upload is None or int(getattr(upload, "version", 0) or 0) <= 0:
        return None
    return (
        report_upload_slot_qs(upload)
        .exclude(pk=upload.pk)
        .filter(version__lt=upload.version)
        .select_related("registration", "registration__type", "performer", "performer__typical_section")
        .order_by("-version", "-pk")
        .first()
    )


def report_slot_row_id(upload) -> str:
    asset_name = getattr(upload, "asset_name", "") or ""
    registration_id = getattr(upload, "registration_id", None) or getattr(getattr(upload, "registration", None), "pk", None)

    if upload.is_full_report:
        # Тот же первый исполнитель, что у строки «Весь отчет» в таблице:
        # пустой исполнитель в таблицу не попадает.
        first_pk = (
            Performer.objects.filter(registration_id=registration_id, asset_name=asset_name)
            .annotate(executor_trim=Trim("executor"))
            .exclude(executor_trim="")
            .order_by("executor", "position", "pk")
            .values_list("pk", flat=True)
            .first()
        ) or 0
        return f"full-{registration_id}-{first_pk}"
    if upload.is_all_sections:
        first_pk = (
            Performer.objects.filter(
                registration_id=registration_id,
                executor=getattr(upload, "executor", "") or "",
                asset_name=asset_name,
            )
            .order_by("position", "pk")
            .values_list("pk", flat=True)
            .first()
        ) or 0
        return f"all-{registration_id}-{first_pk}"
    return f"p-{upload.performer_id}"


def _report_slot_row_parts(upload):
    slot_id = report_slot_row_id(upload)
    performer = None if (upload.is_full_report or upload.is_all_sections) else upload.performer
    registration = upload.registration
    asset_name = upload.asset_name or ""
    if upload.is_full_report:
        performer_ids = list(
            Performer.objects.filter(
                registration_id=upload.registration_id,
                asset_name=asset_name,
            ).values_list("pk", flat=True)
        )
        section_label = FULL_REPORT_LABEL
        group_key = full_report_group_key(upload.registration_id, asset_name)
    elif upload.is_all_sections:
        performer_ids = list(
            Performer.objects.filter(
                registration_id=upload.registration_id,
                executor=upload.executor or "",
                asset_name=asset_name,
            ).values_list("pk", flat=True)
        )
        section_label = plural_sections(len(performer_ids))
        group_key = report_group_key(upload.registration_id, upload.executor, asset_name)
    else:
        performer_ids = [performer.pk] if performer else []
        section_label = typical_section_short(getattr(performer, "typical_section", None)) or "—"
        group_key = report_group_key(upload.registration_id, upload.executor, asset_name)
    return {
        "slot_id": slot_id,
        "performer": performer,
        "performer_ids": performer_ids,
        "registration": registration,
        "registration_id": upload.registration_id,
        "executor": upload.executor or "",
        "asset_name": asset_name,
        "section_label": section_label,
        "group_key": group_key,
        "typical_section": getattr(performer, "typical_section", None),
        "is_all_sections": upload.is_all_sections,
        "is_full_report": upload.is_full_report,
        "section_count": len(performer_ids) or 1,
    }


def build_report_history_row(current_upload, previous_upload):
    parts = _report_slot_row_parts(current_upload)
    slot_id = parts.pop("slot_id")
    return _make_report_row(
        row_id=f"{slot_id}-v{format_report_version(previous_upload.version)}",
        upload=previous_upload,
        is_current=False,
        has_history=False,
        parent_row_id=slot_id,
        version_group=slot_id,
        version_display=format_report_version(previous_upload.version),
        **parts,
    )


def build_report_review_current_row(entry):
    """Текущая строка слота — открытый ручной шаг над строкой «Сдан»."""
    parts = _report_slot_row_parts(entry.upload)
    slot_id = parts.pop("slot_id")
    check_rules = list(
        ReportCheckRule.objects.prefetch_related("lines__macro").order_by("position", "id")
    )
    return _make_report_row(
        row_id=slot_id,
        upload=entry.upload,
        review_entry=entry,
        is_current=True,
        has_history=True,
        parent_row_id="",
        version_group=slot_id,
        check_rules=check_rules,
        **parts,
    )


def build_report_slot_rows(upload):
    """Все строки одного слота после правки замечаний, сверху — актуальная."""
    uploads = list(
        report_upload_slot_qs(upload)
        .filter(step_revision=False)
        .select_related(
            "registration",
            "registration__type",
            "performer",
            "performer__typical_section",
        )
        .order_by("-version", "-pk")
    )
    parts = _report_slot_row_parts(upload)
    slot_id = parts.pop("slot_id")
    rows = []
    check_rules = list(
        ReportCheckRule.objects.prefetch_related("lines__macro").order_by("position", "id")
    )
    _append_slot_rows(
        rows,
        row_id=slot_id,
        uploads=uploads,
        check_rules=check_rules,
        catalog=report_macro_catalog_index(),
        **parts,
    )
    return rows


def build_report_slot_current_row(anchor, current_upload=None, *, has_history=False):
    parts = _report_slot_row_parts(anchor)
    slot_id = parts.pop("slot_id")
    check_rules = list(
        ReportCheckRule.objects.prefetch_related("lines__macro").order_by("position", "id")
    )
    return _make_report_row(
        row_id=slot_id,
        upload=current_upload,
        is_current=True,
        has_history=has_history,
        parent_row_id="",
        version_group=slot_id,
        version_display=format_report_version(current_upload.version) if current_upload else "",
        check_rules=check_rules,
        **parts,
    )


def _delete_local_report_file(cloud_path: str) -> None:
    raw = parse_local_report_path(cloud_path)
    if not raw:
        return
    try:
        path = Path(raw).expanduser().resolve()
    except OSError as exc:
        raise ReportUploadError(f"Не удалось прочитать путь: {exc}") from exc
    if not _local_path_is_allowed(path):
        raise ReportUploadError("Путь вне разрешённых корней локального тестирования.")
    if path.is_dir():
        raise ReportUploadError("Указан путь к папке, а не к файлу.")
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise ReportUploadError(f"Не удалось удалить файл: {exc}") from exc


def _delete_cloud_report_file(user, cloud_path: str) -> None:
    try:
        cloud_user = _cloud_upload_user(user)
    except CloudStorageNotReadyError as exc:
        raise ReportUploadError(str(exc)) from exc
    if not cloud_user:
        raise ReportUploadError("Не найдено подключённое облачное хранилище.")
    try:
        ok = cloud_delete_file(cloud_user, cloud_path)
    except CloudStorageNotReadyError as exc:
        raise ReportUploadError(str(exc)) from exc
    if not ok:
        raise ReportUploadError("Не удалось удалить файл из облачного хранилища.")


def delete_stored_report_file(user, cloud_path: str) -> None:
    path = cloud_path or ""
    if not path:
        return
    if is_local_report_path(path):
        _delete_local_report_file(path)
        return
    _delete_cloud_report_file(user, path)


def _clear_deleted_report_reference(upload, *, kind: str) -> None:
    if kind == "report":
        upload.cloud_path = ""
        upload.file_link = ""
        upload.save(update_fields=["cloud_path", "file_link"])
        return
    upload.check_cloud_path = ""
    upload.check_file_link = ""
    upload.save(update_fields=["check_cloud_path", "check_file_link"])


def delete_report_upload(user, upload):
    """Delete the report file, its check file, and the upload row.

    Returns whether the removed row was the latest version and the remaining
    uploads of the same slot, newest first.

    Each storage delete is recorded on the row before the next one runs. If the
    check file cannot be removed after the report file is gone, the retained
    row no longer points at the deleted report.
    """
    was_latest = (
        report_upload_slot_qs(upload)
        .order_by("-version", "-pk")
        .values_list("pk", flat=True)
        .first()
        == upload.pk
    )
    main_path = upload.cloud_path or ""
    check_path = upload.check_cloud_path or ""
    errors = []
    if main_path:
        try:
            delete_stored_report_file(user, main_path)
        except ReportUploadError as exc:
            errors.append(exc)
        else:
            _clear_deleted_report_reference(upload, kind="report")
            if check_path == main_path:
                _clear_deleted_report_reference(upload, kind="check")
    if check_path and check_path != main_path:
        try:
            delete_stored_report_file(user, check_path)
        except ReportUploadError as exc:
            errors.append(exc)
        else:
            _clear_deleted_report_reference(upload, kind="check")
    if errors:
        raise errors[0]
    slot_qs = report_upload_slot_qs(upload)
    PerformerReportUpload.objects.filter(pk=upload.pk).delete()
    remaining = list(
        slot_qs.select_related(
            "registration",
            "registration__type",
            "performer",
            "performer__typical_section",
        ).order_by("-version", "-pk")
    )
    return was_latest, remaining


def clear_report_check_result(user, upload):
    if not (upload.check_file_name or upload.check_cloud_path or upload.check_file_link):
        raise ReportUploadError("Файл результата проверки не найден.")
    delete_stored_report_file(user, upload.check_cloud_path)
    upload.check_file_name = ""
    upload.check_file_link = ""
    upload.check_cloud_path = ""
    upload.check_status = ""
    upload.check_finding_count = 0
    upload.check_error = ""
    upload.checked_at = None
    upload.check_macro_index = 0
    upload.check_macro_total = 0
    upload.check_macro_name = ""
    upload.check_finding_correction = None
    upload.save(update_fields=[
        "check_file_name",
        "check_file_link",
        "check_cloud_path",
        "check_status",
        "check_finding_count",
        "check_error",
        "checked_at",
        "check_macro_index",
        "check_macro_total",
        "check_macro_name",
        "check_finding_correction",
    ])
    return upload


def _delete_reserved_report_upload(upload):
    if upload is None or not getattr(upload, "pk", None):
        return
    try:
        PerformerReportUpload.objects.filter(pk=upload.pk).delete()
    except Exception:
        logger.exception("Failed to delete reserved report upload %s", upload.pk)


def _reserve_next_report_upload(
    *,
    slot_qs,
    project,
    executor,
    asset_name,
    performer,
    is_all_sections,
    is_full_report,
    uploaded_file,
    asset_code,
    user,
):
    with transaction.atomic():
        latest = slot_qs.select_for_update().order_by("-version", "-pk").first()
        next_version = (latest.version + 1) if latest else 0
        uploaded_at = timezone.now()
        grouped = None
        if is_all_sections:
            grouped = grouped_report_performers(project, executor, asset_name)
        filename = build_report_filename(
            project,
            executor,
            section=getattr(performer, "typical_section", None),
            is_all_sections=is_all_sections,
            is_full_report=is_full_report,
            original_name=getattr(uploaded_file, "name", "") or "",
            version=next_version,
            asset_code=asset_code,
            asset_name=asset_name or "",
            performer=None if (is_full_report or is_all_sections) else performer,
            grouped_performers=grouped,
            uploaded_at=uploaded_at,
        )
        return PerformerReportUpload.objects.create(
            registration=project,
            executor=executor or "",
            asset_name=asset_name or "",
            performer=None if (is_full_report or is_all_sections) else performer,
            is_all_sections=is_all_sections,
            is_full_report=is_full_report,
            version=next_version,
            file_name=filename,
            file_link="",
            cloud_path="",
            check_file_name="",
            check_file_link="",
            check_cloud_path="",
            check_status="",
            check_finding_count=0,
            check_error="",
            checked_at=None,
            uploaded_at=uploaded_at,
            uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        )


def _prepare_report_upload_destination(*, user, project, local_folder, asset_folder_name):
    if local_folder is not None:
        dest_dir = local_folder
        if asset_folder_name:
            dest_dir = local_folder / asset_folder_name
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ReportUploadError(f"Не удалось создать папку актива: {exc}") from exc
        return dest_dir, "", None

    folder_path = resolve_reports_folder_path(project, user)
    try:
        cloud_user = _cloud_upload_user(user)
    except CloudStorageNotReadyError as exc:
        raise ReportUploadError(str(exc)) from exc
    if not cloud_user:
        raise ReportUploadError("Не найдено подключённое облачное хранилище.")
    if asset_folder_name:
        folder_path = join_cloud_path(folder_path, asset_folder_name)
        try:
            folder_ok = cloud_create_folder(cloud_user, folder_path)
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not folder_ok:
            raise ReportUploadError("Не удалось создать папку актива в облачном хранилище.")
    return None, folder_path, cloud_user


def _store_reserved_report_file(*, upload, file_bytes, dest_dir, folder_path, cloud_user):
    if dest_dir is not None:
        dest = dest_dir / upload.file_name
        try:
            dest.write_bytes(file_bytes)
        except OSError as exc:
            raise ReportUploadError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
        disk_path = encode_local_report_path(dest)
        public_url = ""
    else:
        disk_path = join_cloud_path(folder_path, upload.file_name)
        try:
            ok = cloud_upload_file(cloud_user, disk_path, file_bytes)
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not ok:
            raise ReportUploadError("Не удалось загрузить файл в облачное хранилище.")
        try:
            public_url = cloud_publish_resource(cloud_user, disk_path) or ""
        except CloudStorageNotReadyError:
            public_url = ""

    _reconnect_after_storage_io()
    upload.file_link = public_url
    upload.cloud_path = disk_path
    upload.save(update_fields=["file_link", "cloud_path"])
    return upload


def _retire_ai_rework_entries(upload) -> None:
    """Новая версия после «В работе после ИИ» продолжает ту же строку, без отдельной истории."""
    from .models import ReportReviewEntry
    from .report_review import REVIEW_AI, REVIEW_PHASE_REWORK, _slot_upload_ids

    slot_ids = _slot_upload_ids(upload)
    if not slot_ids:
        return
    ReportReviewEntry.objects.filter(
        upload_id__in=slot_ids,
        step=REVIEW_AI,
        phase=REVIEW_PHASE_REWORK,
        settled=False,
    ).delete()


def _return_rework_to_review(upload) -> bool:
    """Отправка файла после «В работе после …» снова открывает ту же роль, без автопроверки."""
    from .models import ReportReviewEntry
    from .report_review import REVIEW_PHASE_REVIEW, REVIEW_PHASE_REWORK, _slot_upload_ids

    slot_ids = _slot_upload_ids(upload)
    if not slot_ids:
        return False
    previous = (
        ReportReviewEntry.objects
        .filter(upload_id__in=slot_ids, settled=False, phase=REVIEW_PHASE_REWORK)
        .order_by("-created_at", "-id")
        .first()
    )
    if previous is None or previous.step == "ai":
        return False
    now = timezone.now()
    previous.phase = REVIEW_PHASE_REVIEW
    previous.upload = upload
    previous.created_at = now
    previous.save(update_fields=["phase", "upload", "created_at"])
    upload.review_step = previous.step
    upload.review_phase = REVIEW_PHASE_REVIEW
    upload.step_revision = True
    upload.status_changed_at = now
    upload.save(update_fields=["review_step", "review_phase", "step_revision", "status_changed_at"])
    return True


def upload_report_file(
    *,
    user,
    project,
    executor,
    asset_name,
    performer,
    is_all_sections,
    uploaded_file,
    is_full_report=False,
    local_folder_path="",
):
    is_full_report = bool(is_full_report)
    is_all_sections = bool(is_all_sections) and not is_full_report
    local_folder = Path(local_folder_path).expanduser().resolve() if local_folder_path else None
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    if not file_bytes:
        raise ReportUploadError("Файл пуст.")

    slot_qs = report_upload_slot_qs(
        project=project,
        executor=executor,
        asset_name=asset_name,
        performer=performer,
        is_all_sections=is_all_sections,
        is_full_report=is_full_report,
    )
    asset_code = report_asset_code(project, asset_name)
    dest_dir, folder_path, cloud_user = _prepare_report_upload_destination(
        user=user,
        project=project,
        local_folder=local_folder,
        asset_folder_name=build_report_asset_folder_name(asset_code, asset_name),
    )

    upload = None
    for attempt in range(3):
        try:
            upload = _reserve_next_report_upload(
                slot_qs=slot_qs,
                project=project,
                executor=executor,
                asset_name=asset_name,
                performer=performer,
                is_all_sections=is_all_sections,
                is_full_report=is_full_report,
                uploaded_file=uploaded_file,
                asset_code=asset_code,
                user=user,
            )
        except IntegrityError:
            logger.warning(
                "Report upload version conflict on attempt %s for registration=%s",
                attempt + 1,
                getattr(project, "pk", None),
            )
            upload = None
            if attempt >= 2:
                raise ReportUploadError("Не удалось сохранить новую версию файла.")
            continue

        try:
            stored = _store_reserved_report_file(
                upload=upload,
                file_bytes=file_bytes,
                dest_dir=dest_dir,
                folder_path=folder_path,
                cloud_user=cloud_user,
            )
            _retire_ai_rework_entries(stored)
            return stored
        except Exception:
            _reconnect_after_storage_io()
            _delete_reserved_report_upload(upload)
            raise
    raise ReportUploadError("Не удалось сохранить новую версию файла.")


def read_report_stored_bytes(upload, user) -> bytes:
    if is_local_report_path(upload.cloud_path):
        data = read_local_report_bytes(upload.cloud_path)
        if not data:
            raise ReportUploadError("Файл не найден.")
        return data
    if not upload.cloud_path:
        raise ReportUploadError("Файл не найден.")
    try:
        cloud_user = _cloud_upload_user(user)
    except CloudStorageNotReadyError as exc:
        raise ReportUploadError(str(exc)) from exc
    if not cloud_user:
        raise ReportUploadError("Не найдено подключённое облачное хранилище.")
    _mime, data = cloud_download_file(cloud_user, upload.cloud_path)
    if not data:
        raise ReportUploadError("Не удалось скачать файл из облачного хранилища.")
    return data


def run_saved_report_check(user, upload):
    from .report_macro_runner import ReportCheckAborted, store_report_macro_progress

    if not store_report_macro_progress(upload, 0, 0, "Чтение файла"):
        logger.info("Report check for upload %s stopped because the claim was lost", upload.pk)
        return upload
    file_bytes = read_report_stored_bytes(upload, user)
    from .report_skill_runner import apply_report_checks

    try:
        processed_bytes = apply_report_checks(upload, file_bytes)
    except ReportCheckAborted:
        logger.info("Report check for upload %s stopped because the claim was lost", upload.pk)
        return upload
    try:
        upload.refresh_from_db()
    except PerformerReportUpload.DoesNotExist:
        return upload
    if upload.check_status != PerformerReportUpload.CheckStatus.DONE:
        return upload
    if is_local_report_path(upload.cloud_path):
        local_dest = Path(parse_local_report_path(upload.cloud_path))
        _save_report_check_copy(
            upload=upload,
            processed_bytes=processed_bytes,
            filename=upload.file_name,
            local_dest=local_dest,
            folder_path="",
            cloud_user=None,
        )
        return upload
    folder_path = (upload.cloud_path or "").rsplit("/", 1)[0]
    try:
        cloud_user = _cloud_upload_user(user)
    except CloudStorageNotReadyError as exc:
        raise ReportUploadError(str(exc)) from exc
    _save_report_check_copy(
        upload=upload,
        processed_bytes=processed_bytes,
        filename=upload.file_name,
        local_dest=None,
        folder_path=folder_path,
        cloud_user=cloud_user,
    )
    return upload


REPORT_CHECK_HEARTBEAT_INTERVAL = 10
REPORT_CHECK_LEASE = timedelta(seconds=120)
REPORT_CHECK_RECOVERY_INTERVAL = 10
MAX_REPORT_CHECK_ATTEMPTS = 3
_recovery_lock = threading.Lock()
_recovery_started = False


def _report_check_upload_qs(upload_id):
    return (
        PerformerReportUpload.objects
        .select_related(
            "registration",
            "registration__type",
            "performer",
            "performer__typical_section",
        )
        .filter(pk=upload_id)
    )


def _owns_report_check(upload_id, claim_token: str) -> bool:
    if not claim_token:
        return False
    return PerformerReportUpload.objects.filter(
        pk=upload_id,
        check_claim=claim_token,
        check_status=PerformerReportUpload.CheckStatus.RUNNING,
    ).exists()


def _heartbeat_report_check(upload_id, claim_token: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(REPORT_CHECK_HEARTBEAT_INTERVAL):
        _close_background_db_connections()
        try:
            updated = PerformerReportUpload.objects.filter(
                pk=upload_id,
                check_claim=claim_token,
                check_status=PerformerReportUpload.CheckStatus.RUNNING,
            ).update(check_heartbeat_at=timezone.now())
            if not updated:
                return
        except Exception:
            logger.exception("Report check heartbeat failed for upload %s", upload_id)
        finally:
            _close_background_db_connections()


def _mark_report_check_error(upload_id, claim_token: str, message: str) -> None:
    if not _owns_report_check(upload_id, claim_token):
        return
    PerformerReportUpload.objects.filter(pk=upload_id, check_claim=claim_token).update(
        check_status=PerformerReportUpload.CheckStatus.ERROR,
        check_error=message or "Не удалось выполнить проверку отчёта.",
        checked_at=timezone.now(),
        check_macro_index=0,
        check_macro_total=0,
        check_macro_name="",
    )


def _run_saved_report_check_background(user_id, upload_id, claim_token: str):
    from .report_macro_runner import bind_report_check_claim, clear_report_check_claim

    _close_background_db_connections()
    stop_event = threading.Event()
    heartbeat = None
    try:
        if not _owns_report_check(upload_id, claim_token):
            return
        upload = _report_check_upload_qs(upload_id).first()
        if upload is None:
            return
        bind_report_check_claim(upload_id, claim_token)
        heartbeat = threading.Thread(
            target=_heartbeat_report_check,
            args=(upload_id, claim_token, stop_event),
            name=f"report-check-heartbeat-{upload_id}",
            daemon=True,
        )
        heartbeat.start()
        user = get_user_model().objects.get(pk=user_id)
        run_saved_report_check(user, upload)
    except Exception as exc:
        logger.exception("Background report check failed for upload %s", upload_id)
        _mark_report_check_error(
            upload_id,
            claim_token,
            str(exc) or "Не удалось выполнить проверку отчёта.",
        )
    finally:
        stop_event.set()
        if heartbeat is not None:
            heartbeat.join(timeout=2)
        clear_report_check_claim()
        _close_background_db_connections()


def _start_report_check_background(user_id, upload_id, claim_token: str):
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(manage_py),
                "run_report_check",
                str(user_id),
                str(upload_id),
                claim_token,
            ],
            cwd=str(settings.BASE_DIR),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        logger.exception("Failed to start report check process for upload %s", upload_id)
        _mark_report_check_error(
            upload_id,
            claim_token,
            "Не удалось запустить проверку отчёта.",
        )


def _abandoned_report_checks(upload_id=None):
    stale_before = timezone.now() - REPORT_CHECK_LEASE
    qs = PerformerReportUpload.objects.filter(
        check_status=PerformerReportUpload.CheckStatus.RUNNING,
    ).filter(
        Q(check_heartbeat_at__isnull=True) | Q(check_heartbeat_at__lt=stale_before)
    )
    if upload_id is not None:
        qs = qs.filter(pk=upload_id)
    return qs


def recover_abandoned_report_checks(upload_id=None) -> list[int]:
    """Restart report checks whose process lease expired.

    The check runs in its own process, so a Gunicorn worker recycle does not
    stop it. A stale heartbeat means that process died; another worker starts
    it again.
    """
    now = timezone.now()
    abandoned = _abandoned_report_checks(upload_id)
    exhausted_ids = list(
        abandoned.filter(check_attempts__gte=MAX_REPORT_CHECK_ATTEMPTS).values_list("pk", flat=True)
    )
    if exhausted_ids:
        PerformerReportUpload.objects.filter(
            pk__in=exhausted_ids,
            check_status=PerformerReportUpload.CheckStatus.RUNNING,
        ).update(
            check_status=PerformerReportUpload.CheckStatus.ERROR,
            check_error="Проверка отчёта была прервана и не завершилась.",
            checked_at=now,
            check_macro_index=0,
            check_macro_total=0,
            check_macro_name="",
        )
    started = []
    candidates = list(
        _abandoned_report_checks(upload_id)
        .filter(check_attempts__lt=MAX_REPORT_CHECK_ATTEMPTS)
        .values("pk", "sent_by_id", "uploaded_by_id")
    )
    for row in candidates:
        token = uuid.uuid4().hex
        updated = PerformerReportUpload.objects.filter(
            pk=row["pk"],
            check_status=PerformerReportUpload.CheckStatus.RUNNING,
            check_attempts__lt=MAX_REPORT_CHECK_ATTEMPTS,
        ).filter(
            Q(check_heartbeat_at__isnull=True)
            | Q(check_heartbeat_at__lt=now - REPORT_CHECK_LEASE)
        ).update(
            check_claim=token,
            check_heartbeat_at=now,
            check_attempts=F("check_attempts") + 1,
            check_macro_index=0,
            check_macro_total=0,
            check_macro_name="",
        )
        if not updated:
            continue
        user_id = row["sent_by_id"] or row["uploaded_by_id"]
        if not user_id:
            PerformerReportUpload.objects.filter(pk=row["pk"], check_claim=token).update(
                check_status=PerformerReportUpload.CheckStatus.ERROR,
                check_error="Не удалось возобновить проверку отчёта: не найден пользователь.",
                checked_at=now,
                check_macro_index=0,
                check_macro_total=0,
                check_macro_name="",
            )
            continue
        _start_report_check_background(user_id, row["pk"], token)
        started.append(row["pk"])
    return started


def _report_check_recovery_loop() -> None:
    while True:
        _close_background_db_connections()
        try:
            recover_abandoned_report_checks()
        except Exception:
            logger.exception("Report check recovery failed")
        finally:
            _close_background_db_connections()
        time.sleep(REPORT_CHECK_RECOVERY_INTERVAL)


def report_check_recovery_autostart() -> bool:
    argv = sys.argv
    blocked = {"test", "migrate", "makemigrations", "collectstatic", "shell", "check", "run_report_check"}
    if any(arg in blocked for arg in argv):
        return False
    if any("pytest" in arg for arg in argv):
        return False
    if "runserver" in argv and os.environ.get("RUN_MAIN") != "true":
        return False
    return True


def start_report_check_recovery() -> None:
    global _recovery_started
    if not report_check_recovery_autostart():
        return
    with _recovery_lock:
        if _recovery_started:
            return
        _recovery_started = True
    threading.Thread(
        target=_report_check_recovery_loop,
        name="report-check-recovery",
        daemon=True,
    ).start()


_CHECK_ERROR_REASONS = (
    (("stream ended", "стрим закрылся", "сессия dsh оборвалась"), "обрыв потока"),
    (("массивом findings", "некорректный json", "findings.json"), "неверный формат ответа"),
    (("пустой ответ",), "пустой ответ"),
    (("429", "rate_limit", "rate limit", "too many requests"), "превышен лимит запросов"),
    (("timeout", "timed out", "не ответил"), "таймаут"),
    (("прервана",), "проверка прервана"),
    (("не удалось сохранить",), "не сохранён файл"),
    (("не найден пользователь",), "не найден пользователь"),
    (("свободного слота",), "ожидание модели"),
    (("вставить принятые замечания",), "не вставлены замечания"),
    (("неизвестный режим",), "неизвестный режим"),
    (("макрос",), "ошибка макроса"),
    (("не запустить проверку",), "не запущена"),
)


def report_check_error_reason(message: str) -> str:
    """Короткое пояснение для строки «Ошибка проверки: …»."""
    text = str(message or "").casefold()
    if not text:
        return ""
    for markers, reason in _CHECK_ERROR_REASONS:
        if any(marker in text for marker in markers):
            return reason
    return "сбой проверки"


def resume_report_check(user, upload):
    """Повторить проверку с места остановки: готовые фрагменты не пересчитываются."""
    from .report_macro_runner import list_macros_for_upload
    from .report_skill_runner import has_skill_rules_for_upload

    if not (upload.file_name or upload.cloud_path):
        raise ReportUploadError("Сначала загрузите файл.")
    if not has_skill_rules_for_upload(upload) and not list_macros_for_upload(upload):
        raise ReportUploadError("Для отчёта нет автоматической проверки.")
    with transaction.atomic():
        upload = PerformerReportUpload.objects.select_for_update().get(pk=upload.pk)
        if upload.check_status == PerformerReportUpload.CheckStatus.RUNNING:
            raise ReportUploadError("Проверка уже выполняется.")
        if upload.check_status != PerformerReportUpload.CheckStatus.ERROR:
            raise ReportUploadError("Проверку можно возобновить только после ошибки.")
        claim_token = uuid.uuid4().hex
        upload.check_status = PerformerReportUpload.CheckStatus.RUNNING
        upload.check_finding_count = 0
        upload.check_error = ""
        upload.checked_at = None
        upload.check_claim = claim_token
        upload.check_heartbeat_at = timezone.now()
        upload.check_attempts = 1
        upload.check_macro_index = 0
        upload.check_macro_total = 0
        upload.check_macro_name = ""
        upload.save(update_fields=[
            "check_status",
            "check_finding_count",
            "check_error",
            "checked_at",
            "check_claim",
            "check_heartbeat_at",
            "check_attempts",
            "check_macro_index",
            "check_macro_total",
            "check_macro_name",
        ])
    _start_report_check_background(user.pk, upload.pk, claim_token)
    return (
        PerformerReportUpload.objects
        .select_related("registration", "registration__type", "performer", "performer__typical_section")
        .get(pk=upload.pk)
    )


def send_report_upload(user, upload):
    if not (upload.file_name or upload.cloud_path):
        raise ReportUploadError("Сначала загрузите файл.")
    if (getattr(upload, "review_step", "") or ""):
        raise ReportUploadError("Отчёт уже на ручной проверке.")
    if _return_rework_to_review(upload):
        return (
            PerformerReportUpload.objects
            .select_related("registration", "registration__type", "performer", "performer__typical_section")
            .get(pk=upload.pk)
        )
    _retire_ai_rework_entries(upload)
    from .report_review import REVIEW_AI, manual_steps, review_chain_for_upload
    from .report_skill_runner import has_skill_rules_for_upload

    chain = review_chain_for_upload(upload)
    if REVIEW_AI not in chain:
        steps = manual_steps(chain)
        if not steps:
            raise ReportUploadError("В порядке проверки нет шагов.")
        from .models import ReportReviewEntry
        from .report_review import REVIEW_PHASE_REVIEW

        with transaction.atomic():
            upload = PerformerReportUpload.objects.select_for_update().get(pk=upload.pk)
            if upload.review_step:
                raise ReportUploadError("Отчёт уже на ручной проверке.")
            existing = (
                ReportReviewEntry.objects
                .filter(upload=upload, phase=REVIEW_PHASE_REVIEW, settled=False)
                .order_by("-created_at", "-id")
                .first()
            )
            step = existing.step if existing is not None else steps[0]
            now = timezone.now()
            if not upload.sent_at:
                upload.sent_at = now
                upload.sent_by = user if getattr(user, "is_authenticated", False) else None
            upload.review_step = step
            upload.review_phase = REVIEW_PHASE_REVIEW
            upload.status_changed_at = now
            upload.save(update_fields=[
                "sent_at",
                "sent_by",
                "review_step",
                "review_phase",
                "status_changed_at",
            ])
            if existing is None:
                ReportReviewEntry.objects.create(
                    upload=upload,
                    step=step,
                    phase=REVIEW_PHASE_REVIEW,
                )
        return (
            PerformerReportUpload.objects
            .select_related("registration", "registration__type", "performer", "performer__typical_section")
            .get(pk=upload.pk)
        )

    has_skill_rules = has_skill_rules_for_upload(upload)
    if has_skill_rules:
        with transaction.atomic():
            upload = (
                PerformerReportUpload.objects
                .select_for_update()
                .get(pk=upload.pk)
            )
            if upload.check_status == PerformerReportUpload.CheckStatus.RUNNING:
                return upload
            claim_token = uuid.uuid4().hex
            upload.sent_at = timezone.now()
            upload.sent_by = user if getattr(user, "is_authenticated", False) else None
            upload.check_status = PerformerReportUpload.CheckStatus.RUNNING
            upload.check_finding_count = 0
            upload.check_error = ""
            upload.checked_at = None
            upload.check_claim = claim_token
            upload.check_heartbeat_at = timezone.now()
            upload.check_attempts = 1
            upload.check_macro_index = 0
            upload.check_macro_total = 0
            upload.check_macro_name = ""
            upload.save(update_fields=[
                "sent_at",
                "sent_by",
                "check_status",
                "check_finding_count",
                "check_error",
                "checked_at",
                "check_claim",
                "check_heartbeat_at",
                "check_attempts",
                "check_macro_index",
                "check_macro_total",
                "check_macro_name",
            ])
        _start_report_check_background(user.pk, upload.pk, claim_token)
        return (
            PerformerReportUpload.objects
            .select_related("registration", "registration__type", "performer", "performer__typical_section")
            .get(pk=upload.pk)
        )

    upload.sent_at = timezone.now()
    upload.sent_by = user if getattr(user, "is_authenticated", False) else None
    upload.save(update_fields=["sent_at", "sent_by"])
    try:
        run_saved_report_check(user, upload)
    except ReportUploadError:
        raise
    except Exception:
        logger.exception("Report check failed after sending upload %s", upload.pk)
    return (
        PerformerReportUpload.objects
        .select_related("registration", "registration__type", "performer", "performer__typical_section")
        .get(pk=upload.pk)
    )


def _save_report_check_copy(*, upload, processed_bytes, filename, local_dest, folder_path, cloud_user):
    from .report_macro_runner import report_check_claim_lost

    try:
        upload.refresh_from_db()
    except PerformerReportUpload.DoesNotExist:
        return
    if report_check_claim_lost(upload) or upload.check_status != PerformerReportUpload.CheckStatus.DONE:
        return

    def _save_check_fields(fields) -> bool:
        if report_check_claim_lost(upload):
            return False
        upload.save(update_fields=fields)
        return True

    from .report_review import REVIEW_AI

    check_name = build_check_filename(filename, next_review_result_cycle(upload, REVIEW_AI))
    if local_dest is not None:
        check_dest = local_dest.parent / check_name
        try:
            check_dest.write_bytes(processed_bytes)
        except OSError as exc:
            upload.check_status = PerformerReportUpload.CheckStatus.ERROR
            upload.check_error = "\n".join(
                part for part in (upload.check_error, f"Не удалось сохранить файл проверки: {exc}") if part
            )
            _save_check_fields(["check_status", "check_error"])
            return
        upload.check_file_name = check_name
        upload.check_cloud_path = encode_local_report_path(check_dest)
        upload.check_file_link = ""
        _save_check_fields(["check_file_name", "check_cloud_path", "check_file_link"])
        return

    check_path = join_cloud_path(folder_path, check_name)
    try:
        ok = cloud_upload_file(cloud_user, check_path, processed_bytes)
    except CloudStorageNotReadyError as exc:
        upload.check_status = PerformerReportUpload.CheckStatus.ERROR
        upload.check_error = "\n".join(
            part for part in (upload.check_error, str(exc)) if part
        )
        _save_check_fields(["check_status", "check_error"])
        return
    if not ok:
        upload.check_status = PerformerReportUpload.CheckStatus.ERROR
        upload.check_error = "\n".join(
            part for part in (upload.check_error, "Не удалось сохранить файл с результатами проверки.") if part
        )
        _save_check_fields(["check_status", "check_error"])
        return
    try:
        public_url = cloud_publish_resource(cloud_user, check_path) or ""
    except CloudStorageNotReadyError:
        public_url = ""
    upload.check_file_name = check_name
    upload.check_cloud_path = check_path
    upload.check_file_link = public_url
    _save_check_fields(["check_file_name", "check_cloud_path", "check_file_link"])


def submit_report_review_file(*, user, upload, file_bytes, original_name, local_folder_path=""):
    """Файл замечаний ручного шага. Комментарии возвращают отчёт, пустой файл закрывает шаг."""
    from .docx_comments import DocxCommentError, count_comments
    from .report_review import (
        REVIEW_PHASE_REVIEW,
        latest_open_entry,
        next_manual_step,
        review_chain_for_upload,
        user_can_submit_review,
    )

    if not user_can_submit_review(user, upload):
        raise ReportUploadError("Недостаточно прав.")
    if Path(original_name or "").suffix.lower() != ".docx":
        raise ReportUploadError("Нужен файл DOCX.")
    if not file_bytes:
        raise ReportUploadError("Файл пуст.")
    try:
        comment_count = count_comments(file_bytes)
    except DocxCommentError as exc:
        raise ReportUploadError(str(exc)) from exc

    open_entry = latest_open_entry(upload)
    if open_entry is None:
        raise ReportUploadError("Нет шага, который принимает файл.")
    step = open_entry.step
    review_name = build_review_filename(
        upload.file_name or original_name,
        step,
        next_review_result_cycle(upload, step),
    )
    local_folder = None
    if is_local_report_path(upload.cloud_path):
        local_folder = Path(parse_local_report_path(upload.cloud_path)).parent
    elif local_folder_path and not upload.cloud_path:
        local_folder = Path(local_folder_path).expanduser().resolve()
    if local_folder is not None:
        dest = local_folder / review_name
        try:
            dest.write_bytes(file_bytes)
        except OSError as exc:
            raise ReportUploadError(f"Не удалось сохранить файл замечаний: {exc}") from exc
        upload.review_file_name = review_name
        upload.review_cloud_path = encode_local_report_path(dest)
        upload.review_file_link = ""
    else:
        folder_path = (upload.cloud_path or "").rsplit("/", 1)[0]
        if not folder_path:
            raise ReportUploadError("Файл не найден.")
        try:
            cloud_user = _cloud_upload_user(user)
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not cloud_user:
            raise ReportUploadError("Не найдено подключённое облачное хранилище.")
        review_path = join_cloud_path(folder_path, review_name)
        try:
            ok = cloud_upload_file(cloud_user, review_path, file_bytes)
        except CloudStorageNotReadyError as exc:
            raise ReportUploadError(str(exc)) from exc
        if not ok:
            raise ReportUploadError("Не удалось сохранить файл замечаний.")
        try:
            public_url = cloud_publish_resource(cloud_user, review_path) or ""
        except CloudStorageNotReadyError:
            public_url = ""
        upload.review_file_name = review_name
        upload.review_cloud_path = review_path
        upload.review_file_link = public_url

    from .models import ReportReviewEntry

    entry = open_entry
    saved_name = upload.review_file_name
    saved_link = upload.review_file_link
    saved_path = upload.review_cloud_path
    upload.review_file_name = ""
    upload.review_file_link = ""
    upload.review_cloud_path = ""
    upload.review_step = ""
    upload.review_phase = ""
    upload.save(update_fields=[
        "review_file_name",
        "review_file_link",
        "review_cloud_path",
        "review_step",
        "review_phase",
    ])
    if comment_count:
        entry.review_file_name = saved_name
        entry.review_file_link = saved_link
        entry.review_cloud_path = saved_path
        entry.comment_count = comment_count
        entry.remarks_notice_pending = True
        entry.save(update_fields=[
            "review_file_name",
            "review_file_link",
            "review_cloud_path",
            "comment_count",
            "remarks_notice_pending",
        ])
    else:
        entry.settled = True
        entry.review_file_name = saved_name
        entry.review_file_link = saved_link
        entry.review_cloud_path = saved_path
        entry.comment_count = comment_count
        entry.created_at = timezone.now()
        entry.remarks_notice_pending = False
        entry.save(update_fields=[
            "settled",
            "review_file_name",
            "review_file_link",
            "review_cloud_path",
            "comment_count",
            "created_at",
            "remarks_notice_pending",
        ])
        nxt = next_manual_step(review_chain_for_upload(entry.upload), entry.step)
        if nxt:
            ReportReviewEntry.objects.create(
                upload=entry.upload,
                basis_entry=entry,
                step=nxt,
                phase=REVIEW_PHASE_REVIEW,
            )
    return upload


def withdraw_pending_report_remarks(*, user, entry):
    """Снять ещё не отправленный файл замечаний и вернуть шаг к загрузке."""
    from .models import ReportReviewEntry
    from .report_review import REVIEW_PHASE_REVIEW, REVIEW_PHASE_REWORK, user_matches_review_step

    if entry.phase != REVIEW_PHASE_REVIEW or entry.settled or not entry.remarks_notice_pending:
        raise ReportUploadError("Эти замечания уже нельзя удалить.")
    upload = entry.upload
    if not user_matches_review_step(user, upload, entry.step):
        raise ReportUploadError("Недостаточно прав.")
    path = entry.review_cloud_path or ""
    if path:
        delete_stored_report_file(user, path)
    ReportReviewEntry.objects.filter(
        upload_id=entry.upload_id,
        step=entry.step,
        phase=REVIEW_PHASE_REWORK,
        pk__gt=entry.pk,
        settled=False,
    ).delete()
    entry.review_file_name = ""
    entry.review_file_link = ""
    entry.review_cloud_path = ""
    entry.comment_count = 0
    entry.remarks_notice_pending = False
    entry.save(update_fields=[
        "review_file_name",
        "review_file_link",
        "review_cloud_path",
        "comment_count",
        "remarks_notice_pending",
    ])
    return entry


def ensure_rework_after_remarks(entry):
    """Открыть «В работе после …» после отправки замечаний, если строки ещё нет."""
    from .models import ReportReviewEntry
    from .report_review import REVIEW_PHASE_REWORK

    if ReportReviewEntry.objects.filter(
        upload_id=entry.upload_id,
        step=entry.step,
        phase=REVIEW_PHASE_REWORK,
        pk__gt=entry.pk,
    ).exists():
        return None
    return ReportReviewEntry.objects.create(
        upload=entry.upload,
        step=entry.step,
        phase=REVIEW_PHASE_REWORK,
    )


def accept_report_review_without_remarks(*, user, upload):
    """Принять шаг без файла: тот же исход, что у файла без примечаний."""
    from .models import ReportReviewEntry
    from .report_review import (
        REVIEW_PHASE_REVIEW,
        latest_open_entry,
        next_manual_step,
        review_chain_for_upload,
        user_can_submit_review,
    )

    if not user_can_submit_review(user, upload):
        raise ReportUploadError("Недостаточно прав.")
    entry = latest_open_entry(upload)
    if entry is None:
        raise ReportUploadError("Нет шага, который можно принять.")
    entry.settled = True
    entry.comment_count = 0
    entry.created_at = timezone.now()
    entry.save(update_fields=["settled", "comment_count", "created_at"])
    target = entry.upload
    target.review_step = ""
    target.review_phase = ""
    target.save(update_fields=["review_step", "review_phase"])
    nxt = next_manual_step(review_chain_for_upload(target), entry.step)
    if nxt:
        ReportReviewEntry.objects.create(
            upload=target,
            basis_entry=entry,
            step=nxt,
            phase=REVIEW_PHASE_REVIEW,
        )
    return target


def validate_workspace_folder_roles(rows):
    seen = set()
    allowed = {choice for choice, _label in RegistrationWorkspaceFolder.ROLE_CHOICES}
    cleaned = []
    for row in rows:
        role = (row.get("role") or "").strip()
        if role not in allowed:
            raise ReportUploadError("Некорректное значение роли папки.")
        if role:
            if role in seen:
                label = dict(RegistrationWorkspaceFolder.ROLE_CHOICES).get(role, role)
                raise ReportUploadError(f"Роль «{label}» можно назначить только одной папке.")
            seen.add(role)
        cleaned.append(role)
    return cleaned
