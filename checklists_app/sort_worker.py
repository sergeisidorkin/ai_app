import os
import socket

from django.conf import settings
from django.utils import timezone
from django.db.models import Q

from .models import (
    ChecklistSortChunk,
    ChecklistSortProposal,
    ChecklistSortRun,
    ChecklistSortWorkerState,
)
from .sort_service import process_sort_step
from .sort_verify import execute_verify_proposal


_verify_streak = 0


def make_worker_id():
    return f"{socket.gethostname()}:{os.getpid()}"


def touch_worker(worker_id):
    now = timezone.now()
    state, created = ChecklistSortWorkerState.objects.get_or_create(
        pk="default",
        defaults={
            "worker_id": worker_id,
            "heartbeat_at": now,
            "started_at": now,
        },
    )
    if not created:
        ChecklistSortWorkerState.objects.filter(pk="default").update(
            worker_id=worker_id,
            heartbeat_at=now,
        )


def recover_interrupted_jobs(worker_id=None):
    now = timezone.now()
    expired_ids = list(
        ChecklistSortRun.objects.filter(
            status=ChecklistSortRun.Status.RUNNING,
        )
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=now))
        .values_list("id", flat=True)
    )
    if expired_ids:
        ChecklistSortChunk.objects.filter(
            run_id__in=expired_ids,
            status=ChecklistSortChunk.Status.RUNNING,
        ).update(
            status=ChecklistSortChunk.Status.PENDING,
            started_at=None,
        )
    sort_count = ChecklistSortRun.objects.filter(
        id__in=expired_ids,
    ).update(
        status=ChecklistSortRun.Status.QUEUED,
        worker_id="",
        heartbeat_at=None,
        lease_expires_at=None,
    )
    verify_count = ChecklistSortProposal.objects.filter(
        verify_status="running",
    ).filter(
        Q(verify_lease_expires_at__isnull=True) | Q(verify_lease_expires_at__lt=now)
    ).update(
        verify_status="queued",
        verify_worker_id="",
        verify_heartbeat_at=None,
        verify_lease_expires_at=None,
    )
    if worker_id:
        touch_worker(worker_id)
    return sort_count, verify_count


def _next_verify_id():
    return (
        ChecklistSortProposal.objects.filter(verify_status="queued")
        .order_by("id")
        .values_list("id", flat=True)
        .first()
    )


def _next_sort_id(worker_id):
    owned = (
        ChecklistSortRun.objects.filter(
            status=ChecklistSortRun.Status.RUNNING,
            worker_id=worker_id,
        )
        .order_by("created_at", "id")
        .values_list("id", flat=True)
        .first()
    )
    if owned is not None:
        return owned
    return (
        ChecklistSortRun.objects.filter(status=ChecklistSortRun.Status.QUEUED)
        .order_by("created_at", "id")
        .values_list("id", flat=True)
        .first()
    )


def process_next_job(worker_id=None):
    global _verify_streak
    identity = worker_id or make_worker_id()
    touch_worker(identity)
    recover_interrupted_jobs(identity)
    proposal_id = _next_verify_id()
    run_id = _next_sort_id(identity)
    verify_burst = max(int(getattr(settings, "DSH_SORT_WORKER_VERIFY_BURST", 1) or 1), 1)

    if proposal_id is not None and (run_id is None or _verify_streak < verify_burst):
        execute_verify_proposal(proposal_id, worker_id=identity)
        _verify_streak += 1
        return True
    if run_id is not None:
        processed = process_sort_step(run_id, identity)
        if processed:
            _verify_streak = 0
        return processed
    if proposal_id is not None:
        execute_verify_proposal(proposal_id, worker_id=identity)
        _verify_streak += 1
        return True
    return False
