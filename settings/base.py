from pathlib import Path
import environ, os
import sys
from urllib.parse import urlparse

from core.oidc_settings import oidc_pkce_required

BASE_DIR = Path(__file__).resolve().parents[1]
env = environ.Env(
    DEBUG=(bool, False),
    READ_DOTENV=(bool, False),
)

ENV_FILE = os.environ.get("ENV_FILE")  # абсолютный путь до .env

BASE_URL = env("BASE_URL", default="http://localhost:8000")
_u = urlparse(BASE_URL)

# Если хотите — можете переиспользовать BASE_URL для дефолтов ниже.
MS_REDIRECT_URI = env("MS_REDIRECT_URI", default=f"{BASE_URL}/onedrive/callback")

# если явно указали ENV_FILE — читаем его
if ENV_FILE and os.path.exists(ENV_FILE):
    environ.Env.read_env(ENV_FILE)
# иначе как раньше: локально читаем ai_app/.env
elif env.bool("READ_DOTENV", False) or (
    os.environ.get("DJANGO_ENV", "local") == "local" and (BASE_DIR / ".env").exists()
):
    environ.Env.read_env(BASE_DIR / ".env")

# On local macOS development, make Python SMTP TLS use certifi by default.
# This avoids per-shell manual exports while leaving server environments unchanged.
if sys.platform == "darwin" and os.environ.get("DJANGO_ENV", "local") == "local":
    try:
        import certifi
    except Exception:
        certifi = None
    if certifi is not None:
        cert_path = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", cert_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)

# В dev удобно читать .env
if env.bool("READ_DOTENV", False) or (
    os.environ.get("DJANGO_ENV", "local") == "local" and (BASE_DIR / ".env").exists()
):
    environ.Env.read_env(BASE_DIR / ".env")


def _read_text_setting_from_env_or_file(name, *, default=""):
    value = env(name, default=default)
    if value:
        return value

    file_path = env(f"{name}_FILE", default="")
    if not file_path:
        return default

    try:
        return Path(file_path).read_text()
    except OSError:
        return default


SECRET_KEY = env("SECRET_KEY", default="dev-secret-please-change")

DEBUG = env.bool("DEBUG", False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[
    "127.0.0.1",
    "0.0.0.0",
    "localhost",
    "testserver",
    "admiringly-conscious-remora.cloudpub.ru",
    ".cloudpub.ru",
    "imcmontanai.ru",
])

INSTALLED_APPS = [
    "core","django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "django.contrib.postgres",
    "policy_app","onedrive_app","blocks_app","blockseditor_app","openai_app","googledrive_app","projects_app",
    "requests_app","debugger_app","office_addin","corsheaders","channels","docops_app",
    "docops_queue","macroops_app","checklists_app","logs_app.apps.LogsAppConfig","yandexdisk_app",
    "oauth2_provider",
    "classifiers_app",
    "contacts_app.apps.ContactsAppConfig",
    "group_app",
    "experts_app",
    "users_app",
    "userprofile_app",
    "notifications_app",
    "contracts_app",
    "letters_app",
    "worktime_app.apps.WorktimeAppConfig",
    "learning_app",
    "proposals_app.apps.ProposalsAppConfig",
    "nextcloud_app.apps.NextcloudAppConfig",
    "smtp_app",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.EnforceLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Включаем пробник только в debug или по флагу окружения
if DEBUG or os.environ.get("RUN_PROBE") == "1":
    MIDDLEWARE.insert(0, "core.runprobe.RunProbeMiddleware")

# В dev Whitenoise будет читать из app static finders, без manifest:
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG

# Хранилище статики:
if DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "runprobe":   {"handlers": ["console"], "level": "WARNING"},
        "blocks_app": {"handlers": ["console"], "level": "WARNING"},
    },
}

LOGGING["loggers"]["office_addin"] = {"handlers": ["console"], "level": "DEBUG"}
LOGGING["loggers"]["office_addin.consumers"] = {"handlers": ["console"], "level": "DEBUG"}

# Аутентификация: куда редиректить после логина/логаута
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/#policy"   # после входа — сразу на вкладку «Продукты»
LOGOUT_REDIRECT_URL = "login"

# Email (SMTP)
# Backward compatible with explicit EMAIL_* settings, but can also be configured
# via a single EMAIL_URL value (e.g. smtp+tls://user:pass@127.0.0.1:587).
DJANGO_SMTP_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CUSTOM_SMTP_EMAIL_BACKEND = "core.email_backend.DomainSMTPEmailBackend"


def _normalize_email_backend(value):
    return CUSTOM_SMTP_EMAIL_BACKEND if value == DJANGO_SMTP_EMAIL_BACKEND else value


EMAIL_BACKEND = _normalize_email_backend(env("EMAIL_BACKEND", default=CUSTOM_SMTP_EMAIL_BACKEND))
EMAIL_HOST = env("EMAIL_HOST", default="smtp.yandex.ru")
EMAIL_PORT = env.int("EMAIL_PORT", default=465)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=True)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@imcmontanai.ru")
PROPOSAL_SYSTEM_FROM_EMAIL = env("PROPOSAL_SYSTEM_FROM_EMAIL", default="ai@imcmontanai.ru")
EMAIL_LOCAL_HOSTNAME = env(
    "EMAIL_LOCAL_HOSTNAME",
    default=(DEFAULT_FROM_EMAIL.split("@", 1)[1] if "@" in DEFAULT_FROM_EMAIL else "localhost"),
)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH", default="")
SMTP_APP_ENCRYPTION_KEY = env("SMTP_APP_ENCRYPTION_KEY", default=SECRET_KEY)

EMAIL_URL = env("EMAIL_URL", default="")
if EMAIL_URL:
    _email_cfg = env.email_url("EMAIL_URL")
    EMAIL_BACKEND = _normalize_email_backend(_email_cfg.get("EMAIL_BACKEND", EMAIL_BACKEND))
    EMAIL_HOST = _email_cfg.get("EMAIL_HOST", EMAIL_HOST)
    EMAIL_PORT = _email_cfg.get("EMAIL_PORT", EMAIL_PORT)
    EMAIL_USE_SSL = _email_cfg.get("EMAIL_USE_SSL", EMAIL_USE_SSL)
    EMAIL_USE_TLS = _email_cfg.get("EMAIL_USE_TLS", EMAIL_USE_TLS)
    EMAIL_HOST_USER = _email_cfg.get("EMAIL_HOST_USER", EMAIL_HOST_USER)
    EMAIL_HOST_PASSWORD = _email_cfg.get("EMAIL_HOST_PASSWORD", EMAIL_HOST_PASSWORD)
    EMAIL_TIMEOUT = _email_cfg.get("EMAIL_TIMEOUT", EMAIL_TIMEOUT)
    EMAIL_FILE_PATH = _email_cfg.get("EMAIL_FILE_PATH", EMAIL_FILE_PATH)

EMAIL_VERIFICATION_CODE_TTL = 30 * 60  # 30 minutes

# Дополнительные разрешённые пути (префиксы), доступные без авторизации
ENFORCE_LOGIN_EXEMPT = (
    "/health/",
    "/gdrive/",
    "/onedrive/",
    "/yadisk/",
    "/onedrive/callback", # ← коллбэк OAuth не должен требовать авторизации
    "/accounts/",  # ← сама страница логина тоже в белом списке
    "/static/",
    "/taskpane.html",
    "/addin/commands.html",
    "/addin/manifest.xml",
    "/api/addin/",  # API надстройки
    "/api/macroops/",
    "/api/macroops/ping",
    "/api/macroops/compile",
    # ---- API для агента и рантайма (фоновая вставка) ----
    "/api/docs/",
    "/api/jobs/",
    "/api/agents/",
    "/logs/api/logs/ingest/",  # фактический путь сейчас
    "/logs/api/",              # на будущее, шире
    "/api/logs/ingest/",        # если решите дать синоним без /logs/
    "/api/logs/",              # шире
    "/queue/",
    "/ws/",  # на всякий случай для WS-рутов
    "/favicon.ico",
    "/site.webmanifest",
    "/checklists/shared/",
    "/media/",
    "/proposals/docx-source/",
    "/o/authorize/",
    "/o/token/",
    "/o/revoke_token/",
    "/o/introspect/",
    "/o/userinfo/",
    "/o/logout/",
    "/o/.well-known/",
)

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[
    "http://localhost",
    "https://localhost",
    "https://localhost:3000",
    "https://localhost:8001",
    "https://word-edit.officeapps.live.com",
    "https://admiringly-conscious-remora.cloudpub.ru",
    "https://imcmontanai.ru",
])

CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.officeapps\.live\.com$",
    r"^https://.*\.sharepoint\.com$",
    r"^https://.*\.cloudpub\.ru$",
]

CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]
CORS_ALLOW_HEADERS = ["content-type", "authorization", "x-requested-with", "ngrok-skip-browser-warning", "x-imc-logs-token"]

CORS_EXPOSE_HEADERS = []
CORS_ALLOW_CREDENTIALS = False

CSRF_TRUSTED_ORIGINS = [
    "https://imcmontanai.ru",
    "http://localhost:8000",
    "https://localhost:8001",
    "https://localhost:3000",
    "https://admiringly-conscious-remora.cloudpub.ru",
    "https://*.cloudpub.ru",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ROOT_URLCONF = "urls"
WSGI_APPLICATION = "wsgi.application"

ASGI_APPLICATION = "asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")],
        },
    }
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],   # можно оставить пустым списком, если нет корневой папки templates
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.nav_items",
                "core.context_processors.templates_products",
                "core.context_processors.templates_sections_map",
                "core.context_processors.notifications_counters",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR/'db.sqlite3'}")
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }

# === Azure / Graph ===
MS_CLIENT_ID = env("MS_CLIENT_ID", default="")
MS_CLIENT_SECRET = env("MS_CLIENT_SECRET", default="")
MS_TENANT_ID = env("MS_TENANT_ID", default="common")
MSAL_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"
MS_REDIRECT_URI = env("MS_REDIRECT_URI", default="http://localhost:8000/onedrive/callback")
MS_SCOPES = ["User.Read", "Files.ReadWrite"]

GDRIVE_CLIENT_ID     = env("GDRIVE_CLIENT_ID", default="")
GDRIVE_CLIENT_SECRET = env("GDRIVE_CLIENT_SECRET", default="")
GDRIVE_API_KEY       = env("GDRIVE_API_KEY", default="")
GDRIVE_PROJECT_NUMBER = env("GDRIVE_PROJECT_NUMBER", default="")  # опционально
PUBLIC_ORIGIN        = env("PUBLIC_ORIGIN", default="")            # опционально для Picker

# === OpenAI ===
OPENAI_API_BASE = env("OPENAI_API_BASE", default="https://api.openai.com/v1")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default=env("OPENAI_API_BASE", default="https://api.openai.com/v1"))
OPENAI_ORG_ID   = env("OPENAI_ORG_ID", default="")
OPENAI_PROJECT_ID=env("OPENAI_PROJECT_ID", default="")

# === Яндекс.Диск ===
YANDEX_DISK_CLIENT_ID = env("YANDEX_DISK_CLIENT_ID", default="")
YANDEX_DISK_CLIENT_SECRET = env("YANDEX_DISK_CLIENT_SECRET", default="")

# === DocOpsAgent ===
BASE_PUBLIC_URL = os.getenv("BASE_PUBLIC_URL", "https://localhost:8001")
ADDIN_TASKPANE_URL = os.getenv("ADDIN_TASKPANE_URL", "https://localhost:3000/taskpane.html")
ADDIN_COMMANDS_URL = os.getenv("ADDIN_COMMANDS_URL", f"{BASE_PUBLIC_URL}/addin/commands.html")
X_FRAME_OPTIONS = "ALLOWALL"

# === Queue (docops_queue) ===
QUEUE_API_BASE   = env("QUEUE_API_BASE", default="")
ADDIN_AGENT_ID   = env("ADDIN_AGENT_ID", default="addin-auto")
ADDIN_AGENT_ROLE = env("ADDIN_AGENT_ROLE", default="addin")

LOGS_INGEST_TOKEN = env("LOGS_INGEST_TOKEN", default="")

# === Learning / Moodle ===
MOODLE_BASE_URL = env("MOODLE_BASE_URL", default="")
MOODLE_LAUNCH_PATH = env("MOODLE_LAUNCH_PATH", default="/")
MOODLE_USER_AUTH_PLUGIN = env("MOODLE_USER_AUTH_PLUGIN", default="manual")
MOODLE_SSO_LAUNCH_MODE = env("MOODLE_SSO_LAUNCH_MODE", default="oidc")
MOODLE_LOGOUT_FIRST_PATH = env("MOODLE_LOGOUT_FIRST_PATH", default="/local/imc_sso/logout_first.php")
MOODLE_OIDC_LOGIN_PATH = env("MOODLE_OIDC_LOGIN_PATH", default="/auth/oidc/")
MOODLE_OIDC_LOGIN_SOURCE = env("MOODLE_OIDC_LOGIN_SOURCE", default="django")
MOODLE_OIDC_PROMPT_LOGIN = env.bool("MOODLE_OIDC_PROMPT_LOGIN", default=False)
MOODLE_WEB_SERVICE_URL = env("MOODLE_WEB_SERVICE_URL", default="")
MOODLE_WEB_SERVICE_TOKEN = env("MOODLE_WEB_SERVICE_TOKEN", default="")
MOODLE_WEB_SERVICE_TIMEOUT = env.int("MOODLE_WEB_SERVICE_TIMEOUT", default=20)

# === Nextcloud ===
NEXTCLOUD_BASE_URL = env("NEXTCLOUD_BASE_URL", default="")
NEXTCLOUD_SSO_ENABLED = env.bool("NEXTCLOUD_SSO_ENABLED", default=False)
NEXTCLOUD_OIDC_LOGIN_PATH = env("NEXTCLOUD_OIDC_LOGIN_PATH", default="")
NEXTCLOUD_PROVISIONING_BASE_URL = env("NEXTCLOUD_PROVISIONING_BASE_URL", default="")
NEXTCLOUD_PROVISIONING_USERNAME = env("NEXTCLOUD_PROVISIONING_USERNAME", default="")
NEXTCLOUD_PROVISIONING_TOKEN = env("NEXTCLOUD_PROVISIONING_TOKEN", default="")
NEXTCLOUD_OIDC_PROVIDER_ID = env.int("NEXTCLOUD_OIDC_PROVIDER_ID", default=0)
NEXTCLOUD_OIDC_CLIENT_ID = env("NEXTCLOUD_OIDC_CLIENT_ID", default="").strip()
ONLYOFFICE_DOCUMENT_SERVER_URL = env("ONLYOFFICE_DOCUMENT_SERVER_URL", default="")
ONLYOFFICE_JWT_SECRET = env("ONLYOFFICE_JWT_SECRET", default="")
ONLYOFFICE_VERIFY_SSL = env.bool("ONLYOFFICE_VERIFY_SSL", default=True)
ONLYOFFICE_CONVERSION_TIMEOUT = env.int("ONLYOFFICE_CONVERSION_TIMEOUT", default=120)
ONLYOFFICE_DOCX_SOURCE_TOKEN_TTL = env.int("ONLYOFFICE_DOCX_SOURCE_TOKEN_TTL", default=300)
NEXTCLOUD_DEFAULT_GROUP = env("NEXTCLOUD_DEFAULT_GROUP", default="staff")
NEXTCLOUD_DEFAULT_QUOTA = env("NEXTCLOUD_DEFAULT_QUOTA", default="")

# === OIDC Provider ===
OIDC_RSA_PRIVATE_KEY = _read_text_setting_from_env_or_file("OIDC_RSA_PRIVATE_KEY", default="").strip()
OIDC_ISSUER_URL = env("OIDC_ISSUER_URL", default=f"{BASE_URL.rstrip('/')}/o").rstrip("/")
MOODLE_OIDC_CLIENT_ID = env("MOODLE_OIDC_CLIENT_ID", default="").strip()
OIDC_STAFF_ONLY_CLIENT_IDS = tuple(
    client_id
    for client_id in env.list("OIDC_STAFF_ONLY_CLIENT_IDS", default=[])
    if client_id
)
if MOODLE_OIDC_CLIENT_ID and MOODLE_OIDC_CLIENT_ID not in OIDC_STAFF_ONLY_CLIENT_IDS:
    OIDC_STAFF_ONLY_CLIENT_IDS = (*OIDC_STAFF_ONLY_CLIENT_IDS, MOODLE_OIDC_CLIENT_ID)
if NEXTCLOUD_OIDC_CLIENT_ID and NEXTCLOUD_OIDC_CLIENT_ID not in OIDC_STAFF_ONLY_CLIENT_IDS:
    OIDC_STAFF_ONLY_CLIENT_IDS = (*OIDC_STAFF_ONLY_CLIENT_IDS, NEXTCLOUD_OIDC_CLIENT_ID)

OAUTH2_PROVIDER = {
    "OAUTH2_VALIDATOR_CLASS": "core.oidc.IMCOAuth2Validator",
    "OIDC_ENABLED": bool(OIDC_RSA_PRIVATE_KEY),
    "OIDC_RSA_PRIVATE_KEY": OIDC_RSA_PRIVATE_KEY,
    "OIDC_ISS_ENDPOINT": OIDC_ISSUER_URL,
    "SCOPES": {
        "openid": "OpenID Connect scope",
        "profile": "Basic profile information",
        "email": "Email address",
    },
    "DEFAULT_SCOPES": ["openid", "profile", "email"],
    "REQUEST_APPROVAL_PROMPT": "auto",
    "PKCE_REQUIRED": oidc_pkce_required,
    "OIDC_RESPONSE_TYPES_SUPPORTED": ["code"],
}

