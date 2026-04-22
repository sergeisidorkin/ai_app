from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.conf import settings

from policy_app.models import DEPARTMENT_HEAD_GROUP
from users_app.models import Employee
from core.cloud_storage import (
    get_cloud_storage_settings,
    get_nextcloud_connection_status,
    get_nextcloud_root_path,
    get_primary_cloud_storage_label,
    set_nextcloud_root_path,
    set_primary_cloud_storage,
)
from nextcloud_app.services import build_nextcloud_overview
from yandexdisk_app.models import YandexDiskAccount, YandexDiskSelection
from smtp_app.forms import ExternalSMTPAccountForm
from smtp_app.models import ExternalSMTPAccount

from .graph import get_auth_url, exchange_code, list_children
from .models import OneDriveSelection, OneDriveAccount

# openai — опционально
try:
    from openai_app.models import OpenAIAccount
except Exception:
    OpenAIAccount = None


def _home_tab(tab: str) -> str:
    """Ссылка на домашнюю страницу с выбранной вкладкой (#templates | #connections)."""
    return reverse("home") + f"#{tab}"

def _onedrive_redirect_uri_for(request) -> str:
    """
    Локально возвращаем http://localhost:{порт}/onedrive/callback
    (порт берём из текущего запроса), чтобы не привязываться к 8000.
    В проде — settings.MS_REDIRECT_URI.
    """
    scheme = "https" if request.is_secure() else "http"
    host = (request.get_host() or "").lower()       # напр. "localhost:8001" | "127.0.0.1:8001" | "imcmontan.ai"
    hostname, _, port = host.partition(":")
    port = port or ("443" if request.is_secure() else "80")

    if hostname in ("localhost", "127.0.0.1"):
        # На локали жёстко используем localhost, но сохраняем порт текущего запроса
        # (Azure любит localhost, а не 127.0.0.1).
        default_port = "443" if request.is_secure() else "80"
        port_part = "" if port == default_port else f":{port}"
        return f"{scheme}://localhost{port_part}/onedrive/callback"

    # Продовый случай — как было
    return settings.MS_REDIRECT_URI


def _connections_context(request):
    selection = OneDriveSelection.objects.filter(user=request.user).first()
    onedrive_connected = OneDriveAccount.objects.filter(user=request.user).exists()
    openai = OpenAIAccount.objects.filter(user=request.user).first() if OpenAIAccount else None

    gdrive_connected = bool(request.session.get("gdrive_tokens"))
    gdrive_selection = request.session.get("gdrive_selection") or None

    yadisk_connected = YandexDiskAccount.objects.filter(user=request.user).exists()
    yadisk_selection = YandexDiskSelection.objects.filter(user=request.user).first()
    smtp_account = ExternalSMTPAccount.objects.filter(user=request.user).first()
    smtp_form = ExternalSMTPAccountForm(instance=smtp_account, user=request.user)
    employee = Employee.objects.filter(user=request.user).first()
    employee_role = getattr(employee, "role", "") or ""
    smtp_only_connections = employee_role == DEPARTMENT_HEAD_GROUP
    storage_settings = get_cloud_storage_settings()
    nextcloud_status = get_nextcloud_connection_status()
    nextcloud_overview = build_nextcloud_overview(request.user)

    return {
        "selection": selection,
        "onedrive_connected": onedrive_connected,
        "openai": openai,
        "gdrive_connected": gdrive_connected,
        "gdrive_selection": gdrive_selection,
        "yadisk_connected": yadisk_connected,
        "yadisk_selection": yadisk_selection,
        "smtp_account": smtp_account,
        "smtp_form": smtp_form,
        "smtp_only_connections": smtp_only_connections,
        "primary_cloud_storage": storage_settings.primary_storage,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "can_manage_primary_cloud_storage": bool(request.user.is_superuser),
        "nextcloud_root_path": get_nextcloud_root_path(),
        "nextcloud_root_configured": bool(get_nextcloud_root_path()),
        "nextcloud_connection_status": nextcloud_status.code,
        "nextcloud_connection_status_label": nextcloud_status.label,
        "nextcloud_enabled": bool(nextcloud_overview.get("nextcloud_enabled")),
        "nextcloud_launch_url": str(nextcloud_overview.get("nextcloud_launch_url") or ""),
        "can_manage_nextcloud_root": bool(request.user.is_superuser),
    }

@login_required
def connections_partial(request):
    """
    Фрагмент для вкладки «Подключения» на домашней странице.
    Рендерит onedrive_app/templates/onedrive_app/connections_partial.html
    """
    return render(
        request,
        "onedrive_app/connections_partial.html",
        _connections_context(request),
    )


@login_required
@require_POST
def primary_cloud_storage_update(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Недостаточно прав для изменения основного облачного хранилища.")

    value = (request.POST.get("primary_storage") or "").strip()
    try:
        set_primary_cloud_storage(value)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    return connections_partial(request)


@login_required
@require_POST
def nextcloud_root_update(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Недостаточно прав для изменения корпоративного root каталога Nextcloud.")

    value = request.POST.get("nextcloud_root_path", "")
    try:
        set_nextcloud_root_path(value)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    return connections_partial(request)

def _redirect_to_localhost_if_needed(request):
    """
    Если пользователь зашел по 127.0.0.1, а Azure требует localhost,
    на критичных шагах (connect/pick) жёстко переводим на localhost,
    сохраняя порт, путь и query.
    Прод на это не реагирует.
    """
    host = request.get_host()  # например: "127.0.0.1:8000" или "localhost:8000" или "imcmontanai.ru"
    if host.startswith("127.0.0.1"):
        # сохранить порт
        if ":" in host:
            _, port = host.split(":", 1)
            new_host = f"localhost:{port}"
        else:
            new_host = "localhost"
        new_url = f"{request.scheme}://{new_host}{request.get_full_path()}"
        return redirect(new_url)
    return None

@login_required
def connect(request):
    ru = _onedrive_redirect_uri_for(request)
    request.session["od_redirect_uri"] = ru  # зафиксируем на время флоу
    return redirect(get_auth_url("connect", redirect_uri=ru))

@login_required
def pick(request):
    # список тоже должен открываться на localhost, иначе потеряем сессию между 127 и localhost
    r = _redirect_to_localhost_if_needed(request)
    if r:
        return r

    parent = request.GET.get("folder")  # id папки
    data = list_children(request.user, parent) or {"value": []}

    # показываем только папки
    only_folders = [it for it in data.get("value", []) if it.get("folder")]

    current = OneDriveSelection.objects.filter(user=request.user).first()
    context = {"items": only_folders, "parent": parent, "current": current}
    return render(request, "onedrive_app/pick.html", context)

@login_required
def callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")

    # используем ТО ЖЕ значение, что и на шаге авторизации
    ru = request.session.pop("od_redirect_uri", _onedrive_redirect_uri_for(request))
    try:
        exchange_code(request.user, code, redirect_uri=ru)
        messages.success(request, "OneDrive подключён.")
    except Exception as e:
        messages.error(request, f"Не удалось подключить OneDrive: {e}")
    return redirect(_home_tab("connections"))

@require_POST
@login_required
def select(request):
    """Сохранить выбор ПАПКИ (только папки!) в БД и перейти в раздел «Подключения»."""
    item_id = request.POST.get("item_id")
    if not item_id:
        return HttpResponseBadRequest("missing item_id")

    # ⬇️ Жёсткая проверка — разрешаем только папки
    is_folder = request.POST.get("is_folder") == "1"
    if not is_folder:
        return HttpResponseBadRequest("only folders can be selected")

    item_name = request.POST.get("item_name", "")
    item_path = request.POST.get("item_path", "")
    web_url   = request.POST.get("web_url", "")
    drive_id  = request.POST.get("drive_id", "")

    OneDriveSelection.objects.update_or_create(
        user=request.user,
        defaults={
            "drive_id": drive_id,
            "item_id": item_id,
            "item_name": item_name,
            "item_path": item_path,
            "web_url": web_url,
            "is_folder": True,  # ⬅️ фиксируем как папку
        },
    )

    messages.success(request, f"Выбрана папка: {item_name}")
    return redirect(_home_tab("connections"))


@require_POST
@login_required
def clear_selection(request):
    OneDriveSelection.objects.filter(user=request.user).delete()
    messages.success(request, "Выбор OneDrive файла/папки сброшен.")
    return redirect(_home_tab("connections"))

@login_required
@require_POST
def disconnect(request):
    """Удаляет подключение OneDrive и сбрасывает выбор."""
    OneDriveAccount.objects.filter(user=request.user).delete()
    OneDriveSelection.objects.filter(user=request.user).delete()
    messages.success(request, "Подключение OneDrive удалено.")
    # Если вызов из HTMX — вернём свежий partial, иначе редирект на главную
    if request.headers.get("HX-Request") == "true":
        return connections_partial(request)
    return redirect("/")