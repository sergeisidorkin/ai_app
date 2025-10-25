# openai_app/llm.py
import os
import requests
from django.conf import settings

BASE = getattr(settings, "OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://llm-relay-dev.imcmontanai.ru/v1"))
DEFAULT_KEY = getattr(settings, "OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))

def ask_llm(prompt: str, api_key: str | None = None, model: str = "gpt-4o-mini") -> str:
    """
    Минимальный вызов /v1/chat/completions к вашему релею.
    Возвращает текст первого completion.
    """
    key = api_key or DEFAULT_KEY
    if not key:
        raise RuntimeError("OPENAI_API_KEY is empty")

    url = f"{BASE}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()