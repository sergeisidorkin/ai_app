from django.core.management.base import BaseCommand, CommandError
from docops_app.normalize import load_ruleset
from pathlib import Path

class Command(BaseCommand):
    help = "Линтер rulesets (минимальная проверка)"

    def add_arguments(self, parser):
        parser.add_argument("--path", default="docops_app/rulesets/base.ru.yml")

    def handle(self, *args, **opts):
        p = Path(opts["path"])
        if not p.exists():
            raise CommandError(f"Файл правил не найден: {p}")
        rs = load_ruleset(str(p))
        if not rs.version:
            raise CommandError("В ruleset отсутствует version")
        if not isinstance(rs.styles, dict):
            raise CommandError("styles должен быть словарём")
        self.stdout.write(self.style.SUCCESS(f"OK: {p} (version={rs.version})"))