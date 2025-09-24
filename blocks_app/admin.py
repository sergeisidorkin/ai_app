from django.contrib import admin
from .models import Block
from policy_app.models import TypicalSection
from requests_app.models import RequestItem
import json


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "product",
        "section",
        "context_display",   # «Код-№ Краткое»
        "model",
        "temperature",
        "updated_at",
    )
    list_select_related = ("product", "section")
    list_filter = ("product", "section", "model")
    search_fields = (
        "code",
        "name",
        "prompt",
        "context",
        "product__short_name",
        "product__name_en",
        "section__name_ru",
        "section__code",
    )
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("product", "section")
    ordering = ("-updated_at",)
    date_hierarchy = "updated_at"
    list_per_page = 50

    @admin.display(description="Контекст")
    def context_display(self, obj: Block) -> str:
        val = (obj.context or "").strip()
        if not val:
            return "—"
        # JSON-массив строк?
        if val.startswith("["):
            try:
                arr = json.loads(val)
                labels = [str(x).strip() for x in (arr or []) if str(x).strip()]
                return ", ".join(labels) if labels else "—"
            except Exception:
                pass
        # старые варианты
        if val.isdigit():
            try:
                ri = (RequestItem.objects
                      .select_related("table__section")
                      .get(pk=val))
                sec_code = getattr(getattr(ri.table, "section", None), "code", "") or ""
                num = f"{ri.number:02d}" if ri.number is not None else ""
                short = ri.short_name or ri.name or ""
                return f"{sec_code}-{num} {short}".strip()
            except RequestItem.DoesNotExist:
                return val
        return val


# Регистрация TypicalSection (если не регистрируется в policy_app.admin)
class TypicalSectionAdmin(admin.ModelAdmin):
    list_display = ("name_ru", "product", "code", "short_name")
    list_select_related = ("product",)
    search_fields = ("name_ru", "name_en", "short_name", "code", "product__short_name")
    list_filter = ("product",)
    ordering = ("name_ru",)


# Безопасная регистрация, чтобы не падать, если модель уже зарегистрирована где-то ещё
try:
    admin.site.register(TypicalSection, TypicalSectionAdmin)
except admin.sites.AlreadyRegistered:
    pass