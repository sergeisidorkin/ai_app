from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.urls import reverse

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


@login_required
def connections_partial(request):
    """
    Фрагмент для вкладки «Подключения» на домашней странице.
    Рендерит onedrive_app/templates/onedrive_app/connections_partial.html
    """
    selection = OneDriveSelection.objects.filter(user=request.user).first()
    onedrive_connected = OneDriveAccount.objects.filter(user=request.user).exists()
    openai = OpenAIAccount.objects.filter(user=request.user).first() if OpenAIAccount else None

    return render(
        request,
        "onedrive_app/connections_partial.html",
        {
            "selection": selection,
            "onedrive_connected": onedrive_connected,
            "openai": openai,
        },
    )


@login_required
def connect(request):
    return redirect(get_auth_url("connect"))


@login_required
def callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")

    try:
        exchange_code(request.user, code)
        messages.success(request, "OneDrive подключён.")
    except Exception as e:
        messages.error(request, f"Не удалось подключить OneDrive: {e}")

    # Возвращаемся на стартовую страницу в раздел «Подключения»
    return redirect(_home_tab("connections"))


@login_required
def pick(request):
    """Список содержимого корня или выбранной папки (folder=item_id)."""
    parent = request.GET.get("folder")  # id папки
    data = list_children(request.user, parent) or {"value": []}

    current = OneDriveSelection.objects.filter(user=request.user).first()
    context = {
        "items": data["value"],
        "parent": parent,
        "current": current,
    }
    return render(request, "onedrive_app/pick.html", context)


@require_POST
@login_required
def select(request):
    """Сохранить выбор файла/папки в БД и перейти в раздел «Подключения»."""
    item_id = request.POST.get("item_id")
    if not item_id:
        return HttpResponseBadRequest("missing item_id")

    item_name = request.POST.get("item_name", "")
    item_path = request.POST.get("item_path", "")
    web_url   = request.POST.get("web_url", "")
    drive_id  = request.POST.get("drive_id", "")
    is_folder = request.POST.get("is_folder") == "1"

    OneDriveSelection.objects.update_or_create(
        user=request.user,
        defaults={
            "drive_id": drive_id,
            "item_id": item_id,
            "item_name": item_name,
            "item_path": item_path,
            "web_url": web_url,
            "is_folder": is_folder,
        },
    )

    what = "папка" if is_folder else "файл"
    messages.success(request, f"Выбран {what}: {item_name}")
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