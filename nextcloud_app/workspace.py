from __future__ import annotations

import logging
import time

from django.db import transaction

from checklists_app.models import ProjectWorkspace
from core.cloud_paths import (
    PROJECTS_SECTION_FOLDER,
    PROPOSALS_SECTION_FOLDER,
    cloud_year_folder,
)
from core.cloud_storage import get_nextcloud_root_path, get_primary_cloud_storage_label
from policy_app.models import DEPARTMENT_HEAD_GROUP, DIRECTION_DIRECTOR_GROUP, PROJECTS_HEAD_GROUP
from users_app.models import Employee
from yandexdisk_app.workspace import (
    DEFAULT_SOURCE_DATA_FOLDER,
    REGISTRATION_STANDARD_FOLDERS,
    WorkspaceResult,
    _build_item_folder_name,
    _build_numbered_section_folder_name,
    _build_folder_tree,
    _build_project_folder_name,
    _build_project_workspace_path,
    _sanitize,
    _sanitize_relative_path,
)

from .api import NextcloudApiClient, NextcloudApiError
from .models import NextcloudUserLink
from .provisioning import _should_manage_in_nextcloud, ensure_nextcloud_account

logger = logging.getLogger(__name__)

_FOLDER_MAX_RETRIES = 5
_FOLDER_RETRY_WAIT_BASE = 3.0
_FOLDER_RETRY_WAIT_MAX = 10.0

_LINK_MAX_RETRIES = 30
_LINK_RETRY_WAIT_BASE = 30.0
_LINK_RETRY_WAIT_MAX = 35.0

_HEARTBEAT_INTERVAL = 2.0
_PROJECT_MANAGER_ROLES = (PROJECTS_HEAD_GROUP, DIRECTION_DIRECTOR_GROUP)
_UNSET_EXPERTISE_DIRECTION_LABEL = "не установлено"


def _heartbeat_sleep(seconds, progress, total):
    """Sleep in small chunks, yielding heartbeat progress events to keep
    the streaming HTTP connection alive."""
    waited = 0.0
    while waited < seconds:
        chunk = min(_HEARTBEAT_INTERVAL, seconds - waited)
        time.sleep(chunk)
        waited += chunk
        yield {"current": progress, "total": total}


def _ensure_folder_with_heartbeat(client, owner_user_id, path, progress, total):
    """Create a folder with generator-level retries and heartbeat events.

    Uses short backoff (3-10s) because folder creation is not subject to
    Nextcloud's share rate-limit — transient errors resolve quickly.
    """
    for attempt in range(_FOLDER_MAX_RETRIES):
        try:
            return client.ensure_folder(owner_user_id, path)
        except NextcloudApiError as exc:
            if attempt == _FOLDER_MAX_RETRIES - 1:
                raise
            wait = min(_FOLDER_RETRY_WAIT_BASE + attempt * 2.0, _FOLDER_RETRY_WAIT_MAX)
            logger.warning(
                "Folder creation failed for %s (attempt %d/%d), "
                "retrying in %.0fs: %s",
                path, attempt + 1, _FOLDER_MAX_RETRIES, wait, exc,
            )
            yield from _heartbeat_sleep(wait, progress, total)
    raise NextcloudApiError(f"Failed to create folder after {_FOLDER_MAX_RETRIES} attempts: {path}")


def _ensure_link_with_heartbeat(client, owner_user_id, path, progress, total):
    """Create a public link share with generator-level retries and heartbeat events.

    Uses ``_quick=True`` so that the internal HTTP layer fails fast on 429;
    the longer wait (with heartbeats) happens here in the generator, keeping
    the streaming connection alive.

    Long backoff (30-35s) accounts for Nextcloud's share rate-limit window.
    """
    for attempt in range(_LINK_MAX_RETRIES):
        try:
            return client.ensure_public_link_share(owner_user_id, path, _quick=True)
        except NextcloudApiError as exc:
            if attempt == _LINK_MAX_RETRIES - 1:
                raise
            wait = min(_LINK_RETRY_WAIT_BASE + attempt * 2.0, _LINK_RETRY_WAIT_MAX)
            logger.warning(
                "Public link creation failed for %s (attempt %d/%d), "
                "retrying in %.0fs: %s",
                path, attempt + 1, _LINK_MAX_RETRIES, wait, exc,
            )
            yield from _heartbeat_sleep(wait, progress, total)
    raise NextcloudApiError(f"Failed to create public link after {_LINK_MAX_RETRIES} attempts: {path}")


def create_proposal_workspace(
    user,
    proposal,
    *,
    client: NextcloudApiClient | None = None,
    return_share_target: bool = False,
) -> str | tuple[str, str]:
    client = client or NextcloudApiClient()
    if not client.is_configured:
        raise NextcloudApiError("Nextcloud не настроен для создания рабочей папки ТКП.")

    base_root = get_nextcloud_root_path()
    if not base_root:
        raise NextcloudApiError("Не задан корневой каталог Nextcloud в разделе «Подключения».")
    if not proposal.year:
        raise NextcloudApiError("Невозможно создать рабочую папку ТКП в Nextcloud: не заполнено поле «Год».")

    owner_user_id = client.username

    proposal_path = build_proposal_workspace_path(proposal, base_root=base_root)
    base = "/" if base_root == "/" else base_root.rstrip("/")
    tkp_root_path = client.ensure_folder(owner_user_id, _join_path(base, _sanitize(PROPOSALS_SECTION_FOLDER)))
    year_path = client.ensure_folder(owner_user_id, _join_path(tkp_root_path, _sanitize(str(proposal.year))))
    proposal_path = client.ensure_folder(owner_user_id, proposal_path)

    user_link = ensure_nextcloud_account(user, client=client)
    if not user_link or not user_link.nextcloud_user_id:
        raise NextcloudApiError("Не удалось определить Nextcloud-пользователя автора записи ТКП.")

    share = client.ensure_user_share(
        owner_user_id,
        proposal_path,
        user_link.nextcloud_user_id,
        permissions=NextcloudApiClient.EDITOR_PERMISSIONS,
    )
    share_target_path = str(getattr(share, "target_path", "") or "").strip()
    if return_share_target:
        return proposal_path, share_target_path
    return proposal_path


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

    confirmed_performer_users = _confirmed_project_performer_users(project)
    total = 4 + len(folder_paths) + len(confirmed_performer_users)
    current = 0
    owner_user_id = client.username

    try:
        manager_link = _resolve_project_manager_nextcloud_link(project, client=client)
        if manager_link is None:
            yield WorkspaceResult(False, "Не удалось определить Nextcloud-пользователя руководителя проекта.")
            return
        projects_root_path = yield from _ensure_folder_with_heartbeat(
            client, owner_user_id, _join_path(base, _sanitize(PROJECTS_SECTION_FOLDER)), current, total,
        )
        current += 1
        yield {"current": current, "total": total}

        year_str = cloud_year_folder(project.year)
        year_path = yield from _ensure_folder_with_heartbeat(
            client, owner_user_id, _join_path(projects_root_path, _sanitize(year_str)), current, total,
        )
        current += 1
        yield {"current": current, "total": total}

        project_folder = _build_project_folder_name(project)
        project_path = yield from _ensure_folder_with_heartbeat(
            client, owner_user_id, _join_path(year_path, project_folder), current, total,
        )
        current += 1
        yield {"current": current, "total": total}

        for rel_path in folder_paths:
            yield from _ensure_folder_with_heartbeat(
                client, owner_user_id, _join_path(project_path, rel_path), current, total,
            )
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

        for performer_user in confirmed_performer_users:
            performer_link = _ensure_nextcloud_link_for_user(performer_user, client=client)
            if not performer_link or not performer_link.nextcloud_user_id:
                raise NextcloudApiError("Не удалось определить Nextcloud-пользователя исполнителя проекта.")
            client.ensure_user_share(
                owner_user_id,
                project_path,
                performer_link.nextcloud_user_id,
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

    product_rank_map = getattr(project, "product_rank_map", {})
    product_ids = list(product_rank_map.keys())
    if not product_ids and getattr(project, "type_id", None):
        product_ids = [project.type_id]
        product_rank_map = {project.type_id: 1}
    all_sections = list(
        TypicalSection.objects
        .filter(product_id__in=product_ids)
        .order_by("position", "id")
    ) if product_ids else []
    all_sections.sort(
        key=lambda section: (
            product_rank_map.get(section.product_id, 999999),
            section.position,
            section.id,
        )
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
    existing_section_urls = {
        (row.section_id, row.asset_name): row.public_url
        for row in SourceDataSectionFolder.objects.filter(project=project)
    }
    existing_item_urls = {
        (row.checklist_item_id, row.asset_name): row.public_url
        for row in SourceDataItemFolder.objects.filter(project=project)
    }

    try:
        for asset in (unique_assets if multi_asset else [single_asset_name]):
            if multi_asset:
                asset_path = yield from _ensure_folder_with_heartbeat(
                    client, owner_user_id, _join_path(base_path, _sanitize(asset)), current, total,
                )
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
                section_disk_path = yield from _ensure_folder_with_heartbeat(
                    client, owner_user_id, _join_path(asset_path, section_folder), current, total,
                )
                section_public_url = existing_section_urls.get((section.id, asset), "")
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
                    item_disk_path = yield from _ensure_folder_with_heartbeat(
                        client, owner_user_id, _join_path(section_disk_path, item_folder), current, total,
                    )
                    item_public_url = existing_item_urls.get((item.id, asset), "")
                    if not item_public_url:
                        item_public_url = yield from _ensure_link_with_heartbeat(
                            client, owner_user_id, item_disk_path, current, total,
                        )
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
    manager_prs_id = _normalize_person_lookup(getattr(project, "project_manager_prs_id", "") or "")
    manager_name = _normalize_person_lookup(getattr(project, "project_manager", "") or "")
    if not manager_prs_id and not manager_name:
        return None

    match = None
    employees = (
        Employee.objects
        .select_related("user", "person_record")
        .filter(user__is_active=True, user__is_staff=True, role__in=_PROJECT_MANAGER_ROLES)
        .order_by("user__last_name", "user__first_name", "patronymic", "id")
    )
    if manager_prs_id:
        for employee in employees:
            if manager_prs_id == _normalize_person_lookup(_employee_prs_id(employee)):
                match = employee
                break

    if match is None and manager_name:
        for employee in employees:
            if manager_name in _employee_lookup_values(employee):
                match = employee
                break
    if match is None:
        return None

    return _ensure_nextcloud_link_for_user(match.user, client=client, display_name=_employee_full_name(match))


def grant_project_workspace_editor_access_for_performers(
    performer_ids,
    *,
    client: NextcloudApiClient | None = None,
) -> int:
    from projects_app.models import Performer

    normalized_ids = sorted({int(value) for value in performer_ids or [] if str(value).strip()})
    if not normalized_ids:
        return 0

    client = client or NextcloudApiClient()
    if not client.is_configured:
        raise NextcloudApiError("Nextcloud не настроен для предоставления доступа к рабочему пространству проекта.")

    performers = list(
        Performer.objects
        .select_related("employee", "employee__user", "registration")
        .filter(
            pk__in=normalized_ids,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            employee__user__isnull=False,
            employee__user__is_active=True,
            employee__user__is_staff=True,
        )
        .exclude(employee__user__email="")
        .order_by("registration_id", "employee__user_id", "id")
    )
    direction_head_by_employee_id = _direction_head_by_performer_employee(performers)
    workspace_by_project_id = {
        workspace.project_id: workspace
        for workspace in ProjectWorkspace.objects.filter(
            project_id__in={performer.registration_id for performer in performers}
        )
    }

    granted = 0
    seen = set()
    for performer in performers:
        workspace = workspace_by_project_id.get(performer.registration_id)
        if not workspace or not workspace.disk_path:
            continue
        access_users = [performer.employee.user]
        direction_head = direction_head_by_employee_id.get(performer.employee_id)
        if direction_head and direction_head.user_id:
            access_users.append(direction_head.user)

        for user in access_users:
            share_key = (workspace.project_id, user.pk)
            if share_key in seen:
                continue
            seen.add(share_key)
            if not _should_manage_in_nextcloud(user):
                continue
            link = _ensure_nextcloud_link_for_user(user, client=client)
            if not link or not link.nextcloud_user_id:
                raise NextcloudApiError("Не удалось определить Nextcloud-пользователя участника проекта.")
            client.ensure_user_share(
                client.username,
                workspace.disk_path,
                link.nextcloud_user_id,
                permissions=NextcloudApiClient.EDITOR_PERMISSIONS,
            )
            granted += 1
    return granted


def _confirmed_project_performer_users(project):
    from projects_app.models import Performer

    users = []
    seen_user_ids = set()
    performers = (
        Performer.objects
        .select_related("employee", "employee__user")
        .filter(
            registration=project,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            employee__user__isnull=False,
            employee__user__is_active=True,
            employee__user__is_staff=True,
        )
        .exclude(employee__user__email="")
        .order_by("employee__user_id", "id")
    )
    direction_head_by_employee_id = _direction_head_by_performer_employee(performers)
    for performer in performers:
        access_users = [performer.employee.user]
        direction_head = direction_head_by_employee_id.get(performer.employee_id)
        if direction_head and direction_head.user_id:
            access_users.append(direction_head.user)
        for user in access_users:
            if not _should_manage_in_nextcloud(user):
                continue
            if user.pk in seen_user_ids:
                continue
            seen_user_ids.add(user.pk)
            users.append(user)
    return users


def _direction_head_by_performer_employee(performers):
    from experts_app.models import ExpertProfile

    performer_list = list(performers)
    employee_ids = {performer.employee_id for performer in performer_list if performer.employee_id}
    if not employee_ids:
        return {}

    profile_direction_by_employee_id = {}
    direction_ids = set()
    profiles = (
        ExpertProfile.objects
        .select_related("expertise_direction")
        .filter(employee_id__in=employee_ids, expertise_direction_id__isnull=False)
    )
    for profile in profiles:
        if _is_unset_expertise_direction(profile.expertise_direction):
            continue
        profile_direction_by_employee_id[profile.employee_id] = profile.expertise_direction_id
        direction_ids.add(profile.expertise_direction_id)
    if not direction_ids:
        return {}

    head_by_direction_id = {}
    heads = (
        Employee.objects
        .select_related("user")
        .filter(
            department_id__in=direction_ids,
            role=DEPARTMENT_HEAD_GROUP,
            user__is_active=True,
            user__is_staff=True,
        )
        .exclude(user__email="")
        .order_by("position", "id")
    )
    for head in heads:
        head_by_direction_id.setdefault(head.department_id, head)

    return {
        employee_id: head_by_direction_id[direction_id]
        for employee_id, direction_id in profile_direction_by_employee_id.items()
        if direction_id in head_by_direction_id
    }


def _is_unset_expertise_direction(direction) -> bool:
    if direction is None:
        return True
    labels = (
        getattr(direction, "department_name", ""),
        getattr(direction, "short_name", ""),
    )
    return any(str(label or "").strip().casefold() == _UNSET_EXPERTISE_DIRECTION_LABEL for label in labels)


def _ensure_nextcloud_link_for_user(user, *, client: NextcloudApiClient, display_name: str | None = None):
    existing_link = NextcloudUserLink.objects.filter(user=user).first()
    if existing_link and existing_link.nextcloud_user_id:
        client.enable_user(existing_link.nextcloud_user_id)
        client.set_user_email(existing_link.nextcloud_user_id, (user.email or "").strip())
        client.set_user_display_name(existing_link.nextcloud_user_id, display_name or _user_display_name(user))
        return existing_link

    link = ensure_nextcloud_account(user, client=client)
    if link and link.nextcloud_user_id:
        return link
    return None


def _user_display_name(user) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.get_username()


def _employee_full_name(employee: Employee) -> str:
    parts = [
        (employee.user.last_name or "").strip(),
        (employee.user.first_name or "").strip(),
        (employee.patronymic or "").strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _employee_short_name(employee: Employee, *, dots: bool = True) -> str:
    last_name = (employee.user.last_name or "").strip()
    initials = []
    for value in ((employee.user.first_name or "").strip(), (employee.patronymic or "").strip()):
        if value:
            initials.append(f"{value[0]}." if dots else value[0])
    return " ".join(part for part in (last_name, "".join(initials)) if part).strip()


def _employee_prs_id(employee: Employee) -> str:
    return (getattr(employee, "formatted_prs_id", "") or "").strip()


def _employee_lookup_values(employee: Employee) -> set[str]:
    values = {
        _employee_prs_id(employee),
        _employee_full_name(employee),
        _employee_short_name(employee),
        _employee_short_name(employee, dots=False),
        (employee.user.email or "").strip(),
        (employee.user.username or "").strip(),
    }
    return {_normalize_person_lookup(value) for value in values if value}


def _normalize_person_lookup(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).casefold()


def _resolve_nextcloud_source_data_base(user, project):
    from projects_app.models import SourceDataTargetFolder

    base_root = get_nextcloud_root_path()
    if not base_root:
        return None, WorkspaceResult(False, "Не задан корневой каталог Nextcloud в разделе «Подключения».")

    base = "/" if base_root == "/" else base_root.rstrip("/")
    project_path = _build_project_workspace_path(base, project)

    target_obj = SourceDataTargetFolder.objects.filter(user=user).first()
    target_folder = _sanitize_relative_path(
        target_obj.folder_name if target_obj else DEFAULT_SOURCE_DATA_FOLDER
    )
    return _join_path(project_path, target_folder), None


def _join_path(base: str, child: str) -> str:
    clean_base = "/" if base == "/" else str(base or "").rstrip("/")
    clean_child = str(child or "").lstrip("/")
    if not clean_child:
        return clean_base or "/"
    if clean_base in {"", "/"}:
        return "/" + clean_child
    return f"{clean_base}/{clean_child}"


def _build_proposal_workspace_folder_name(proposal) -> str:
    type_name = ""
    if getattr(proposal, "type", None):
        type_name = getattr(proposal.type, "short_name", "") or str(proposal.type)
    return _sanitize(" ".join(part for part in (proposal.short_uid, type_name, proposal.name) if str(part or "").strip()))


def build_proposal_workspace_path(proposal, *, base_root: str | None = None) -> str:
    if not getattr(proposal, "year", None):
        return ""

    root_path = str(base_root or get_nextcloud_root_path() or "").strip()
    if not root_path:
        return ""

    base = "/" if root_path == "/" else root_path.rstrip("/")
    tkp_root_path = _join_path(base, _sanitize(PROPOSALS_SECTION_FOLDER))
    year_path = _join_path(tkp_root_path, _sanitize(str(proposal.year)))
    return _join_path(year_path, _build_proposal_workspace_folder_name(proposal))
