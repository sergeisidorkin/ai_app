from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}


def _normalize_launch_url(raw):
    value = (raw or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    path = (parts.path or "").rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _read_launch_url_file(path):
    if not path:
        return ""
    try:
        raw = Path(path).read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    if not raw.startswith(("http://", "https://")):
        return ""
    return raw


def _align_launch_host(launch_url, request):
    if not launch_url or request is None:
        return launch_url
    app_host = (request.get_host() or "").split(":")[0].strip().lower()
    parts = urlsplit(launch_url)
    dsh_host = (parts.hostname or "").lower()
    if app_host not in _LOOPBACK_HOSTS or dsh_host not in _LOOPBACK_HOSTS:
        return launch_url
    port = parts.port or 3080
    return urlunsplit(
        (parts.scheme or "http", f"{app_host}:{port}", parts.path, parts.query, parts.fragment)
    )


def build_dsh_overview(request=None):
    file_url = _normalize_launch_url(
        _read_launch_url_file((getattr(settings, "DSH_LAUNCH_URL_FILE", "") or "").strip())
    )
    launch_url = _align_launch_host(
        file_url or _normalize_launch_url(getattr(settings, "DSH_BASE_URL", "") or ""),
        request,
    )
    return {
        "dsh_enabled": bool(launch_url),
        "dsh_launch_url": launch_url,
        "dsh_open_url": "/dsh/",
    }
