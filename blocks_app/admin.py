from django.contrib import admin
from blocks_app.models import Block
from .models import TypicalSection

@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "product", "section", "updated_at")
    list_select_related = ("product", "section")
    list_filter = ("product", "section")
    search_fields = (
        "code",
        "name",
        "prompt",
        "context",
        "product__short_name",
        "section__name_ru",
    )
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("product", "section")
    ordering = ("-updated_at",)

@admin.register(TypicalSection)
class TypicalSectionAdmin(admin.ModelAdmin):
    list_display = ("name_ru", "product", "code", "short_name")
    list_select_related = ("product",)
    search_fields = ("name_ru", "name_en", "short_name", "code", "product__short_name")
    list_filter = ("product",)
    ordering = ("name_ru",)