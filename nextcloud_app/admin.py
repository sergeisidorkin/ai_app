from django.contrib import admin

from .models import NextcloudUserLink


@admin.register(NextcloudUserLink)
class NextcloudUserLinkAdmin(admin.ModelAdmin):
    list_display = ("user", "nextcloud_user_id", "nextcloud_email", "last_synced_at")
    search_fields = ("user__username", "user__email", "nextcloud_username", "nextcloud_email")
