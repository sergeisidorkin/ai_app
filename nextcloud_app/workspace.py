from __future__ import annotations

from django.db import transaction

from checklists_app.models import ProjectWorkspace
from core.cloud_storage import get_nextcloud_root_path, get_primary_cloud_storage_label
from users_app.models import Employee
from yandexdisk_app.workspace import (
    DEFAULT_SOURCE_DATA_FOLDER,
    REGISTRATION_STANDARD_FOLDERS,
    WorkspaceResult,
    _build_item_folder_name,
    _build_numbered_section_folder_name,
    _build_folder_tree,
    _build_project_folder_name,
    _sanitize,
    _sanitize_relative_path,
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


def create_source_data_workspace_stream(
    user,
    project,
    *,
    client: NextcloudApiClient | None = None,
):
    from collections import OrderedDict

    from checklists_app.models import (
        ChecklistItem,
        SourceDataItemFolder,
        SourceDataSectionFolder,
        SourceDataWorkspace,
    )
    from policy_app.models import TypicalSection
    from projects_app.models import Performer

    client = client or NextcloudApiClient()
    if not client.is_configured:
        yield WorkspaceResult(False, "Nextcloud не настроен для создания пространства исходных данных.")
        return

    base_path, err = _resolve_nextcloud_source_data_base(user, project)
    if err:
        yield err
        return

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
    unique_assets = sorted({asset for asset, _ in approved_pairs})
    multi_asset = len(unique_assets) > 1

    all_sections = list(
        TypicalSection.objects
        .filter(product=project.type)
        .order_by("position", "id")
    )
    section_nn = {sec.id: idx for idx, sec in enumerate(all_sections, start=1)}

    items_by_section = OrderedDict()
    items_qs = (
        ChecklistItem.objects
        .filter(project=project, section_id__in=approved_section_ids)
        .select_related("section")
        .order_by("section__position", "section__id", "position", "id")
    )
    for item in items_qs:
        items_by_section.setdefault(item.section_id, []).append(item)

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
            total += 1
            total += len(items_by_section.get(sec.id, []))
    current = 0
    owner_user_id = client.username

    section_upserts = []
    item_upserts = []

    try:
        for asset in (unique_assets if multi_asset else [single_asset_name]):
            if multi_asset:
                asset_path = client.ensure_folder(owner_user_id, _join_path(base_path, _sanitize(asset)))
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
                section_disk_path = client.ensure_folder(owner_user_id, _join_path(asset_path, section_folder))
                section_public_url = client.ensure_public_link_share(owner_user_id, section_disk_path)
                section_upserts.append(
                    (
                        {"project": project, "section": section, "asset_name": asset},
                        {"disk_path": section_disk_path, "public_url": section_public_url},
                    )
                )
                current += 1
                yield {"current": current, "total": total}

                for item in items_by_section.get(section.id, []):
                    item_folder = _build_item_folder_name(item)
                    item_disk_path = client.ensure_folder(owner_user_id, _join_path(section_disk_path, item_folder))
                    item_public_url = client.ensure_public_link_share(owner_user_id, item_disk_path)
                    item_upserts.append(
                        (
                            {"project": project, "checklist_item": item, "asset_name": asset},
                            {"disk_path": item_disk_path, "public_url": item_public_url},
                        )
                    )
                    current += 1
                    yield {"current": current, "total": total}
    except NextcloudApiError as exc:
        yield WorkspaceResult(False, str(exc))
        return

    with transaction.atomic():
        for lookup, defaults in section_upserts:
            SourceDataSectionFolder.objects.update_or_create(**lookup, defaults=defaults)
        for lookup, defaults in item_upserts:
            SourceDataItemFolder.objects.update_or_create(**lookup, defaults=defaults)
        SourceDataWorkspace.objects.update_or_create(
            project=project,
            defaults={"disk_path": base_path, "created_by": user},
        )

    storage_label = get_primary_cloud_storage_label()
    yield WorkspaceResult(True, f"Пространство исходных данных в облачном хранилище «{storage_label}» успешно создано.")


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


def _resolve_nextcloud_source_data_base(user, project):
    from projects_app.models import SourceDataTargetFolder

    base_root = get_nextcloud_root_path()
    if not base_root:
        return None, WorkspaceResult(False, "Не задан корневой каталог Nextcloud в разделе «Подключения».")

    base = "/" if base_root == "/" else base_root.rstrip("/")
    year_str = str(project.year) if project.year else "Без года"
    project_folder = _build_project_folder_name(project)

    target_obj = SourceDataTargetFolder.objects.filter(user=user).first()
    target_folder = _sanitize_relative_path(
        target_obj.folder_name if target_obj else DEFAULT_SOURCE_DATA_FOLDER
    )
    return _join_path(_join_path(_join_path(base, _sanitize(year_str)), project_folder), target_folder), None


def _join_path(base: str, child: str) -> str:
    clean_base = "/" if base == "/" else str(base or "").rstrip("/")
    clean_child = str(child or "").lstrip("/")
    if not clean_child:
        return clean_base or "/"
    if clean_base in {"", "/"}:
        return "/" + clean_child
    return f"{clean_base}/{clean_child}"
