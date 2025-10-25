import json
import os
from urllib.parse import urlparse

import requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from .utils import send_paragraph, group_for_email
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .utils import send_text_as_paragraphs
from .utils import group_for_email, handle_llm_answer


from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings

from .utils import send_llm_answer_to_addin

def _origin(u: str) -> str:
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}"

def manifest_xml(request):
    ctx = {
        "base_url": settings.BASE_PUBLIC_URL,                 # например, https://imcmontan.ai
        "commands_url": settings.ADDIN_COMMANDS_URL,          # например, https://imcmontan.ai/addin/commands.html
        "taskpane_url": settings.ADDIN_TASKPANE_URL,          # dev: https://localhost:3000/taskpane.html
        "commands_origin": _origin(settings.ADDIN_COMMANDS_URL),
        "taskpane_origin": _origin(settings.ADDIN_TASKPANE_URL),
    }
    xml = render_to_string("office_addin/manifest.xml", ctx)
    return HttpResponse(xml, content_type="application/xml")




@require_GET
def ping(request):
    return JsonResponse({"ok": True, "service": "office_addin"})


@require_POST
def insert_demo(request):
    # сюда позже добавим прокси к OpenAI/логике
    return JsonResponse({"ok": True, "received": True})

@require_GET
def push_test(request):
    email = (request.GET.get("email") or "").strip()
    if not email:
        return JsonResponse({"ok": False, "error": "email required"}, status=400)
    group = group_for_email(email)
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(group, {
        "type": "addin.block",
        "block": {"kind": "paragraph.insert", "text": "Test from /api/addin/push-test"},
    })
    return JsonResponse({"ok": True, "group": group})

@require_GET
def push_paragraph(request):
    email = (request.GET.get("email") or "").strip()
    if not email:
        return HttpResponseBadRequest("email required")
    text = request.GET.get("text") or "Test paragraph from /api/addin/push-paragraph"
    style = request.GET.get("style") or "Normal"
    send_paragraph(email, text, style)
    return JsonResponse({"ok": True})

@csrf_exempt
@require_POST
def push_raw(request):
    email = (request.GET.get("email") or "").strip()
    if not email:
        return HttpResponseBadRequest("email required")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(f"bad json: {e}")
    # отправляем как есть (для проверки формата)
    layer = get_channel_layer()
    grp = group_for_email(email)
    async_to_sync(layer.group_send)(grp, payload)
    return JsonResponse({"ok": True, "sent": payload})

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://llm-relay-dev.imcmontanai.ru/v1")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY",  "")  # ключ для вашего relay

def ask_llm(prompt: str, model: str = None) -> str:
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = f"{OPENAI_BASE}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"} if OPENAI_KEY else {}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Отвечай кратко и только текстом без разметки."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()

@require_GET
def push_llm_demo(request):
    email = (request.GET.get("email") or "").strip()
    if not email:
        return HttpResponseBadRequest("email required")
    q = request.GET.get("q") or "Сгенерируй два коротких абзаца приветствия."
    model = request.GET.get("model") or None

    try:
        text = ask_llm(q, model=model)   # может прийти DocOps в ```docops/```json или чистый текст
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"llm_request_failed: {e}"}, status=502)

    try:
        sent = send_llm_answer_to_addin(email, text)  # ← ВАЖНО: не send_text_as_paragraphs!
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"ws_send_failed: {e}"}, status=500)

    return JsonResponse({"ok": True, "chars": len(text), "sent_ops": sent})

@csrf_exempt
@require_POST
def push_docops_text(request):
    email = (request.GET.get("email") or "").strip()
    if not email:
        return HttpResponseBadRequest("email required")
    raw = request.body.decode("utf-8", errors="replace")  # может быть ```docops, чистый JSON или просто текст
    group = group_for_email(email)
    sent = handle_llm_answer(raw, group)                  # сам распарсит/сделает fallback и разошлёт по WS
    return JsonResponse({"ok": True, "sent_ops": sent})