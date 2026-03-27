from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings


def _normalize_relative_path(path: str | None, *, default: str = "/") -> str:
    raw = (path or "").strip()
    if not raw:
        return default

    split = urlsplit(raw)
    normalized_path = split.path or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    if split.query:
        return f"{normalized_path}?{split.query}"
    return normalized_path


def _build_absolute_moodle_url(path: str) -> str:
    base_url = (getattr(settings, "MOODLE_BASE_URL", "") or "").strip().rstrip("/")
    relative = _normalize_relative_path(path)
    return f"{base_url}{relative}"


def _build_relative_url(path: str, *, extra_params: dict[str, str] | None = None) -> str:
    split = urlsplit(_normalize_relative_path(path))
    params = dict(parse_qsl(split.query, keep_blank_values=True))
    if extra_params:
        params.update({key: value for key, value in extra_params.items() if value != ""})
    query = urlencode(params)
    return urlunsplit(("", "", split.path, query, split.fragment))


def build_moodle_target_url(target_path: str | None = None) -> str:
    launch_path = target_path or getattr(settings, "MOODLE_LAUNCH_PATH", "") or "/"
    return _build_absolute_moodle_url(launch_path)


def build_moodle_launch_url(target_path: str | None = None) -> str:
    launch_mode = (getattr(settings, "MOODLE_SSO_LAUNCH_MODE", "") or "oidc").strip().lower()
    if launch_mode == "page":
        return build_moodle_target_url(target_path)

    entry_path = getattr(settings, "MOODLE_OIDC_LOGIN_PATH", "") or "/auth/oidc/"
    login_url = _build_absolute_moodle_url(entry_path)
    source = (getattr(settings, "MOODLE_OIDC_LOGIN_SOURCE", "") or "").strip()
    prompt_login = getattr(settings, "MOODLE_OIDC_PROMPT_LOGIN", False)

    split = urlsplit(login_url)
    params = dict(parse_qsl(split.query, keep_blank_values=True))
    if source:
        params.setdefault("source", source)
    if prompt_login:
        params["promptlogin"] = "1"
    oidc_target = urlunsplit((split.scheme, split.netloc, split.path, urlencode(params), split.fragment))

    logout_first_path = (getattr(settings, "MOODLE_LOGOUT_FIRST_PATH", "") or "").strip()
    if not logout_first_path:
        return oidc_target

    next_path = _build_relative_url(entry_path, extra_params=params)
    return _build_absolute_moodle_url(
        _build_relative_url(logout_first_path, extra_params={"next": next_path})
    )
