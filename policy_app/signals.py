from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from classifiers_app.models import OKVCurrency
from experts_app.models import ExpertSpecialty
from group_app.models import GroupMember, OrgUnit

from .cache import schedule_policy_cache_invalidation
from .models import ExpertiseDirection, Product, SpecialtyTariff, TypicalSection


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
    TypicalSection.specialties.through,
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
