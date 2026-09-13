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

if DATABASES["default"]["ENGINE"].startswith("django.db.backends.postgresql"):
    DATABASES["default"]["CONN_MAX_AGE"] = env.int(
        "DB_CONN_MAX_AGE",
        default=60,
    )
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool(
        "DB_CONN_HEALTH_CHECKS",
        default=True,
    )


