"""Синхронизация участников группы с базой юридических лиц."""

import re
from datetime import date

from django.db import transaction
from django.db.models import Max

from classifiers_app.models import (
    BusinessEntityIdentifierRecord,
    BusinessEntityRecord,
    LegalEntityRecord,
    OKSMCountry,
)

from .models import GroupMember

GROUP_BUSINESS_ENTITY_SOURCE = "[Группа / Состав группы]"
GROUP_CHAIN_LOCKED_MESSAGE = (
    "Эту запись ведёт раздел «Группа → Состав группы». Измените или удалите компанию там."
)

_BSN_REF = re.compile(r"^(\d+)-BSN$", re.IGNORECASE)
_IDN_REF = re.compile(r"^(\d+)-IDN$", re.IGNORECASE)


def csv_ref_pk(ref, suffix):
    pattern = _BSN_REF if suffix == "BSN" else _IDN_REF
    match = pattern.match((ref or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _author_name(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full or getattr(user, "email", "") or getattr(user, "username", "") or ""


def _next_position(model):
    return (model.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _country_for_member(member):
    code = (member.country_code or "").strip()
    if not code:
        return None
    return OKSMCountry.objects.filter(code=code).order_by("id").first()


def group_owned_business_entity_ids():
    return set(
        GroupMember.objects.exclude(business_entity_id=None).values_list("business_entity_id", flat=True)
    )


def is_group_owned_business_entity(entity_id):
    if not entity_id:
        return False
    return GroupMember.objects.filter(business_entity_id=entity_id).exists()


def primary_identifier(entity_id):
    if not entity_id:
        return None
    return (
        BusinessEntityIdentifierRecord.objects.filter(business_entity_id=entity_id)
        .order_by("id")
        .first()
    )


def group_owned_primary_identifier_ids():
    identifier_ids = set()
    for entity_id in group_owned_business_entity_ids():
        identifier = primary_identifier(entity_id)
        if identifier is not None:
            identifier_ids.add(identifier.pk)
    return identifier_ids


def is_group_primary_identifier(identifier):
    if identifier is None or not getattr(identifier, "pk", None):
        return False
    if not is_group_owned_business_entity(identifier.business_entity_id):
        return False
    primary = primary_identifier(identifier.business_entity_id)
    return primary is not None and primary.pk == identifier.pk


def is_group_owned_name_record(record):
    if record is None or getattr(record, "attribute", None) != LegalEntityRecord.ATTRIBUTE_NAME:
        return False
    if not record.identifier_record_id:
        return False
    identifier = record.identifier_record
    if identifier is None or identifier.pk != record.identifier_record_id:
        identifier = BusinessEntityIdentifierRecord.objects.filter(pk=record.identifier_record_id).first()
    return is_group_primary_identifier(identifier)


def sync_group_member_registry(member, user=None):
    with transaction.atomic():
        locked = GroupMember.objects.get(pk=member.pk)
        if locked.business_entity_id is None:
            _create_chain(locked, user)
        else:
            _overwrite_locked_fields(locked)
    member.refresh_from_db()
    return member


def backfill_group_member_registries():
    member_ids = list(
        GroupMember.objects.filter(business_entity_id=None).order_by("id").values_list("id", flat=True)
    )
    for member_id in member_ids:
        member = GroupMember.objects.get(pk=member_id)
        sync_group_member_registry(member, user=None)


def reapply_all_group_locked_fields():
    for member in GroupMember.objects.exclude(business_entity_id=None).order_by("id"):
        _overwrite_locked_fields(member)


def delete_linked_business_entity(entity_id):
    if not entity_id:
        return
    BusinessEntityRecord.objects.filter(pk=entity_id).delete()


def _create_chain(member, user):
    country = _country_for_member(member)
    today = date.today()
    author = _author_name(user)
    entity = BusinessEntityRecord.objects.create(
        name=member.short_name or "",
        record_date=today,
        record_author=author,
        source=GROUP_BUSINESS_ENTITY_SOURCE,
        comment="",
        position=_next_position(BusinessEntityRecord),
    )
    identifier = BusinessEntityIdentifierRecord.objects.create(
        business_entity=entity,
        identifier_type=member.identifier or "",
        registration_country=country,
        registration_region="",
        registration_date=member.registration_date,
        number=member.registration_number or "",
        valid_from=member.registration_date,
        valid_to=None,
        record_date=today,
        record_author=author,
        position=_next_position(BusinessEntityIdentifierRecord),
    )
    LegalEntityRecord.objects.create(
        attribute=LegalEntityRecord.ATTRIBUTE_NAME,
        identifier_record=identifier,
        short_name=member.short_name or "",
        full_name=member.full_name or "",
        identifier=member.identifier or "",
        registration_number=member.registration_number or "",
        registration_date=member.registration_date,
        registration_country=country,
        registration_region="",
        name_received_date=member.registration_date,
        record_date=today,
        record_author=author,
        position=_next_position(LegalEntityRecord),
    )
    from classifiers_app.views import _ensure_identifier_has_legal_address_record

    _ensure_identifier_has_legal_address_record(identifier, user)
    member.business_entity = entity
    member.save(update_fields=["business_entity"])


def _overwrite_locked_fields(member):
    entity = member.business_entity
    if entity is None:
        return
    short_name = member.short_name or ""
    full_name = member.full_name or ""
    identifier_type = member.identifier or ""
    number = member.registration_number or ""
    country = _country_for_member(member)
    country_id = country.pk if country is not None else None

    if entity.name != short_name:
        entity.name = short_name
        entity.save(update_fields=["name", "updated_at"])

    identifier = primary_identifier(entity.pk)
    if identifier is None:
        return

    identifier_changed = False
    if identifier.business_entity_id != entity.pk:
        identifier.business_entity = entity
        identifier_changed = True
    if identifier.identifier_type != identifier_type:
        identifier.identifier_type = identifier_type
        identifier_changed = True
    if identifier.registration_country_id != country_id:
        identifier.registration_country = country
        identifier_changed = True
    if identifier.number != number:
        identifier.number = number
        identifier_changed = True
    if identifier.registration_date != member.registration_date:
        identifier.registration_date = member.registration_date
        identifier_changed = True
    if identifier_changed:
        identifier.save()

    name_records = list(
        LegalEntityRecord.objects.filter(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier,
        )
    )
    if not name_records:
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier,
            short_name=short_name,
            full_name=full_name,
            identifier=identifier_type,
            registration_number=number,
            registration_date=member.registration_date,
            registration_country=country,
            name_received_date=member.registration_date,
            record_date=date.today(),
            record_author="",
            position=_next_position(LegalEntityRecord),
        )
    else:
        for record in name_records:
            changed = False
            if record.short_name != short_name:
                record.short_name = short_name
                changed = True
            if record.full_name != full_name:
                record.full_name = full_name
                changed = True
            if record.identifier != identifier_type:
                record.identifier = identifier_type
                changed = True
            if record.registration_number != number:
                record.registration_number = number
                changed = True
            if record.registration_date != member.registration_date:
                record.registration_date = member.registration_date
                changed = True
            if record.registration_country_id != country_id:
                record.registration_country = country
                changed = True
            if changed:
                record.save()

    for address in LegalEntityRecord.objects.filter(
        attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
        identifier_record=identifier,
        is_active=True,
    ):
        if address.registration_country_id != country_id:
            address.registration_country = country
            address.save()
