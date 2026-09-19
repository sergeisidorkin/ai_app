from __future__ import annotations

import logging
import os
from itertools import groupby
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.db import IntegrityError, close_old_connections
from django.utils import timezone

from checklists_app.models import ProjectWorkspace
from core.cloud_paths import join_cloud_path
from core.cloud_storage import (
    CloudStorageNotReadyError,
    download_file as cloud_download_file,
    get_any_connected_service_user,
    is_nextcloud_primary,
    publish_resource as cloud_publish_resource,
    upload_file as cloud_upload_file,
)
from yandexdisk_app.workspace import _resolve_workspace_folder_name, _sanitize

from .models import Performer, PerformerReportUpload, RegistrationWorkspaceFolder, ReportCheckRule
from .report_macro_runner import report_acceptance_threshold

logger = logging.getLogger(__name__)


def _reconnect_after_storage_io():
    from django.db import connection

    if connection.in_atomic_block:
        return
    close_old_connections()


class ReportUploadError(Exception):
    """Controlled error shown to the user when a report cannot be uploaded."""


def plural_sections(n: int) -> str:
    mod10 = n % 10
    mod100 = n % 100
    if mod10 == 1 and mod100 != 11:
        return f"{n} раздел"
    if 2 <= mod10 <= 4 and (mod100 < 12 or mod100 > 14):
        return f"{n} раздела"
    return f"{n} разделов"


def typical_section_short(section) -> str:
    if not section:
        return ""
    code = getattr(section, "code", "") or ""
    short_name_ru = getattr(section, "short_name_ru", "") or ""
    return " ".join(part for part in (code, short_name_ru) if part).strip()


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


def format_report_version(version) -> str:
    return f"{int(version or 0):02d}"


def format_report_datetime(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")


REPORT_STATUS_IN_PROGRESS = "В работе"
REPORT_STATUS_UPLOADED = "Загружен"
REPORT_STATUS_SENT = "Отправлен"
REPORT_STATUS_CHECKED = "Проверен"
REPORT_STATUS_ACCEPTED = "Сдан"


def report_findings_meet_threshold(finding_count, threshold) -> bool:
    findings = int(finding_count or 0)
    limit = int(threshold or 0)
    if findings < 0:
        findings = 0
    if limit < 0:
        limit = 0
    return findings < limit or (limit == 0 and findings == 0)


def report_workflow_status(upload, threshold=None, check_rules=None) -> str:
    if not upload:
        return REPORT_STATUS_IN_PROGRESS
    has_file = bool(getattr(upload, "file_name", "") or getattr(upload, "cloud_path", ""))
    if not has_file:
        return REPORT_STATUS_IN_PROGRESS
    check_status = getattr(upload, "check_status", "") or ""
    if check_status == PerformerReportUpload.CheckStatus.DONE:
        if threshold is None:
            threshold = report_acceptance_threshold(upload, check_rules)
        if report_findings_meet_threshold(getattr(upload, "check_finding_count", 0), threshold):
            return REPORT_STATUS_ACCEPTED
        return REPORT_STATUS_CHECKED
    if getattr(upload, "sent_at", None):
        return REPORT_STATUS_SENT
    return REPORT_STATUS_UPLOADED


def format_report_finding_count(upload) -> str:
    if not upload or (getattr(upload, "check_status", "") or "") != PerformerReportUpload.CheckStatus.DONE:
        return "—"
    return str(int(getattr(upload, "check_finding_count", 0) or 0))


REPORT_STATUS_DOT_CLASS = {
    REPORT_STATUS_IN_PROGRESS: "report-status--idle",
    REPORT_STATUS_UPLOADED: "report-status--uploaded",
    REPORT_STATUS_SENT: "report-status--sent",
    REPORT_STATUS_CHECKED: "report-status--checked",
    REPORT_STATUS_ACCEPTED: "report-status--accepted",
}


def report_workflow_status_class(status: str) -> str:
    return REPORT_STATUS_DOT_CLASS.get(status or "", "report-status--idle")


def report_workflow_status_date(upload, status=None):
    status = status or report_workflow_status(upload)
    if not upload or status == REPORT_STATUS_IN_PROGRESS:
        return None
    if status == REPORT_STATUS_UPLOADED:
        return getattr(upload, "uploaded_at", None)
    if status == REPORT_STATUS_SENT:
        return getattr(upload, "sent_at", None)
    if status in (REPORT_STATUS_CHECKED, REPORT_STATUS_ACCEPTED):
        return getattr(upload, "checked_at", None) or getattr(upload, "sent_at", None)
    return None


def format_report_status_date(upload, status=None) -> str:
    return format_report_datetime(report_workflow_status_date(upload, status)) or "—"


def build_report_filename(
    registration,
    executor,
    *,
    section=None,
    is_all_sections=False,
    is_full_report=False,
    original_name="",
    version=0,
) -> str:
    ext = os.path.splitext(original_name or "")[1]
    short_uid = _sanitize(getattr(registration, "short_uid", "") or "")
    fio = _sanitize(short_fio_no_dots(executor))
    if is_full_report:
        scope = "весь_отчет"
    elif is_all_sections:
        scope = "все_разделы"
    else:
        scope = _sanitize(getattr(section, "code", "") or typical_section_short(section) or "раздел")
    parts = [part for part in (short_uid, fio, scope) if part]
    stem = "_".join(parts) or "отчет"
    return f"{stem}_{format_report_version(version)}{ext}"


def build_check_filename(filename: str) -> str:
    stem, ext = os.path.splitext(filename or "")
    stem = (stem or "отчет").rstrip()
    if stem.endswith("_check"):
        return f"{stem}{ext}"
    return f"{stem}_check{ext}"


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
):
    workflow_status = report_workflow_status(upload, check_rules=check_rules)
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
        version_display=version_display or "",
        workflow_status=workflow_status,
        workflow_status_class=report_workflow_status_class(workflow_status),
        status_date_display=format_report_status_date(upload, workflow_status),
        finding_count_display=format_report_finding_count(upload),
    )


def _sorted_slot_uploads(uploads):
    return sorted(list(uploads or []), key=lambda item: (item.version, item.pk or 0), reverse=True)


def _append_slot_rows(rows, *, row_id, uploads, **kwargs):
    items = _sorted_slot_uploads(uploads)
    current = items[0] if items else None
    history = items[1:]
    rows.append(
        _make_report_row(
            row_id=row_id,
            upload=current,
            is_current=True,
            has_history=bool(history),
            parent_row_id="",
            version_group=row_id,
            version_display=format_report_version(current.version) if current else "",
            **kwargs,
        )
    )
    for older in history:
        rows.append(
            _make_report_row(
                row_id=f"{row_id}-v{format_report_version(older.version)}",
                upload=older,
                is_current=False,
                has_history=False,
                parent_row_id=row_id,
                version_group=row_id,
                version_display=format_report_version(older.version),
                **kwargs,
            )
        )


def build_report_submission_rows(performers, uploads=None):
    uploads = list(uploads or [])
    by_full, by_all, by_performer = index_report_uploads(uploads)
    check_rules = list(ReportCheckRule.objects.order_by("position", "id"))
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
        first_pk = (
            Performer.objects.filter(registration_id=registration_id, asset_name=asset_name)
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


def build_report_history_row(current_upload, previous_upload):
    slot_id = report_slot_row_id(current_upload)
    performer = None if (current_upload.is_full_report or current_upload.is_all_sections) else current_upload.performer
    registration = current_upload.registration
    asset_name = current_upload.asset_name or ""
    if current_upload.is_full_report:
        performer_ids = list(
            Performer.objects.filter(
                registration_id=current_upload.registration_id,
                asset_name=asset_name,
            ).values_list("pk", flat=True)
        )
        section_label = FULL_REPORT_LABEL
        group_key = full_report_group_key(current_upload.registration_id, asset_name)
    elif current_upload.is_all_sections:
        performer_ids = list(
            Performer.objects.filter(
                registration_id=current_upload.registration_id,
                executor=current_upload.executor or "",
                asset_name=asset_name,
            ).values_list("pk", flat=True)
        )
        section_label = plural_sections(len(performer_ids))
        group_key = report_group_key(current_upload.registration_id, current_upload.executor, asset_name)
    else:
        performer_ids = [performer.pk] if performer else []
        section_label = typical_section_short(getattr(performer, "typical_section", None)) or "—"
        group_key = report_group_key(current_upload.registration_id, current_upload.executor, asset_name)
    return _make_report_row(
        row_id=f"{slot_id}-v{format_report_version(previous_upload.version)}",
        performer=performer,
        performer_ids=performer_ids,
        registration=registration,
        registration_id=current_upload.registration_id,
        executor=current_upload.executor or "",
        asset_name=asset_name,
        section_label=section_label,
        group_key=group_key,
        upload=previous_upload,
        typical_section=getattr(performer, "typical_section", None),
        is_all_sections=current_upload.is_all_sections,
        is_full_report=current_upload.is_full_report,
        section_count=len(performer_ids) or 1,
        is_current=False,
        has_history=False,
        parent_row_id=slot_id,
        version_group=slot_id,
        version_display=format_report_version(previous_upload.version),
    )


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
    dest = None
    folder_path = ""
    cloud_user = None
    disk_path = ""
    public_url = ""
    filename = ""
    next_version = 0
    upload = None
    for attempt in range(3):
        latest = slot_qs.order_by("-version", "-pk").first()
        next_version = (latest.version + 1) if latest else 0
        filename = build_report_filename(
            project,
            executor,
            section=getattr(performer, "typical_section", None),
            is_all_sections=is_all_sections,
            is_full_report=is_full_report,
            original_name=getattr(uploaded_file, "name", "") or "",
            version=next_version,
        )
        if local_folder is not None:
            dest = local_folder / filename
            try:
                dest.write_bytes(file_bytes)
            except OSError as exc:
                raise ReportUploadError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
            disk_path = encode_local_report_path(dest)
            public_url = ""
            cloud_user = None
        else:
            folder_path = resolve_reports_folder_path(project, user)
            try:
                cloud_user = _cloud_upload_user(user)
            except CloudStorageNotReadyError as exc:
                raise ReportUploadError(str(exc)) from exc
            if not cloud_user:
                raise ReportUploadError("Не найдено подключённое облачное хранилище.")

            disk_path = join_cloud_path(folder_path, filename)
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
        try:
            upload = PerformerReportUpload.objects.create(
                registration=project,
                executor=executor or "",
                asset_name=asset_name or "",
                performer=None if (is_full_report or is_all_sections) else performer,
                is_all_sections=is_all_sections,
                is_full_report=is_full_report,
                version=next_version,
                file_name=filename,
                file_link=public_url,
                cloud_path=disk_path,
                check_file_name="",
                check_file_link="",
                check_cloud_path="",
                check_status="",
                check_finding_count=0,
                check_error="",
                checked_at=None,
                uploaded_at=timezone.now(),
                uploaded_by=user if getattr(user, "is_authenticated", False) else None,
            )
            break
        except IntegrityError:
            logger.warning(
                "Report upload version conflict on attempt %s for registration=%s version=%s",
                attempt + 1,
                getattr(project, "pk", None),
                next_version,
            )
            if attempt >= 2:
                raise ReportUploadError("Не удалось сохранить новую версию файла.")
    if upload is None:
        raise ReportUploadError("Не удалось сохранить новую версию файла.")
    return upload


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
    file_bytes = read_report_stored_bytes(upload, user)
    from .report_macro_runner import apply_report_macro_checks

    processed_bytes = apply_report_macro_checks(upload, file_bytes)
    upload.refresh_from_db()
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


def send_report_upload(user, upload):
    if not (upload.file_name or upload.cloud_path):
        raise ReportUploadError("Сначала загрузите файл.")
    upload.sent_at = timezone.now()
    upload.save(update_fields=["sent_at"])
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
    check_name = build_check_filename(filename)
    if local_dest is not None:
        check_dest = local_dest.parent / check_name
        try:
            check_dest.write_bytes(processed_bytes)
        except OSError as exc:
            upload.check_status = PerformerReportUpload.CheckStatus.ERROR
            upload.check_error = "\n".join(
                part for part in (upload.check_error, f"Не удалось сохранить файл проверки: {exc}") if part
            )
            upload.save(update_fields=["check_status", "check_error"])
            return
        upload.check_file_name = check_name
        upload.check_cloud_path = encode_local_report_path(check_dest)
        upload.check_file_link = ""
        upload.save(update_fields=["check_file_name", "check_cloud_path", "check_file_link"])
        return

    check_path = join_cloud_path(folder_path, check_name)
    try:
        ok = cloud_upload_file(cloud_user, check_path, processed_bytes)
    except CloudStorageNotReadyError as exc:
        upload.check_status = PerformerReportUpload.CheckStatus.ERROR
        upload.check_error = "\n".join(
            part for part in (upload.check_error, str(exc)) if part
        )
        upload.save(update_fields=["check_status", "check_error"])
        return
    if not ok:
        upload.check_status = PerformerReportUpload.CheckStatus.ERROR
        upload.check_error = "\n".join(
            part for part in (upload.check_error, "Не удалось сохранить файл с результатами проверки.") if part
        )
        upload.save(update_fields=["check_status", "check_error"])
        return
    try:
        public_url = cloud_publish_resource(cloud_user, check_path) or ""
    except CloudStorageNotReadyError:
        public_url = ""
    upload.check_file_name = check_name
    upload.check_cloud_path = check_path
    upload.check_file_link = public_url
    upload.save(update_fields=["check_file_name", "check_cloud_path", "check_file_link"])


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
