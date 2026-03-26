from django.apps import AppConfig


class LearningAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "learning_app"
    verbose_name = "Обучение"

    def ready(self):
        from . import signals  # noqa: F401
