from django.contrib import admin
from .models import (
    ChecklistCommentHistory,
    ChecklistRequestNote,
    ChecklistStatus,
    ChecklistStatusHistory,
)

@admin.register(ChecklistStatus)
class ChecklistStatusAdmin(admin.ModelAdmin):
    list_display = ("request_item", "legal_entity", "status", "status_changed_at", "updated_by")
    list_filter = ("status", "status_changed_at")
    search_fields = ("request_item__name", "legal_entity__legal_name")


@admin.register(ChecklistStatusHistory)
class ChecklistStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("request_item", "legal_entity", "previous_status", "new_status", "changed_at", "changed_by")
    list_filter = ("new_status", "changed_at")
    search_fields = ("request_item__name", "legal_entity__legal_name")


@admin.register(ChecklistRequestNote)
class ChecklistRequestNoteAdmin(admin.ModelAdmin):
    list_display = ("request_item", "project", "asset_name", "section", "updated_at")
    search_fields = ("request_item__name", "asset_name", "project__name")


@admin.register(ChecklistCommentHistory)
class ChecklistCommentHistoryAdmin(admin.ModelAdmin):
    list_display = ("note", "field", "author", "created_at")
    list_filter = ("field", "created_at")
    search_fields = ("note__request_item__name", "author__username", "author__first_name", "author__last_name")