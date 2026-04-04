from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.utils import timezone

CBR_EUR_DAILY_XML_URL = "http://www.cbr.ru/scripts/XML_daily.asp"
CBR_EUR_DAILY_PAGE_URL = "https://www.cbr.ru/currency_base/daily/"

_EUR_RATE_CACHE: dict[str, object] = {
    "date": None,
    "value": None,
    "fetched_at": None,
}
_EUR_RATE_CACHE_LOCK = Lock()
_EUR_RATE_CACHE_FILE = Path(tempfile.gettempdir()) / "ai_app_cbr_eur_rate.json"


def _parse_cbr_decimal(value: str) -> Decimal | None:
    normalized = str(value or "").replace(" ", "").replace("\xa0", "").replace(",", ".").strip()
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _read_file_cache(today) -> Decimal | None:
    try:
        payload = json.loads(_EUR_RATE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(payload.get("date") or "") != today.isoformat():
        return None
    return _parse_cbr_decimal(str(payload.get("value") or ""))


def _write_file_cache(today, value: Decimal) -> None:
    try:
        _EUR_RATE_CACHE_FILE.write_text(
            json.dumps({"date": today.isoformat(), "value": format(value, "f")}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        return


def _fetch_cbr_payload() -> bytes | None:
    request = Request(
        CBR_EUR_DAILY_XML_URL,
        headers={"User-Agent": "Mozilla/5.0 ai_app/1.0"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.read()
    except Exception:
        pass

    curl_path = shutil.which("curl")
    if not curl_path:
        return None
    try:
        result = subprocess.run(
            [curl_path, "-fsSL", "--max-time", "10", CBR_EUR_DAILY_XML_URL],
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def get_cbr_eur_rate_for_today() -> Decimal | None:
    now = timezone.now()
    today = timezone.localdate()

    with _EUR_RATE_CACHE_LOCK:
        cached_date = _EUR_RATE_CACHE.get("date")
        fetched_at = _EUR_RATE_CACHE.get("fetched_at")
        if (
            cached_date == today
            and _EUR_RATE_CACHE.get("value") is not None
            and fetched_at is not None
            and now - fetched_at < timedelta(hours=12)
        ):
            return _EUR_RATE_CACHE["value"]  # type: ignore[return-value]

    cached_file_value = _read_file_cache(today)
    if cached_file_value is not None:
        with _EUR_RATE_CACHE_LOCK:
            _EUR_RATE_CACHE["date"] = today
            _EUR_RATE_CACHE["value"] = cached_file_value
            _EUR_RATE_CACHE["fetched_at"] = now
        return cached_file_value

    payload = _fetch_cbr_payload()
    if not payload:
        return None

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None

    eur_rate = None
    for item in root.findall("Valute"):
        char_code = (item.findtext("CharCode") or "").strip().upper()
        if char_code != "EUR":
            continue
        nominal = _parse_cbr_decimal(item.findtext("Nominal") or "1") or Decimal("1")
        value = _parse_cbr_decimal(item.findtext("Value") or "")
        if value is None or nominal == 0:
            return None
        eur_rate = value / nominal
        break

    if eur_rate is None:
        return None

    with _EUR_RATE_CACHE_LOCK:
        _EUR_RATE_CACHE["date"] = today
        _EUR_RATE_CACHE["value"] = eur_rate
        _EUR_RATE_CACHE["fetched_at"] = now
    _write_file_cache(today, eur_rate)

    return eur_rate


def get_cbr_rate_date_label(target_date=None) -> str:
    value = target_date or timezone.localdate()
    return value.strftime("%d.%m.%Y")


def get_cbr_eur_rate_text(target_date=None) -> str:
    return f"Курс евро Банка России на {get_cbr_rate_date_label(target_date)}:"
