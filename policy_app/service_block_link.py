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


class ServiceBlockMigrationError(RuntimeError):
    """Миграция остановлена, чтобы не стереть разделы или их экспертизу."""


def link_unlinked_sections_by_existing_code(section_model, block_model):
    """Привязывает раздел к уже существующему блоку с тем же кодом.

    Имена при этом не переписываются: строка раздела сохраняет свой id.
    Новый блок здесь не создаётся — для этого есть связь по совпавшим именам.
    """
    blocks = {_code(block.code): block.pk for block in block_model.objects.all()}
    grouped = {}
    for section in section_model.objects.filter(service_block_id=None).only("id", "code"):
        code = _code(section.code)
        block_id = blocks.get(code)
        if block_id is None or not _THREE_LETTERS.fullmatch(code):
            continue
        grouped.setdefault(block_id, []).append(section.pk)
    for block_id, section_ids in grouped.items():
        section_model.objects.filter(pk__in=section_ids).update(service_block_id=block_id)


def conflicting_product_block_ids(rows):
    """Группы id разделов, которые делят одну пару продукт + блок."""
    grouped = {}
    for section_id, product_id, block_id in rows:
        grouped.setdefault((product_id, block_id), []).append(section_id)
    return [section_ids for section_ids in grouped.values() if len(section_ids) > 1]


def reconcile_classifier_expertise(block_dir_id, block_direction_id, section_rows):
    """Возвращает экспертизу блока после переноса однозначных значений из разделов.

    section_rows — пары (id раздела, expertise_dir_id, expertise_direction_id).
    Пустое поле блока заполняется, только если все непустые разделы называют одно
    и то же значение. Уже записанное поле блока не затирается. Расхождение — ошибка.
    """
    section_rows = list(section_rows)
    dir_id, dir_conflicts = _reconcile_expertise_id(
        block_dir_id,
        ((section_id, dir_id) for section_id, dir_id, _direction_id in section_rows),
    )
    direction_id, direction_conflicts = _reconcile_expertise_id(
        block_direction_id,
        ((section_id, direction_id) for section_id, _dir_id, direction_id in section_rows),
    )
    if dir_conflicts or direction_conflicts:
        raise ServiceBlockMigrationError(
            "Миграция остановлена: экспертизу раздела нельзя перенести в классификатор "
            "без конфликта. Поля раздела не удалены. Согласуйте экспертизу и подразделение "
            "у перечисленных строк и повторите миграцию.\n"
            + _expertise_conflict_text(dir_conflicts, direction_conflicts)
        )
    return dir_id, direction_id


def _reconcile_expertise_id(current, pairs):
    filled = [(section_id, value) for section_id, value in pairs if value is not None]
    if current is not None:
        conflicts = [(section_id, value) for section_id, value in filled if value != current]
        return current, conflicts
    unique = {value for _section_id, value in filled}
    if len(unique) <= 1:
        return (next(iter(unique)) if unique else None), []
    return None, filled


def _expertise_conflict_text(dir_conflicts, direction_conflicts):
    lines = []
    for section_id, value in dir_conflicts:
        lines.append(f"- раздел id={section_id}: экспертиза id={value}")
    for section_id, value in direction_conflicts:
        lines.append(f"- раздел id={section_id}: подразделение id={value}")
    return "\n".join(lines)


def prepare_sections_for_required_service_block(section_model, block_model, schema_editor):
    """Готовит разделы к обязательному блоку услуг, не удаляя живые строки.

    Сначала повторяет однозначную связь по имени, затем привязывает оставшиеся
    разделы к уже существующему блоку с тем же кодом. Если раздел так и не
    привязан, у продукта два раздела на один блок или экспертиза конфликтует,
    миграция останавливается с текстом, по которому можно поправить данные.
    """
    link_typical_sections_to_service_blocks(section_model, block_model)
    link_unlinked_sections_by_existing_code(section_model, block_model)
    _raise_if_sections_stay_unlinked(section_model)
    _raise_if_product_blocks_repeat(section_model)
    _backfill_empty_classifier_expertise(section_model, block_model)
    # Обновление ссылки на блок ставит отложенные проверки внешних ключей.
    # PostgreSQL не даёт изменить таблицу, пока эти проверки не выполнены.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _raise_if_sections_stay_unlinked(section_model):
    unlinked = list(
        section_model.objects.filter(service_block_id=None)
        .select_related("product")
        .order_by("product_id", "id")
    )
    if not unlinked:
        return
    names_by_code = {}
    for section in unlinked:
        code = _code(section.code)
        names_by_code.setdefault(code, set()).add(
            (_name(getattr(section, "short_name", "")), _name(getattr(section, "short_name_ru", "")))
        )
    lines = [
        "Миграция остановлена: есть типовые разделы без блока услуг. Строки не удалены.",
        "Привяжите раздел к классификатору с кодом из трёх латинских букв.",
        "Если блока ещё нет, выровняйте краткие имена разделов с одним кодом, "
        "чтобы его можно было создать однозначно, и повторите миграцию.",
    ]
    for section in unlinked:
        code = _code(section.code)
        product = getattr(section, "product", None)
        product_name = getattr(product, "short_name", None) or section.product_id
        lines.append(
            f"- id={section.pk} продукт={product_name} код={section.code!r} "
            f"краткое имя={_name(getattr(section, 'short_name', ''))!r}/"
            f"{_name(getattr(section, 'short_name_ru', ''))!r}: "
            f"{_unlinked_section_reason(section, names_by_code.get(code, set()))}"
        )
    raise ServiceBlockMigrationError("\n".join(lines))


def _unlinked_section_reason(section, names):
    code = _code(section.code)
    if not _THREE_LETTERS.fullmatch(code):
        return "код не состоит из трёх латинских букв"
    if len(names) > 1:
        return "у разделов с этим кодом разные краткие имена, поэтому блок не создан"
    if not _name(getattr(section, "short_name", "")):
        return "нет краткого имени, чтобы создать новый блок"
    return "нет блока услуг с таким кодом"


def _raise_if_product_blocks_repeat(section_model):
    rows = section_model.objects.order_by("product_id", "service_block_id", "id").values_list(
        "id",
        "product_id",
        "service_block_id",
    )
    groups = conflicting_product_block_ids(rows)
    if not groups:
        return
    lines = [
        "Миграция остановлена: у одного продукта несколько разделов ссылаются на один блок услуг.",
        "Строки не удалены. Оставьте один раздел на эту пару и повторите миграцию.",
    ]
    for section_ids in groups:
        lines.append("- разделы id=" + ", ".join(str(section_id) for section_id in section_ids))
    raise ServiceBlockMigrationError("\n".join(lines))


def _backfill_empty_classifier_expertise(section_model, block_model):
    sections = list(
        section_model.objects.exclude(service_block_id=None).order_by("service_block_id", "id")
    )
    if not sections:
        return
    by_block = {}
    for section in sections:
        by_block.setdefault(section.service_block_id, []).append(
            (section.pk, section.expertise_dir_id, section.expertise_direction_id)
        )
    blocks = {
        block.pk: block
        for block in block_model.objects.filter(pk__in=by_block)
    }
    for block_id, section_rows in by_block.items():
        block = blocks.get(block_id)
        if block is None:
            continue
        try:
            dir_id, direction_id = reconcile_classifier_expertise(
                block.expertise_dir_id,
                block.expertise_direction_id,
                section_rows,
            )
        except ServiceBlockMigrationError as exc:
            raise ServiceBlockMigrationError(
                f"{exc}\n"
                f"Блок {block.code} (id={block.pk}): "
                f"экспертиза id={block.expertise_dir_id}, "
                f"подразделение id={block.expertise_direction_id}."
            ) from exc
        changed = []
        if block.expertise_dir_id != dir_id:
            block.expertise_dir_id = dir_id
            changed.append("expertise_dir")
        if block.expertise_direction_id != direction_id:
            block.expertise_direction_id = direction_id
            changed.append("expertise_direction")
        if changed:
            block.save(update_fields=changed)


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
