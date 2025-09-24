import io
import os
import requests
from typing import List, Dict, Optional, Tuple

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

SESSION_KEY = "gdrive_tokens"


def _refresh_access_token_in_session(request):
    toks = request.session.get("gdrive_tokens") or {}
    rt = toks.get("refresh_token")
    if not rt:
        return None
    import os
    cid = os.environ.get("GDRIVE_CLIENT_ID", "")
    cs  = os.environ.get("GDRIVE_CLIENT_SECRET", "")
    r = requests.post(GOOGLE_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": rt,
        "client_id": cid,
        "client_secret": cs,
    }, timeout=20)
    if not r.ok:
        return None
    j = r.json()
    toks["access_token"] = j.get("access_token")
    request.session["gdrive_tokens"] = toks
    request.session.modified = True
    return toks["access_token"]

def _api_get_with_refresh(request, url, *, params=None, headers=None, file_id_for_rk=None, rk=None):
    """
    Делает GET к Drive. Если 401 — рефрешим токен и повторяем.
    Если передан resourceKey — добавляем X-Goog-Drive-Resource-Keys.
    """
    at = get_access_token(request)  # ваша текущая функция
    if not at:
        return None
    h = {"Authorization": f"Bearer {at}"}
    if headers:
        h.update(headers)
    if file_id_for_rk and rk:
        h["X-Goog-Drive-Resource-Keys"] = f"{file_id_for_rk}/{rk}"

    r = requests.get(url, headers=h, params=params, timeout=30)
    if r.status_code == 401:
        at2 = _refresh_access_token_in_session(request)
        if not at2:
            return None
        h["Authorization"] = f"Bearer {at2}"
        r = requests.get(url, headers=h, params=params, timeout=30)

    if not r.ok:
        return None
    try:
        return r.json()
    except Exception:
        return None


def download_file(request, file_id, mime_type, resource_key=""):
    """
    Для PDF и обычных файлов — alt=media.
    Для google-docs — export.
    Возвращает (mime, bytes) или (None, b"").
    """
    # google-документы экспортируем:
    if mime_type.startswith("application/vnd.google-apps."):
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        params = {"mimeType": "application/pdf"}  # в PDF
    else:
        # отдать как есть (для PDF/картинок/и пр.)
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media", "supportsAllDrives": True}

    at = get_access_token(request)
    if not at:
        return (None, b"")
    h = {"Authorization": f"Bearer {at}"}
    if resource_key:
        h["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"

    r = requests.get(url, headers=h, params=params, timeout=60)
    if r.status_code == 401:
        at2 = _refresh_access_token_in_session(request)
        if not at2:
            return (None, b"")
        h["Authorization"] = f"Bearer {at2}"
        r = requests.get(url, headers=h, params=params, timeout=60)

    if not r.ok:
        return (None, b"")
    out_mime = "application/pdf" if "export" in url else (r.headers.get("Content-Type") or mime_type)
    return (out_mime, r.content)


def _env_client_id() -> str:
    return os.environ.get("GDRIVE_CLIENT_ID", "").strip()

def _env_client_secret() -> str:
    return os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()

def get_access_token(request) -> Optional[str]:
    """
    Достаём действующий access_token из сессии.
    Если его нет, пробуем обновить по refresh_token.
    """
    t = request.session.get(SESSION_KEY, {}) or {}
    at = t.get("access_token")
    if at:
        return at

    rf = t.get("refresh_token")
    if not rf:
        return None

    data = {
        "client_id": _env_client_id(),
        "client_secret": _env_client_secret(),
        "refresh_token": rf,
        "grant_type": "refresh_token",
    }
    try:
        r = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=15)
        r.raise_for_status()
        j = r.json() or {}
        at = j.get("access_token")
        if at:
            t["access_token"] = at
            request.session[SESSION_KEY] = t
            request.session.modified = True
            return at
        return None
    except Exception:
        return None


def _auth_headers(request, rk_map: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    at = get_access_token(request)
    if not at:
        return {}
    h = {"Authorization": f"Bearer {at}"}
    if rk_map:
        pairs = [f"{fid}/{rk}" for fid, rk in rk_map.items() if fid and rk]
        if pairs:
            h["X-Goog-Drive-Resource-Keys"] = ",".join(pairs)
    return h





def list_children(request, folder_id, resource_key=""):
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,resourceKey,driveId,size)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
        "corpora": "allDrives",
        "pageSize": 200,
    }
    j = _api_get_with_refresh(
        request,
        "https://www.googleapis.com/drive/v3/files",
        params=params,
        file_id_for_rk=folder_id,
        rk=resource_key or None,
    )
    return (j or {}).get("files") or []

# def list_children(request, folder_id: str, folder_res_key: str = "") -> List[Dict]:
#     """
#     Вернёт список файлов/папок из указанной папки.
#     Возвращаем элементы: id, name, mimeType, resourceKey (если есть).
#     """
#     rk_map = {}
#     if folder_id and folder_res_key:
#         rk_map[folder_id] = folder_res_key
#
#     items: List[Dict] = []
#     page_token = None
#     while True:
#         params = {
#             "q": f"'{folder_id}' in parents and trashed = false",
#             "fields": "nextPageToken, files(id,name,mimeType,resourceKey,driveId)",
#             "supportsAllDrives": True,
#             "includeItemsFromAllDrives": True,
#             "pageSize": 1000,
#             "orderBy": "name_natural"
#         }
#         if page_token:
#             params["pageToken"] = page_token
#
#         r = requests.get(
#             "https://www.googleapis.com/drive/v3/files",
#             params=params,
#             headers=_auth_headers(request, rk_map),
#             timeout=30
#         )
#
#         # если нужна подсказка по ключам — Google вернёт заголовок с ключами
#         if r.status_code == 404:
#             hdr = r.headers.get("X-Goog-Drive-Resource-Keys") or r.headers.get("x-goog-drive-resource-keys")
#             if hdr:
#                 for pair in str(hdr).split(","):
#                     pair = pair.strip()
#                     if "/" in pair:
#                         fid, rk = pair.split("/", 1)
#                         fid, rk = fid.strip(), rk.strip()
#                         if fid and rk and fid not in rk_map:
#                             rk_map[fid] = rk
#                 # повторим запрос
#                 r = requests.get(
#                     "https://www.googleapis.com/drive/v3/files",
#                     params=params,
#                     headers=_auth_headers(request, rk_map),
#                     timeout=30
#                 )
#
#         r.raise_for_status()
#         j = r.json() or {}
#         files = j.get("files") or []
#         for f in files:
#             items.append({
#                 "id": f.get("id"),
#                 "name": f.get("name"),
#                 "mimeType": f.get("mimeType"),
#                 "resourceKey": f.get("resourceKey"),
#                 "driveId": f.get("driveId"),
#             })
#
#         page_token = j.get("nextPageToken")
#         if not page_token:
#             break
#
#     return items


def _export_mime(mime_type: str) -> Optional[str]:
    """
    Для Google-типов вернём MIME для экспорта, чтобы это было удобно модели.
    """
    if mime_type == "application/vnd.google-apps.document":
        return "application/pdf"  # или DOCX: application/vnd.openxmlformats-officedocument.wordprocessingml.document
    if mime_type == "application/vnd.google-apps.spreadsheet":
        return "text/csv"         # или application/pdf
    if mime_type == "application/vnd.google-apps.presentation":
        return "application/pdf"
    return None


def download_file(request, file_id: str, mime_type: str, res_key: str = "", rk_map: Optional[Dict[str, str]] = None) -> Tuple[str, bytes]:
    """
    Скачивает файл (или экспортирует, если Google-тип). Возвращает (mime, bytes).
    """
    rk_map = dict(rk_map or {})
    if file_id and res_key and file_id not in rk_map:
        rk_map[file_id] = res_key

    # Google-native → export
    exp = _export_mime(mime_type)
    if exp:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        params = {"mimeType": exp}
        r = requests.get(url, params=params, headers=_auth_headers(request, rk_map), timeout=60, stream=True)
        if r.status_code == 404:
            hdr = r.headers.get("X-Goog-Drive-Resource-Keys") or r.headers.get("x-goog-drive-resource-keys")
            if hdr:
                for pair in str(hdr).split(","):
                    pair = pair.strip()
                    if "/" in pair:
                        fid, rk = pair.split("/", 1)
                        fid, rk = fid.strip(), rk.strip()
                        if fid and rk and fid not in rk_map:
                            rk_map[fid] = rk
                r = requests.get(url, params=params, headers=_auth_headers(request, rk_map), timeout=60, stream=True)
        r.raise_for_status()
        return exp, r.content

    # Обычный бинарник
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    params = {"alt": "media"}
    r = requests.get(url, params=params, headers=_auth_headers(request, rk_map), timeout=60, stream=True)
    if r.status_code == 404:
        hdr = r.headers.get("X-Goog-Drive-Resource-Keys") or r.headers.get("x-goog-drive-resource-keys")
        if hdr:
            for pair in str(hdr).split(","):
                pair = pair.strip()
                if "/" in pair:
                    fid, rk = pair.split("/", 1)
                    fid, rk = fid.strip(), rk.strip()
                    if fid and rk and fid not in rk_map:
                        rk_map[fid] = rk
            r = requests.get(url, params=params, headers=_auth_headers(request, rk_map), timeout=60, stream=True)
    r.raise_for_status()
    # MIME нам неизвестен точно (Google его не возвращает в этом запросе),
    # но для Files API это не критично — можно отдать исходный mime_type.
    return mime_type, r.content