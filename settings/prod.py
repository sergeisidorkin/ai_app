from .base import *

# Прод-режим
DEBUG = False

# Хосты и доверенные источники для CSRF — читаем из env
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["imcmontanai.ru", "www.imcmontanai.ru", "127.0.0.1", "localhost"],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://imcmontanai.ru", "https://www.imcmontanai.ru"],
)

# Django за nginx должен понимать, что трафик HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# безопасность
# Рекомендуемые флаги на HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"

# A missing dedicated policy cache must not silently reuse Channels Redis or
# create process-local, cross-worker inconsistent production entries.
if not POLICY_CACHE_URL:
    CACHES["policy"] = {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }

# Keep one WhiteNoise middleware entry from base.py. Nginx should serve
# /static/ in production; manifest storage still creates hashed/compressed
# artifacts and WhiteNoise remains a safe application-level fallback.
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Headless DSH runs inside the compose stack, not on the gunicorn PATH.
# Local inbox paths on the laptop must stay off in production.
DSH_SORT_ALLOW_LOCAL_INBOX = env.bool("DSH_SORT_ALLOW_LOCAL_INBOX", default=False)
if not (DSH_COMPOSE_DIR or "").strip():
    DSH_COMPOSE_DIR = "/opt/dsh"
_dsh_compose_dir = Path(DSH_COMPOSE_DIR)
_dsh_compose_file = _dsh_compose_dir / "docker-compose.yml"
_dsh_env_file = _dsh_compose_dir / "dsh.env"
if not (DSH_HEADLESS_CMD or "").strip() and _dsh_compose_file.exists():
    _dsh_env_flag = f"--env-file {_dsh_env_file} " if _dsh_env_file.exists() else ""
    DSH_HEADLESS_CMD = (
        f"docker compose --project-directory {_dsh_compose_dir} {_dsh_env_flag}"
        "exec -T -w {cwd} dsh dsh --profile headless"
    )
if not (DSH_SORT_WORKSPACE or "").strip() and (_dsh_compose_dir / "workspace").is_dir():
    DSH_SORT_WORKSPACE = str(_dsh_compose_dir / "workspace" / "sort-runs")
if (
    not (DSH_HEADLESS_CONTAINER_CWD or "").strip()
    and "{cwd}" in (DSH_HEADLESS_CMD or "")
):
    DSH_HEADLESS_CONTAINER_CWD = "/workspace/sort-runs"

if DATABASES["default"]["ENGINE"].startswith("django.db.backends.postgresql"):
    DATABASES["default"]["CONN_MAX_AGE"] = env.int(
        "DB_CONN_MAX_AGE",
        default=60,
    )
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool(
        "DB_CONN_HEALTH_CHECKS",
        default=True,
    )


