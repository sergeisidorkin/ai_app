"""Связь типовых разделов с классификатором без перезаписи существующих значений."""

import re

from policy_app.models import SYSTEM_DSC_SECTION_CODE, SYSTEM_DSC_SECTION_DEFAULTS

_THREE_LETTERS = re.compile(r"^[A-Z]{3}$")


def _code(value):
    return str(value or "").strip().upper()


def _name(value):
    return str(value or "").strip()


def link_typical_sections_to_service_blocks(section_model, block_model):
    """Связывает только совпавшие код и краткие имена. Колонки разделов не меняет.

    Функция безопасна для повторного запуска и для пустой базы: она не падает
    на чужих кодах и не выбирает одно имя из нескольких разных.
    """
    blocks = {_code(block.code): block for block in block_model.objects.all()}
    sections = list(section_model.objects.all())

    system_dsc = [
        section
        for section in sections
        if section.is_system and _code(section.code) == SYSTEM_DSC_SECTION_CODE
    ]
    if system_dsc and SYSTEM_DSC_SECTION_CODE not in blocks:
        position = (block_model.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0) + 1
        blocks[SYSTEM_DSC_SECTION_CODE] = block_model.objects.create(
            code=SYSTEM_DSC_SECTION_CODE,
            short_name=SYSTEM_DSC_SECTION_DEFAULTS["short_name"],
            short_name_ru=SYSTEM_DSC_SECTION_DEFAULTS["short_name_ru"],
            accounting_type="Разделы",
            position=position,
        )
    dsc_block = blocks.get(SYSTEM_DSC_SECTION_CODE)
    if dsc_block is not None:
        pending = [
            section.pk
            for section in system_dsc
            if section.service_block_id != dsc_block.pk
        ]
        if pending:
            section_model.objects.filter(pk__in=pending).update(service_block_id=dsc_block.pk)

    grouped = {}
    for section in sections:
        if section.is_system and _code(section.code) == SYSTEM_DSC_SECTION_CODE:
            continue
        grouped.setdefault(_code(section.code), []).append(section)

    for code, group in grouped.items():
        if not _THREE_LETTERS.fullmatch(code):
            continue
        block = blocks.get(code)
        if block is None:
            names = {(_name(section.short_name), _name(section.short_name_ru)) for section in group}
            if len(names) != 1:
                continue
            short_name, short_name_ru = next(iter(names))
            if not short_name:
                continue
            position = (block_model.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0) + 1
            block = block_model.objects.create(
                code=code,
                short_name=short_name,
                short_name_ru=short_name_ru,
                accounting_type="Разделы",
                position=position,
            )
            blocks[code] = block
            section_model.objects.filter(pk__in=[section.pk for section in group]).update(
                service_block_id=block.pk
            )
            continue
        block_names = (_name(block.short_name), _name(block.short_name_ru))
        matched = [
            section.pk
            for section in group
            if (_name(section.short_name), _name(section.short_name_ru)) == block_names
            and section.service_block_id != block.pk
        ]
        if matched:
            section_model.objects.filter(pk__in=matched).update(service_block_id=block.pk)


def backfill_service_block_executors(section_model, section_link_model, block_link_model):
    """Копирует исполнителя в пустой блок, только если у всех его разделов один порядок.

    Строки разделов и их специальности не изменяет. Уже заполненный блок не трогает.
    """
    filled = set(block_link_model.objects.values_list("classifier_id", flat=True))
    sections = list(
        section_model.objects.exclude(service_block_id=None).values_list("pk", "service_block_id")
    )
    if not sections:
        return
    by_block = {}
    section_ids = []
    for section_id, block_id in sections:
        by_block.setdefault(block_id, []).append(section_id)
        section_ids.append(section_id)
    by_section = {}
    for link in section_link_model.objects.filter(section_id__in=section_ids).order_by("rank", "id"):
        by_section.setdefault(link.section_id, []).append(link.specialty_id)

    to_create = []
    for block_id, block_sections in by_block.items():
        if block_id in filled:
            continue
        orders = [tuple(by_section.get(section_id, ())) for section_id in block_sections]
        chosen = orders[0]
        if not chosen or any(order != chosen for order in orders[1:]):
            continue
        for rank, specialty_id in enumerate(chosen, start=1):
            to_create.append(block_link_model(
                classifier_id=block_id,
                specialty_id=specialty_id,
                rank=rank,
            ))
    if to_create:
        block_link_model.objects.bulk_create(to_create)


def replace_service_block_classifier_specialties(classifier, raw_ids):
    """Заменяет список специальностей одного блока. Разделы не читает и не меняет."""
    from experts_app.models import ExpertSpecialty

    from policy_app.models import ServiceBlockClassifierSpecialty

    ids = []
    seen = set()
    for raw in raw_ids or []:
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if pk <= 0 or pk in seen:
            continue
        seen.add(pk)
        ids.append(pk)
    direction_id = getattr(classifier, "expertise_dir_id", None)
    valid = set()
    if direction_id:
        valid = set(
            ExpertSpecialty.objects.filter(
                pk__in=ids,
                expertise_dir_id=direction_id,
            ).values_list("pk", flat=True)
        )
    ServiceBlockClassifierSpecialty.objects.filter(classifier=classifier).delete()
    ServiceBlockClassifierSpecialty.objects.bulk_create([
        ServiceBlockClassifierSpecialty(classifier=classifier, specialty_id=pk, rank=rank)
        for rank, pk in enumerate((pk for pk in ids if pk in valid), start=1)
    ])
