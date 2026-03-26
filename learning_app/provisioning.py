from __future__ import annotations

import logging
import secrets
import string

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import LearningUserLink
from .moodle_api import MoodleApiClient, MoodleApiError

logger = logging.getLogger(__name__)
User = get_user_model()

MOODLE_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"


def sync_moodle_account_for_user(user_id: int, *, client: MoodleApiClient | None = None) -> LearningUserLink | None:
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return None
    return ensure_moodle_account(user, client=client)


def ensure_moodle_account(user, *, client: MoodleApiClient | None = None) -> LearningUserLink | None:
    client = client or MoodleApiClient()
    if not client.is_configured:
        logger.debug("Skip Moodle provisioning for user %s: Moodle is not configured.", user.pk)
        return None

    existing_link = LearningUserLink.objects.filter(user=user).first()
    if not _should_manage_in_moodle(user):
        if existing_link and existing_link.moodle_user_id:
            moodle_user_id = existing_link.moodle_user_id
            client.update_users([{"id": moodle_user_id, "suspended": 1}])
            existing_link.last_synced_at = timezone.now()
            existing_link.save(update_fields=["last_synced_at"])
        return existing_link

    moodle_user = _resolve_moodle_user(user, client=client, existing_link=existing_link)
    moodle_payload = _build_moodle_user_payload(user)

    if moodle_user:
        moodle_user_id = int(moodle_user["id"])
        _assert_link_is_available(user, moodle_user_id)
        client.update_users([{**moodle_payload, "id": moodle_user_id}])
        refreshed = client.get_users_by_id(moodle_user_id)
        moodle_user = refreshed[0] if refreshed else {**moodle_payload, "id": moodle_user_id}
    else:
        created_users = client.create_users([{**moodle_payload, "password": _generate_moodle_password()}])
        moodle_user = created_users[0] if created_users else _resolve_moodle_user(user, client=client)
        if not moodle_user:
            raise MoodleApiError(f"Unable to create or resolve Moodle user for Django user `{user.pk}`.")

    link, _ = LearningUserLink.objects.get_or_create(user=user)
    link.moodle_user_id = int(moodle_user["id"])
    link.moodle_username = str(moodle_user.get("username") or moodle_payload["username"])
    link.moodle_email = str(moodle_user.get("email") or moodle_payload["email"])
    link.last_synced_at = timezone.now()
    link.source_payload = moodle_user
    link.save()
    return link


def _should_manage_in_moodle(user) -> bool:
    return bool(user.is_active and user.is_staff and (user.email or "").strip())


def _resolve_moodle_user(user, *, client: MoodleApiClient, existing_link: LearningUserLink | None = None) -> dict:
    if existing_link and existing_link.moodle_user_id:
        candidates = client.get_users_by_id(existing_link.moodle_user_id)
        if candidates:
            return candidates[0]

    idnumber = _build_moodle_idnumber(user)
    candidates = client.get_users_by_idnumber(idnumber)
    if candidates:
        return candidates[0]

    email = (user.email or "").strip()
    if email:
        candidates = client.get_users_by_email(email)
        if candidates:
            return candidates[0]

    username = _build_moodle_username(user)
    candidates = client.get_users_by_username(username)
    if candidates:
        return candidates[0]

    return {}


def _build_moodle_user_payload(user) -> dict[str, object]:
    return {
        "username": _build_moodle_username(user),
        "firstname": (user.first_name or "").strip() or _build_moodle_username(user),
        "lastname": (user.last_name or "").strip() or "-",
        "email": (user.email or "").strip(),
        "auth": "manual",
        "suspended": 0 if user.is_active and user.is_staff else 1,
        "idnumber": _build_moodle_idnumber(user),
    }


def _build_moodle_username(user) -> str:
    username = (user.username or user.email or f"user-{user.pk}").strip().lower()
    return username[:100]


def _build_moodle_idnumber(user) -> str:
    return f"django:{user.pk}"


def _generate_moodle_password(length: int = 24) -> str:
    base = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    base.extend(secrets.choice(MOODLE_PASSWORD_ALPHABET) for _ in range(max(length - len(base), 0)))
    secrets.SystemRandom().shuffle(base)
    return "".join(base)


def _assert_link_is_available(user, moodle_user_id: int) -> None:
    other_link = (
        LearningUserLink.objects.select_related("user")
        .exclude(user=user)
        .filter(moodle_user_id=moodle_user_id)
        .first()
    )
    if other_link is None:
        return
    raise MoodleApiError(
        "Django users "
        f"`{other_link.user.get_username()}` and `{user.get_username()}` "
        f"resolve to the same Moodle user `{moodle_user_id}`."
    )
