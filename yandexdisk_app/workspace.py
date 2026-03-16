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
from yandexdisk_app.service import create_folder, get_resource_info

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


def _sanitize(name: str) -> str:
    """Убирает символы, недопустимые в именах папок на Яндекс.Диске."""
    for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
        name = name.replace(ch, '_')
    return name.strip().rstrip('.')


def _build_project_folder_name(project: ProjectRegistration) -> str:
    type_name = ""
    if project.type:
        type_name = getattr(project.type, "short_name", "") or str(project.type)
    parts = [project.short_uid, type_name, project.name]
    return _sanitize(" ".join(p for p in parts if p))


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


def _build_folder_tree(rows):
    """
    Строит список путей из плоского списка (level, name),
    где level 2 вкладывается в ближайшую предыдущую level 1,
    level 3 — в ближайшую предыдущую level 2.
    """
    paths = []
    parent = {1: "", 2: "", 3: ""}
    for level, name in rows:
        sanitized = _sanitize(name)
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

    db_rows = list(
        RegistrationWorkspaceFolder.objects
        .order_by("position")
        .values_list("level", "name")
    )
    folder_paths = _build_folder_tree(db_rows) if db_rows else [_sanitize(n) for n in REGISTRATION_STANDARD_FOLDERS]

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

    yield WorkspaceResult(True, "Рабочее пространство успешно создано.")
