import os
import sys

from django.apps import AppConfig


class YandexDiskAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "yandexdisk_app"
    verbose_name = "Яндекс.Диск"

    def ready(self):
        # Start background sync only for long-running server processes.
        # This avoids DB access during management commands like check/migrate.
        if any("pytest" in arg for arg in sys.argv):
            return
        if os.environ.get("DISABLE_YADISK_BACKGROUND_SYNC") == "1":
            return
        if len(sys.argv) > 1 and sys.argv[1] != "runserver":
            return

        is_reloader_main = os.environ.get("RUN_MAIN") == "true"
        is_not_reloader = "RUN_MAIN" not in os.environ

        if is_reloader_main or is_not_reloader:
            from yandexdisk_app.sync import start_background_sync
            # Defer the first DB-backed sync until Django startup settles.
            start_background_sync(initial_delay=5.0)
