from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Import <app>/row_order.py modules so RowOrderSpec registrations are available
        # before the first request to core.row_order.row_order_save.
        autodiscover_modules("row_order")
