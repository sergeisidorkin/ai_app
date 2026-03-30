"""
Создание рабочего пространства (структуры папок) на Яндекс.Диске
для проекта и его чек-листа.
"""
import logging
from typing import Optional

from django.db import transaction

from checklists_app.models import ChecklistItem, ChecklistItemFolder, ProjectWorkspace
from projects_app.models import Performer, ProjectRegistration
from yandexdisk_app.models import YandexDiskSelection
from yandexdisk_app.service import create_folder, get_resource_info, publish_resource

logger = logging.getLogger(__name__)

STANDARD_FOLDERS = [
    "00 Документы",
    "01 Командировки",
    "02 Письма",
    "03 Протоколы",
    "04 Запросы",
    "05 Данные",
    "06 Отчеты",
    "07 Комментарии",
    "08 Результат",
]

DATA_FOLDER = "05 Данные"

WORKSPACE_PROJECT_VARIABLES = [
    (
        "{project_label}",
        "Обозначение проекта в формате «Проект ID Тип Название проекта»",
    ),
]


def _sanitize(name: str) -> str:
    """Убирает символы, недопустимые в именах папок на Яндекс.Диске."""
    for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
        name = name.replace(ch, '_')
    return name.strip().rstrip('.')


def _build_project_label(project: ProjectRegistration) -> str:
    type_name = ""
    if project.type:
        type_name = getattr(project.type, "short_name", "") or str(project.type)
    return " ".join(part for part in (project.short_uid, type_name, project.name) if part).strip()


def _resolve_workspace_folder_name(name: str, project: ProjectRegistration | None = None) -> str:
    resolved = str(name or "")
    if project is not None:
        resolved = resolved.replace("{project_label}", _build_project_label(project))
    return _sanitize(" ".join(resolved.split()))


def _contains_workspace_project_variable(path: str) -> bool:
    raw = str(path or "")
    return any(variable in raw for variable, _description in WORKSPACE_PROJECT_VARIABLES)


def _sanitize_relative_path(path: str) -> str:
    parts = [
        _sanitize(" ".join(part.split()))
        for part in str(path or "").split("/")
    ]
    return "/".join(part for part in parts if part)


def _build_project_folder_name(project: ProjectRegistration) -> str:
    return _resolve_workspace_folder_name(_build_project_label(project))


def _build_section_folder_name(section) -> str:
    code = getattr(section, "code", "") or ""
    short_name = getattr(section, "short_name_ru", "") or getattr(section, "short_name", "")
    return _sanitize(" ".join(p for p in (code, short_name) if p))


def _build_item_folder_name(item: ChecklistItem) -> str:
    return _sanitize(f"{item.code}-{item.number:02d} {item.short_name}")


class WorkspaceResult:
    def __init__(self, ok: bool, message: str, workspace: Optional[ProjectWorkspace] = None):
        self.ok = ok
        self.message = message
        self.workspace = workspace


def create_project_workspace(user, project: ProjectRegistration) -> WorkspaceResult:
    """
    Создаёт полную структуру рабочего пространства на Яндекс.Диске.
    Возвращает WorkspaceResult с флагом ok и сообщением.
    """
    selection = YandexDiskSelection.objects.filter(user=user).first()
    if not selection or not selection.resource_path:
        return WorkspaceResult(False, "Не выбрана папка на Яндекс.Диске. Подключите Яндекс.Диск и выберите папку.")

    base = selection.resource_path.rstrip("/")

    year_str = str(project.year) if project.year else "Без года"
    year_path = f"{base}/{_sanitize(year_str)}"
    if not create_folder(user, year_path):
        return WorkspaceResult(False, f"Не удалось создать папку года: {year_path}")

    project_folder = _build_project_folder_name(project)
    project_path = f"{year_path}/{project_folder}"

    info = get_resource_info(user, project_path)
    existing_ws = ProjectWorkspace.objects.filter(project=project).first()
    if info and info.get("type") == "dir" and existing_ws:
        return WorkspaceResult(False, f"Рабочее пространство для проекта «{project.short_uid}» уже существует.")

    if not create_folder(user, project_path):
        return WorkspaceResult(False, f"Не удалось создать папку проекта: {project_path}")

    for folder in STANDARD_FOLDERS:
        create_folder(user, f"{project_path}/{folder}")

    data_path = f"{project_path}/{DATA_FOLDER}"

    approved_section_ids = set(
        Performer.objects
        .filter(
            registration=project,
            info_approval_status=Performer.InfoApprovalStatus.APPROVED,
            typical_section__isnull=False,
        )
        .values_list("typical_section_id", flat=True)
        .distinct()
    )

    if not approved_section_ids:
        with transaction.atomic():
            ws, _ = ProjectWorkspace.objects.update_or_create(
                project=project,
                defaults={"disk_path": project_path, "created_by": user},
            )
        return WorkspaceResult(
            True,
            "Рабочее пространство создано, но согласованных разделов не найдено — папки в «05 Данные» не созданы.",
            workspace=ws,
        )

    items = (
        ChecklistItem.objects
        .filter(project=project, section_id__in=approved_section_ids)
        .select_related("section")
        .order_by("section__position", "section__id", "position", "id")
    )

    sections_seen = set()
    folder_records = []

    for item in items:
        section = item.section
        if section.id not in sections_seen:
            section_folder = _build_section_folder_name(section)
            section_path = f"{data_path}/{section_folder}"
            create_folder(user, section_path)
            sections_seen.add(section.id)

        section_folder = _build_section_folder_name(section)
        item_folder = _build_item_folder_name(item)
        item_path = f"{data_path}/{section_folder}/{item_folder}"
        create_folder(user, item_path)

        folder_records.append(
            ChecklistItemFolder(
                checklist_item=item,
                project=project,
                disk_path=item_path,
            )
        )

    with transaction.atomic():
        ChecklistItemFolder.objects.filter(project=project).delete()
        ChecklistItemFolder.objects.bulk_create(folder_records)

        ws, _ = ProjectWorkspace.objects.update_or_create(
            project=project,
            defaults={"disk_path": project_path, "created_by": user},
        )

    return WorkspaceResult(True, "Рабочее пространство успешно создано.", workspace=ws)


REGISTRATION_STANDARD_FOLDERS = [
    "00 Документы",
    "01 Командировки",
    "02 Письма",
    "03 Протоколы",
    "04 Запросы",
    "05 Исходные данные",
    "06 Отчеты",
    "07 Комментарии",
    "08 Результат",
]


def _build_folder_tree(rows, project: ProjectRegistration | None = None):
    """
    Строит список путей из плоского списка (level, name),
    где level 2 вкладывается в ближайшую предыдущую level 1,
    level 3 — в ближайшую предыдущую level 2.
    """
    paths = []
    parent = {1: "", 2: "", 3: ""}
    for level, name in rows:
        sanitized = _resolve_workspace_folder_name(name, project)
        if level == 1:
            parent[1] = sanitized
            parent[2] = ""
            parent[3] = ""
            paths.append(sanitized)
        elif level == 2:
            parent[2] = sanitized
            parent[3] = ""
            paths.append(f"{parent[1]}/{sanitized}" if parent[1] else sanitized)
        elif level == 3:
            base = f"{parent[1]}/{parent[2]}" if parent[1] and parent[2] else (parent[2] or parent[1])
            paths.append(f"{base}/{sanitized}" if base else sanitized)
    return paths


def create_basic_project_workspace(user, project: ProjectRegistration) -> WorkspaceResult:
    """
    Создаёт базовую структуру папок на Яндекс.Диске:
    Год / Проект ID Тип Название / настраиваемые подпапки.
    Без чек-листов и записей ProjectWorkspace.
    """
    for item in create_basic_project_workspace_stream(user, project):
        pass
    return item  # last yielded value is the final WorkspaceResult


def create_basic_project_workspace_stream(user, project: ProjectRegistration):
    """
    Generator that yields progress dicts ``{"current": int, "total": int}``
    after each folder is created, and a final ``WorkspaceResult``.
    """
    from projects_app.models import RegistrationWorkspaceFolder

    selection = YandexDiskSelection.objects.filter(user=user).first()
    if not selection or not selection.resource_path:
        yield WorkspaceResult(False, "Не выбрана папка на Яндекс.Диске. Подключите Яндекс.Диск и выберите папку.")
        return

    base = selection.resource_path.rstrip("/")

    user_rows = list(
        RegistrationWorkspaceFolder.objects
        .filter(user=user)
        .order_by("position")
        .values_list("level", "name")
    )
    if not user_rows:
        user_rows = list(
            RegistrationWorkspaceFolder.objects
            .filter(user__isnull=True)
            .order_by("position")
            .values_list("level", "name")
        )
    folder_paths = (
        _build_folder_tree(user_rows, project=project)
        if user_rows
        else [_sanitize(n) for n in REGISTRATION_STANDARD_FOLDERS]
    )

    total = 2 + len(folder_paths)  # year + project + sub-folders
    current = 0

    year_str = str(project.year) if project.year else "Без года"
    year_path = f"{base}/{_sanitize(year_str)}"
    if not create_folder(user, year_path):
        yield WorkspaceResult(False, f"Не удалось создать папку года: {year_path}")
        return
    current += 1
    yield {"current": current, "total": total}

    project_folder = _build_project_folder_name(project)
    project_path = f"{year_path}/{project_folder}"

    if not create_folder(user, project_path):
        yield WorkspaceResult(False, f"Не удалось создать папку проекта: {project_path}")
        return
    current += 1
    yield {"current": current, "total": total}

    for rel_path in folder_paths:
        create_folder(user, f"{project_path}/{rel_path}")
        current += 1
        yield {"current": current, "total": total}

    ProjectWorkspace.objects.update_or_create(
        project=project,
        defaults={
            "disk_path": project_path,
            "public_url": "",
            "created_by": user,
        },
    )

    yield WorkspaceResult(True, "Рабочее пространство в облачном хранилище «Яндекс Диск» успешно создано.")


DEFAULT_SOURCE_DATA_FOLDER = "05 Исходные данные"


def _build_numbered_section_folder_name(nn: int, section) -> str:
    code = getattr(section, "code", "") or ""
    short_name_ru = getattr(section, "short_name_ru", "") or getattr(section, "short_name", "")
    return _sanitize(f"{nn:02d} {code} {short_name_ru}".strip())


def _resolve_source_data_base(user, project: ProjectRegistration):
    """Return (base_path, error_result).

    base_path is ``<disk_root>/<year>/<project_folder>/<target_folder>``.
    If something is wrong, *error_result* is a ``WorkspaceResult``.
    """
    from projects_app.models import SourceDataTargetFolder

    selection = YandexDiskSelection.objects.filter(user=user).first()
    if not selection or not selection.resource_path:
        return None, WorkspaceResult(
            False, "Не выбрана папка на Яндекс.Диске. Подключите Яндекс.Диск и выберите папку.")

    disk_root = selection.resource_path.rstrip("/")
    year_str = str(project.year) if project.year else "Без года"
    project_folder = _build_project_folder_name(project)

    target_obj = SourceDataTargetFolder.objects.filter(user=user).first()
    target_folder = _sanitize_relative_path(
        target_obj.folder_name if target_obj else DEFAULT_SOURCE_DATA_FOLDER
    )

    base_path = f"{disk_root}/{_sanitize(year_str)}/{project_folder}/{target_folder}"
    return base_path, None


def create_source_data_workspace_stream(user, project: ProjectRegistration):
    """Generator: yields ``{"current": int, "total": int}`` progress dicts
    and a final ``WorkspaceResult``."""
    from collections import OrderedDict

    from policy_app.models import TypicalSection
    from checklists_app.models import (
        ChecklistItem, SourceDataSectionFolder, SourceDataItemFolder,
        SourceDataWorkspace,
    )

    base_path, err = _resolve_source_data_base(user, project)
    if err:
        yield err
        return

    # -- approved (asset_name, section_id) pairs -------------------------
    approved_qs = (
        Performer.objects
        .filter(
            registration=project,
            info_approval_status=Performer.InfoApprovalStatus.APPROVED,
            typical_section__isnull=False,
        )
        .values_list("asset_name", "typical_section_id")
        .distinct()
    )
    approved_pairs = set(approved_qs)

    if not approved_pairs:
        yield WorkspaceResult(False, "Нет согласованных строк — папки не созданы.")
        return

    approved_section_ids = {sid for _, sid in approved_pairs}
    unique_assets = sorted({a for a, _ in approved_pairs})
    multi_asset = len(unique_assets) > 1

    # -- numbering: NN by position among ALL product sections -------------
    all_sections = list(
        TypicalSection.objects
        .filter(product=project.type)
        .order_by("position", "id")
    )
    section_nn = {}  # section.id -> ordinal
    for idx, sec in enumerate(all_sections, start=1):
        section_nn[sec.id] = idx

    # -- checklist items per section --------------------------------------
    items_by_section = OrderedDict()
    items_qs = (
        ChecklistItem.objects
        .filter(project=project, section_id__in=approved_section_ids)
        .select_related("section")
        .order_by("section__position", "section__id", "position", "id")
    )
    for item in items_qs:
        items_by_section.setdefault(item.section_id, []).append(item)

    # -- calculate total -------------------------------------------------
    single_asset_name = unique_assets[0] if not multi_asset else ""

    total = 0
    if multi_asset:
        total += len(unique_assets)
    for asset in (unique_assets if multi_asset else [single_asset_name]):
        for sec in all_sections:
            if sec.id not in approved_section_ids:
                continue
            if multi_asset and (asset, sec.id) not in approved_pairs:
                continue
            total += 1  # section folder
            total += len(items_by_section.get(sec.id, []))  # item folders
    current = 0

    section_upserts = []  # (lookup_kwargs, defaults) tuples
    item_upserts = []     # (lookup_kwargs, defaults) tuples

    # -- create folders ---------------------------------------------------
    for asset in (unique_assets if multi_asset else [single_asset_name]):
        if multi_asset:
            asset_path = f"{base_path}/{_sanitize(asset)}"
            if not create_folder(user, asset_path):
                yield WorkspaceResult(False, f"Не удалось создать папку актива: {asset}")
                return
            current += 1
            yield {"current": current, "total": total}
        else:
            asset_path = base_path

        for section in all_sections:
            if section.id not in approved_section_ids:
                continue
            if multi_asset and (asset, section.id) not in approved_pairs:
                continue

            nn = section_nn[section.id]
            section_folder = _build_numbered_section_folder_name(nn, section)
            section_disk_path = f"{asset_path}/{section_folder}"

            if not create_folder(user, section_disk_path):
                yield WorkspaceResult(False, f"Не удалось создать папку раздела: {section_folder}")
                return

            section_public_url = publish_resource(user, section_disk_path)
            section_upserts.append((
                {"project": project, "section": section, "asset_name": asset},
                {"disk_path": section_disk_path, "public_url": section_public_url},
            ))
            current += 1
            yield {"current": current, "total": total}

            for item in items_by_section.get(section.id, []):
                item_folder = _build_item_folder_name(item)
                item_disk_path = f"{section_disk_path}/{item_folder}"

                if not create_folder(user, item_disk_path):
                    yield WorkspaceResult(
                        False, f"Не удалось создать папку запроса: {item_folder}")
                    return

                item_public_url = publish_resource(user, item_disk_path)
                item_upserts.append((
                    {"project": project, "checklist_item": item, "asset_name": asset},
                    {"disk_path": item_disk_path, "public_url": item_public_url},
                ))
                current += 1
                yield {"current": current, "total": total}

    # -- persist to DB (upsert: preserve file_count / last_upload_at) -----
    with transaction.atomic():
        for lookup, defaults in section_upserts:
            SourceDataSectionFolder.objects.update_or_create(
                **lookup, defaults=defaults,
            )
        for lookup, defaults in item_upserts:
            SourceDataItemFolder.objects.update_or_create(
                **lookup, defaults=defaults,
            )
        SourceDataWorkspace.objects.update_or_create(
            project=project,
            defaults={"disk_path": base_path, "created_by": user},
        )

    yield WorkspaceResult(True, "Пространство исходных данных успешно создано.")
