from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from learning_app.models import LearningSyncRun
from learning_app.moodle_api import MoodleApiClient, MoodleApiError
from learning_app.sync import sync_staff_learning

User = get_user_model()


class Command(BaseCommand):
    help = "Synchronize Moodle users, courses and learning results for staff users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            action="append",
            dest="user_ids",
            help="Sync only selected Django staff user id. Can be passed multiple times.",
        )
        parser.add_argument(
            "--email",
            action="append",
            dest="emails",
            help="Sync only selected Django staff user email. Can be passed multiple times.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate configuration and selected users without writing data.",
        )

    def handle(self, *args, **options):
        client = MoodleApiClient()
        if not client.is_configured:
            raise CommandError(
                "Moodle API is not configured. Set MOODLE_BASE_URL and MOODLE_WEB_SERVICE_TOKEN."
            )

        users = User.objects.filter(is_active=True, is_staff=True).order_by("id")
        user_ids = options.get("user_ids") or []
        emails = options.get("emails") or []
        if user_ids:
            users = users.filter(id__in=user_ids)
        if emails:
            users = users.filter(email__in=emails)

        if not users.exists():
            raise CommandError("No matching active staff users found for synchronization.")

        self.stdout.write(
            f"Selected {users.count()} staff user(s) for Moodle synchronization."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run mode: no data will be written."))
            return

        run = LearningSyncRun.objects.create(
            scope=LearningSyncRun.Scope.FULL,
            status=LearningSyncRun.Status.STARTED,
            source_payload={
                "user_ids": user_ids,
                "emails": emails,
                "started_from_command": "sync_moodle_learning",
            },
        )

        try:
            stats = sync_staff_learning(users=users, client=client, run=run)
        except MoodleApiError as exc:
            run.status = LearningSyncRun.Status.FAILED
            run.error_message = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            run.status = LearningSyncRun.Status.FAILED
            run.error_message = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])
            raise

        self.stdout.write(self.style.SUCCESS("Moodle synchronization completed."))
        for key, value in stats.items():
            self.stdout.write(f"{key}: {value}")
