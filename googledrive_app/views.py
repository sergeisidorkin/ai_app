from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
import os
import urllib.parse
import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

def _client_id() -> str:
    return os.environ.get("GDRIVE_CLIENT_ID", "").strip()

def _client_secret() -> str:
    return os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()

def _api_key() -> str:
    return os.environ.get("GDRIVE_API_KEY", "").strip()

def _project_number() -> str:
    """
    Необязательно. Если зададите GDRIVE_PROJECT_NUMBER (числовой Project Number из GCP),
    можно прокинуть его в Picker через setAppId — иногда это помогает.
    """
    return os.environ.get("GDRIVE_PROJECT_NUMBER", "").strip()

def _callback_url(request) -> str:
    # абсолютный URL до /gdrive/callback
    return request.build_absolute_uri(reverse("gdrive_callback")).rstrip("/")

def _session_key():
    return "gdrive_tokens"

def _has_tokens(request) -> bool:
    t = request.session.get(_session_key(), {})
    return bool(t.get("access_token") or t.get("refresh_token"))

def _get_tokens(request) -> dict:
    """
    Возвращает словарь токенов из сессии или пустой dict.
    """
    return request.session.get(_session_key(), {}) or {}

def _save_tokens(request, tokens: dict):
    """
    Сохраняет словарь токенов в сессию.
    """
    request.session[_session_key()] = tokens or {}
    request.session.modified = True

def _get_access_token(request) -> str | None:
    """
    Возвращает действительный access_token, при необходимости обновляет по refresh_token.
    """
    tokens = _get_tokens(request)
    at = tokens.get("access_token")
    if at:
        return at
    # пробуем обновить
    return _refresh_access_token(request)

def _drive_get(request, file_id: str, fields: str = "id,name,parents") -> dict | None:
    """
    Получить метаданные файла/папки через Drive API files.get.
    """
    at = _get_access_token(request)
    if not at:
        return None
    headers = {"Authorization": f"Bearer {at}"}
    # Поддержка Shared Drives и resourceKey (если есть в запросе)
    params = {"fileId": file_id, "fields": fields, "supportsAllDrives": True}
    resource_key = getattr(request, "_gdrive_resource_key", "") or ""
    if resource_key:
    # Требование API: ключи — в заголовке
        headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"

    try:
        resp = requests.get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params=params, headers=headers, timeout=15)
        if resp.status_code == 401:
            # одно обновление и повтор
            at = _refresh_access_token(request)
            if not at:
                return None
            headers = {"Authorization": f"Bearer {at}"}
            if resource_key:
                 headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
            resp = requests.get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json() or {}
    except Exception:
        return None

def _drive_get_ex(request, file_id: str, fields: str, rk_map: dict[str, str]) -> dict | None:
    """
    files.get с поддержкой множественных resourceKey через заголовок X-Goog-Drive-Resource-Keys
    и авто‑подхватом ключей из заголовка ответа при 404.
    """
    at = _get_access_token(request)
    if not at:
        return None
    def _build_headers():
        headers = {"Authorization": f"Bearer {at}"}
        if rk_map:
            pairs = [f"{fid}/{rk}" for fid, rk in rk_map.items() if fid and rk]
            if pairs:
                headers["X-Goog-Drive-Resource-Keys"] = ",".join(pairs)
        return headers
    params = {"fields": fields, "supportsAllDrives": True}
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"

    try:
        # Первой попыткой — с текущими ключами
        resp = requests.get(url, params=params, headers=_build_headers(), timeout=15)
        if resp.status_code == 401:
            at2 = _refresh_access_token(request)
            if not at2:
                return None
            at = at2
            resp = requests.get(url, params=params, headers=_build_headers(), timeout=15)
        if resp.status_code == 404:
            # Попробуем вытащить ключи предков/объекта из заголовка и повторить
            h = resp.headers.get("X-Goog-Drive-Resource-Keys") or resp.headers.get("x-goog-drive-resource-keys")
            if h:
                for pair in str(h).split(","):
                    pair = pair.strip()
                    if "/" in pair:
                        fid, rk = pair.split("/", 1)
                        fid, rk = fid.strip(), rk.strip()
                        if fid and rk and fid not in rk_map:
                            rk_map[fid] = rk
                # Повтор с обновлённой картой ключей
                resp = requests.get(url, params=params, headers=_build_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json() or {}
    except Exception:
        return None

def _drive_get_drive_name_ex(request, drive_id: str, rk_map: dict[str, str]) -> str | None:
    """
    Имя общего диска, учитывая заголовок X-Goog-Drive-Resource-Keys (на всякий случай).
    """
    if not drive_id:
        return None
    at = _get_access_token(request)
    if not at:
        return None
    headers = {"Authorization": f"Bearer {at}"}
    if rk_map:
        pairs = [f"{fid}/{rk}" for fid, rk in rk_map.items() if fid and rk]
        if pairs:
            headers["X-Goog-Drive-Resource-Keys"] = ",".join(pairs)
    params = {"fields": "id,name", "supportsAllDrives": True}
    url = f"https://www.googleapis.com/drive/v3/drives/{drive_id}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 401:
            at2 = _refresh_access_token(request)
            if not at2:
                return None
            headers["Authorization"] = f"Bearer {at2}"
            resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return (resp.json() or {}).get("name")
    except Exception:
        return None

def _drive_get_drive_name(request, drive_id: str) -> str | None:
    """
    Возвращает отображаемое имя общего диска по driveId.
    """
    if not drive_id:
        return None
    at = _get_access_token(request)
    if not at:
        return None
    headers = {"Authorization": f"Bearer {at}"}
    params = {"fields": "id,name", "supportsAllDrives": True}
    try:
        resp = requests.get(f"https://www.googleapis.com/drive/v3/drives/{drive_id}", params=params, headers=headers, timeout=15)
        if resp.status_code == 401:
            at = _refresh_access_token(request)
            if not at:
                return None
            headers = {"Authorization": f"Bearer {at}"}
            resp = requests.get(f"https://www.googleapis.com/drive/v3/drives/{drive_id}", params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json() or {}
        return data.get("name")
    except Exception:
        return None


def _resolve_path(request, file_id: str) -> str:
    """
    Строит «путь» по именам папок от корня (root) до файла.
    В Picker у нас есть только id выбранного объекта; поднимаемся по parents.
    """
    parts = []
    cur_id = file_id
    seen = set()
    # Будем хранить собранные resourceKey и использовать их для предков
    rk_map: dict[str, str] = {}
    # Если при выборе пришёл ключ для файла — положим его сразу
    initial_rk = getattr(request, "_gdrive_resource_key", "") or ""

    if initial_rk and file_id:
        rk_map[file_id] = initial_rk

    # Получим имя самого файла (и развернём ярлык)
    # берём ещё mimeType
    cur = _drive_get_ex(request, cur_id, fields="id,name,parents,shortcutDetails,driveId,mimeType", rk_map=rk_map)
    if not cur:
        return ""

    # разворачиваем ярлык и снова берём mimeType
    if (cur.get("shortcutDetails") or {}).get("targetId"):
        cur = _drive_get_ex(request, cur["shortcutDetails"]["targetId"], fields="id,name,parents,driveId,mimeType",
                            rk_map=rk_map)
        if not cur:
            return ""

    top_drive_id = cur.get("driveId")
    self_name = cur.get("name") or ""
    is_folder = (cur.get("mimeType") == "application/vnd.google-apps.folder")

    # собираем родителей
    parts = []
    seen = set()
    while True:
        parents = cur.get("parents") or []
        if not parents: break
        pid = parents[0]
        if pid in ("root", None) or pid in seen: break
        seen.add(pid)
        cur = _drive_get_ex(request, pid, fields="id,name,parents,driveId", rk_map=rk_map)
        if not cur: break
        pname = cur.get("name") or ""
        if pname:
            parts.append(pname)
        else:
            break

    # если это ПАПКА — добавим её собственное имя
    if is_folder and self_name:
        parts.insert(0, self_name)  # вставляем в конец пути (после reverse станет последним сегментом)

    parts.reverse()
    path_core = ("/" + "/".join(parts)) if parts else ""

    if top_drive_id:
        dname = _drive_get_drive_name_ex(request, top_drive_id, rk_map)
        result = f"/{dname or 'Shared drive'}{path_core}"
    else:
        result = f"/Мой диск{path_core}"

    if result.startswith("/Мой диск/Мой диск"):
        result = result.replace("/Мой диск/Мой диск", "/Мой диск", 1)

    return result

@login_required
def connections_partial(request):
    """
    Фрагмент для вкладки «Подключения» (Google Drive).
    Заглушка: показывает состояние подключения и кнопки действий.
    """
    # В реальной интеграции здесь читается состояние из БД.
    connected = False
    selection = None
    return render(
        request,
        "googledrive_app/connections_partial.html",
        {"gdrive_connected": connected, "selection": selection},
    )

@login_required
def connect(request):
    """
    Инициация OAuth2 авторизации с Google.
    """
    cid = _client_id()
    if not cid or not _client_secret():
        messages.error(request, "GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET не заданы в окружении.")
        return redirect(reverse("gdrive_connections_partial"))

    params = {
        "client_id": cid,
        "redirect_uri": _callback_url(request),
        "response_type": "code",
        "scope": GDRIVE_SCOPE,
        "access_type": "offline",   # чтобы получить refresh_token
        "prompt": "consent",        # форсируем consent, чтобы refresh_token точно пришёл
        "include_granted_scopes": "true",
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(url)

@login_required
def callback(request):
    """
    Обработка коллбэка: обмен authorization code на access/refresh токены.
    """
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Google OAuth вернул ошибку: {error}")
        return redirect(reverse("gdrive_connections_partial"))

    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")

    data = {
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": _callback_url(request),
        "grant_type": "authorization_code",
    }
    try:
        resp = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        payload = resp.json() or {}
        # Сохраняем токены в сессии (для продакшна — в БД с шифрованием)
        request.session[_session_key()] = {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),  # может не прийти при повторном consent
            "token_type": payload.get("token_type"),
            "expires_in": payload.get("expires_in"),
            "scope": payload.get("scope"),
        }
        request.session.modified = True
        if not payload.get("refresh_token"):
            messages.warning(
                request,
                "Google не вернул refresh_token. При следующей авторизации может понадобиться 'prompt=consent'."
            )
        messages.success(request, "Google Drive подключён.")
    except requests.HTTPError as e:
        messages.error(request, f"Не удалось обменять код на токен: {e} ({resp.text})")
    except Exception as e:
        messages.error(request, f"Ошибка при обращении к Google: {e}")

    # Ведём пользователя в общий раздел «Подключения»
    return redirect("/#connections")

@login_required
def pick(request):
    """
    Запуск Google Picker для выбора файла.
    Требует:
      - действительный access_token (OAuth)
      - GDRIVE_API_KEY (API key для Picker)
    """
    if not _has_tokens(request):
        messages.error(request, "Сначала подключите Google Drive.")
        return redirect("/#connections")

    api_key = _api_key()
    if not api_key:
        messages.error(request, "Не задан GDRIVE_API_KEY (API‑ключ Google) — добавьте в окружение.")
        return redirect("/#connections")

    tokens = _get_tokens(request)
    access_token = tokens.get("access_token") or _refresh_access_token(request)
    if not access_token:
        messages.error(request, "Нет действительного access_token. Подключите Google Drive заново.")
        return redirect("/#connections")

    origin = f"{request.scheme}://{request.get_host()}"
    app_id = _project_number()  # можно оставить пустым

    # Рендерим страницу с кнопкой «Открыть Google Picker»
    return render(
        request,
        "googledrive_app/pick.html",
        {
            "api_key": api_key,
            "access_token": access_token,
            "origin": origin,
            "app_id": app_id,
        },
    )

@login_required
def select(request):
    """
    Сохранение выбранного файла (минимум id и name) в сессии.
    """
    file_id = (request.POST.get("file_id") or "").strip()
    file_name = (request.POST.get("file_name") or "").strip()
    file_path = (request.POST.get("file_path") or "").strip()
    file_res_key = (request.POST.get("file_resource_key") or "").strip()

    if not file_id:
        return HttpResponseBadRequest("missing file_id")
    # Прокинем resourceKey в контекст запроса, чтобы _drive_get смог его использовать
    request._gdrive_resource_key = file_res_key

    # Всегда пересчитываем путь на сервере; client-path используем как fallback
    server_path = ""
    try:
        server_path = _resolve_path(request, file_id) or ""
    except Exception:
        server_path = ""
    final_path = server_path or file_path or ""

    # Сохраним также res_key (если есть) — пригодится для скачивания
    request.session["gdrive_selection"] = {"id": file_id, "name": file_name, "path": final_path, "res_key": file_res_key}
    request.session.modified = True
    messages.success(request, f"Выбран файл: {file_name or file_id}")
    return redirect("/#connections")

@login_required
def disconnect(request):
    """
    Удаляет локальные токены (в сессии) и выбранный объект.
    """
    try:
        request.session.pop(_session_key(), None)
        request.session.pop("gdrive_selection", None)
        request.session.modified = True
        messages.success(request, "Подключение Google Drive удалено.")
    except Exception:
        messages.info(request, "Подключение Google Drive уже отсутствовало.")
    return redirect("/#connections")


