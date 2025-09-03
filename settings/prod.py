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

# статика (опционально)
try:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
except Exception:
    pass






