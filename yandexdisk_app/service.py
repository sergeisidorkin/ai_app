"""
Сервисные функции для работы с API Яндекс.Диска.
"""
import requests
from typing import Optional, List, Dict, Tuple

from .models import YandexDiskAccount

YANDEX_DISK_API = "https://cloud-api.yandex.net/v1/disk"


def _get_token(user) -> Optional[str]:
    """Получить access_token из БД."""
    acc = YandexDiskAccount.objects.filter(user=user).first()
    return acc.access_token if acc else None


def _auth_headers(user) -> Dict[str, str]:
    """Заголовки авторизации для API."""
    token = _get_token(user)
    if not token:
        return {}
    return {"Authorization": f"OAuth {token}"}


def list_resources(user, path: str = "/", limit: int = 100) -> List[Dict]:
    """
    Получить список файлов/папок по указанному пути.
    """
    token = _get_token(user)
    if not token:
        return []

    headers = {"Authorization": f"OAuth {token}"}
    params = {
        "path": path,
        "limit": limit,
        "fields": "_embedded.items.name,_embedded.items.path,_embedded.items.type,_embedded.items.size,_embedded.items.modified",
    }

    try:
        resp = requests.get(f"{YANDEX_DISK_API}/resources", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("_embedded", {}).get("items", [])
        return [
            {
                "name": it.get("name", ""),
                "path": it.get("path", "").replace("disk:", ""),
                "type": it.get("type", ""),
                "size": it.get("size"),
                "modified": it.get("modified"),
            }
            for it in items
        ]
    except Exception:
        return []


def download_file(user, path: str) -> Tuple[Optional[str], bytes]:
    """
    Скачать файл с Яндекс.Диска.
    Возвращает (mime_type, content) или (None, b"") при ошибке.
    """
    token = _get_token(user)
    if not token:
        return (None, b"")

    headers = {"Authorization": f"OAuth {token}"}

    try:
        # Сначала получаем ссылку на скачивание
        params = {"path": path}
        resp = requests.get(f"{YANDEX_DISK_API}/resources/download", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        download_url = resp.json().get("href")

        if not download_url:
            return (None, b"")

        # Скачиваем файл
        dl_resp = requests.get(download_url, timeout=60)
        dl_resp.raise_for_status()

        content_type = dl_resp.headers.get("Content-Type", "application/octet-stream")
        return (content_type, dl_resp.content)

    except Exception:
        return (None, b"")


def upload_file(user, path: str, data: bytes, overwrite: bool = True) -> bool:
    """
    Загрузить файл на Яндекс.Диск.
    path — полный путь включая имя файла, напр. "/Documents/report.docx"
    """
    token = _get_token(user)
    if not token:
        return False

    headers = {"Authorization": f"OAuth {token}"}

    try:
        # Получаем URL для загрузки
        params = {"path": path, "overwrite": str(overwrite).lower()}
        resp = requests.get(f"{YANDEX_DISK_API}/resources/upload", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        upload_url = resp.json().get("href")

        if not upload_url:
            return False

        # Загружаем файл
        up_resp = requests.put(upload_url, data=data, timeout=60)
        up_resp.raise_for_status()
        return True

    except Exception:
        return False


def create_folder(user, path: str) -> bool:
    """Создать папку на Яндекс.Диске."""
    token = _get_token(user)
    if not token:
        return False

    headers = {"Authorization": f"OAuth {token}"}

    try:
        params = {"path": path}
        resp = requests.put(f"{YANDEX_DISK_API}/resources", headers=headers, params=params, timeout=15)
        # 201 — создано, 409 — уже существует (тоже ок)
        return resp.status_code in (201, 409)
    except Exception:
        return False


def get_resource_info(user, path: str) -> Optional[Dict]:
    """Получить информацию о ресурсе (файле/папке)."""
    token = _get_token(user)
    if not token:
        return None

    headers = {"Authorization": f"OAuth {token}"}

    try:
        params = {"path": path}
        resp = requests.get(f"{YANDEX_DISK_API}/resources", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None