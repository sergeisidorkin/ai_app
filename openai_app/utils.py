from typing import List, Dict
from openai import OpenAI
from django.contrib.auth import get_user_model
from .models import OpenAIAccount

# Возвращаем инициализированный клиент OpenAI для пользователя или None
def get_openai_client_for(user) -> OpenAI | None:
    acct = OpenAIAccount.objects.filter(user=user).first()
    if not acct or not acct.api_key:
        return None
    # organization/project по желанию, если поля есть в модели
    kwargs = {"api_key": acct.api_key}
    if getattr(acct, "organization", None):
        kwargs["organization"] = acct.organization
    if getattr(acct, "project", None):
        kwargs["project"] = acct.project
    return OpenAI(**kwargs)

def list_openai_models(user) -> List[Dict[str, str]]:
    """
    Возвращает список моделей для выпадающего списка:
    [{ "id": "gpt-4o-mini", "label": "OpenAI · gpt-4o-mini" }, ...]
    Если подключения нет или запрос не удался — пустой список.
    """
    client = get_openai_client_for(user)
    if not client:
        return []

    try:
        # Получим список моделей и отфильтруем: оставим популярные чат-модели.
        models = client.models.list()
        ids = [m.id for m in models.data]  # type: ignore[attr-defined]

        # Сузим до чатов (актуальные семейства под GPT/o*)
        preferred_prefixes = ("gpt-4", "gpt-4o", "o4", "gpt-3.5", "gpt-4.1")
        chat_like = [mid for mid in ids if mid.startswith(preferred_prefixes)]

        # На случай, если API вернул нежданчик — небольшой curated fallback
        if not chat_like:
            chat_like = ["gpt-4o-mini", "o4-mini", "gpt-4.1-mini"]

        return [{"id": mid, "label": f"OpenAI · {mid}"} for mid in sorted(set(chat_like))]
    except Exception:
        # Тихий фолбэк, чтобы не рушить дашборд
        return [{"id": "gpt-4o-mini", "label": "OpenAI · gpt-4o-mini"}]