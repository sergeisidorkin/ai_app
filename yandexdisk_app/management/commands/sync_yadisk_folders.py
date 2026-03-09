"""
Периодическая синхронизация метаданных папок Яндекс.Диска
для всех ChecklistItemFolder.

Запуск:  python manage.py sync_yadisk_folders
"""
from django.core.management.base import BaseCommand
from yandexdisk_app.sync import run_sync, API_DELAY


class Command(BaseCommand):
    help = "Синхронизирует метаданные папок Яндекс.Диска (число файлов, дата последней загрузки)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay", type=float, default=API_DELAY,
            help="Задержка между API-запросами в секундах (по умолчанию 1.0)",
        )

    def handle(self, *args, **options):
        updated = run_sync(delay=options["delay"])
        self.stdout.write(self.style.SUCCESS(f"Синхронизация завершена. Обновлено папок: {updated}"))
