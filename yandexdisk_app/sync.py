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


def run_sync(delay: float = API_DELAY) -> int:
    """
    Один цикл синхронизации. Возвращает число обновлённых папок.
    """
    from checklists_app.models import ChecklistItemFolder, ProjectWorkspace
    from yandexdisk_app.models import YandexDiskAccount
    from yandexdisk_app.service import list_resources

    workspaces = ProjectWorkspace.objects.select_related("created_by").all()
    if not workspaces.exists():
        return 0

    ws_by_user = defaultdict(list)
    for ws in workspaces:
        if ws.created_by_id:
            ws_by_user[ws.created_by_id].append(ws)

    total_updated = 0

    for user_id, user_workspaces in ws_by_user.items():
        user = user_workspaces[0].created_by
        if not YandexDiskAccount.objects.filter(user=user).exists():
            logger.warning("У пользователя %s нет подключения к Яндекс.Диску, пропускаем", user)
            continue

        for ws in user_workspaces:
            folders = ChecklistItemFolder.objects.filter(project=ws.project)
            if not folders.exists():
                continue

            section_paths = set()
            for f in folders:
                parts = f.disk_path.rsplit("/", 1)
                if len(parts) == 2:
                    section_paths.add(parts[0])

            section_cache = {}
            for section_path in section_paths:
                items = list_resources(user, section_path, limit=1000)
                time.sleep(delay)
                section_cache[section_path] = {it["path"]: it for it in items}

            now = timezone.now()
            for folder in folders:
                section_path = folder.disk_path.rsplit("/", 1)[0] if "/" in folder.disk_path else ""
                item_data = section_cache.get(section_path, {})

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
                    contents = list_resources(user, folder.disk_path, limit=1000)
                    time.sleep(delay)

                    files_only = [c for c in contents if c.get("type") == "file"]
                    file_count = len(files_only)
                    last_mod = None
                    for f in files_only:
                        mod = _parse_modified(f.get("modified"))
                        if mod and (last_mod is None or mod > last_mod):
                            last_mod = mod

                    folder.file_count = file_count
                    folder.last_upload_at = last_mod
                    folder.synced_at = now
                    folder.save(update_fields=["file_count", "last_upload_at", "synced_at"])
                    total_updated += 1
                else:
                    folder.synced_at = now
                    folder.save(update_fields=["synced_at"])

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
