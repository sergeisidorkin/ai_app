from django.contrib import admin

from .models import Notification, NotificationPerformerLink


class NotificationPerformerLinkInline(admin.TabularInline):
    model = NotificationPerformerLink
    extra = 0
    autocomplete_fields = ("performer",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title_text",
        "recipient",
        "related_section",
        "notification_type",
        "is_read",
        "is_processed",
        "sent_at",
    )
    list_filter = ("related_section", "notification_type", "is_read", "is_processed")
    search_fields = ("title_text", "content_text", "recipient__username", "recipient__email")
    list_select_related = ("recipient", "sender", "project")
    autocomplete_fields = ("recipient", "sender", "project", "read_by", "action_by")
    inlines = [NotificationPerformerLinkInline]


@admin.register(NotificationPerformerLink)
class NotificationPerformerLinkAdmin(admin.ModelAdmin):
    list_display = ("notification", "performer", "position")
    autocomplete_fields = ("notification", "performer")
