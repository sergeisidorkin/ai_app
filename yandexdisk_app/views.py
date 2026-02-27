import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import YandexDiskAccount, YandexDiskSelection

# ─────────────────────────────────────────────────────────────────────────────
# Яндекс OAuth URLs
# ─────────────────────────────────────────────────────────────────────────────
YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_DISK_API = "https://cloud-api.yandex.net/v1/disk"


def _client_id() -> str:
    return getattr(settings, "YANDEX_DISK_CLIENT_ID", "") or os.environ.get("YANDEX_DISK_CLIENT_ID", "")


def _client_secret() -> str:
    return getattr(settings, "YANDEX_DISK_CLIENT_SECRET", "") or os.environ.get("YANDEX_DISK_CLIENT_SECRET", "")


def _callback_url(request) -> str:
    return request.build_absolute_uri(reverse("yadisk_callback")).rstrip("/")


def _home_tab(tab: str) -> str:
    return reverse("home") + f"#{tab}"


# ─────────────────────────────────────────────────────────────────────────────
# Token helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get_access_token(user) -> str | None:
    """Возвращает действительный access_token, при необходимости обновляет."""
    acc = YandexDiskAccount.objects.filter(user=user).first()
    if not acc:
        return None

    # Если токен ещё действителен
    if acc.access_token and acc.expires_at and acc.expires_at > datetime.now(timezone.utc):
        return acc.access_token

    # Пробуем обновить по refresh_token
    if acc.refresh_token:
        new_token = _refresh_access_token(acc)
        if new_token:
            return new_token

    return acc.access_token or None


def _refresh_access_token(acc: YandexDiskAccount) -> str | None:
    """Обновляет access_token по refresh_token."""
    if not acc.refresh_token:
        return None

    data = {
        "grant_type": "refresh_token",
        "refresh_token": acc.refresh_token,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
    }
    try:
        resp = requests.post(YANDEX_TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        acc.access_token = payload.get("access_token", "")
        acc.refresh_token = payload.get("refresh_token", acc.refresh_token)
        expires_in = payload.get("expires_in", 3600)
        acc.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        acc.save()
        return acc.access_token
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def connections_partial(request):
    """Фрагмент для вкладки «Подключения» (Яндекс.Диск)."""
    connected = YandexDiskAccount.objects.filter(user=request.user).exists()
    selection = YandexDiskSelection.objects.filter(user=request.user).first()
    return render(
        request,
        "yandexdisk_app/connections_partial.html",
        {"yadisk_connected": connected, "selection": selection},
    )


OAUTH_STATE_SESSION_KEY = "yadisk_oauth_state"


@login_required
def connect(request):
    """Инициация OAuth2 авторизации с Яндекс.Диском."""
    cid = _client_id()
    if not cid or not _client_secret():
        messages.error(request, "YANDEX_DISK_CLIENT_ID / YANDEX_DISK_CLIENT_SECRET не заданы.")
        return redirect(_home_tab("connections"))

    state = secrets.token_urlsafe(32)
    request.session[OAUTH_STATE_SESSION_KEY] = state

    params = {
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": _callback_url(request),
        "force_confirm": "yes",
        "state": state,
    }
    url = f"{YANDEX_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(url)


@login_required
def callback(request):
    """Обработка коллбэка: обмен code на токены."""
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Яндекс OAuth вернул ошибку: {error}")
        return redirect(_home_tab("connections"))

    expected_state = request.session.pop(OAUTH_STATE_SESSION_KEY, None)
    received_state = request.GET.get("state")
    if not expected_state or expected_state != received_state:
        return HttpResponseBadRequest("invalid or missing OAuth state")

    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
    }
    try:
        resp = requests.post(YANDEX_TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        acc, _ = YandexDiskAccount.objects.update_or_create(
            user=request.user,
            defaults={
                "access_token": payload.get("access_token", ""),
                "refresh_token": payload.get("refresh_token", ""),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=payload.get("expires_in", 3600)),
            },
        )
        messages.success(request, "Яндекс.Диск подключён.")
    except requests.HTTPError as e:
        messages.error(request, f"Не удалось обменять код на токен: {e}")
    except Exception as e:
        messages.error(request, f"Ошибка при подключении к Яндекс.Диску: {e}")

    return redirect(_home_tab("connections"))


@login_required
def pick(request):
    """Страница выбора папки на Яндекс.Диске."""
    if not YandexDiskAccount.objects.filter(user=request.user).exists():
        messages.error(request, "Сначала подключите Яндекс.Диск.")
        return redirect(_home_tab("connections"))

    path = request.GET.get("path", "/")
    if not path.startswith("/"):
        path = "/" + path

    token = _get_access_token(request.user)
    if not token:
        messages.error(request, "Нет действительного токена. Подключите Яндекс.Диск заново.")
        return redirect(_home_tab("connections"))

    # Запрос к API для получения содержимого папки
    items = []
    parent_path = None
    current_name = path.rstrip("/").split("/")[-1] or "Диск"

    try:
        headers = {"Authorization": f"OAuth {token}"}
        params = {"path": path, "limit": 100, "fields": "_embedded.items.name,_embedded.items.path,_embedded.items.type"}
        resp = requests.get(f"{YANDEX_DISK_API}/resources", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        embedded = data.get("_embedded", {})
        for item in embedded.get("items", []):
            items.append({
                "name": item.get("name", ""),
                "path": item.get("path", "").replace("disk:", ""),
                "type": item.get("type", ""),  # "dir" или "file"
            })

        # Вычисляем родительский путь
        if path != "/":
            parts = path.rstrip("/").rsplit("/", 1)
            parent_path = parts[0] if parts[0] else "/"

    except requests.HTTPError as e:
        messages.error(request, f"Ошибка при получении списка файлов: {e}")
    except Exception as e:
        messages.error(request, f"Ошибка: {e}")

    # Показываем только папки
    folders = [it for it in items if it.get("type") == "dir"]

    current = YandexDiskSelection.objects.filter(user=request.user).first()

    return render(
        request,
        "yandexdisk_app/pick.html",
        {
            "items": folders,
            "current_path": path,
            "current_name": current_name,
            "parent_path": parent_path,
            "current": current,
        },
    )


@require_POST
@login_required
def select(request):
    """Сохранение выбранной папки."""
    resource_path = request.POST.get("resource_path", "").strip()
    resource_name = request.POST.get("resource_name", "").strip()
    resource_type = request.POST.get("resource_type", "dir").strip()

    if not resource_path:
        return HttpResponseBadRequest("missing resource_path")

    YandexDiskSelection.objects.update_or_create(
        user=request.user,
        defaults={
            "resource_path": resource_path,
            "resource_name": resource_name,
            "resource_type": resource_type,
            "public_url": "",
        },
    )

    messages.success(request, f"Выбрана папка: {resource_name or resource_path}")
    return redirect(_home_tab("connections"))


@require_POST
@login_required
def clear_selection(request):
    """Сброс выбора папки."""
    YandexDiskSelection.objects.filter(user=request.user).delete()
    messages.success(request, "Выбор Яндекс.Диска сброшен.")
    return redirect(_home_tab("connections"))


@require_POST
@login_required
def disconnect(request):
    """Удаление подключения Яндекс.Диска."""
    YandexDiskAccount.objects.filter(user=request.user).delete()
    YandexDiskSelection.objects.filter(user=request.user).delete()
    messages.success(request, "Подключение Яндекс.Диска удалено.")

    if request.headers.get("HX-Request") == "true":
        from onedrive_app.views import connections_partial as full_connections_partial
        return full_connections_partial(request)
    return redirect(_home_tab("connections"))