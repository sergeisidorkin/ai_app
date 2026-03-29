from django.contrib import admin

from .models import CloudStorageSettings


@admin.register(CloudStorageSettings)
class CloudStorageSettingsAdmin(admin.ModelAdmin):
    list_display = ("primary_storage", "nextcloud_root_path", "updated_at")
    readonly_fields = ("updated_at",)
    fields = ("primary_storage", "nextcloud_root_path", "updated_at")

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        if not self.has_module_permission(request):
            return False
        return not CloudStorageSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
