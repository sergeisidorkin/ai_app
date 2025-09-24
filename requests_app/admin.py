from django.contrib import admin
from .models import RequestTable, RequestItem

@admin.register(RequestTable)
class RequestTableAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "section")
    list_filter = ("product", "section")
    search_fields = ("product__short_name", "product__name_en", "section__name_ru")

@admin.register(RequestItem)
class RequestItemAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "position", "code", "number", "name")
    list_display_links = ("id", "code")   # ВАЖНО
    list_editable = ("position",)
    list_filter = ("table",)
    search_fields = ("code", "name")