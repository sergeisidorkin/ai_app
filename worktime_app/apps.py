from django.apps import AppConfig


class WorktimeAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worktime_app"
    verbose_name = "Рабочее время"

    def ready(self):
        from . import signals  # noqa: F401

