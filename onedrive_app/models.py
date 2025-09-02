from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model

class OneDriveAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token_cache = models.TextField(blank=True, default="")  # сериализованный MSAL cache

    def __str__(self):
        return f"OneDriveAccount({self.user})"

class OneDriveSelection(models.Model):
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="onedrive_selection"
    )
    drive_id = models.CharField(max_length=128, blank=True)
    item_id = models.CharField(max_length=256, blank=True)
    item_name = models.CharField(max_length=512, blank=True)
    item_path = models.CharField(max_length=1024, blank=True)
    web_url = models.URLField(blank=True)
    is_folder = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} -> {self.item_name or '-'}"