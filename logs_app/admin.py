# logs_app/admin.py
from django.contrib import admin
from .models import LogEvent

@admin.register(LogEvent)
class LogEventAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    list_select_related = ("user",)
    raw_id_fields = ("user",)

    # Колонки списка
    list_display = (
        "created_at",
        "level",
        "phase",
        "event",
        "via",
        "email",
        "user",
        "project_code6",
        "company",
        "section",
        "job_id",
        "trace_id",
        "short_message",
    )

    # Фильтры справа
    list_filter = ("level", "phase", "via", "company", "section")

    # Поиск
    search_fields = (
        "email",
        "user__email",
        "message",
        "doc_url",
        "trace_id",
        "request_id",
        "job_id",
        "event",
        "company",
        "section",
        "project_code6",
        "anchor_text",
    )

    # Только чтение
    readonly_fields = ("id", "created_at", "trace_id")

    # Группировка полей на форме
    fieldsets = (
        ("General", {
            "fields": ("id", "created_at", "level", "phase", "event", "message"),
        }),
        ("Context", {
            "fields": ("user", "email", "via", "project_code6", "company", "section", "anchor_text"),
        }),
        ("IDs", {
            "fields": ("trace_id", "request_id", "job_id"),
        }),
        ("Document", {
            "fields": ("doc_url",),
        }),
        ("Data", {
            "fields": ("data",),
        }),
    )

    # Короткая версия message в списке
    def short_message(self, obj):
        msg = obj.message or ""
        return (msg[:120] + "…") if len(msg) > 120 else msg
    short_message.short_description = "message"