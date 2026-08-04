from django.core.management.base import BaseCommand

from yandexdisk_app.sync import API_DELAY, run_sync


class Command(BaseCommand):
    help = (
        "Синхронизирует число файлов и дату последней загрузки для папок "
        "текущего облачного хранилища (Nextcloud или Яндекс.Диск)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay",
            type=float,
            default=API_DELAY,
            help="Задержка между запросами к облачному API в секундах",
        )

    def handle(self, *args, **options):
        updated = run_sync(delay=max(float(options["delay"]), 0.0))
        self.stdout.write(
            self.style.SUCCESS(
                f"Синхронизация метаданных завершена. Обновлено папок: {updated}"
            )
        )
