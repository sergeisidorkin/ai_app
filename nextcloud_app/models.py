from django.conf import settings
from django.db import models


class NextcloudUserLink(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nextcloud_link",
    )
    nextcloud_user_id = models.CharField("ID пользователя в Nextcloud", max_length=255, unique=True)
    nextcloud_username = models.CharField("Логин в Nextcloud", max_length=255, blank=True, default="")
    nextcloud_email = models.EmailField("Email в Nextcloud", blank=True, default="")
    last_synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    source_payload = models.JSONField("Сырые данные Nextcloud", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Связка пользователя с Nextcloud"
        verbose_name_plural = "Связки пользователей с Nextcloud"

    def __str__(self):
        return self.user.get_username()
