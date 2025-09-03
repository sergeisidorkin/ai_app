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
    try:
        from openai import OpenAI
    except Exception:
        return None

    api_key = _get_api_key_for(user)
    if not api_key:
        return None

    base_url = _base_url()

    # ⬇️ Автопочинка: если идём в релей, но ключ похож на sk-..., подставляем RELAY_TOKEN из ENV
    if _is_relay(base_url) and api_key.startswith("sk-"):
        env_token = _env("OPENAI_API_KEY")
        if env_token and not env_token.startswith("sk-"):
            api_key = env_token.strip()

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
        # Оставим «разумные» чатовые модели в приоритете
        allow_prefixes = ("gpt-4", "gpt-4o", "o4")
        filtered = [mid for mid in ids if mid.startswith(allow_prefixes)]
        return filtered or ids
    except Exception:
        return _curated_fallback()

# ---- Вызов модели ----

_NEW_STYLE = {"o4", "o4-mini", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"}

def _use_responses_api(model: str) -> bool:
    """
    Новые модели (o4 / gpt-4o / gpt-4.1*) корректно работают через /v1/responses.
    Для старых (например, gpt-4-0613) безопаснее использовать /v1/chat/completions.
    """
    m = (model or "").lower()
    return any(m == x or m.startswith(x + "-") for x in (s.lower() for s in _NEW_STYLE))

def run_prompt(user, model: str, prompt: str) -> str:
    """
    Выполняет запрос к выбранной модели и возвращает текст ответа.
    Бросает исключение, если клиент не настроен или вызов не удался.
    """
    client = get_client(user)
    if client is None:
        raise RuntimeError("OpenAI не подключён")

    # 1) Новые модели — через /v1/responses
    if _use_responses_api(model):
        try:
            resp = client.responses.create(model=model, input=prompt)
            # Пытаемся взять output_text (новый SDK)
            text = getattr(resp, "output_text", None)
            if text:
                return text.strip()

            # Фоллбек-разбор структуры
            parts = []
            for item in getattr(resp, "output", []):
                if getattr(item, "type", "") == "message":
                    for content in getattr(item, "content", []):
                        if getattr(content, "type", "") == "text":
                            parts.append(getattr(content, "text", ""))
            return "".join(parts).strip()
        except Exception as e:
            raise RuntimeError(f"Ошибка responses.create: {e}")

    # 2) Старые модели — через /v1/chat/completions
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        msg = chat.choices[0].message
        # У новых SDK message может быть объектом с .content
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            # когда content — массив частичных блоков
            return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
        return (content or "").strip()
    except Exception as e:
        raise RuntimeError(f"Ошибка chat.completions.create: {e}")