from typing import List
from django.conf import settings

def _curated_fallback() -> List[str]:
    # Модели, которые чаще всего нужны. Используем как запасной вариант,
    # если вызов /v1/models недоступен (но только когда ключ сохранён).
    return getattr(settings, "OPENAI_DEFAULT_MODELS", [
        "gpt-4o-mini",
        "o4-mini",
        "gpt-4.1-mini",
        "gpt-4o",
        "o4",
        "gpt-4.1",
    ])

def get_client(user):
    """
    Возвращает OpenAI client, настроенный на ключ пользователя.
    Вернёт None, если подключение OpenAI не настроено.
    """
    try:
        from openai import OpenAI
        from .models import OpenAIAccount
    except Exception:
        return None

    acc = OpenAIAccount.objects.filter(user=user).first()
    if not acc or not acc.api_key:
        return None

    # Если хочешь поддержать org/project headers — добавь поля в модель и сюда
    client = OpenAI(api_key=acc.api_key)
    return client

def get_available_models(user) -> List[str]:
    """
    Возвращает список ID моделей, доступных пользователю.
    Если OpenAI не подключён — пустой список.
    Если подключён, но запрос к API не удался — вернём curated fallback.
    """
    client = get_client(user)
    if client is None:
        return []

    try:
        resp = client.models.list()
        # resp.data — список объектов с полем id
        ids = [m.id for m in getattr(resp, "data", []) if getattr(m, "id", None)]
        if not ids:
            # если ответ пустой — всё равно отдадим fallback
            return _curated_fallback()
        # Опциональная фильтрация «разумных» чат-моделей
        allow_prefixes = ("gpt-4", "gpt-4o", "o4")
        filtered = [mid for mid in ids if mid.startswith(allow_prefixes)]
        return filtered or ids  # если фильтр слишком строгий — отдаём всё
    except Exception:
        # сеть/ключ/доступ — дадим fallback, чтобы в UI хоть что-то выбрать
        return _curated_fallback()

def run_prompt(user, model: str, prompt: str) -> str:
    """
    Выполняет запрос к выбранной модели и возвращает текст ответа.
    Бросает исключение, если OpenAI не подключён или запрос не удался.
    """
    client = get_client(user)
    if client is None:
        raise RuntimeError("OpenAI не подключён")

    # Универсальный вызов под новые модели
    resp = client.responses.create(model=model, input=prompt)

    # Пытаемся получить склеенный текст (новые версии SDK)
    text = getattr(resp, "output_text", None)
    if text:
        return text

    # Фоллбек: распарсим структуру вручную
    parts = []
    for item in getattr(resp, "output", []):
        if getattr(item, "type", "") == "message":
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "text":
                    parts.append(getattr(content, "text", ""))
    return "".join(parts).strip()