from django.db import migrations


ATTRIBUTE_NAME = "Наименование"
ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def _period_order_is_invalid(valid_from, valid_to, *, exclusive_end):
    if valid_from is None or valid_to is None:
        return False
    return valid_to <= valid_from if exclusive_end else valid_to < valid_from


def _periods_overlap(valid_from, valid_to, other_from, other_to, *, exclusive_end):
    if exclusive_end:
        if valid_to is not None and other_from is not None and valid_to <= other_from:
            return False
        if other_to is not None and valid_from is not None and other_to <= valid_from:
            return False
        return True
    if valid_to is not None and other_from is not None and valid_to < other_from:
        return False
    if other_to is not None and valid_from is not None and other_to < valid_from:
        return False
    return True


def _end_is_after(current_end, previous_end):
    if current_end is None:
        return previous_end is not None
    if previous_end is None:
        return False
    return current_end > previous_end


def _validate_queryset(queryset, *, group_attr, start_attr, end_attr, exclusive_end, registry_label, group_label):
    items = list(queryset.iterator())
    items.sort(
        key=lambda item: (
            getattr(item, group_attr),
            getattr(item, start_attr) is not None,
            getattr(item, start_attr),
            getattr(item, end_attr) is not None,
            getattr(item, end_attr),
            item.pk,
        )
    )
    current_group = None
    current_item = None
    for item in items:
        group_value = getattr(item, group_attr)
        start_value = getattr(item, start_attr)
        end_value = getattr(item, end_attr)

        if _period_order_is_invalid(start_value, end_value, exclusive_end=exclusive_end):
            raise RuntimeError(
                f"Обнаружен некорректный период в \"{registry_label}\": запись {item.pk} "
                f"для {group_label} {group_value} имеет несовместимые границы периода."
            )

        if current_group != group_value:
            current_group = group_value
            current_item = item
            continue

        if _periods_overlap(
            getattr(current_item, start_attr),
            getattr(current_item, end_attr),
            start_value,
            end_value,
            exclusive_end=exclusive_end,
        ):
            raise RuntimeError(
                f"Обнаружены пересекающиеся периоды в \"{registry_label}\" для {group_label} {group_value}: "
                f"записи {current_item.pk} и {item.pk}. Устраните пересечение до применения EXCLUDE constraint."
            )

        if _end_is_after(end_value, getattr(current_item, end_attr)):
            current_item = item


def forwards_validate_no_period_overlaps(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias

    _validate_queryset(
        BusinessEntityIdentifierRecord.objects.using(db_alias).order_by("business_entity_id", "valid_from", "valid_to", "id"),
        group_attr="business_entity_id",
        start_attr="valid_from",
        end_attr="valid_to",
        exclusive_end=False,
        registry_label="Реестр идентификаторов",
        group_label="ID-BSN",
    )
    _validate_queryset(
        LegalEntityRecord.objects.using(db_alias)
        .filter(attribute=ATTRIBUTE_NAME, identifier_record_id__isnull=False)
        .order_by("identifier_record_id", "name_received_date", "name_changed_date", "id"),
        group_attr="identifier_record_id",
        start_attr="name_received_date",
        end_attr="name_changed_date",
        exclusive_end=True,
        registry_label="Реестр наименований",
        group_label="ID-IDN",
    )
    _validate_queryset(
        LegalEntityRecord.objects.using(db_alias)
        .filter(attribute=ATTRIBUTE_LEGAL_ADDRESS, identifier_record_id__isnull=False)
        .order_by("identifier_record_id", "valid_from", "valid_to", "id"),
        group_attr="identifier_record_id",
        start_attr="valid_from",
        end_attr="valid_to",
        exclusive_end=False,
        registry_label="Реестр юридических адресов",
        group_label="ID-IDN",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0035_backfill_valid_ranges"),
    ]

    operations = [
        migrations.RunPython(forwards_validate_no_period_overlaps, migrations.RunPython.noop),
    ]
