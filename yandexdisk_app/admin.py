from django.contrib import admin
from .models import YandexDiskAccount, YandexDiskSelection


@admin.register(YandexDiskAccount)
class YandexDiskAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__username",)


@admin.register(YandexDiskSelection)
class YandexDiskSelectionAdmin(admin.ModelAdmin):
    list_display = ("user", "resource_name", "resource_path", "updated_at")
    search_fields = ("user__username", "resource_name")