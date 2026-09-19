from __future__ import annotations

from django.db import models
from django.db.models.functions import Trim

from policy_app.models import SYSTEM_DSC_SECTION_CODE, Product, TypicalSection

from .models import Performer, ProjectRegistration, ProjectRegistrationProduct
from .report_submission import typical_section_short

ALL_PRODUCTS_LABEL = "Все продукты"
ALL_SECTIONS_LABEL = "Все разделы"
FULL_REPORT_SECTION_VALUE = "__full__"
MACRO_CHECK_VALUE = "Макрос"
ACTIVE_REPORT_STATUSES = ["Не начат", "В работе"]


def report_check_product_ids() -> list[int]:
    project_ids = (
        Performer.objects
        .annotate(executor_trim=Trim("executor"))
        .filter(registration__status__in=ACTIVE_REPORT_STATUSES)
        .exclude(executor_trim="")
        .values_list("registration_id", flat=True)
        .distinct()
    )
    linked_ids = set(
        ProjectRegistrationProduct.objects
        .filter(registration_id__in=project_ids)
        .values_list("product_id", flat=True)
        .distinct()
    )
    type_ids = set(
        ProjectRegistration.objects
        .filter(id__in=project_ids, type_id__isnull=False)
        .values_list("type_id", flat=True)
        .distinct()
    )
    return sorted(pid for pid in (linked_ids | type_ids) if pid)


def report_check_products():
    product_ids = report_check_product_ids()
    qs = Product.objects.filter(pk__in=product_ids) if product_ids else Product.objects.none()
    if not qs.exists():
        qs = Product.objects.all()
    return qs.order_by("position", "short_name", "id")


def report_check_sections(product_ids=None):
    qs = TypicalSection.objects.select_related("product")
    if product_ids is not None:
        qs = qs.filter(product_id__in=list(product_ids))
    return (
        qs.exclude(models.Q(is_system=True) | models.Q(code__iexact=SYSTEM_DSC_SECTION_CODE))
        .order_by("product__position", "product__short_name", "position", "id")
    )


def section_choice_label(section) -> str:
    return typical_section_short(section)


def product_choice_label(product) -> str:
    return (getattr(product, "short_name", "") or str(product or "")).strip()
