from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from classifiers_app.models import OKVCurrency
from experts_app.models import ExpertSpecialty
from group_app.models import GroupMember, OrgUnit

from .cache import schedule_policy_cache_invalidation
from .models import ExpertiseDirection, Product, SpecialtyTariff, TypicalSection
from .service_block_usage import sync_service_block_usage_counts


EXTERNAL_POLICY_DISPLAY_MODELS = {
    GroupMember,
    OrgUnit,
    ExpertSpecialty,
    OKVCurrency,
}

POLICY_M2M_THROUGH_MODELS = {
    Product.owners.through,
    ExpertiseDirection.owners.through,
    SpecialtyTariff.specialties.through,
}


@receiver(
    (post_save, post_delete),
    dispatch_uid="policy_app.invalidate_policy_models_after_commit",
)
def invalidate_policy_models_after_commit(sender, using, **kwargs):
    meta = getattr(sender, "_meta", None)
    if (
        getattr(meta, "app_label", None) == "policy_app"
        or sender in EXTERNAL_POLICY_DISPLAY_MODELS
    ):
        schedule_policy_cache_invalidation(using=using)


@receiver(pre_save, sender=TypicalSection, dispatch_uid="policy_app.remember_section_service_block")
def remember_section_service_block(sender, instance, **kwargs):
    if getattr(instance, "_skip_usage_recount", False) or not instance.pk:
        instance._usage_previous_service_block_id = instance.service_block_id if instance.pk else None
        return
    instance._usage_previous_service_block_id = (
        sender.objects.filter(pk=instance.pk).values_list("service_block_id", flat=True).first()
    )


@receiver(post_save, sender=TypicalSection, dispatch_uid="policy_app.sync_section_service_block_usage")
def sync_section_service_block_usage(sender, instance, **kwargs):
    if getattr(instance, "_skip_usage_recount", False):
        return
    previous = getattr(instance, "_usage_previous_service_block_id", None)
    if previous == instance.service_block_id:
        return
    sync_service_block_usage_counts([previous, instance.service_block_id])


@receiver(post_delete, sender=TypicalSection, dispatch_uid="policy_app.sync_section_service_block_usage_on_delete")
def sync_section_service_block_usage_on_delete(sender, instance, **kwargs):
    sync_service_block_usage_counts([instance.service_block_id])


@receiver(
    m2m_changed,
    dispatch_uid="policy_app.invalidate_policy_m2m_after_commit",
)
def invalidate_policy_m2m_after_commit(sender, action, using, **kwargs):
    if sender in POLICY_M2M_THROUGH_MODELS and action in {
        "post_add",
        "post_remove",
        "post_clear",
    }:
        schedule_policy_cache_invalidation(using=using)
