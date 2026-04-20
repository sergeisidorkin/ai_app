from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .contact_sync import detach_employee_contacts, sync_employee_contacts
from .models import Employee


@receiver(post_save, sender=Employee)
def employee_post_save_sync_contacts(sender, instance, **kwargs):
    sync_employee_contacts(instance)


@receiver(pre_delete, sender=Employee)
def employee_pre_delete_detach_contacts(sender, instance, **kwargs):
    detach_employee_contacts(instance)
