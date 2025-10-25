# openai_app/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import OpenAIAccount

# наш мини-клиент LLM
from .llm import ask_llm
# утилиты для пуша в аддин
from office_addin.utils import send_text_as_paragraphs, group_for_email

from django.utils.timezone import now
import logging, time

from office_addin.utils import send_text_as_paragraphs

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


# === Новый минимальный мост LLM -> Word Add-in ===

@require_GET
def push_llm_to_addin(request):
    t0 = time.time()
    email = (request.GET.get("email") or "").strip()
    q     = (request.GET.get("q") or "").strip()
    mode  = (request.GET.get("mode") or "").strip().lower()  # "", "dry"
    style = (request.GET.get("style") or "Normal").strip()

    if not email:
        return JsonResponse({"ok": False, "error": "email is required"}, status=400)

    try:
        logging.info("[LLM->ADDIN] start email=%s mode=%s q_len=%s", email, mode, len(q))

        if mode == "dry":
            text = "Абзац A.\n\nАбзац B."
        else:
            text = q or "Сделай два очень коротких абзаца для проверки."
            text = ask_llm(text)

        sent = send_text_as_paragraphs(email, text, styleBuiltIn=style)
        ms = int((time.time() - t0) * 1000)
        logging.info("[LLM->ADDIN] pushed paragraphs: %s in %sms", sent, ms)
        return JsonResponse({"ok": True, "paragraphs": sent, "mode": mode, "elapsed_ms": ms})
    except Exception as e:
        logging.exception("push_llm_to_addin failed")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)