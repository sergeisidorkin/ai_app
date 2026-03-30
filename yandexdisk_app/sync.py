"""
Фоновая синхронизация метаданных папок Яндекс.Диска.

Может использоваться как:
- из management command: run_sync(delay=1.0)
- как фоновый поток: start_background_sync(interval=300)
"""
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime

from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

API_DELAY = 1.0
DEFAULT_INTERVAL = 300  # 5 минут


def _parse_modified(dt_str: str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    except (ValueError, TypeError):
        return None


def _collect_recursive_metrics(user, root_path, delay, list_resources):
    file_count = 0
    last_mod = None
    stack = [root_path]
    visited = set()

    while stack:
        current_path = stack.pop()
        if current_path in visited:
            continue
        visited.add(current_path)

        contents = list_resources(user, current_path, limit=1000)
        time.sleep(delay)
        for item in contents:
            item_type = item.get("type")
            if item_type == "file":
                file_count += 1
                mod = _parse_modified(item.get("modified"))
                if mod and (last_mod is None or mod > last_mod):
                    last_mod = mod
            elif item_type == "dir":
                child_path = item.get("path") or ""
                if child_path and child_path not in visited:
                    stack.append(child_path)

    return file_count, last_mod


def _sync_folders(user, folders, delay, list_resources):
    """Sync file_count / last_upload_at for a queryset of folder records.

    Each record must have ``disk_path``, ``file_count``, ``last_upload_at``,
    ``synced_at`` fields.  Returns the number of actually updated folders.
    """
    if not folders.exists():
        return 0

    parent_paths = set()
    for f in folders:
        parts = f.disk_path.rsplit("/", 1)
        if len(parts) == 2:
            parent_paths.add(parts[0])

    parent_cache = {}
    for pp in parent_paths:
        items = list_resources(user, pp, limit=1000)
        time.sleep(delay)
        parent_cache[pp] = {it["path"]: it for it in items}

    now = timezone.now()
    updated = 0

    for folder in folders:
        parent_path = folder.disk_path.rsplit("/", 1)[0] if "/" in folder.disk_path else ""
        item_data = parent_cache.get(parent_path, {})

        folder_info = item_data.get(folder.disk_path)
        if not folder_info:
            normalized = folder.disk_path
            if normalized.startswith("disk:"):
                normalized = normalized[5:]
            for key, val in item_data.items():
                k = key[5:] if key.startswith("disk:") else key
                if k == normalized:
                    folder_info = val
                    break

        if folder_info:
            file_count, last_mod = _collect_recursive_metrics(user, folder.disk_path, delay, list_resources)

            folder.file_count = file_count
            folder.last_upload_at = last_mod
            folder.synced_at = now
            folder.save(update_fields=["file_count", "last_upload_at", "synced_at"])
            updated += 1
        else:
            folder.synced_at = now
            folder.save(update_fields=["synced_at"])

    return updated


def run_sync(delay: float = API_DELAY) -> int:
    """
    Один цикл синхронизации. Возвращает число обновлённых папок.
    """
    from checklists_app.models import (
        ChecklistItemFolder, ProjectWorkspace,
        SourceDataWorkspace, SourceDataSectionFolder, SourceDataItemFolder,
    )
    from core.cloud_storage import CloudStorageNotReadyError, is_nextcloud_primary, list_folder_resources
    from yandexdisk_app.models import YandexDiskAccount

    total_updated = 0

    # ── 1. Рабочие пространства проектов (ChecklistItemFolder) ──────────
    workspaces = ProjectWorkspace.objects.select_related("created_by").all()
    ws_by_user = defaultdict(list)
    for ws in workspaces:
        if ws.created_by_id:
            ws_by_user[ws.created_by_id].append(ws)

    for user_id, user_workspaces in ws_by_user.items():
        user = user_workspaces[0].created_by
        if not is_nextcloud_primary() and not YandexDiskAccount.objects.filter(user=user).exists():
            logger.warning("У пользователя %s нет подключения к Яндекс.Диску, пропускаем", user)
            continue
        for ws in user_workspaces:
            folders = ChecklistItemFolder.objects.filter(project=ws.project)
            try:
                total_updated += _sync_folders(user, folders, delay, list_folder_resources)
            except CloudStorageNotReadyError:
                logger.info("Пропускаем синхронизацию папок проекта: текущее облачное хранилище ещё не настроено.")
                return total_updated

    # ── 2. Пространства исходных данных (SourceData*Folder) ─────────────
    sd_workspaces = SourceDataWorkspace.objects.select_related("created_by").all()
    sd_by_user = defaultdict(list)
    for sdws in sd_workspaces:
        if sdws.created_by_id:
            sd_by_user[sdws.created_by_id].append(sdws)

    for user_id, user_sd_workspaces in sd_by_user.items():
        user = user_sd_workspaces[0].created_by
        if not is_nextcloud_primary() and not YandexDiskAccount.objects.filter(user=user).exists():
            logger.warning("У пользователя %s нет подключения к Яндекс.Диску, пропускаем", user)
            continue
        for sdws in user_sd_workspaces:
            section_folders = SourceDataSectionFolder.objects.filter(project=sdws.project)
            try:
                total_updated += _sync_folders(user, section_folders, delay, list_folder_resources)

                item_folders = SourceDataItemFolder.objects.filter(project=sdws.project)
                total_updated += _sync_folders(user, item_folders, delay, list_folder_resources)
            except CloudStorageNotReadyError:
                logger.info("Пропускаем синхронизацию source-data: текущее облачное хранилище ещё не настроено.")
                return total_updated

    return total_updated


def _sync_loop(interval: float, delay: float):
    """Бесконечный цикл синхронизации, запускаемый в фоновом потоке."""
    logger.info("Фоновая синхронизация Яндекс.Диска запущена (интервал %ds)", interval)
    while True:
        try:
            close_old_connections()
            updated = run_sync(delay=delay)
            if updated:
                logger.info("Синхронизация Яндекс.Диска: обновлено %d папок", updated)
        except Exception:
            logger.exception("Ошибка фоновой синхронизации Яндекс.Диска")
        time.sleep(interval)


_started = False
_lock = threading.Lock()


def start_background_sync(interval: float = DEFAULT_INTERVAL, delay: float = API_DELAY):
    """
    Запускает фоновый daemon-поток для периодической синхронизации.
    Безопасен для повторного вызова — поток создаётся только один раз.
    """
    global _started
    with _lock:
        if _started:
            return
        _started = True

    t = threading.Thread(
        target=_sync_loop,
        args=(interval, delay),
        name="yadisk-sync",
        daemon=True,
    )
    t.start()
