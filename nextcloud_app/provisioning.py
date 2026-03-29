from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from .api import NextcloudApiClient, NextcloudApiError
from .models import NextcloudUserLink

logger = logging.getLogger(__name__)
User = get_user_model()


def sync_nextcloud_account_for_user(user_id: int, *, client: NextcloudApiClient | None = None) -> NextcloudUserLink | None:
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return None
    return ensure_nextcloud_account(user, client=client)


def ensure_nextcloud_account(user, *, client: NextcloudApiClient | None = None) -> NextcloudUserLink | None:
    client = client or NextcloudApiClient()
    if not client.is_configured:
        logger.debug("Skip Nextcloud provisioning for user %s: Nextcloud is not configured.", user.pk)
        return None

    existing_link = NextcloudUserLink.objects.filter(user=user).first()
    nextcloud_user_id = _build_nextcloud_user_id(user)

    if not _should_manage_in_nextcloud(user):
        if existing_link and existing_link.nextcloud_user_id:
            client.disable_user(existing_link.nextcloud_user_id)
            existing_link.last_synced_at = timezone.now()
            existing_link.save(update_fields=["last_synced_at"])
        return existing_link

    provisioned = client.provision_user(
        user_id=nextcloud_user_id,
        display_name=_build_display_name(user),
        email=(user.email or "").strip(),
    )
    client.enable_user(provisioned.user_id)
    client.set_user_email(provisioned.user_id, (user.email or "").strip())
    client.set_user_display_name(provisioned.user_id, _build_display_name(user))

    link, _ = NextcloudUserLink.objects.get_or_create(user=user)
    _assert_link_is_available(user, provisioned.user_id)
    link.nextcloud_user_id = provisioned.user_id
    link.nextcloud_username = provisioned.user_id
    link.nextcloud_email = provisioned.email
    link.last_synced_at = timezone.now()
    link.source_payload = {
        "user_id": provisioned.user_id,
        "display_name": provisioned.display_name,
        "email": provisioned.email,
    }
    link.save()
    return link


def _should_manage_in_nextcloud(user) -> bool:
    return bool(user.is_active and user.is_staff and (user.email or "").strip())


def _build_nextcloud_user_id(user) -> str:
    return f"ncstaff-{user.pk}"


def _build_display_name(user) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.get_username()


def _assert_link_is_available(user, nextcloud_user_id: str) -> None:
    other_link = (
        NextcloudUserLink.objects.select_related("user")
        .exclude(user=user)
        .filter(nextcloud_user_id=nextcloud_user_id)
        .first()
    )
    if other_link is None:
        return
    raise NextcloudApiError(
        "Django users "
        f"`{other_link.user.get_username()}` and `{user.get_username()}` "
        f"resolve to the same Nextcloud user `{nextcloud_user_id}`."
    )
