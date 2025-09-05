from __future__ import annotations
from typing import List, Optional, Tuple
import os

from urllib.parse import urlparse

from django.conf import settings

# ---- Вспомогательные настройки из ENV/Django settings ----

def _env(key, default=None):
    return getattr(settings, key, None) or os.environ.get(key, default)

def _base_url() -> str:
    # поддержим оба названия переменных, чтобы не ломать prod:
    return _env("OPENAI_BASE_URL", _env("OPENAI_API_BASE", "https://api.openai.com/v1")).rstrip("/")

def _curated_fallback() -> List[str]:
    # Модели «по умолчанию», если список не удалось получить
    return getattr(settings, "OPENAI_DEFAULT_MODELS", [
        "gpt-4o-mini",
        "o4-mini",
        "gpt-4.1-mini",
        "gpt-4o",
        "o4",
        "gpt-4.1",
    ])

# ---- Получение клиента и ключа ----

def _get_api_key_for(user):
    try:
        from .models import OpenAIAccount
        acc = OpenAIAccount.objects.filter(user=user).first()
        if acc and acc.api_key:
            return acc.api_key.strip()
    except Exception:
        pass
    k = _env("OPENAI_API_KEY")
    return k.strip() if k else None

def _is_relay(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host != "" and host != "api.openai.com"

def get_client(user):
    """
    Возвращает OpenAI client, корректно выбирая ключ:
    - если base_url указывает на релей — всегда используем RELAY_TOKEN из ENV (OPENAI_API_KEY);
    - иначе: сначала ключ из БД, иначе из ENV (обычный sk-ключ).
    """
    try:
        from openai import OpenAI
    except Exception:
        return None

    base_url = _base_url()

    if _is_relay(base_url):
        # Работает через релей — используем общий RELAY_TOKEN из ENV и игнорируем БД
        api_key = (_env("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return None
    else:
        # Прямое подключение к OpenAI — поддерживаем персональные ключи из БД
        api_key = (_get_api_key_for(user) or _env("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return None

    return OpenAI(api_key=api_key, base_url=base_url)

# ---- Работа со списком моделей ----

def get_available_models(user) -> List[str]:
    """
    Возвращает список ID моделей из /v1/models.
    Если не удаётся — отдаёт curated fallback.
    """
    client = get_client(user)
    if client is None:
        return []

    try:
        resp = client.models.list()
        ids = [m.id for m in getattr(resp, "data", []) if getattr(m, "id", None)]
        if not ids:
            return _curated_fallback()

        # Переключаемая фильтрация (по умолчанию — БЕЗ фильтра)
        if getattr(settings, "OPENAI_FILTER_MODELS", False):
            allow_prefixes = getattr(settings, "OPENAI_ALLOWED_PREFIXES", ("gpt-4", "gpt-4o", "o4"))
            filtered = [mid for mid in ids if mid.startswith(tuple(allow_prefixes))]
            return filtered or ids
        return ids
    except Exception:
        return _curated_fallback()

# ---- Новые модели, которые нужно вызывать через /v1/responses ----
# Держим всё в нижнем регистре и проверяем как "равно" или "начинается с <prefix>-"
_NEW_STYLE_PREFIXES = tuple(x.lower() for x in (
    "o4", "o4-mini",
    "o3", "o3-mini",
    "gpt-4o", "gpt-4o-mini",
    "gpt-4.1", "gpt-4.1-mini",
))

def _use_responses_api(model: str) -> bool:
    """
    Новые модели (o4 / o3 / gpt-4o / gpt-4.1*) корректно работают через /v1/responses.
    Для старых (например, gpt-4-0613) безопаснее использовать /v1/chat/completions.
    """
    m = (model or "").strip().lower()
    if not m:
        return False
    return any(m == p or m.startswith(p + "-") for p in _NEW_STYLE_PREFIXES)

def _is_unsupported_temperature_error(err: Exception) -> bool:
    s = str(err).lower()
    return ("unsupported value" in s and "temperature" in s) or ("param': 'temperature" in s)

def run_prompt(user, model: str, prompt: str, temperature: float | None = None) -> str:
    """
    Выполняет запрос к выбранной модели и возвращает текст ответа.
    temperature:
      - None  → вообще не передавать параметр (значение по умолчанию модели);
      - число → передать в вызов, при 400 (unsupported) ретраим без temperature.
    """
    client = get_client(user)
    if client is None:
        raise RuntimeError("OpenAI не подключён")

    # 1) Новые модели — через /v1/responses
    if _use_responses_api(model):
        try:
            kwargs = {"model": model, "input": prompt}
            if temperature is not None:
                kwargs["temperature"] = temperature
            resp = client.responses.create(**kwargs)
            text = getattr(resp, "output_text", None)
            if text:
                return text.strip()
            parts = []
            for item in getattr(resp, "output", []):
                if getattr(item, "type", "") == "message":
                    for content in getattr(item, "content", []):
                        if getattr(content, "type", "") == "text":
                            parts.append(getattr(content, "text", ""))
            return "".join(parts).strip()
        except Exception as e:
            if temperature is not None and _is_unsupported_temperature_error(e):
                # повтор без temperature
                resp = client.responses.create(model=model, input=prompt)
                text = getattr(resp, "output_text", None)
                return text.strip() if text else ""
            raise RuntimeError(f"Ошибка responses.create: {e}")

    # 2) Старые модели — через /v1/chat/completions
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        if temperature is not None:
            chat = client.chat.completions.create(temperature=temperature, **payload)
        else:
            chat = client.chat.completions.create(**payload)
    except Exception as e:
        if temperature is not None and _is_unsupported_temperature_error(e):
            chat = client.chat.completions.create(**payload)
        else:
            raise RuntimeError(f"Ошибка chat.completions.create: {e}")

    msg = chat.choices[0].message
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    return (content or "").strip()