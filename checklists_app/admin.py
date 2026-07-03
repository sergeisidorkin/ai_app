from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from .models import (
    ChecklistCommentHistory,
    ChecklistItem,
    ChecklistItemAuditLog,
    ChecklistRequestNote,
    ChecklistStatus,
    ChecklistStatusHistory,
    _sync_project_gantt_for_checklist_item,
)


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("code", "number", "short_name", "project", "section", "position", "deleted_at", "deleted_by")
    list_filter = ("project", "section", "deleted_at", "item_type")
    search_fields = ("code", "short_name", "name")
    readonly_fields = ("created_at", "deleted_at", "deleted_by")
    actions = ("restore_items",)

    def get_queryset(self, request):
        return ChecklistItem.all_objects.select_related("project", "section", "deleted_by")

    @admin.action(description="Восстановить выбранные пункты чек-листа")
    def restore_items(self, request, queryset):
        actor = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(deleted_at__isnull=False))
            audit_rows = []
            for item in items:
                snapshot = item.snapshot()
                item.deleted_at = None
                item.deleted_by = None
                audit_rows.append(ChecklistItemAuditLog(
                    checklist_item=item,
                    project_id=item.project_id,
                    section_id=item.section_id,
                    action=ChecklistItemAuditLog.Action.RESTORED,
                    actor=actor,
                    snapshot=snapshot,
                    metadata={"source": "admin_restore"},
                ))
            if items:
                ChecklistItem.all_objects.bulk_update(items, ["deleted_at", "deleted_by"])
                ChecklistItemAuditLog.objects.bulk_create(audit_rows, batch_size=200)
                self._renumber_restored_sections(items)
                self._sync_restored_projects(items)
        self.message_user(request, f"Восстановлено пунктов: {len(items)}")

    def delete_model(self, request, obj):
        self._soft_delete_queryset(request, ChecklistItem.all_objects.filter(pk=obj.pk), source="admin_delete")

    def delete_queryset(self, request, queryset):
        self._soft_delete_queryset(request, queryset, source="admin_delete_selected")

    def _soft_delete_queryset(self, request, queryset, *, source):
        actor = request.user if request.user.is_authenticated else None
        now = timezone.now()
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(deleted_at__isnull=True))
            audit_rows = []
            for item in items:
                snapshot = item.snapshot()
                item.deleted_at = now
                item.deleted_by = actor
                audit_rows.append(ChecklistItemAuditLog(
                    checklist_item=item,
                    project_id=item.project_id,
                    section_id=item.section_id,
                    action=ChecklistItemAuditLog.Action.SOFT_DELETED,
                    actor=actor,
                    snapshot=snapshot,
                    metadata={"source": source, "deleted_at": now.isoformat()},
                ))
            if items:
                ChecklistItem.all_objects.bulk_update(items, ["deleted_at", "deleted_by"])
                ChecklistItemAuditLog.objects.bulk_create(audit_rows, batch_size=200)
                self._renumber_restored_sections(items)
                self._sync_restored_projects(items)

    def _renumber_restored_sections(self, items):
        section_keys = {(item.project_id, item.section_id) for item in items}
        for project_id, section_id in section_keys:
            active_items = list(
                ChecklistItem.objects
                .select_for_update()
                .filter(project_id=project_id, section_id=section_id)
                .order_by("position", "id")
            )
            changed = []
            for idx, item in enumerate(active_items, start=1):
                if item.number != idx:
                    item.number = idx
                    changed.append(item)
            if changed:
                ChecklistItem.objects.bulk_update(changed, ["number"], batch_size=200)

    def _sync_restored_projects(self, items):
        for project_id in {item.project_id for item in items}:
            _sync_project_gantt_for_checklist_item(project_id)


@admin.register(ChecklistItemAuditLog)
class ChecklistItemAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "checklist_item", "project", "section", "actor", "change_batch_id")
    list_filter = ("action", "created_at", "project", "section")
    search_fields = ("checklist_item__name", "checklist_item__short_name", "actor__username")
    readonly_fields = (
        "checklist_item",
        "project",
        "section",
        "action",
        "actor",
        "snapshot",
        "metadata",
        "change_batch_id",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
