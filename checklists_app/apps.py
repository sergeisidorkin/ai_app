import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ChecklistsAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "checklists_app"
    verbose_name = "Чек-листы"

    def ready(self):
        if any(arg in sys.argv for arg in ("migrate", "makemigrations", "test", "flush", "shell")):
            return
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return
        try:
            from django.db import connection

            tables = connection.introspection.table_names()
            if "checklists_app_checklistsortproposal" not in tables:
                return
            from .models import ChecklistSortProposal

            ChecklistSortProposal.objects.filter(verify_status="running").update(
                verify_status="error",
                verify_error="Проверка прервалась. Нажмите «Проверить» ещё раз.",
                verify_started_at=None,
            )
        except Exception:
            logger.debug("skip verify reclaim on startup", exc_info=True)
