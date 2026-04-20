from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from classifiers_app.numcap_official_csv import DEFAULT_FILENAMES, process_numcap_official_sources


class Command(BaseCommand):
    help = "Обновляет numcap из локальных официальных CSV-файлов Минцифры."

    def add_arguments(self, parser):
        parser.add_argument(
            "files",
            nargs="*",
            help="Пути к CSV-файлам. Если не указаны, берутся ABC-3xx.csv, ABC-4xx.csv, ABC-8xx.csv и DEF-9xx.csv из корня проекта.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Полностью заменить текущее содержимое таблицы numcap.",
        )

    def _resolve_files(self, raw_paths):
        if raw_paths:
            paths = [Path(item).expanduser().resolve() for item in raw_paths]
        else:
            base_dir = Path(settings.BASE_DIR)
            paths = [(base_dir / filename).resolve() for filename in DEFAULT_FILENAMES]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise CommandError("Не найдены файлы:\n" + "\n".join(missing))
        return paths

    def handle(self, *args, **options):
        paths = self._resolve_files(options["files"])
        stats = process_numcap_official_sources(
            paths,
            replace=options["replace"],
            report=lambda message: (self.stdout.write(message), self.stdout.flush()),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Обновление numcap завершено. Обработано строк: {stats['processed']}. "
                f"Добавлено записей: {stats['created']}. Пропущено строк: {stats['skipped']}."
            )
        )
