from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    LearningCourse,
    LearningCourseResult,
    LearningEnrollment,
    LearningSyncRun,
    LearningUserLink,
)
from .moodle_api import MoodleApiClient, MoodleApiError

User = get_user_model()


@dataclass(slots=True)
class SyncStats:
    users_scanned: int = 0
    users_linked: int = 0
    users_missing_in_moodle: int = 0
    courses_upserted: int = 0
    enrollments_upserted: int = 0
    enrollments_removed: int = 0
    results_upserted: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "users_scanned": self.users_scanned,
            "users_linked": self.users_linked,
            "users_missing_in_moodle": self.users_missing_in_moodle,
            "courses_upserted": self.courses_upserted,
            "enrollments_upserted": self.enrollments_upserted,
            "enrollments_removed": self.enrollments_removed,
            "results_upserted": self.results_upserted,
        }


def sync_staff_learning(
    *,
    users=None,
    client: MoodleApiClient | None = None,
    run: LearningSyncRun | None = None,
) -> dict[str, int]:
    client = client or MoodleApiClient()
    client.ensure_configured()

    if users is None:
        users = User.objects.filter(is_active=True, is_staff=True).order_by("id")

    stats = SyncStats()
    for user in users:
        stats.users_scanned += 1
        synced = sync_user_learning(user, client=client)
        stats.users_linked += int(synced["user_linked"])
        stats.users_missing_in_moodle += int(not synced["user_linked"])
        stats.courses_upserted += synced["courses_upserted"]
        stats.enrollments_upserted += synced["enrollments_upserted"]
        stats.enrollments_removed += synced["enrollments_removed"]
        stats.results_upserted += synced["results_upserted"]

    if run is not None:
        run.stats = stats.as_dict()
        run.status = LearningSyncRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "status", "finished_at"])

    return stats.as_dict()


def sync_user_learning(user, *, client: MoodleApiClient | None = None) -> dict[str, int | bool]:
    client = client or MoodleApiClient()
    moodle_user = _find_moodle_user(user, client)
    if not moodle_user:
        return {
            "user_linked": False,
            "courses_upserted": 0,
            "enrollments_upserted": 0,
            "enrollments_removed": 0,
            "results_upserted": 0,
        }

    now = timezone.now()
    with transaction.atomic():
        link, _ = LearningUserLink.objects.get_or_create(user=user)
        link.moodle_user_id = moodle_user.get("id")
        link.moodle_username = moodle_user.get("username", "") or ""
        link.moodle_email = moodle_user.get("email", "") or user.email or ""
        link.last_synced_at = now
        link.source_payload = moodle_user
        link.save()

        courses = client.get_user_courses(link.moodle_user_id)
        seen_course_ids: set[int] = set()
        courses_upserted = 0
        enrollments_upserted = 0
        results_upserted = 0

        for course_payload in courses:
            course, _ = _upsert_course(course_payload, now=now, client=client)
            seen_course_ids.add(course.pk)
            courses_upserted += 1

            _, _ = LearningEnrollment.objects.update_or_create(
                user=user,
                course=course,
                defaults={
                    "moodle_enrollment_id": _safe_int(course_payload.get("enrollmentid")),
                    "role_name": _extract_role_name(course_payload),
                    "enrolled_at": None,
                    "last_synced_at": now,
                    "source_payload": course_payload,
                },
            )
            enrollments_upserted += 1

            _sync_course_result(
                user=user,
                course=course,
                moodle_user_id=link.moodle_user_id,
                course_payload=course_payload,
                client=client,
                now=now,
            )
            results_upserted += 1

        removed, _ = LearningEnrollment.objects.filter(user=user).exclude(course_id__in=seen_course_ids).delete()
        link.last_login_at = _parse_moodle_datetime(moodle_user.get("lastaccess"))
        link.save(update_fields=["last_login_at"])

    return {
        "user_linked": True,
        "courses_upserted": courses_upserted,
        "enrollments_upserted": enrollments_upserted,
        "enrollments_removed": removed,
        "results_upserted": results_upserted,
    }


def _find_moodle_user(user, client: MoodleApiClient) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    email = (user.email or "").strip()
    username = (user.username or "").strip()
    if email:
        candidates.extend(client.get_users_by_email(email))
    if not candidates and username and username != email:
        candidates.extend(client.get_users_by_username(username))
    if not candidates:
        return {}
    return candidates[0] if isinstance(candidates[0], dict) else {}


def _upsert_course(course_payload: dict[str, Any], *, now, client: MoodleApiClient) -> tuple[LearningCourse, bool]:
    moodle_course_id = _safe_int(course_payload.get("id"))
    if not moodle_course_id:
        raise MoodleApiError("Course payload does not contain a valid `id`.")

    course_url = course_payload.get("viewurl") or course_payload.get("courseurl") or ""
    if not course_url and client.config.base_url:
        course_url = f"{client.config.base_url}/course/view.php?id={moodle_course_id}"

    defaults = {
        "shortname": course_payload.get("shortname", "") or "",
        "fullname": (
            course_payload.get("fullname")
            or course_payload.get("displayname")
            or f"Course {moodle_course_id}"
        ),
        "category_name": str(course_payload.get("categoryname", "") or ""),
        "summary": course_payload.get("summary", "") or "",
        "moodle_url": course_url,
        "is_visible": bool(course_payload.get("visible", True)),
        "last_synced_at": now,
        "source_payload": course_payload,
    }
    course, created = LearningCourse.objects.update_or_create(
        moodle_course_id=moodle_course_id,
        defaults=defaults,
    )
    return course, created


def _sync_course_result(*, user, course, moodle_user_id: int, course_payload, client, now) -> None:
    completion_payload = client.get_course_completion_status(course.moodle_course_id, moodle_user_id)
    activities_payload = client.get_activities_completion_status(course.moodle_course_id, moodle_user_id)

    progress_percent = _calculate_progress_percent(activities_payload)
    status, completed_at = _derive_status_and_completion(
        completion_payload=completion_payload,
        activities_payload=activities_payload,
        progress_percent=progress_percent,
    )
    grade_value, grade_display = _extract_grade(course_payload, completion_payload)

    LearningCourseResult.objects.update_or_create(
        user=user,
        course=course,
        defaults={
            "status": status,
            "progress_percent": progress_percent,
            "grade_value": grade_value,
            "grade_display": grade_display,
            "completed_at": completed_at,
            "certificate_url": "",
            "last_synced_at": now,
            "source_payload": {
                "course": course_payload,
                "completion": completion_payload,
                "activities": activities_payload,
            },
        },
    )


def _calculate_progress_percent(activities_payload: dict[str, Any]) -> int:
    activities = activities_payload.get("statuses") or activities_payload.get("activities") or []
    if not isinstance(activities, list) or not activities:
        return 0

    completed = 0
    for item in activities:
        if not isinstance(item, dict):
            continue
        if _is_activity_completed(item):
            completed += 1

    return int(round((completed / max(len(activities), 1)) * 100))


def _derive_status_and_completion(*, completion_payload, activities_payload, progress_percent):
    completion = completion_payload.get("completionstatus") if isinstance(completion_payload, dict) else {}
    completed_flag = bool(
        (completion or {}).get("completed")
        or completion_payload.get("completed")
        or completion_payload.get("complete")
    )
    completed_at = _parse_moodle_datetime(
        (completion or {}).get("timecompleted")
        or completion_payload.get("timecompleted")
    )
    if completed_flag:
        return LearningCourseResult.Status.COMPLETED, completed_at or timezone.now()

    activities = activities_payload.get("statuses") or activities_payload.get("activities") or []
    if not activities or progress_percent <= 0:
        return LearningCourseResult.Status.NOT_STARTED, None

    return LearningCourseResult.Status.IN_PROGRESS, None


def _extract_grade(course_payload: dict[str, Any], completion_payload: dict[str, Any]):
    for source in (course_payload, completion_payload):
        if not isinstance(source, dict):
            continue
        for key in ("gradeformatted", "grade", "grademax"):
            value = source.get(key)
            if value in (None, ""):
                continue
            display = str(value)
            decimal_value = _to_decimal(value)
            return decimal_value, display
    return None, ""


def _extract_role_name(course_payload: dict[str, Any]) -> str:
    roles = course_payload.get("roles")
    if isinstance(roles, list) and roles:
        first = roles[0]
        if isinstance(first, dict):
            return str(first.get("shortname") or first.get("name") or "")
        return str(first)
    return ""


def _is_activity_completed(activity_payload: dict[str, Any]) -> bool:
    state = activity_payload.get("state")
    completionstate = activity_payload.get("completionstate")
    if state in (1, 2, 3):
        return True
    if completionstate in (1, 2):
        return True
    return bool(
        activity_payload.get("completed")
        or activity_payload.get("complete")
        or activity_payload.get("iscompleted")
    )


def _safe_int(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except Exception:
        return None


def _parse_moodle_datetime(value):
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    try:
        int_value = int(value)
        if int_value > 0:
            return datetime.fromtimestamp(int_value, tz=timezone.get_current_timezone())
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    except ValueError:
        return None
