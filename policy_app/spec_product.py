"""Состав спецпроекта: строки берутся из классификатора блоков, а не из разделов продукта."""

from policy_app.models import (
    SYSTEM_DSC_SECTION_CODE,
    ServiceBlockClassifier,
    is_system_dsc_code,
    normalize_service_block_code,
)


def spec_blocks_by_code():
    blocks = (
        ServiceBlockClassifier.objects.exclude(code__iexact=SYSTEM_DSC_SECTION_CODE)
        .select_related("expertise_dir")
        .prefetch_related("ranked_specialties__specialty")
        .order_by("position", "id")
    )
    return {normalize_service_block_code(block.code): block for block in blocks}


def spec_block_service_name(block) -> str:
    return (
        (block.name_ru or "").strip()
        or (block.short_name_ru or "").strip()
        or (block.short_name or "").strip()
        or (block.code or "").strip()
    )


def spec_block_job_title(block) -> str:
    if block is None:
        return ""
    for link in block.ranked_specialties.all():
        specialty = getattr(link, "specialty", None)
        name = str(getattr(specialty, "specialty", "") or "").strip()
        if name:
            return name
    return ""


def document_spec_section_codes(document, system_product_ids):
    """Коды блоков этапа, у которого продукт — системный SPEC.

    Если этапов нет и сам документ оформлен на SPEC, берётся его состав.
    DSC и неизвестные коды пропускаются позже, при сверке с классификатором.
    """
    system_ids = {str(product_id) for product_id in system_product_ids if product_id}
    payloads = [
        item for item in (getattr(document, "stage_payloads_json", None) or [])
        if isinstance(item, dict)
    ]
    spec_payloads = [
        item for item in payloads
        if str(item.get("product_id") or "").strip() in system_ids
    ]
    source_items = []
    if spec_payloads:
        for payload in spec_payloads:
            sections = payload.get("service_sections_json") or []
            if isinstance(sections, list):
                source_items.extend(sections)
    elif not payloads and str(getattr(document, "type_id", "") or "") in system_ids:
        sections = getattr(document, "service_sections_json", None) or []
        if isinstance(sections, list):
            source_items = sections
    codes = []
    seen = set()
    for item in source_items:
        if not isinstance(item, dict):
            continue
        code = normalize_service_block_code(item.get("code"))
        if not code or is_system_dsc_code(code) or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def canonical_spec_service_section(item, blocks_by_code):
    """Имя и код строки SPEC берутся из классификатора. Неизвестный код отбрасывается."""
    if not isinstance(item, dict):
        return None
    code = normalize_service_block_code(item.get("code"))
    if not code or is_system_dsc_code(code):
        return None
    block = blocks_by_code.get(code)
    if block is None:
        return None
    return {
        "service_name": spec_block_service_name(block),
        "code": block.code,
        "block": block,
    }
