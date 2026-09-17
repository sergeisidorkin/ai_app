from .models import ChecklistSortProposal, ChecklistSortRun
from .sort_service import execute_sort_run
from .sort_verify import execute_verify_proposal


def recover_interrupted_jobs():
    sort_count = ChecklistSortRun.objects.filter(
        status=ChecklistSortRun.Status.RUNNING,
    ).update(
        status=ChecklistSortRun.Status.QUEUED,
        started_at=None,
        finished_at=None,
        error_message="",
    )
    verify_count = ChecklistSortProposal.objects.filter(
        verify_status="running",
    ).update(
        verify_status="queued",
        verify_started_at=None,
        verify_error="",
    )
    return sort_count, verify_count


def process_next_job():
    run_id = (
        ChecklistSortRun.objects.filter(status=ChecklistSortRun.Status.QUEUED)
        .order_by("created_at", "id")
        .values_list("id", flat=True)
        .first()
    )
    if run_id is not None:
        execute_sort_run(run_id)
        return True

    proposal_id = (
        ChecklistSortProposal.objects.filter(verify_status="queued")
        .order_by("id")
        .values_list("id", flat=True)
        .first()
    )
    if proposal_id is not None:
        execute_verify_proposal(proposal_id)
        return True

    return False
