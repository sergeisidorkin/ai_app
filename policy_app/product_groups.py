from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import PRODUCT_GROUP_MARK, Product, with_product_group_mark
from .querysets import ordered_owner_display_prefetch

PRODUCT_GROUP_CSV_HEADER = "Групповой продукт"
CLASSIFICATION_LOCK_FIELDS = (
    "consulting_type_ref",
    "service_category_ref",
    "service_subtype_ref",
    "owner_ids",
)


def grouping_signature(product):
    return (
        product.consulting_type_ref_id,
        product.service_category_ref_id,
        (product.service_code or "").strip(),
        product.service_subtype_ref_id,
        product.grouping_owner_key(),
    )


def load_products_for_grouping(product_ids):
    ids = []
    for value in product_ids:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in ids:
            ids.append(parsed)
    if not ids:
        return []
    products = list(
        Product.objects.filter(pk__in=ids)
        .select_related("consulting_type_ref", "service_category_ref", "service_subtype_ref")
        .prefetch_related(ordered_owner_display_prefetch())
    )
    by_id = {product.pk: product for product in products}
    return [by_id[pk] for pk in ids if pk in by_id]


def validate_group_members(products, expected_count=None):
    if expected_count is not None and len(products) != expected_count:
        raise ValidationError("Не удалось найти все выбранные продукты.")
    if len(products) < 2:
        raise ValidationError("Выберите не меньше двух продуктов.")
    if any(product.is_product_group or product.group_id for product in products):
        raise ValidationError("В группу можно объединить только обычные продукты.")
    signature = grouping_signature(products[0])
    if any(grouping_signature(product) != signature for product in products[1:]):
        raise ValidationError(
            "У выбранных продуктов должны совпадать вид консалтинга, тип услуг, код, подтип услуги и владелец."
        )
    return products


def _copy_classification(source, target):
    target.consulting_type_ref_id = source.consulting_type_ref_id
    target.service_category_ref_id = source.service_category_ref_id
    target.service_subtype_ref_id = source.service_subtype_ref_id
    target.consulting_type = source.consulting_type
    target.service_category = source.service_category
    target.service_code = source.service_code
    target.service_subtype = source.service_subtype
    target.is_group_owner = source.is_group_owner


def _locked_products():
    return list(Product.objects.select_for_update().order_by("position", "id"))


def _blocks(products):
    by_group = defaultdict(list)
    top = []
    for product in sorted(products, key=lambda item: (item.position, item.id)):
        if product.group_id:
            by_group[product.group_id].append(product)
        else:
            top.append(product)
    return top, by_group


def _flatten(top, by_group):
    ordered = []
    for item in top:
        ordered.append(item)
        if item.is_product_group:
            ordered.extend(by_group.get(item.pk, []))
    return ordered


def _write_positions(ordered):
    changed = []
    for index, product in enumerate(ordered, start=1):
        if product.position != index:
            product.position = index
            changed.append(product)
    if changed:
        Product.objects.bulk_update(changed, ["position"])
    return ordered


def normalize_product_positions():
    products = _locked_products()
    top, by_group = _blocks(products)
    return _write_positions(_flatten(top, by_group))


def move_product(pk, direction):
    with transaction.atomic():
        products = _locked_products()
        top, by_group = _blocks(products)
        product = next((item for item in products if item.pk == pk), None)
        if product is None:
            return
        if product.group_id:
            siblings = by_group.get(product.group_id, [])
            index = next(i for i, item in enumerate(siblings) if item.pk == pk)
            swap_with = index - 1 if direction == "up" else index + 1
            if 0 <= swap_with < len(siblings):
                siblings[index], siblings[swap_with] = siblings[swap_with], siblings[index]
                by_group[product.group_id] = siblings
        else:
            index = next(i for i, item in enumerate(top) if item.pk == pk)
            swap_with = index - 1 if direction == "up" else index + 1
            if 0 <= swap_with < len(top):
                top[index], top[swap_with] = top[swap_with], top[index]
        _write_positions(_flatten(top, by_group))


def dissolve_product_group_if_sparse(group_id):
    if not group_id:
        return
    if Product.objects.filter(group_id=group_id).count() >= 2:
        return
    Product.objects.filter(pk=group_id, is_product_group=True).delete()


@transaction.atomic
def create_product_group(products, short_name, name_en, name_ru, display_name):
    validate_group_members(products)
    members = sorted(products, key=lambda item: (item.position, item.id))
    source = members[0]
    group = Product(
        short_name=with_product_group_mark(short_name),
        name_en=(name_en or "").strip(),
        name_ru=(name_ru or "").strip(),
        display_name=(display_name or "").strip(),
        is_product_group=True,
        position=source.position,
        accuracy="",
    )
    _copy_classification(source, group)
    group.save()
    if group.is_group_owner:
        group.owners.clear()
    else:
        group.owners.set([owner.pk for owner in getattr(source, "_policy_owner_display_items", [])] or list(
            source.owners.values_list("pk", flat=True)
        ))
    Product.objects.filter(pk__in=[member.pk for member in members]).update(group_id=group.pk)
    normalize_product_positions()
    return group


def ungroup_products(products):
    labels = [product for product in products if getattr(product, "is_product_group", False)]
    for label in labels:
        label.delete()


def csv_group_label(product):
    group = getattr(product, "group", None)
    if product.group_id and group is not None:
        return group.short_name or ""
    return ""


def product_short_name_is_group(short_name):
    return str(short_name or "").strip().endswith(PRODUCT_GROUP_MARK)


def product_catalog_queryset():
    from django.db.models import Prefetch

    return Product.objects.order_by("position", "id").prefetch_related(
        Prefetch(
            "grouped_products",
            queryset=Product.objects.order_by("position", "id"),
            to_attr="grouped_members",
        )
    )


def catalog_group_payload(product):
    members = list(getattr(product, "grouped_members", []) or [])
    return {
        "is_group": bool(product.is_product_group),
        "member_ids": [member.pk for member in members] if product.is_product_group else [],
    }


def grouped_type_short_names(links):
    prepared = []
    counts = {}
    for link in links:
        product = getattr(link, "product", None)
        if product is None:
            continue
        group_id = getattr(link, "product_group_id", None)
        is_member = bool(group_id and getattr(product, "group_id", None) == group_id)
        group = None
        if is_member:
            counts[group_id] = counts.get(group_id, 0) + 1
            group = getattr(link, "product_group", None) or getattr(product, "group", None)
        prepared.append((product, group_id, group, is_member))
    names = []
    emitted = set()
    for product, group_id, group, is_member in prepared:
        if is_member and counts.get(group_id, 0) >= 2:
            if group_id in emitted:
                continue
            label = (getattr(group, "short_name", "") or "").strip()
            if label:
                names.append(label)
                emitted.add(group_id)
            continue
        label = (getattr(product, "short_name", "") or "").strip()
        if label:
            names.append(label)
    return names


def resolve_posted_group_ids(product_ids, raw_group_ids):
    membership = {
        product.pk: product.group_id
        for product in Product.objects.filter(pk__in=set(product_ids)).only("id", "group_id")
    }
    resolved = []
    for index, product_id in enumerate(product_ids):
        raw = raw_group_ids[index] if index < len(raw_group_ids or []) else ""
        try:
            group_id = int(str(raw).strip())
        except (TypeError, ValueError):
            group_id = None
        if not group_id or membership.get(product_id) != group_id:
            resolved.append(None)
            continue
        resolved.append(group_id)
    counts = {}
    for group_id in resolved:
        if group_id:
            counts[group_id] = counts.get(group_id, 0) + 1
    return [
        group_id if group_id and counts[group_id] >= 2 else None
        for group_id in resolved
    ]
