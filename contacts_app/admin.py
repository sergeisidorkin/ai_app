from django.contrib import admin

from .models import PersonRecord, PositionRecord


@admin.register(PersonRecord)
class PersonRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "last_name", "first_name", "middle_name", "citizenship", "identifier", "number")
    search_fields = ("last_name", "first_name", "middle_name", "identifier", "number")
    list_filter = ("citizenship",)


@admin.register(PositionRecord)
class PositionRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "organization_short_name", "job_title", "valid_from", "valid_to", "record_date")
    search_fields = ("person__last_name", "person__first_name", "organization_short_name", "job_title", "source")
