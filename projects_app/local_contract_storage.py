"""Локальная замена облака для создания проекта договора на стенде разработчика."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings


LOCAL_CONTRACT_PATH_PREFIX = "local:"


class LocalContractFolderError(Exception):
    """Путь локальной папки нельзя использовать для создания проекта договора."""


class LocalContractCloud:
    """Пишет дерево папок договора на диск вместо Nextcloud или Яндекс.Диска."""

    def __init__(self, output_dir, root_path):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.root_path = self._normalize_cloud_path(root_path)
        self.uploaded_files = []
        self._published_counter = 0

    @staticmethod
    def _normalize_cloud_path(path):
        raw = str(path or "").strip().replace("\\", "/")
        parts = [part.strip() for part in raw.split("/") if part.strip()]
        if any(part in {".", ".."} for part in parts):
            raise ValueError("Локальный cloud path не должен содержать '.' или '..'.")
        return "/" + "/".join(parts) if parts else "/"

    def local_path(self, cloud_path):
        normalized = self._normalize_cloud_path(cloud_path)
        parts = [part for part in normalized.strip("/").split("/") if part]
        return self.output_dir.joinpath(*parts)

    def create_folder(self, _user, cloud_path):
        self.local_path(cloud_path).mkdir(parents=True, exist_ok=True)
        return True

    def list_resources(self, _user, cloud_path, *, limit=100, offset=0):
        local_path = self.local_path(cloud_path)
        if not local_path.exists():
            return []
        items = []
        start = max(int(offset or 0), 0)
        children = sorted(local_path.iterdir(), key=lambda item: item.name)
        for child in children[start:start + limit]:
            items.append({
                "name": child.name,
                "path": f"{self._normalize_cloud_path(cloud_path).rstrip('/')}/{child.name}",
            })
        return items

    def upload_file(self, _user, cloud_path, data, *, overwrite=True):
        local_path = self.local_path(cloud_path)
        if local_path.exists() and not overwrite:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        payload = data if isinstance(data, (bytes, bytearray)) else bytes(data)
        local_path.write_bytes(payload)
        self.uploaded_files.append((cloud_path, local_path))
        return True

    def publish_resource(self, _user, cloud_path):
        self._published_counter += 1
        return f"https://local.contract.test/{self._published_counter}"


def local_contract_folder_enabled() -> bool:
    return bool(getattr(settings, "CONTRACT_PROJECT_ALLOW_LOCAL_FOLDER", False))


def local_contract_folder_placeholder() -> str:
    return str(Path.home() / "Desktop")


def encode_local_contract_path(path) -> str:
    return f"{LOCAL_CONTRACT_PATH_PREFIX}{path}"


def parse_local_contract_path(stored_path: str) -> str:
    raw = stored_path or ""
    if not raw.startswith(LOCAL_CONTRACT_PATH_PREFIX):
        return ""
    return raw[len(LOCAL_CONTRACT_PATH_PREFIX):]


def is_local_contract_path(stored_path: str) -> bool:
    return bool(parse_local_contract_path(stored_path))


def _local_contract_roots():
    roots = getattr(settings, "REPORT_CHECK_LOCAL_ROOTS", ()) or ()
    if not roots:
        roots = getattr(settings, "DSH_SORT_LOCAL_ROOTS", ()) or ()
    return roots


def _local_path_is_allowed(resolved: Path) -> bool:
    for raw in _local_contract_roots():
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


def resolve_local_contract_folder(raw_path) -> Path:
    if not local_contract_folder_enabled():
        raise LocalContractFolderError("Локальная папка на этом стенде выключена.")
    text = _normalize_local_folder_text(raw_path)
    if not text:
        raise LocalContractFolderError("Укажите путь к локальной папке.")
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError as exc:
        raise LocalContractFolderError(f"Не удалось прочитать путь: {exc}") from exc
    if resolved.exists() and not resolved.is_dir():
        raise LocalContractFolderError("Укажите путь к папке, а не к файлу.")
    if not _local_path_is_allowed(resolved):
        raise LocalContractFolderError(
            "Путь вне разрешённых корней локального тестирования. "
            "Укажите каталог внутри домашней папки пользователя или папки проекта."
        )
    if not resolved.is_dir():
        raise LocalContractFolderError(f"Папка не найдена: {resolved}")
    return resolved


def local_contract_cloud_path(stored_path: str, output_dir) -> str:
    """Вернуть виртуальный путь облака, если сохранённая папка лежит внутри output_dir."""
    raw = parse_local_contract_path(stored_path)
    if not raw:
        return ""
    try:
        absolute = Path(raw).expanduser().resolve()
        relative = absolute.relative_to(Path(output_dir).expanduser().resolve())
    except (OSError, ValueError):
        return ""
    if not absolute.is_dir():
        return ""
    return "/" + "/".join(relative.parts) if relative.parts else "/"


def read_local_contract_docx(stored_folder: str, file_name: str):
    """Байты DOCX из локальной папки проекта договора, либо None."""
    if not local_contract_folder_enabled():
        return None
    raw = parse_local_contract_path(stored_folder)
    name = os.path.basename(str(file_name or "").replace("\\", "/"))
    if not raw or not name or name in {".", ".."}:
        return None
    try:
        folder = Path(raw).expanduser().resolve()
        path = (folder / name).resolve()
        path.relative_to(folder)
    except (OSError, ValueError):
        return None
    if not path.is_file() or not _local_path_is_allowed(path):
        return None
    try:
        return path, path.read_bytes()
    except OSError:
        return None
