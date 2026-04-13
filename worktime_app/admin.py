from django.contrib import admin

from .models import PersonalWorktimeWeekAssignment, WorktimeAssignment, WorktimeEntry


@admin.register(WorktimeAssignment)
class WorktimeAssignmentAdmin(admin.ModelAdmin):
    list_display = ("executor_name", "registration", "record_type", "source_type", "employee", "performer")
    list_filter = ("record_type", "source_type")
    search_fields = ("executor_name", "registration__short_uid", "registration__name")
    autocomplete_fields = ("registration", "performer")


@admin.register(WorktimeEntry)
class WorktimeEntryAdmin(admin.ModelAdmin):
    list_display = ("assignment", "work_date", "hours")
    list_filter = ("work_date",)
    search_fields = ("assignment__executor_name", "assignment__registration__short_uid")


@admin.register(PersonalWorktimeWeekAssignment)
class PersonalWorktimeWeekAssignmentAdmin(admin.ModelAdmin):
    list_display = ("assignment", "week_start")
    list_filter = ("week_start",)
    search_fields = ("assignment__executor_name", "assignment__registration__short_uid", "assignment__registration__name")

