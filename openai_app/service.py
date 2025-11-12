from __future__ import annotations
from typing import List, Optional, Tuple
import os

from urllib.parse import urlparse
from django.conf import settings

import mimetypes


# ---- Вспомогательные настройки из ENV/Django settings ----

def _org_id() -> str | None:
    return _env("OPENAI_ORG_ID") or _env("OPENAI_ORGANIZATION")

def _project_id() -> str | None:
    return _env("OPENAI_PROJECT_ID") or _env("OPENAI_PROJECT")

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
    - если base_url указывает на релей — используем общий OPENAI_API_KEY из ENV;
    - иначе: сначала ключ из БД, иначе из ENV (обычный sk-ключ).
    Пробрасываем organization/project только при прямом доступе к api.openai.com.
    """
    from openai import OpenAI  # чтобы импорт точно был до вызова

    base_url = _base_url()
    is_relay = _is_relay(base_url)

    # 1) API-ключ
    if is_relay:
        api_key = (_env("OPENAI_API_KEY") or "").strip()
    else:
        api_key = (_get_api_key_for(user) or _env("OPENAI_API_KEY") or "").strip()

    if not api_key:
        return None  # пусть вызывающая сторона обработает отсутствие клиента

    # 2) Базовые аргументы клиента
    kwargs = {"api_key": api_key, "base_url": base_url}

    # 3) org/project — только для прямого API
    if not is_relay:
        org = _org_id()
        prj = _project_id()
        if org:
            kwargs["organization"] = org
        if prj:
            kwargs["project"] = prj

    # 4) Конструируем клиент; фолбэк для старых SDK
    try:
        return OpenAI(**kwargs)
    except TypeError:
        headers = {}
        if not is_relay:
            if _org_id():
                headers["OpenAI-Organization"] = _org_id()
            if _project_id():
                headers["OpenAI-Project"] = _project_id()
        return OpenAI(api_key=api_key, base_url=base_url, default_headers=headers)

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


import io
from typing import List, Tuple, Optional


def _guess_mime(name: str | None, default: str = "application/octet-stream") -> str:
    if not name:
        return default
    mt, _ = mimetypes.guess_type(name)
    return mt or default


def run_prompt_with_files(user, model: str, prompt: str,
                          attachments: List[Tuple] | None,
                          temperature: float | None = None) -> str:
    """
    Отправляет промпт + файлы в OpenAI Responses:
    - PDF -> input_file
    - image/* -> input_image
    - docx/txt/csv/md/json -> как input_text (извлекаем / декодируем)
    attachments: [(name, bytes)] или [(name, bytes, mime)]
    """
    client = get_client(user)
    if client is None:
        raise RuntimeError("OpenAI не подключён.")

    # Нет Responses API? Фолбэк — просто текст.
    if not hasattr(client, "responses"):
        return run_prompt(user, model, prompt, temperature=temperature)

    # Нормализуем список вложений
    norm = []
    for a in (attachments or []):
        if isinstance(a, dict):
            name = a.get("name") or "file"
            data = a.get("data") or a.get("bytes")
            mime = a.get("mime") or _guess_mime(name)
        else:
            # tuple формы: (name, bytes) ИЛИ (name, bytes, mime)
            if len(a) >= 3:
                name, data, mime = a[0], a[1], a[2]
            else:
                name, data = a[0], a[1]
                mime = _guess_mime(name)
        if not data:
            continue
        norm.append((name, data, mime))

    pdf_ids: list[str] = []
    image_ids: list[str] = []
    text_chunks: list[str] = []

    # Перебор вложений
    for name, data, mime in norm:
        mt = (mime or "").lower()
        # PDF -> input_file
        if mt == "application/pdf" or (name or "").lower().endswith(".pdf"):
            try:
                up = client.files.create(file=(name or "file.pdf", io.BytesIO(data)), purpose="assistants")
                pdf_ids.append(up.id)
            except Exception:
                continue
            continue

        # Картинки -> input_image
        if mt.startswith("image/"):
            try:
                up = client.files.create(file=(name or "image", io.BytesIO(data)), purpose="assistants")
                image_ids.append(up.id)
            except Exception:
                continue
            continue

        # DOCX -> извлечь текст
        if (name or "").lower().endswith(".docx") or mt == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            try:
                from docx import Document  # python-docx
                from io import BytesIO
                doc = Document(BytesIO(data))
                txt = []
                for p in doc.paragraphs:
                    if p.text:
                        txt.append(p.text)
                text = "\n".join(txt).strip()
                if text:
                    text_chunks.append(f"----- {name} -----\n{text}")
            except Exception:
                # если не вышло — пропускаем
                pass
            continue

        # Текстовые форматы -> input_text
        if mt.startswith("text/") or (name or "").lower().endswith((".txt", ".md", ".csv", ".json")):
            try:
                # ограничим объём, чтобы не упереться в лимиты модели
                text = (data.decode("utf-8", errors="replace"))[:200_000]
                if text.strip():
                    text_chunks.append(f"----- {name} -----\n{text}")
            except Exception:
                pass
            continue

        # Прочее (xls, ppt, zip и т.п.) — пропускаем
        # при необходимости добавьте конвертацию в PDF на вашей стороне
        continue

    # Формируем parts
    parts = [{"type": "input_text", "text": prompt}]
    for t in text_chunks:
        parts.append({"type": "input_text", "text": t})
    for fid in pdf_ids:
        parts.append({"type": "input_file", "file_id": fid})
    for fid in image_ids:
        parts.append({"type": "input_image", "image_file": {"file_id": fid}})

    req = {
        "model": model,
        "input": [{
            "role": "user",
            "content": parts,
        }],
    }
    if temperature is not None:
        req["temperature"] = float(temperature)

    try:
        resp = client.responses.create(**req)
    except TypeError:
        # очень старый SDK — фолбэк: только текст
        return run_prompt(user, model, prompt, temperature=temperature)

    text = getattr(resp, "output_text", None)
    if text:
        return text.strip()

    # универсальный парс
    try:
        chunks = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(getattr(c, "text", None), "value", None)
                if t:
                    chunks.append(t)
        if chunks:
            return "\n".join(chunks).strip()
    except Exception:
        pass

    return str(resp)