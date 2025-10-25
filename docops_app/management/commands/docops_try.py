from django.core.management.base import BaseCommand
from docops_app.services import run

class Command(BaseCommand):
    help = "Пробный прогон DocOps: NL → IR → (опционально) исполнение"

    def add_arguments(self, parser):
        parser.add_argument("--text", required=True, help="RU фраза")
        parser.add_argument("--email", default=None, help="email для канала Add-in")
        parser.add_argument("--execute", action="store_true", help="исполнить через Channels")

    def handle(self, *args, **opts):
        result = run(opts["text"], email=opts.get("email"), execute=opts.get("execute"))
        self.stdout.write(self.style.SUCCESS("IR:"))
        self.stdout.write(self.style.HTTP_INFO(str(result["program"])))
        self.stdout.write(self.style.SUCCESS("Blocks:"))
        for b in result["blocks"]:
            self.stdout.write(self.style.HTTP_INFO(str(b)))
        if opts.get("execute"):
            self.stdout.write(self.style.SUCCESS("Отправлено в Add-in."))