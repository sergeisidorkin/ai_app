from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from projects_app.models import ProjectRegistration

from .services import sync_project_manager_assignment


@receiver(pre_save, sender=ProjectRegistration)
def remember_previous_project_manager(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_project_manager = ""
        return
    instance._previous_project_manager = (
        sender.objects
        .filter(pk=instance.pk)
        .values_list("project_manager", flat=True)
        .first()
        or ""
    )


@receiver(post_save, sender=ProjectRegistration)
def sync_project_manager_worktime_assignment(sender, instance, **kwargs):
    sync_project_manager_assignment(
        instance,
        previous_project_manager=getattr(instance, "_previous_project_manager", ""),
    )
