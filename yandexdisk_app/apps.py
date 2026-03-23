import os
import sys

from django.apps import AppConfig


class YandexDiskAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "yandexdisk_app"
    verbose_name = "Яндекс.Диск"

    def ready(self):
        # Avoid double-start in dev (runserver spawns two processes).
        # RUN_MAIN is set by Django's reloader in the child process.
        if any("pytest" in arg for arg in sys.argv):
            return
        if os.environ.get("DISABLE_YADISK_BACKGROUND_SYNC") == "1":
            return

        is_reloader_main = os.environ.get("RUN_MAIN") == "true"
        is_not_reloader = "RUN_MAIN" not in os.environ

        if is_reloader_main or is_not_reloader:
            from yandexdisk_app.sync import start_background_sync
            start_background_sync()
