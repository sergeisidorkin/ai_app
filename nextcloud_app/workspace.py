from __future__ import annotations

from checklists_app.models import ProjectWorkspace
from core.cloud_storage import get_nextcloud_root_path, get_primary_cloud_storage_label
from users_app.models import Employee
from yandexdisk_app.workspace import (
    REGISTRATION_STANDARD_FOLDERS,
    WorkspaceResult,
    _build_folder_tree,
    _build_project_folder_name,
    _sanitize,
)

from .api import NextcloudApiClient, NextcloudApiError
from .models import NextcloudUserLink
from .provisioning import ensure_nextcloud_account


def create_basic_project_workspace_stream(
    user,
    project,
    *,
    client: NextcloudApiClient | None = None,
):
    from projects_app.models import RegistrationWorkspaceFolder

    client = client or NextcloudApiClient()
    if not client.is_configured:
        yield WorkspaceResult(False, "Nextcloud не настроен для создания рабочих пространств.")
        return

    base_root = get_nextcloud_root_path()
    if not base_root:
        yield WorkspaceResult(False, "Не задан корневой каталог Nextcloud в разделе «Подключения».")
        return
    base = "/" if base_root == "/" else base_root.rstrip("/")

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
        else [_sanitize(name) for name in REGISTRATION_STANDARD_FOLDERS]
    )

    total = 3 + len(folder_paths)
    current = 0
    owner_user_id = client.username

    try:
        manager_link = _resolve_project_manager_nextcloud_link(project, client=client)
        if manager_link is None:
            yield WorkspaceResult(False, "Не удалось определить Nextcloud-пользователя руководителя проекта.")
            return

        year_str = str(project.year) if project.year else "Без года"
        year_path = client.ensure_folder(owner_user_id, _join_path(base, _sanitize(year_str)))
        current += 1
        yield {"current": current, "total": total}

        project_folder = _build_project_folder_name(project)
        project_path = client.ensure_folder(owner_user_id, _join_path(year_path, project_folder))
        current += 1
        yield {"current": current, "total": total}

        for rel_path in folder_paths:
            client.ensure_folder(owner_user_id, _join_path(project_path, rel_path))
            current += 1
            yield {"current": current, "total": total}

        client.ensure_user_share(
            owner_user_id,
            project_path,
            manager_link.nextcloud_user_id,
            permissions=NextcloudApiClient.EDITOR_PERMISSIONS,
        )
        current += 1
        yield {"current": current, "total": total}
    except NextcloudApiError as exc:
        yield WorkspaceResult(False, str(exc))
        return

    ProjectWorkspace.objects.update_or_create(
        project=project,
        defaults={
            "disk_path": project_path,
            "public_url": client.build_files_url(project_path),
            "created_by": user,
        },
    )

    storage_label = get_primary_cloud_storage_label()
    yield WorkspaceResult(True, f"Рабочее пространство в облачном хранилище «{storage_label}» успешно создано.")


def _resolve_project_manager_nextcloud_link(
    project,
    *,
    client: NextcloudApiClient,
) -> NextcloudUserLink | None:
    manager_name = (project.project_manager or "").strip()
    if not manager_name:
        return None

    match = None
    for employee in (
        Employee.objects
        .select_related("user")
        .filter(user__is_active=True, user__is_staff=True)
        .order_by("user__last_name", "user__first_name", "patronymic", "id")
    ):
        if _employee_full_name(employee) == manager_name:
            match = employee
            break
    if match is None:
        return None

    existing_link = NextcloudUserLink.objects.filter(user=match.user).first()
    if existing_link and existing_link.nextcloud_user_id:
        client.enable_user(existing_link.nextcloud_user_id)
        client.set_user_email(existing_link.nextcloud_user_id, (match.user.email or "").strip())
        client.set_user_display_name(existing_link.nextcloud_user_id, _employee_full_name(match))
        return existing_link

    link = ensure_nextcloud_account(match.user, client=client)
    if link and link.nextcloud_user_id:
        return link
    return None


def _employee_full_name(employee: Employee) -> str:
    parts = [
        (employee.user.last_name or "").strip(),
        (employee.user.first_name or "").strip(),
        (employee.patronymic or "").strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _join_path(base: str, child: str) -> str:
    clean_base = "/" if base == "/" else str(base or "").rstrip("/")
    clean_child = str(child or "").lstrip("/")
    if not clean_child:
        return clean_base or "/"
    if clean_base in {"", "/"}:
        return "/" + clean_child
    return f"{clean_base}/{clean_child}"
