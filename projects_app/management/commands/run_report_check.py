from django.core.management.base import BaseCommand

from projects_app.report_submission import _run_saved_report_check_background


class Command(BaseCommand):
    help = "Выполнить проверку отчёта в отдельном процессе, не привязанном к воркеру Gunicorn."

    def add_arguments(self, parser):
        parser.add_argument("user_id", type=int)
        parser.add_argument("upload_id", type=int)
        parser.add_argument("claim_token")

    def handle(self, *args, **options):
        _run_saved_report_check_background(
            options["user_id"],
            options["upload_id"],
            options["claim_token"],
        )
