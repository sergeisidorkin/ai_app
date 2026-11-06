"""Частота продукта по этапам реестра проектов.

Считается заранее и хранится на продукте, чтобы списки «Продукт» не делали
COUNT при каждом открытии. Этап — дочерняя строка реестра. Если у проекта
только одна строка, она тоже считается этапом. Сводная строка при наличии
этапов в частоту не входит.
"""

from django.db.models import Count, Q
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver


def countable_stage_registrations():
    from projects_app.models import ProjectRegistration

    parent_ids = ProjectRegistration.objects.filter(
        stage_project_id__isnull=False
    ).values("stage_project_id")
    return ProjectRegistration.objects.filter(
        Q(stage_project_id__isnull=False)
        | (Q(stage_project_id__isnull=True) & ~Q(pk__in=parent_ids))
    )


def sync_product_usage_counts(product_ids):
    ids = {product_id for product_id in product_ids if product_id}
    if not ids:
        return

    from policy_app.models import Product
    from projects_app.models import ProjectRegistrationProduct

    stages = countable_stage_registrations()
    totals = {product_id: 0 for product_id in ids}
    link_rows = (
        ProjectRegistrationProduct.objects.filter(product_id__in=ids, registration__in=stages)
        .values("product_id")
        .annotate(total=Count("registration_id", distinct=True))
    )
    for row in link_rows:
        totals[row["product_id"]] = row["total"]
    linked_registration_ids = ProjectRegistrationProduct.objects.filter(
        registration__in=stages
    ).values("registration_id")
    type_rows = (
        stages.filter(type_id__in=ids)
        .exclude(pk__in=linked_registration_ids)
        .values("type_id")
        .annotate(total=Count("pk"))
    )
    for row in type_rows:
        totals[row["type_id"]] += row["total"]
    for product_id, total in totals.items():
        Product.objects.filter(pk=product_id).update(usage_count=total)


def _registration_product_ids(registration):
    ids = set(registration.product_links.values_list("product_id", flat=True))
    if registration.type_id:
        ids.add(registration.type_id)
    return ids


def _family_product_ids(registration, previous_stage_project_id=None):
    from projects_app.models import ProjectRegistration

    registration_ids = {registration.pk}
    if registration.stage_project_id:
        registration_ids.add(registration.stage_project_id)
    if previous_stage_project_id:
        registration_ids.add(previous_stage_project_id)
    ids = set()
    for item in ProjectRegistration.objects.filter(pk__in=registration_ids):
        ids.update(_registration_product_ids(item))
    if registration.type_id:
        ids.add(registration.type_id)
    return ids


@receiver(pre_save, sender="projects_app.ProjectRegistration", dispatch_uid="projects_app.remember_product_usage_stage")
def remember_product_usage_stage(sender, instance, **kwargs):
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and not set(update_fields).intersection(
        {"stage_project", "stage_project_id", "type", "type_id"}
    ):
        instance._skip_product_usage_recount = True
        return
    instance._skip_product_usage_recount = False
    if not instance.pk:
        instance._usage_previous_stage_project_id = None
        return
    instance._usage_previous_stage_project_id = (
        sender.objects.filter(pk=instance.pk).values_list("stage_project_id", flat=True).first()
    )


@receiver(post_save, sender="projects_app.ProjectRegistration", dispatch_uid="projects_app.sync_product_usage_on_registration_save")
def sync_product_usage_on_registration_save(sender, instance, **kwargs):
    if getattr(instance, "_skip_product_usage_recount", False):
        return
    sync_product_usage_counts(
        _family_product_ids(instance, getattr(instance, "_usage_previous_stage_project_id", None))
    )


@receiver(pre_delete, sender="projects_app.ProjectRegistration", dispatch_uid="projects_app.remember_product_usage_on_registration_delete")
def remember_product_usage_on_registration_delete(sender, instance, **kwargs):
    instance._usage_product_ids_before_delete = _family_product_ids(instance)


@receiver(post_delete, sender="projects_app.ProjectRegistration", dispatch_uid="projects_app.sync_product_usage_on_registration_delete")
def sync_product_usage_on_registration_delete(sender, instance, **kwargs):
    ids = set(getattr(instance, "_usage_product_ids_before_delete", set()))
    if instance.type_id:
        ids.add(instance.type_id)
    if instance.stage_project_id:
        from projects_app.models import ProjectRegistration

        parent = ProjectRegistration.objects.filter(pk=instance.stage_project_id).first()
        if parent is not None:
            ids.update(_registration_product_ids(parent))
    sync_product_usage_counts(ids)


@receiver(pre_save, sender="projects_app.ProjectRegistrationProduct", dispatch_uid="projects_app.remember_product_usage_link")
def remember_product_usage_link(sender, instance, **kwargs):
    if not instance.pk:
        instance._usage_previous_product_id = None
        return
    instance._usage_previous_product_id = (
        sender.objects.filter(pk=instance.pk).values_list("product_id", flat=True).first()
    )


@receiver(post_save, sender="projects_app.ProjectRegistrationProduct", dispatch_uid="projects_app.sync_product_usage_on_link_save")
def sync_product_usage_on_link_save(sender, instance, **kwargs):
    sync_product_usage_counts([instance.product_id, getattr(instance, "_usage_previous_product_id", None)])


@receiver(post_delete, sender="projects_app.ProjectRegistrationProduct", dispatch_uid="projects_app.sync_product_usage_on_link_delete")
def sync_product_usage_on_link_delete(sender, instance, **kwargs):
    sync_product_usage_counts([instance.product_id])
