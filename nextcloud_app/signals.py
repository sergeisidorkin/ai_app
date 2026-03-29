import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import NextcloudUserLink
from .provisioning import sync_nextcloud_account_for_user

logger = logging.getLogger(__name__)
User = get_user_model()
RELEVANT_USER_FIELDS = {"is_active", "is_staff", "username", "email", "first_name", "last_name"}


@receiver(post_save, sender=User)
def sync_staff_user_to_nextcloud(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw:
        return

    if not created and update_fields is not None and RELEVANT_USER_FIELDS.isdisjoint(set(update_fields)):
        return

    should_sync = instance.is_staff or NextcloudUserLink.objects.filter(user=instance).exists()
    if not should_sync:
        return

    def _run():
        try:
            sync_nextcloud_account_for_user(instance.pk)
        except Exception:
            logger.exception("Failed to sync Nextcloud account for Django user %s", instance.pk)

    transaction.on_commit(_run)
