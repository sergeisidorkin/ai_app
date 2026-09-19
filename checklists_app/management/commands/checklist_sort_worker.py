import fcntl
import hashlib
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from checklists_app.sort_worker import (
    make_worker_id,
    process_next_job,
    recover_interrupted_jobs,
    touch_worker,
)


def _lock_path():
    project_key = hashlib.sha256(str(settings.BASE_DIR).encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"ai-app-checklist-sort-{project_key}.lock"


class Command(BaseCommand):
    help = "Process durable checklist sorting and verification jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        if getattr(settings, "DSH_SORT_INLINE", False):
            raise CommandError("checklist_sort_worker cannot run when DSH_SORT_INLINE is enabled.")

        lock_path = _lock_path()
        lock_file = lock_path.open("a+")
        try:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CommandError("Another checklist_sort_worker is already running.") from exc

            worker_id = make_worker_id()
            sort_count, verify_count = recover_interrupted_jobs(worker_id)
            if sort_count or verify_count:
                self.stdout.write(
                    f"Recovered interrupted jobs: sort={sort_count}, verify={verify_count}"
                )

            once = options["once"]
            poll_interval = max(0.1, options["poll_interval"])
            while True:
                touch_worker(worker_id)
                processed = process_next_job(worker_id)
                if once:
                    return
                if not processed:
                    time.sleep(poll_interval)
        finally:
            lock_file.close()
