"""Скачивание и обновление истории наименований без замены реестра."""

import re
from datetime import date, datetime

from django.apps import apps
from django.db import transaction
from django.db.models import Max

from .models import (
    BusinessEntityIdentifierRecord,
    BusinessEntityRecord,
    BusinessEntityRelationRecord,
    BusinessEntityReorganizationEvent,
    LegalEntityRecord,
    OKSMCountry,
    detect_legal_entity_region_by_identifier,
)

NAME_HISTORY_CSV_FIELDS = [
    "ID-BSN",
    "Наименование бизнес-сущности",
    "ID-IDN",
    "ID-ATR",
    "Идентификатор",
    "Регистрационный номер",
    "Код страны",
    "Страна",
    "Регион",
    "Дата регистрации",
    "Идентификатор действителен от",
    "Идентификатор действителен до",
    "Наименование (краткое)",
    "Наименование (полное)",
    "Дата получения наименования",
    "Дата смены наименования",
]

_ADDRESS_DETAIL_FIELDS = (
    "postal_code",
    "municipality",
    "settlement",
    "locality",
    "district",
    "street",
    "building",
    "premise",
    "premise_part",
)


class NameHistoryImportError(ValueError):
    pass


def registration_number_key(number):
    value = re.sub(r"\s+", "", (number or "").strip())
    if not value:
        return ""
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value.casefold()


def find_identifier_for_registration_number(number):
    key = registration_number_key(number)
    if not key:
        return None
    matches = [
        item
        for item in BusinessEntityIdentifierRecord.objects.order_by("id")
        if registration_number_key(item.number) == key
    ]
    return matches[0] if matches else None


def iter_name_history_rows():
    names = (
        LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_NAME)
        .select_related("identifier_record__business_entity", "identifier_record__registration_country", "registration_country")
        .order_by("identifier_record__business_entity_id", "identifier_record_id", "name_received_date", "id")
    )
    for item in names:
        identifier = item.identifier_record
        entity = identifier.business_entity if identifier and identifier.business_entity_id else None
        country = item.registration_country or (identifier.registration_country if identifier else None)
        yield {
            "ID-BSN": f"{entity.pk:05d}-BSN" if entity else "",
            "Наименование бизнес-сущности": entity.name if entity else "",
            "ID-IDN": f"{identifier.pk:05d}-IDN" if identifier else "",
            "ID-ATR": f"{item.pk:05d}-ATR",
            "Идентификатор": item.identifier or (identifier.identifier_type if identifier else ""),
            "Регистрационный номер": item.registration_number or (identifier.number if identifier else ""),
            "Код страны": country.code if country else "",
            "Страна": country.short_name if country else "",
            "Регион": item.registration_region or (identifier.registration_region if identifier else ""),
            "Дата регистрации": _csv_date(item.registration_date or (identifier.registration_date if identifier else None)),
            "Идентификатор действителен от": _csv_date(identifier.valid_from if identifier else None),
            "Идентификатор действителен до": _csv_date(identifier.valid_to if identifier else None),
            "Наименование (краткое)": item.short_name or "",
            "Наименование (полное)": item.full_name or "",
            "Дата получения наименования": _csv_date(item.name_received_date),
            "Дата смены наименования": _csv_date(item.name_changed_date),
        }


def import_name_history_rows(rows, *, user):
    parsed, errors = _parse_rows(rows)
    if errors:
        raise NameHistoryImportError(errors)
    groups = _group_rows(parsed)
    plan, plan_errors = _build_plan(groups)
    if plan_errors:
        raise NameHistoryImportError(plan_errors)
    with transaction.atomic():
        return _apply_plan(plan, user)


def _csv_date(value):
    return value.isoformat() if value else ""


def _parse_date(raw):
    value = (raw or "").strip()
    if not value or value == "—":
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return False


def _parse_ref(raw, suffix):
    value = (raw or "").strip()
    if not value:
        return "", None
    match = re.fullmatch(rf"(\d+)-{suffix}", value, flags=re.IGNORECASE)
    if match:
        return value, int(match.group(1))
    if value.isdigit():
        return value, int(value)
    return value, False


def _parse_rows(rows):
    parsed = []
    errors = []
    countries_by_code = {item.code.strip(): item for item in OKSMCountry.objects.exclude(code="")}
    countries_by_name = {item.short_name.strip().lower(): item for item in OKSMCountry.objects.exclude(short_name="")}
    seen_atr = {}
    for row_number, row in enumerate(rows, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        short_name = (row.get("Наименование (краткое)") or "").strip()
        if not short_name:
            errors.append(f"Строка {row_number}: отсутствует краткое наименование.")
            continue
        bsn_raw, bsn_id = _parse_ref(row.get("ID-BSN"), "BSN")
        idn_raw, idn_id = _parse_ref(row.get("ID-IDN"), "IDN")
        atr_raw, atr_id = _parse_ref(row.get("ID-ATR"), "ATR")
        if bsn_id is False:
            errors.append(f"Строка {row_number}: не распознан ID-BSN «{bsn_raw}».")
        if idn_id is False:
            errors.append(f"Строка {row_number}: не распознан ID-IDN «{idn_raw}».")
        if atr_id is False:
            errors.append(f"Строка {row_number}: не распознан ID-ATR «{atr_raw}».")
        dates = {}
        date_error = False
        for label in (
            "Дата регистрации",
            "Идентификатор действителен от",
            "Идентификатор действителен до",
            "Дата получения наименования",
            "Дата смены наименования",
        ):
            parsed_date = _parse_date(row.get(label))
            if parsed_date is False:
                errors.append(f"Строка {row_number}: дата «{label}» не распознана.")
                date_error = True
            else:
                dates[label] = parsed_date
        if date_error or bsn_id is False or idn_id is False or atr_id is False:
            continue
        if atr_id and atr_id in seen_atr:
            errors.append(f"Строка {row_number}: ID-ATR «{atr_raw}» повторяется.")
            continue
        if atr_id:
            seen_atr[atr_id] = row_number
        code = (row.get("Код страны") or "").strip()
        country_name = (row.get("Страна") or "").strip()
        country = None
        if code or country_name:
            country = countries_by_code.get(code) if code else None
            if country is None and country_name:
                country = countries_by_name.get(country_name.lower())
            if country is None:
                errors.append(f"Строка {row_number}: страна «{code or country_name}» не найдена в ОКСМ.")
                continue
        number = (row.get("Регистрационный номер") or "").strip()
        parsed.append(
            {
                "row_number": row_number,
                "bsn_raw": bsn_raw,
                "bsn_id": bsn_id or None,
                "entity_name": (row.get("Наименование бизнес-сущности") or "").strip(),
                "idn_raw": idn_raw,
                "idn_id": idn_id or None,
                "atr_id": atr_id or None,
                "identifier_type": (row.get("Идентификатор") or "").strip(),
                "number": number,
                "number_key": registration_number_key(number),
                "country": country,
                "region": (row.get("Регион") or "").strip(),
                "registration_date": dates["Дата регистрации"],
                "valid_from": dates["Идентификатор действителен от"],
                "valid_to": dates["Идентификатор действителен до"],
                "short_name": short_name,
                "full_name": (row.get("Наименование (полное)") or "").strip(),
                "name_received_date": dates["Дата получения наименования"],
                "name_changed_date": dates["Дата смены наименования"],
            }
        )
    return parsed, errors


def _group_rows(rows):
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, row in enumerate(rows):
        find(index)
        if row["number_key"]:
            union(index, ("num", row["number_key"]))
        if row["bsn_id"]:
            union(index, ("bsn", row["bsn_id"]))
        elif row["bsn_raw"]:
            union(index, ("bsn", row["bsn_raw"]))
    grouped = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append(row)
    return list(grouped.values())


def _distinct_values(rows, field):
    values = []
    for row in rows:
        value = row[field]
        if value in ("", None):
            continue
        if value not in values:
            values.append(value)
    return values


def _single_value(rows, field, *, label, errors, where):
    values = _distinct_values(rows, field)
    if len(values) > 1:
        rendered = ", ".join(_display_value(value) for value in values)
        errors.append(f"{where}: разные значения поля «{label}»: {rendered}.")
        return None
    return values[0] if values else None


def _display_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "short_name"):
        return value.short_name
    return str(value)


def _ranges_overlap(start_a, end_a, start_b, end_b, *, closed):
    def before(left, right):
        if left is None or right is None:
            return True
        return left <= right if closed else left < right

    return before(start_a, end_b) and before(start_b, end_a)


def _build_plan(groups):
    errors = []
    identifier_cache = {item.pk: item for item in BusinessEntityIdentifierRecord.objects.select_related("business_entity")}
    name_cache = {
        item.pk: item
        for item in LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_NAME).select_related("identifier_record")
    }
    entities = {item.pk: item for item in BusinessEntityRecord.objects.all()}
    planned_groups = []
    for rows in groups:
        entity_names = _distinct_values(rows, "entity_name")
        if len(entity_names) > 1:
            errors.append(
                "Строки "
                + ", ".join(str(row["row_number"]) for row in rows)
                + ": у одной бизнес-сущности указаны разные наименования."
            )
        bsn_ids = []
        for row in rows:
            if row["bsn_id"] and row["bsn_id"] not in bsn_ids:
                bsn_ids.append(row["bsn_id"])
        existing_ids = [pk for pk in bsn_ids if pk in entities]
        unique_refs = {row["bsn_id"] or row["bsn_raw"] for row in rows if row["bsn_id"] or row["bsn_raw"]}
        keeper_entity_id = None
        if len(unique_refs) == 1 and existing_ids:
            keeper_entity_id = existing_ids[0]
        elif existing_ids:
            keeper_entity_id = min(existing_ids)
        number_keys = []
        for row in rows:
            if row["number_key"] not in number_keys:
                number_keys.append(row["number_key"])
        number_plans = []
        for number_key in number_keys:
            number_rows = [row for row in rows if row["number_key"] == number_key]
            where = _number_label(number_rows)
            identifier_type = _single_value(number_rows, "identifier_type", label="Идентификатор", errors=errors, where=where)
            country = _single_value(number_rows, "country", label="Страна", errors=errors, where=where)
            region = _single_value(number_rows, "region", label="Регион", errors=errors, where=where)
            registration_date = _single_value(number_rows, "registration_date", label="Дата регистрации", errors=errors, where=where)
            valid_from = _single_value(number_rows, "valid_from", label="Идентификатор действителен от", errors=errors, where=where)
            valid_to = _single_value(number_rows, "valid_to", label="Идентификатор действителен до", errors=errors, where=where)
            candidates = _candidate_identifiers(number_rows, number_key, identifier_cache)
            idn_ids = [row["idn_id"] for row in number_rows if row["idn_id"]]
            unique_idn = {row["idn_id"] for row in number_rows if row["idn_id"]}
            keeper_identifier = None
            if len(unique_idn) == 1 and idn_ids[0] in identifier_cache:
                keeper_identifier = identifier_cache[idn_ids[0]]
            elif candidates:
                on_keeper = [item for item in candidates if keeper_entity_id and item.business_entity_id == keeper_entity_id]
                keeper_identifier = min(on_keeper or candidates, key=lambda item: item.pk)
            stored_number = _preferred_number(number_rows)
            detected_region = detect_legal_entity_region_by_identifier(
                identifier_type or (keeper_identifier.identifier_type if keeper_identifier else ""),
                stored_number,
            )
            final_region = region or detected_region or (keeper_identifier.registration_region if keeper_identifier else "")
            final_from = valid_from if valid_from is not None else (keeper_identifier.valid_from if keeper_identifier else registration_date)
            final_to = valid_to if valid_to is not None else (keeper_identifier.valid_to if keeper_identifier else None)
            names = _planned_names(number_rows, candidates, name_cache, errors, where)
            number_plans.append(
                {
                    "rows": number_rows,
                    "where": where,
                    "candidates": candidates,
                    "keeper_identifier": keeper_identifier,
                    "stored_number": stored_number,
                    "identifier_type": identifier_type,
                    "country": country,
                    "region": final_region,
                    "registration_date": registration_date,
                    "valid_from": final_from,
                    "valid_to": final_to,
                    "names": names,
                }
            )
        kept_identifier_ids = {item["keeper_identifier"].pk for item in number_plans if item["keeper_identifier"]}
        removed_identifier_ids = {
            item.pk
            for plan in number_plans
            for item in plan["candidates"]
            if item.pk not in kept_identifier_ids
        }
        final_ranges = []
        if keeper_entity_id:
            for item in identifier_cache.values():
                if item.business_entity_id == keeper_entity_id and item.pk not in removed_identifier_ids and item.pk not in kept_identifier_ids:
                    final_ranges.append((f"{item.pk:05d}-IDN", item.valid_from, item.valid_to))
        for plan in number_plans:
            label = plan["stored_number"] or plan["where"]
            final_ranges.append((label, plan["valid_from"], plan["valid_to"]))
        for index, (left_label, left_from, left_to) in enumerate(final_ranges):
            for right_label, right_from, right_to in final_ranges[index + 1:]:
                if _ranges_overlap(left_from, left_to, right_from, right_to, closed=True):
                    errors.append(
                        f"Сроки идентификаторов «{left_label}» и «{right_label}» пересекаются. "
                        "У предыдущего номера заполните дату окончания раньше даты начала следующего."
                    )
        for plan in number_plans:
            _validate_name_ranges(plan["names"], errors, plan["where"])
        planned_groups.append(
            {
                "rows": rows,
                "entity_name": entity_names[0] if entity_names else "",
                "keeper_entity_id": keeper_entity_id,
                "number_plans": number_plans,
                "removed_identifier_ids": removed_identifier_ids,
            }
        )
    if errors:
        return [], errors
    return planned_groups, []


def _number_label(rows):
    number = next((row["number"] for row in rows if row["number"]), "")
    if number:
        return f"Номер {number}"
    return "Строки " + ", ".join(str(row["row_number"]) for row in rows)


def _candidate_identifiers(rows, number_key, identifier_cache):
    found = {}
    for row in rows:
        if row["idn_id"] and row["idn_id"] in identifier_cache:
            found[row["idn_id"]] = identifier_cache[row["idn_id"]]
    if number_key:
        for item in identifier_cache.values():
            if registration_number_key(item.number) == number_key:
                found[item.pk] = item
    return list(found.values())


def _preferred_number(rows):
    values = [row["number"] for row in rows if row["number"]]
    digit_values = [value for value in values if re.sub(r"\s+", "", value).isdigit()]
    if digit_values:
        return max(digit_values, key=lambda value: len(re.sub(r"\D", "", value)))
    return values[0] if values else ""


def _planned_names(rows, candidates, name_cache, errors, where):
    candidate_ids = {item.pk for item in candidates}
    by_short = {}
    for name in name_cache.values():
        if name.identifier_record_id in candidate_ids:
            by_short.setdefault(((name.short_name or "").casefold(), name.name_received_date), []).append(name)
    planned = []
    claimed = set()
    for row in rows:
        record = name_cache.get(row["atr_id"]) if row["atr_id"] else None
        if row["atr_id"] and record is None:
            record = None
        if record and record.identifier_record_id:
            current_number = record.registration_number or record.identifier_record.number
            current_key = registration_number_key(current_number)
            if row["number_key"] and current_key and current_key != row["number_key"]:
                errors.append(
                    f"Строка {row['row_number']}: ID-ATR {record.pk:05d}-ATR относится к другому регистрационному номеру."
                )
                continue
        if record is None:
            matches = [
                item
                for item in by_short.get(((row["short_name"] or "").casefold(), row["name_received_date"]), [])
                if item.pk not in claimed
            ]
            record = matches[0] if matches else None
        if record and record.pk in claimed:
            errors.append(f"Строка {row['row_number']}: наименование уже указано в другой строке файла.")
            continue
        if record:
            claimed.add(record.pk)
        received = row["name_received_date"] if row["name_received_date"] is not None else (record.name_received_date if record else None)
        changed = row["name_changed_date"] if row["name_changed_date"] is not None else (record.name_changed_date if record else None)
        planned.append({"row": row, "record": record, "received": received, "changed": changed})
    for name in name_cache.values():
        if name.identifier_record_id in candidate_ids and name.pk not in claimed:
            planned.append(
                {
                    "row": None,
                    "record": name,
                    "received": name.name_received_date,
                    "changed": name.name_changed_date,
                }
            )
    return planned


def _validate_name_ranges(names, errors, where):
    spans = [(item["record"].short_name if item["record"] else item["row"]["short_name"], item["received"], item["changed"]) for item in names]
    for index, (left_name, left_from, left_to) in enumerate(spans):
        for right_name, right_from, right_to in spans[index + 1:]:
            if _ranges_overlap(left_from, left_to, right_from, right_to, closed=False):
                errors.append(
                    f"{where}: периоды наименований «{left_name}» и «{right_name}» пересекаются."
                )


def _apply_plan(groups, user):
    author = _author_name(user)
    today = date.today()
    created_names = 0
    updated_names = 0
    merged_entities = 0
    notes = []
    for group in groups:
        entity = _keeper_entity(group, author, today)
        removed_entity_ids = set()
        merged_here = 0
        for number_plan in sorted(group["number_plans"], key=_identifier_apply_order):
            _prepare_name_dates(number_plan["names"])
            identifier = _keeper_identifier(number_plan, entity, author, today)
            previous_entity_id = identifier.business_entity_id
            _assign_identifier_fields(identifier, number_plan)
            identifier.business_entity = entity
            identifier.save()
            if previous_entity_id and previous_entity_id != entity.pk:
                removed_entity_ids.add(previous_entity_id)
            duplicates = [item for item in number_plan["candidates"] if item.pk != identifier.pk]
            _collapse_addresses([identifier, *duplicates], identifier)
            for duplicate in duplicates:
                removed_entity_ids.add(duplicate.business_entity_id)
                _move_names(duplicate, identifier)
                _reassign_identifier_links(duplicate.pk, identifier.pk)
                duplicate.delete()
            for name_plan in number_plan["names"]:
                if name_plan["row"] is None:
                    if name_plan["record"].identifier_record_id != identifier.pk:
                        name_plan["record"].identifier_record = identifier
                        name_plan["record"].save()
                    continue
                created, changed = _upsert_name(name_plan, identifier, number_plan, author, today)
                if created:
                    created_names += 1
                elif changed:
                    updated_names += 1
            _ensure_address(identifier, author, today)
            if number_plan["region"]:
                for address in LegalEntityRecord.objects.filter(
                    attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
                    identifier_record=identifier,
                    registration_region="",
                ):
                    address.registration_region = number_plan["region"]
                    address.save(update_fields=["registration_region", "updated_at"])
        removed_entity_ids.discard(entity.pk)
        for entity_id in removed_entity_ids:
            if _delete_entity_if_empty(entity_id, entity.pk):
                merged_here += 1
        merged_entities += merged_here
        if group["entity_name"] and entity.name != group["entity_name"]:
            entity.name = group["entity_name"]
            entity.save(update_fields=["name", "updated_at"])
        if merged_here:
            notes.append(f"{entity.name}: объединены повторы одного регистрационного номера, оставлена {entity.pk:05d}-BSN.")
    return {
        "ok": True,
        "created": created_names,
        "updated": updated_names,
        "skipped": 0,
        "summary": [
            f"Наименования: создано {created_names}, обновлено {updated_names}.",
            f"Объединено бизнес-сущностей: {merged_entities}.",
        ],
        "conflicts": notes,
    }


def _identifier_apply_order(number_plan):
    current = number_plan["keeper_identifier"]
    if current is None:
        return 2
    new_end = number_plan["valid_to"] or date.max
    old_end = current.valid_to or date.max
    if new_end < old_end:
        return 0
    return 1


def _prepare_name_dates(names):
    dated = [item for item in names if item["row"] is not None and item["record"] is not None]

    def grows(item):
        record = item["record"]
        new_end = item["changed"] or date.max
        old_end = record.name_changed_date or date.max
        return new_end > old_end

    for item in sorted(dated, key=grows):
        record = item["record"]
        if record.name_received_date == item["received"] and record.name_changed_date == item["changed"]:
            continue
        record.name_received_date = item["received"]
        record.name_changed_date = item["changed"]
        record.save()


def _author_name(user):
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() if user else ""
    return full or getattr(user, "email", "") or getattr(user, "username", "") or ""


def _keeper_entity(group, author, today):
    if group["keeper_entity_id"]:
        return BusinessEntityRecord.objects.get(pk=group["keeper_entity_id"])
    active = next((row for row in group["rows"] if row["name_changed_date"] is None), group["rows"][0])
    name = group["entity_name"] or active["short_name"]
    position = (BusinessEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
    return BusinessEntityRecord.objects.create(
        name=name,
        record_date=today,
        record_author=author,
        position=position,
    )


def _keeper_identifier(number_plan, entity, author, today):
    identifier = number_plan["keeper_identifier"]
    if identifier is not None:
        return BusinessEntityIdentifierRecord.objects.get(pk=identifier.pk)
    position = (BusinessEntityIdentifierRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
    return BusinessEntityIdentifierRecord.objects.create(
        business_entity=entity,
        identifier_type=number_plan["identifier_type"] or "",
        registration_country=number_plan["country"],
        registration_region=number_plan["region"] or "",
        registration_date=number_plan["registration_date"],
        number=number_plan["stored_number"] or "",
        valid_from=number_plan["valid_from"],
        valid_to=number_plan["valid_to"],
        record_date=today,
        record_author=author,
        position=position,
    )


def _assign_identifier_fields(identifier, number_plan):
    if number_plan["stored_number"]:
        identifier.number = number_plan["stored_number"]
    if number_plan["identifier_type"]:
        identifier.identifier_type = number_plan["identifier_type"]
    if number_plan["country"] is not None:
        identifier.registration_country = number_plan["country"]
    if number_plan["region"]:
        identifier.registration_region = number_plan["region"]
    if number_plan["registration_date"] is not None:
        identifier.registration_date = number_plan["registration_date"]
    identifier.valid_from = number_plan["valid_from"]
    identifier.valid_to = number_plan["valid_to"]


def _collapse_addresses(identifiers, keeper):
    addresses = list(
        LegalEntityRecord.objects.filter(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record__in=identifiers,
        ).order_by("id")
    )
    kept = []
    for address in sorted(addresses, key=lambda item: (-_address_score(item), item.pk)):
        overlapping = next(
            (
                other
                for other in kept
                if _ranges_overlap(address.valid_from, address.valid_to, other.valid_from, other.valid_to, closed=True)
            ),
            None,
        )
        if overlapping is not None:
            if address.registration_region and not overlapping.registration_region:
                overlapping.registration_region = address.registration_region
                overlapping.save(update_fields=["registration_region", "updated_at"])
            address.delete()
            continue
        kept.append(address)
    for address in kept:
        if address.identifier_record_id != keeper.pk:
            address.identifier_record = keeper
            address.save()


def _address_score(address):
    return sum(1 for field in _ADDRESS_DETAIL_FIELDS if getattr(address, field)) + (1 if address.registration_region else 0)


def _move_names(source, target):
    for record in LegalEntityRecord.objects.filter(
        attribute=LegalEntityRecord.ATTRIBUTE_NAME,
        identifier_record=source,
    ):
        record.identifier_record = target
        record.save()


def _reassign_identifier_links(source_id, target_id):
    for model in apps.get_models():
        if model is LegalEntityRecord:
            continue
        for field in model._meta.get_fields():
            if getattr(field, "many_to_one", False) and field.related_model is BusinessEntityIdentifierRecord:
                model.objects.filter(**{field.name: source_id}).update(**{field.name: target_id})


def _upsert_name(name_plan, identifier, number_plan, author, today):
    row = name_plan["row"]
    record = name_plan["record"]
    created = record is None
    if created:
        position = (LegalEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        record = LegalEntityRecord(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            position=position,
            record_date=today,
            record_author=author,
        )
    changed = created
    assignments = {
        "short_name": row["short_name"],
        "identifier_record": identifier,
        "identifier": number_plan["identifier_type"] or record.identifier or identifier.identifier_type,
        "registration_number": number_plan["stored_number"] or record.registration_number,
    }
    if row["full_name"]:
        assignments["full_name"] = row["full_name"]
    if number_plan["country"] is not None:
        assignments["registration_country"] = number_plan["country"]
    if number_plan["region"]:
        assignments["registration_region"] = number_plan["region"]
    if row["registration_date"] is not None:
        assignments["registration_date"] = row["registration_date"]
    if row["name_received_date"] is not None:
        assignments["name_received_date"] = row["name_received_date"]
    if row["name_changed_date"] is not None:
        assignments["name_changed_date"] = row["name_changed_date"]
    for field, value in assignments.items():
        if getattr(record, field) != value:
            setattr(record, field, value)
            changed = True
    if changed:
        record.record_date = today
        record.record_author = author
        record.save()
    return created, changed


def _ensure_address(identifier, author, today):
    if LegalEntityRecord.objects.filter(
        attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
        identifier_record=identifier,
    ).exists():
        return
    position = (LegalEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
    LegalEntityRecord.objects.create(
        attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
        identifier_record=identifier,
        registration_country=identifier.registration_country,
        registration_region=identifier.registration_region or "",
        record_date=today,
        record_author=author,
        valid_from=identifier.valid_from,
        position=position,
    )


def _delete_entity_if_empty(entity_id, keeper_id):
    if not entity_id or entity_id == keeper_id:
        return False
    if BusinessEntityIdentifierRecord.objects.filter(business_entity_id=entity_id).exists():
        return False
    BusinessEntityRelationRecord.objects.filter(from_business_entity_id=entity_id).update(from_business_entity_id=keeper_id)
    BusinessEntityRelationRecord.objects.filter(to_business_entity_id=entity_id).update(to_business_entity_id=keeper_id)
    BusinessEntityRelationRecord.objects.filter(
        from_business_entity_id=keeper_id,
        to_business_entity_id=keeper_id,
    ).delete()
    orphan_event_ids = BusinessEntityReorganizationEvent.objects.filter(relations__isnull=True).values_list("pk", flat=True)
    BusinessEntityReorganizationEvent.objects.filter(pk__in=list(orphan_event_ids)).delete()
    BusinessEntityRecord.objects.filter(pk=entity_id).delete()
    return True
