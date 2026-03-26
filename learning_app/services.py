from django.conf import settings
from django.db.models import Count
from django.db.utils import OperationalError, ProgrammingError
from django.urls import reverse

from .models import LearningCourseResult, LearningEnrollment


def build_learning_overview(user):
    moodle_base_url = (getattr(settings, "MOODLE_BASE_URL", "") or "").strip()
    moodle_launch_path = (getattr(settings, "MOODLE_LAUNCH_PATH", "") or "").strip() or "/"
    assigned_total = 0
    status_counts = {}
    latest_results = []
    learning_schema_ready = True

    try:
        assigned_total = (
            LearningEnrollment.objects
            .filter(user=user)
            .aggregate(total=Count("course", distinct=True))
            .get("total", 0)
            or 0
        )
        status_counts = {
            item["status"]: item["total"]
            for item in (
                LearningCourseResult.objects
                .filter(user=user)
                .values("status")
                .annotate(total=Count("id"))
            )
        }
        latest_results = list(
            LearningCourseResult.objects
            .filter(user=user)
            .select_related("course")
            .order_by("-completed_at", "-updated_at", "-id")[:5]
        )
    except (ProgrammingError, OperationalError):
        # Local DB may not have learning_app migrations yet.
        learning_schema_ready = False

    return {
        "learning_assigned_total": assigned_total,
        "learning_not_started_total": status_counts.get(LearningCourseResult.Status.NOT_STARTED, 0),
        "learning_in_progress_total": status_counts.get(LearningCourseResult.Status.IN_PROGRESS, 0),
        "learning_completed_total": status_counts.get(LearningCourseResult.Status.COMPLETED, 0),
        "learning_failed_total": status_counts.get(LearningCourseResult.Status.FAILED, 0),
        "learning_latest_results": latest_results,
        "learning_has_data": assigned_total > 0 or bool(latest_results),
        "learning_schema_ready": learning_schema_ready,
        "moodle_configured": bool(moodle_base_url),
        "moodle_base_url": moodle_base_url,
        "moodle_launch_path": moodle_launch_path,
        "learning_launch_url": reverse("learning_app:launch"),
    }
