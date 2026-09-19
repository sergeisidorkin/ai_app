from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings
from nextcloud_app.services import build_nextcloud_overview

from .models import CloudStorageSettings


class CloudStorageNotReadyError(RuntimeError):
    """Raised when the selected cloud backend is not migrated yet."""


@dataclass(frozen=True)
class CloudStorageBackend:
    code: str
    label: str


def get_cloud_storage_settings() -> CloudStorageSettings:
    return CloudStorageSettings.get_solo()


def get_primary_cloud_storage() -> str:
    return get_cloud_storage_settings().primary_storage


def get_primary_cloud_storage_label() -> str:
    return get_cloud_storage_settings().get_primary_storage_display()


def set_primary_cloud_storage(value: str) -> CloudStorageSettings:
    allowed = {choice for choice, _label in CloudStorageSettings.PrimaryStorage.choices}
    if value not in allowed:
        raise ValueError("Некорректное значение основного облачного хранилища.")

    settings_obj = get_cloud_storage_settings()
    settings_obj.primary_storage = value
    settings_obj.save(update_fields=["primary_storage", "updated_at"])
    return settings_obj


def normalize_nextcloud_root_path(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""

    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Корневой каталог Nextcloud не должен содержать '.' или '..'.")

    if not parts:
        return "/"

    return "/" + "/".join(parts)


def validate_nextcloud_root_path(path: str) -> str:
    normalized = normalize_nextcloud_root_path(path)
    if not normalized:
        return ""
    if len(normalized) > 1024:
        raise ValueError("Корневой каталог Nextcloud слишком длинный.")
    return normalized


def get_nextcloud_root_path() -> str:
    return str(get_cloud_storage_settings().nextcloud_root_path or "")


def is_nextcloud_root_configured() -> bool:
    return bool(get_nextcloud_root_path())


def set_nextcloud_root_path(path: str) -> CloudStorageSettings:
    settings_obj = get_cloud_storage_settings()
    settings_obj.nextcloud_root_path = validate_nextcloud_root_path(path)
    settings_obj.save(update_fields=["nextcloud_root_path", "updated_at"])
    return settings_obj


def is_nextcloud_available() -> bool:
    return bool((getattr(settings, "NEXTCLOUD_BASE_URL", "") or "").strip())


def is_nextcloud_primary() -> bool:
    return get_primary_cloud_storage() == CloudStorageSettings.PrimaryStorage.NEXTCLOUD


def is_yandex_disk_primary() -> bool:
    return get_primary_cloud_storage() == CloudStorageSettings.PrimaryStorage.YANDEX_DISK


def get_primary_cloud_backend() -> CloudStorageBackend:
    settings_obj = get_cloud_storage_settings()
    return CloudStorageBackend(
        code=settings_obj.primary_storage,
        label=settings_obj.get_primary_storage_display(),
    )


def get_nextcloud_connection_status() -> CloudStorageBackend:
    if is_nextcloud_available() and is_nextcloud_root_configured():
        return CloudStorageBackend(code="connected", label="Подключено")
    if is_nextcloud_available():
        return CloudStorageBackend(code="pending", label="Не подключено")
    return CloudStorageBackend(code="unavailable", label="Недоступно")


def ensure_backend_supported(action_name: str):
    if is_yandex_disk_primary():
        return

    raise CloudStorageNotReadyError(
        "Основное облачное хранилище сейчас переключено на Nextcloud. "
        f"Сценарий «{action_name}» ещё не переведён на Nextcloud."
    )


def create_project_workspace(user, project):
    ensure_backend_supported("создание рабочего пространства проекта")
    from yandexdisk_app.workspace import create_project_workspace as create_yadisk_project_workspace

    return create_yadisk_project_workspace(user, project)


def create_basic_project_workspace_stream(user, project):
    if is_nextcloud_primary():
        from nextcloud_app.workspace import create_basic_project_workspace_stream as create_nextcloud_workspace_stream

        return create_nextcloud_workspace_stream(user, project)

    from yandexdisk_app.workspace import create_basic_project_workspace_stream as create_yadisk_workspace_stream

    return create_yadisk_workspace_stream(user, project)


def create_source_data_workspace_stream(user, project):
    if is_nextcloud_primary():
        from nextcloud_app.workspace import create_source_data_workspace_stream as create_nextcloud_source_stream

        return create_nextcloud_source_stream(user, project)

    from yandexdisk_app.workspace import create_source_data_workspace_stream as create_yadisk_source_stream

    return create_yadisk_source_stream(user, project)


def get_workspace_result_class():
    from yandexdisk_app.workspace import WorkspaceResult

    return WorkspaceResult


def build_workspace_folder_tree(rows, project=None):
    from yandexdisk_app.workspace import _build_folder_tree

    return _build_folder_tree(rows, project=project)


def contains_workspace_project_variable(path: str) -> bool:
    from yandexdisk_app.workspace import _contains_workspace_project_variable

    return _contains_workspace_project_variable(path)


def get_registration_standard_folders():
    from yandexdisk_app.workspace import REGISTRATION_STANDARD_FOLDERS

    return tuple(REGISTRATION_STANDARD_FOLDERS)


def build_project_folder_name(project):
    from yandexdisk_app.workspace import _build_project_folder_name

    return _build_project_folder_name(project)


def sanitize_folder_name(name: str) -> str:
    from yandexdisk_app.workspace import _sanitize

    return _sanitize(name)


def get_selected_root_path(user) -> str:
    if is_nextcloud_primary():
        root_path = get_nextcloud_root_path()
        if root_path:
            return root_path
        raise CloudStorageNotReadyError("Для Nextcloud ещё не задан корпоративный root каталог.")

    from yandexdisk_app.models import YandexDiskSelection

    selection = YandexDiskSelection.objects.filter(user=user).first()
    return (selection.resource_path or "").rstrip("/") if selection else ""


def list_folder_resources(user, path: str, *, limit: int = 100, offset: int = 0):
    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CloudStorageNotReadyError("Nextcloud не настроен для просмотра содержимого облачного хранилища.")
        try:
            return client.list_resources(client.username, path, limit=limit, offset=offset)
        except NextcloudApiError as exc:
            raise CloudStorageNotReadyError(
                f"Не удалось прочитать каталог Nextcloud: {path}"
            ) from exc

    from yandexdisk_app.service import list_resources

    try:
        return list_resources(
            user,
            path,
            limit=limit,
            offset=offset,
            raise_errors=True,
        )
    except Exception as exc:
        raise CloudStorageNotReadyError(
            f"Не удалось прочитать каталог Яндекс.Диска: {path}"
        ) from exc


def create_folder(user, path: str) -> bool:
    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CloudStorageNotReadyError("Nextcloud не настроен для создания папок в облачном хранилище.")
        try:
            client.ensure_folder(client.username, path)
            return True
        except NextcloudApiError:
            return False

    from yandexdisk_app.service import create_folder as yadisk_create_folder

    return yadisk_create_folder(user, path)


def upload_file(user, path: str, data: bytes, *, overwrite: bool = True) -> bool:
    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CloudStorageNotReadyError("Nextcloud не настроен для загрузки файлов в облачное хранилище.")
        try:
            return client.upload_file(client.username, path, data, overwrite=overwrite)
        except NextcloudApiError:
            return False

    from yandexdisk_app.service import upload_file as yadisk_upload_file

    return yadisk_upload_file(user, path, data, overwrite=overwrite)


def download_file(user, path: str):
    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CloudStorageNotReadyError("Nextcloud не настроен для скачивания файлов из облачного хранилища.")
        try:
            return client.download_file(client.username, path)
        except NextcloudApiError:
            return (None, b"")

    from yandexdisk_app.service import download_file as yadisk_download_file

    return yadisk_download_file(user, path)


def publish_resource(user, path: str) -> str:
    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CloudStorageNotReadyError("Nextcloud не настроен для публикации файлов в облачном хранилище.")
        try:
            return client.ensure_public_link_share(client.username, path)
        except NextcloudApiError:
            return ""

    from yandexdisk_app.service import publish_resource as yadisk_publish_resource

    return yadisk_publish_resource(user, path)


def get_any_connected_service_user():
    ensure_backend_supported("поиск подключённого облачного хранилища")

    from yandexdisk_app.models import YandexDiskAccount

    account = YandexDiskAccount.objects.filter(access_token__gt="").select_related("user").first()
    return account.user if account else None


def build_folder_url(path: str) -> str:
    if not path:
        return ""

    if is_nextcloud_primary():
        from nextcloud_app.api import NextcloudApiClient

        client = NextcloudApiClient()
        if client.base_url:
            return client.build_files_url(path)
        return ""

    clean = str(path).removeprefix("disk:")
    return "https://disk.yandex.ru/client/disk" + quote(clean)


def resolve_source_data_folder_path(user, project) -> str:
    """Return the source-data folder path for a project without storing per-user links.

    Prefer the already created source-data workspace. Otherwise use the project
    folder on disk plus the target folder from settings (Projects → Information
    request → Create source data space). If that project folder is not stored
    yet, rebuild the same path used when creating the workspace.
    """
    from checklists_app.models import ProjectWorkspace, SourceDataWorkspace
    from core.cloud_paths import join_cloud_path
    from projects_app.models import SourceDataTargetFolder
    from yandexdisk_app.workspace import DEFAULT_SOURCE_DATA_FOLDER, _sanitize_relative_path

    workspace = (
        SourceDataWorkspace.objects.filter(project=project)
        .only("disk_path")
        .first()
    )
    disk_path = (getattr(workspace, "disk_path", "") or "").strip()
    if disk_path:
        return disk_path

    target_obj = SourceDataTargetFolder.objects.filter(user=user).first()
    target_folder = _sanitize_relative_path(
        target_obj.folder_name if target_obj else DEFAULT_SOURCE_DATA_FOLDER
    )

    project_ws = (
        ProjectWorkspace.objects.filter(project=project)
        .only("disk_path")
        .first()
    )
    project_path = (getattr(project_ws, "disk_path", "") or "").strip()
    if project_path:
        return join_cloud_path(project_path, target_folder)

    if is_nextcloud_primary():
        from nextcloud_app.workspace import _resolve_nextcloud_source_data_base

        path, _err = _resolve_nextcloud_source_data_base(user, project)
        return str(path or "").strip()

    from yandexdisk_app.workspace import _resolve_source_data_base

    path, _err = _resolve_source_data_base(user, project)
    return str(path or "").strip()


def get_project_source_data_folder_url(user, project) -> str:
    owner_path = resolve_source_data_folder_path(user, project)
    if not owner_path:
        return ""

    if is_nextcloud_primary():
        from checklists_app.models import ProjectWorkspace
        from nextcloud_app.workspace import build_viewer_files_url_for_user

        project_ws = (
            ProjectWorkspace.objects.filter(project=project)
            .only("disk_path")
            .first()
        )
        return build_viewer_files_url_for_user(
            user,
            owner_path,
            project_share_path=(getattr(project_ws, "disk_path", "") or "").strip(),
        )

    return build_folder_url(owner_path)


def get_user_cloud_launch_url(user) -> str:
    if is_nextcloud_primary():
        overview = build_nextcloud_overview(user)
        return str(overview.get("nextcloud_launch_url") or "")

    from yandexdisk_app.models import YandexDiskAccount, YandexDiskSelection

    selection = YandexDiskSelection.objects.filter(user=user).first()
    if selection and selection.resource_path:
        path = selection.resource_path.strip("/")
        return f"https://disk.yandex.ru/client/disk/{path}" if path else "https://disk.yandex.ru/client/disk"
    if YandexDiskAccount.objects.filter(user=user).exists():
        return "https://disk.yandex.ru/client/disk"
    return ""
