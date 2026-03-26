from django.contrib import admin

from .models import (
    LearningCourse,
    LearningCourseResult,
    LearningEnrollment,
    LearningSyncRun,
    LearningUserLink,
)


@admin.register(LearningUserLink)
class LearningUserLinkAdmin(admin.ModelAdmin):
    list_display = ("user", "moodle_user_id", "moodle_email", "last_synced_at")
    search_fields = ("user__username", "user__email", "moodle_username", "moodle_email")


@admin.register(LearningCourse)
class LearningCourseAdmin(admin.ModelAdmin):
    list_display = ("fullname", "moodle_course_id", "category_name", "is_visible", "last_synced_at")
    list_filter = ("is_visible", "category_name")
    search_fields = ("fullname", "shortname", "category_name")


@admin.register(LearningEnrollment)
class LearningEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "role_name", "enrolled_at", "last_synced_at")
    list_filter = ("role_name",)
    search_fields = ("user__username", "user__email", "course__fullname", "course__shortname")


@admin.register(LearningCourseResult)
class LearningCourseResultAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "course",
        "status",
        "progress_percent",
        "grade_display",
        "completed_at",
        "last_synced_at",
    )
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "course__fullname", "course__shortname")


@admin.register(LearningSyncRun)
class LearningSyncRunAdmin(admin.ModelAdmin):
    list_display = ("scope", "status", "started_at", "finished_at")
    list_filter = ("scope", "status")
