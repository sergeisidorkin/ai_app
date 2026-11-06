from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from projects_app.models import ProjectRegistration
from projects_app.project_roles import PROJECT_SLOTS

from .services import sync_project_position_assignments

_POSITION_FIELDS = tuple(slot.name_field for slot in PROJECT_SLOTS.values())


@receiver(pre_save, sender=ProjectRegistration)
def remember_previous_project_positions(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_project_positions = {}
        return
    instance._previous_project_positions = (
        sender.objects
        .filter(pk=instance.pk)
        .values(*_POSITION_FIELDS)
        .first()
        or {}
    )


@receiver(post_save, sender=ProjectRegistration)
def sync_project_position_worktime_assignments(sender, instance, **kwargs):
    sync_project_position_assignments(
        instance,
        previous_names=getattr(instance, "_previous_project_positions", {}),
    )
