from django.db import models
from django.contrib.auth import get_user_model


class YandexDiskAccount(models.Model):
    """Хранит OAuth-токены Яндекс.Диска для пользователя."""
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="yandexdisk_account"
    )
    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"YandexDiskAccount({self.user})"


class YandexDiskSelection(models.Model):
    """Выбранная папка/файл на Яндекс.Диске."""
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="yandexdisk_selection"
    )
    resource_path = models.CharField(max_length=1024, blank=True)  # путь на диске, напр. "/Documents/Projects"
    resource_name = models.CharField(max_length=512, blank=True)
    resource_type = models.CharField(max_length=32, blank=True)  # "dir" или "file"
    public_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} -> {self.resource_name or '-'}"
