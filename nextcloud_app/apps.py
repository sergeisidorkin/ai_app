from django.apps import AppConfig


class NextcloudAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nextcloud_app"
    verbose_name = "Nextcloud"

    def ready(self):
        from . import signals  # noqa: F401
