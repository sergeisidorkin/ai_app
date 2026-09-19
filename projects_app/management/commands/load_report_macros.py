from django.core.management.base import BaseCommand

from projects_app.models import ReportMacro
from projects_app.report_macros import TPGR_MACROS, sync_tpgr_macros


class Command(BaseCommand):
    help = "Загрузить макросы TPGR в таблицу Макросы (создать новые и обновить код существующих по имени)."

    def handle(self, *args, **options):
        created, updated = sync_tpgr_macros(ReportMacro)
        self.stdout.write(
            self.style.SUCCESS(
                f"Макросы TPGR: создано {created}, обновлено {updated}, всего в каталоге {len(TPGR_MACROS)}."
            )
        )
