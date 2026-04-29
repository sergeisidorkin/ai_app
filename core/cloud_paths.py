from __future__ import annotations


PROPOSALS_SECTION_FOLDER = "01 ТКП"
CONTRACTS_SECTION_FOLDER = "02 Договоры"
PROJECTS_SECTION_FOLDER = "03 Проекты"
CONTRACTS_PERFORMERS_FOLDER = "02 Исполнители"
LEGACY_PROPOSALS_SECTION_FOLDER = "ТКП"
LEGACY_PROJECTS_SECTION_FOLDER = "02 Проекты"


def normalize_cloud_path(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def join_cloud_path(base: str, *children: str) -> str:
    current = normalize_cloud_path(base)
    for child in children:
        child_parts = [part.strip() for part in str(child or "").replace("\\", "/").split("/") if part.strip()]
        for part in child_parts:
            current = f"{current.rstrip('/')}/{part}" if current != "/" else f"/{part}"
    return current


def cloud_year_folder(year) -> str:
    return str(year) if year else "Без года"


def parent_cloud_path(path: str) -> str:
    normalized = normalize_cloud_path(path)
    if normalized == "/":
        return "/"
    parent = normalized.rsplit("/", 1)[0]
    return parent or "/"


def replace_cloud_path_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
    normalized_path = normalize_cloud_path(path)
    normalized_old = normalize_cloud_path(old_prefix)
    normalized_new = normalize_cloud_path(new_prefix)
    if normalized_path == normalized_old:
        return normalized_new
    if normalized_path.startswith(f"{normalized_old}/"):
        return f"{normalized_new}{normalized_path[len(normalized_old):]}"
    return normalized_path
