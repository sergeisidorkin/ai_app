from pathlib import Path
import environ, os

BASE_DIR = Path(__file__).resolve().parents[1]
env = environ.Env(
    DEBUG=(bool, False),
    READ_DOTENV=(bool, False),
)

LOGIN_URL = "/admin/login/"

# В dev удобно читать .env
if env.bool("READ_DOTENV", False) or (
    os.environ.get("DJANGO_ENV", "local") == "local" and (BASE_DIR / ".env").exists()
):
    environ.Env.read_env(BASE_DIR / ".env")


SECRET_KEY = env("SECRET_KEY", default="dev-secret-please-change")
DEBUG = env.bool("DEBUG", False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1","localhost"])

INSTALLED_APPS = [
    "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "onedrive_app","blocks_app","openai_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "urls"
WSGI_APPLICATION = "wsgi.application"

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
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR/'db.sqlite3'}")
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))

# === Azure / Graph ===
MS_CLIENT_ID = env("MS_CLIENT_ID", default="")
MS_CLIENT_SECRET = env("MS_CLIENT_SECRET", default="")
MS_TENANT_ID = env("MS_TENANT_ID", default="common")
MSAL_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"
MS_REDIRECT_URI = env("MS_REDIRECT_URI", default="http://localhost:8000/onedrive/callback")
MS_SCOPES = ["User.Read", "Files.ReadWrite"]

# === OpenAI ===
OPENAI_API_BASE = env("OPENAI_API_BASE", default="https://api.openai.com/v1")