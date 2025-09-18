from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse

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
    TODO: заменить на реальный redirect к Google OAuth.
    """
    messages.info(request, "Google Drive: страница авторизации ещё не настроена.")
    return redirect(reverse("gdrive_connections_partial"))

@login_required
def callback(request):
    """
    Обработка коллбэка от Google OAuth2.
    TODO: обмен кода на токен, сохранение в БД, проверка аккаунта.
    """
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")
    messages.success(request, "Google Drive: получен код авторизации (заглушка).")
    return redirect(reverse("gdrive_connections_partial"))

@login_required
def pick(request):
    """
    Выбор файла/папки (заглушка).
    """
    return render(request, "googledrive_app/panel.html", {"gdrive_connected": True})

@login_required
def select(request):
    """
    Сохранение выбранного файла/папки (заглушка).
    """
    messages.success(request, "Google Drive: выбор сохранён (заглушка).")
    return redirect(reverse("gdrive_connections_partial"))

@login_required
def disconnect(request):
    """
    Удалить подключение (заглушка).
    """
    messages.success(request, "Google Drive: подключение удалено (заглушка).")
    return redirect(reverse("gdrive_connections_partial"))