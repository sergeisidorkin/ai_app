from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings


def build_nextcloud_overview(user) -> dict[str, object]:
    del user

    nextcloud_base_url = (getattr(settings, "NEXTCLOUD_BASE_URL", "") or "").strip()
    nextcloud_sso_enabled = bool(getattr(settings, "NEXTCLOUD_SSO_ENABLED", False))
    oidc_login_path = (getattr(settings, "NEXTCLOUD_OIDC_LOGIN_PATH", "") or "").strip()

    launch_url = nextcloud_base_url
    if nextcloud_base_url and nextcloud_sso_enabled and oidc_login_path:
        launch_url = _build_nextcloud_url(nextcloud_base_url, oidc_login_path)

    return {
        "nextcloud_enabled": bool(nextcloud_base_url),
        "nextcloud_launch_url": launch_url,
        "nextcloud_sso_enabled": nextcloud_sso_enabled,
    }


def _build_nextcloud_url(base_url: str, relative_path: str) -> str:
    base = urlsplit(base_url)
    split = urlsplit(relative_path)
    path = split.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return urlunsplit((base.scheme, base.netloc, path, split.query, split.fragment))
