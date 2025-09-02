from django.conf import settings
from django.db import models

class OpenAIAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="openai_account"
    )
    api_key = models.CharField(max_length=256)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"OpenAI({self.user})"