import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.cloud_paths import normalize_cloud_path
from users_app.models import Employee

from .models import NextcloudUserLink
from .provisioning import sync_nextcloud_account_for_user
from .workspace import revoke_contract_folder_access_for_user

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


def _employee_user_id(employee_id: int | None) -> int | None:
    if not employee_id:
        return None
    return Employee.objects.filter(pk=employee_id).values_list("user_id", flat=True).first()


def _performer_contract_access_snapshot(performer) -> tuple[int | None, str]:
    folder = normalize_cloud_path(getattr(performer, "contract_project_disk_folder", "") or "")
    if folder == "/":
        folder = ""
    return _employee_user_id(getattr(performer, "employee_id", None)), folder


def _schedule_contract_share_revoke(user_id: int | None, folder_path: str) -> None:
    if not user_id or not folder_path:
        return

    def _run():
        revoke_contract_folder_access_for_user(user_id, folder_path)

    transaction.on_commit(_run)


from projects_app.models import Performer, ProjectRegistration  # noqa: E402

_WORKSPACE_POSITION_FIELDS = (
    "project_manager",
    "project_manager_prs_id",
    "project_coordinator",
    "project_coordinator_prs_id",
)


def _workspace_position_snapshot(registration) -> dict:
    return {
        field: (getattr(registration, field, "") or "")
        for field in _WORKSPACE_POSITION_FIELDS
    }


@receiver(pre_save, sender=ProjectRegistration)
def remember_previous_workspace_positions(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        instance._previous_workspace_positions = {}
        return
    instance._previous_workspace_positions = (
        sender.objects.filter(pk=instance.pk).values(*_WORKSPACE_POSITION_FIELDS).first()
        or {}
    )


@receiver(post_save, sender=ProjectRegistration)
def grant_workspace_access_on_position_assignment(
    sender,
    instance,
    raw=False,
    update_fields=None,
    **kwargs,
):
    if raw:
        return
    if update_fields is not None and set(update_fields).isdisjoint(_WORKSPACE_POSITION_FIELDS):
        return
    previous = getattr(instance, "_previous_workspace_positions", {}) or {}
    current = _workspace_position_snapshot(instance)
    if all((previous.get(field) or "") == current[field] for field in _WORKSPACE_POSITION_FIELDS):
        return

    project_id = instance.pk

    def _run():
        from .workspace import grant_existing_project_workspace_editor_access

        try:
            grant_existing_project_workspace_editor_access(project_id)
        except Exception:
            logger.exception(
                "Failed to grant Nextcloud workspace access after position assignment on project %s",
                project_id,
            )

    transaction.on_commit(_run)


@receiver(pre_save, sender=Performer)
def capture_previous_nextcloud_contract_share(sender, instance, raw=False, **kwargs):
    if hasattr(instance, "_nextcloud_previous_contract_share"):
        delattr(instance, "_nextcloud_previous_contract_share")
    if raw or not instance.pk:
        return

    previous = (
        sender.objects
        .filter(pk=instance.pk)
        .values("employee_id", "contract_project_disk_folder")
        .first()
    )
    if previous is None:
        return

    old_user_id = _employee_user_id(previous["employee_id"])
    old_folder = normalize_cloud_path(previous["contract_project_disk_folder"] or "")
    if old_folder == "/":
        old_folder = ""
    new_user_id, new_folder = _performer_contract_access_snapshot(instance)
    if old_user_id != new_user_id or old_folder != new_folder:
        instance._nextcloud_previous_contract_share = (old_user_id, old_folder)


@receiver(post_save, sender=Performer)
def revoke_previous_nextcloud_contract_share(sender, instance, raw=False, **kwargs):
    if raw:
        return

    snapshot = getattr(instance, "_nextcloud_previous_contract_share", None)
    if not snapshot:
        return
    delattr(instance, "_nextcloud_previous_contract_share")
    old_user_id, old_folder = snapshot
    _schedule_contract_share_revoke(old_user_id, old_folder)


@receiver(post_delete, sender=Performer)
def revoke_deleted_nextcloud_contract_share(sender, instance, **kwargs):
    old_user_id, old_folder = _performer_contract_access_snapshot(instance)
    _schedule_contract_share_revoke(old_user_id, old_folder)
