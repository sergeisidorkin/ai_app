from django.contrib import admin
from .models import (
    ChecklistCommentHistory,
    ChecklistItem,
    ChecklistRequestNote,
    ChecklistStatus,
    ChecklistStatusHistory,
)


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("code", "number", "short_name", "project", "section", "position")
    list_filter = ("project", "section")
    search_fields = ("code", "short_name", "name")


@admin.register(ChecklistStatus)
class ChecklistStatusAdmin(admin.ModelAdmin):
    list_display = ("checklist_item", "legal_entity", "status", "status_changed_at", "updated_by")
    list_filter = ("status", "status_changed_at")
    search_fields = ("checklist_item__name", "legal_entity__legal_name")


@admin.register(ChecklistStatusHistory)
class ChecklistStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("checklist_item", "legal_entity", "previous_status", "new_status", "changed_at", "changed_by")
    list_filter = ("new_status", "changed_at")
    search_fields = ("checklist_item__name", "legal_entity__legal_name")


@admin.register(ChecklistRequestNote)
class ChecklistRequestNoteAdmin(admin.ModelAdmin):
    list_display = ("checklist_item", "project", "asset_name", "section", "updated_at")
    search_fields = ("checklist_item__name", "asset_name", "project__name")


@admin.register(ChecklistCommentHistory)
class ChecklistCommentHistoryAdmin(admin.ModelAdmin):
    list_display = ("note", "field", "author", "created_at")
    list_filter = ("field", "created_at")
    search_fields = ("note__checklist_item__name", "author__username")
