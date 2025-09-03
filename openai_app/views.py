from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.urls import reverse

from .models import OpenAIAccount

@login_required
@require_POST
def save_key(request):
    key = (request.POST.get("openai_api_key") or "").strip()
    if not key:
        messages.error(request, "Укажите API-ключ.")
    else:
        if not key.startswith("sk-"):
            messages.warning(request, "Ключ не начинается с «sk-». Сохраняю (локальная разработка).")
        OpenAIAccount.objects.update_or_create(user=request.user, defaults={"api_key": key})
        messages.success(request, "OpenAI API-ключ сохранён.")
    return redirect("/#connections")

@login_required
@require_POST
def delete_key(request):
    OpenAIAccount.objects.filter(user=request.user).delete()
    messages.success(request, "OpenAI API-ключ удалён.")
    return redirect("/#connections")