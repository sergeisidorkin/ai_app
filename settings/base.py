from pathlib import Path
import environ, os
from urllib.parse import urlparse

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

# В dev удобно читать .env
if env.bool("READ_DOTENV", False) or (
    os.environ.get("DJANGO_ENV", "local") == "local" and (BASE_DIR / ".env").exists()
):
    environ.Env.read_env(BASE_DIR / ".env")


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
    "policy_app","onedrive_app","blocks_app","blockseditor_app","openai_app","googledrive_app","projects_app",
    "requests_app","debugger_app","office_addin","corsheaders","channels","docops_app",
    "docops_queue","macroops_app","checklists_app","logs_app.apps.LogsAppConfig",
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

# Дополнительные разрешённые пути (префиксы), доступные без авторизации
ENFORCE_LOGIN_EXEMPT = (
    "/health/",
    "/gdrive/",
    "/onedrive/",
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
)

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[
    "https://localhost",
    "https://localhost:3000",
    "https://localhost:8001",
    "https://word-edit.officeapps.live.com",
    "https://admiringly-conscious-remora.cloudpub.ru",
    "https://imcmontanai.ru",
])

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

