from __future__ import annotations

import sys
import calendar
from html import escape

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from policy_app.models import ServiceGoalReport

sys.modules.setdefault("proposals_app.variable_resolver", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.variable_resolver", sys.modules[__name__])


def _today() -> date:
    return date.today()


def _proposal_number(proposal) -> str:
    return str(proposal.number or "")


def _proposal_sub_number(proposal) -> str:
    return str(proposal.sub_number or 0)


def _proposal_group(proposal) -> str:
    return proposal.group_display or ""


def _proposal_tkp_id(proposal) -> str:
    return proposal.short_uid or ""


def _proposal_type(proposal) -> str:
    if not proposal.type_id:
        return ""
    return proposal.type.short_name or str(proposal.type)


def _proposal_name(proposal) -> str:
    return proposal.name or ""


def _proposal_kind(proposal) -> str:
    return proposal.get_kind_display() or ""


def _proposal_status(proposal) -> str:
    return proposal.get_status_display() or ""


def _proposal_year(proposal) -> str:
    return str(proposal.year or "")


def _proposal_customer(proposal) -> str:
    return proposal.customer or ""


def _proposal_country(proposal) -> str:
    if not proposal.country_id:
        return ""
    return proposal.country.short_name or proposal.country.full_name or ""


def _proposal_country_full_name(proposal) -> str:
    if not proposal.country_id:
        return ""
    return proposal.country.full_name or proposal.country.short_name or ""


def _proposal_identifier(proposal) -> str:
    return proposal.identifier or ""


def _proposal_registration_number(proposal) -> str:
    return proposal.registration_number or ""


def _proposal_registration_region(proposal) -> str:
    return proposal.registration_region or ""


def _proposal_date(proposal) -> str:
    return _format_date(proposal.registration_date, "%d.%m.%y")


def _proposal_asset_owner(proposal) -> str:
    return proposal.asset_owner or ""


def _proposal_asset_owner_country(proposal) -> str:
    if not proposal.asset_owner_country_id:
        return ""
    return proposal.asset_owner_country.short_name or proposal.asset_owner_country.full_name or ""


def _proposal_asset_owner_country_full_name(proposal) -> str:
    if not proposal.asset_owner_country_id:
        return ""
    return proposal.asset_owner_country.full_name or proposal.asset_owner_country.short_name or ""


def _proposal_client_owner_name(proposal) -> str:
    customer = str(getattr(proposal, "customer", "") or "").strip()
    if getattr(proposal, "asset_owner_matches_customer", True):
        return customer
    asset_owner = str(getattr(proposal, "asset_owner", "") or "").strip()
    if customer and asset_owner:
        return f"{customer} / {asset_owner}"
    return customer or asset_owner


def _proposal_service_type_short(proposal) -> str:
    full = str(getattr(proposal, "proposal_project_name", "") or "").strip()
    suffix = str(getattr(proposal, "asset_owner", "") or "").strip()
    if not full:
        return ""
    if suffix and full == suffix:
        return ""
    if suffix and full.endswith(" " + suffix):
        return full[: len(full) - len(suffix)].strip()
    return full


def _proposal_actives_name_list(proposal) -> list[str]:
    if not getattr(proposal, "pk", None):
        return []
    from proposals_app.models import ProposalAsset

    seen = set()
    result = []
    for asset in ProposalAsset.objects.filter(proposal_id=proposal.pk).order_by("position", "id").only("short_name"):
        name = str(asset.short_name or "").strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _proposal_asset_owner_identifier(proposal) -> str:
    return proposal.asset_owner_identifier or ""


def _proposal_asset_owner_registration_number(proposal) -> str:
    return proposal.asset_owner_registration_number or ""


def _proposal_asset_owner_region(proposal) -> str:
    if getattr(proposal, "asset_owner_matches_customer", False):
        return proposal.registration_region or ""
    return proposal.asset_owner_region or ""


def _proposal_asset_owner_registration_date(proposal) -> str:
    return _format_date(proposal.asset_owner_registration_date, "%d.%m.%y")


def _proposal_project_name(proposal) -> str:
    return proposal.proposal_project_name or ""


def _format_date(value, fmt="%d.%m.%Y") -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime(fmt)
    try:
        return date.fromisoformat(str(value)).strftime(fmt)
    except (TypeError, ValueError):
        return str(value)


def _format_decimal(value, precision=2, *, strip_trailing_zeros=False) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    text = f"{number:.{precision}f}".replace(".", ",")
    if strip_trailing_zeros and "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def _format_percent(value, precision=2, *, strip_trailing_zeros=False) -> str:
    text = _format_decimal(value, precision=precision, strip_trailing_zeros=strip_trailing_zeros)
    return f"{text}%" if text else ""


def _format_money(value) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if number < 0 else ""
    number = abs(number)
    integer_part = int(number)
    frac = f"{number - integer_part:.2f}"[1:]
    int_str = f"{integer_part:,}".replace(",", "\u00a0")
    return f"{sign}{int_str}{frac}".replace(".", ",")


def _proposal_purpose(proposal) -> str:
    return proposal.purpose or ""


def _proposal_service_goal_genitive(proposal) -> str:
    if not getattr(proposal, "type_id", None):
        return ""
    item = (
        ServiceGoalReport.objects.filter(product_id=proposal.type_id)
        .order_by("position", "id")
        .only("service_goal_genitive")
        .first()
    )
    if not item:
        return ""
    return item.service_goal_genitive or ""


def _service_goal_report_value(product_id, field_name: str) -> str:
    if not product_id:
        return ""
    item = (
        ServiceGoalReport.objects.filter(product_id=product_id)
        .order_by("position", "id")
        .only(field_name)
        .first()
    )
    if not item:
        return ""
    return str(getattr(item, field_name, "") or "")


def _proposal_service_goal(proposal) -> str:
    return _service_goal_report_value(getattr(proposal, "type_id", None), "service_goal")


def _proposal_report_title(proposal) -> str:
    return _service_goal_report_value(getattr(proposal, "type_id", None), "report_title")


def _proposal_product_name(proposal) -> str:
    return _service_goal_report_value(getattr(proposal, "type_id", None), "product_name")


def _proposal_tkp_preliminary(proposal) -> str:
    try:
        from proposals_app.models import ProposalRegistration

        if getattr(proposal, "status", "") == ProposalRegistration.ProposalStatus.PRELIMINARY:
            return "(предварительное)"
    except Exception:
        if getattr(proposal, "status", "") == "preliminary":
            return "(предварительное)"
    return ""


def _proposal_service_composition(proposal) -> str:
    return proposal.service_composition or ""


def _proposal_scope_of_work(proposal) -> list[dict[str, object] | str]:
    def source_value(source, key, default=None):
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    def plain_text_to_html(value):
        text = str(value or "").strip()
        if not text:
            return ""
        paragraphs = []
        for chunk in text.split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            paragraphs.append("<p>" + escape(chunk).replace("\n", "<br>") + "</p>")
        return "".join(paragraphs)

    def build_item(html_value, plain_text_value):
        html = str(html_value or "").strip()
        plain_text = str(plain_text_value or "").strip()
        if html:
            return {"html": html}
        if not plain_text:
            return None
        return {"html": plain_text_to_html(plain_text)}

    def items_from_source(source) -> list[dict[str, object] | str]:
        mode = str(source_value(source, "service_composition_mode", "") or "sections").strip()
        if mode == "customer_tz":
            stored = source_value(source, "service_customer_tz_editor_state", {}) or {}
            item = build_item(
                stored.get("html") if isinstance(stored, dict) else "",
                stored.get("plain_text")
                if isinstance(stored, dict)
                else source_value(source, "service_composition_customer_tz", ""),
            )
            if item is None:
                fallback = build_item("", source_value(source, "service_composition_customer_tz", ""))
                if fallback is None:
                    return []
                return fallback if isinstance(fallback, list) else [fallback]
            if isinstance(item, list):
                return item
            return [item]

        result: list[dict[str, object] | str] = []
        stored_sections = source_value(source, "service_sections_editor_state", []) or []
        if isinstance(stored_sections, list):
            for section in stored_sections:
                if not isinstance(section, dict):
                    continue
                item = build_item(section.get("html"), section.get("plain_text"))
                if item is None:
                    continue
                if isinstance(item, list):
                    result.extend(item)
                else:
                    result.append(item)
        if result:
            return result

        fallback = build_item("", source_value(source, "service_composition", ""))
        if fallback is None:
            return []
        return fallback if isinstance(fallback, list) else [fallback]

    def strong_line(text):
        return {"runs": [{"text": text, "character_style_id": "Сильное выделение"}]}

    def evaluation_date_line(source):
        value = _format_date(source_value(source, "evaluation_date", ""))
        if not value:
            return None
        return {"runs": [{"text": f"Дата оценки: {value}."}]}

    products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
    if not products and getattr(proposal, "type_id", None):
        products = [proposal.type]
    if len(products) <= 1:
        source = proposal
        stage_payloads = [item for item in (getattr(proposal, "stage_payloads_json", None) or []) if isinstance(item, dict)]
        if stage_payloads:
            source = stage_payloads[0]
        return [strong_line("Состав услуг:")] + items_from_source(source)

    stage_payloads = [item for item in (getattr(proposal, "stage_payloads_json", None) or []) if isinstance(item, dict)]
    payload_by_product_id = {}
    for payload in stage_payloads:
        product_id = str(payload.get("product_id") or "").strip()
        if product_id and product_id not in payload_by_product_id:
            payload_by_product_id[product_id] = payload

    result: list[dict[str, object] | str] = []
    for index, product in enumerate(products, start=1):
        product_id = str(getattr(product, "pk", "") or "")
        indexed_source = stage_payloads[index - 1] if index - 1 < len(stage_payloads) else {}
        if indexed_source and (not product_id or str(indexed_source.get("product_id") or "") == product_id):
            source = indexed_source
        else:
            source = payload_by_product_id.get(product_id) or indexed_source
        product_name = _service_goal_report_value(getattr(product, "pk", None), "product_name")
        result.append({"runs": [{"text": f"ЭТАП {index} — {product_name}.", "bold": True}]})
        result.append(strong_line("Состав услуг по этапу:"))
        result.extend(items_from_source(source))
        date_line = evaluation_date_line(source)
        if date_line is not None:
            result.append(date_line)
    return result


PROPOSAL_TRAVEL_EXPENSES_LABEL = "Командировочные расходы, евро"
PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY = "Командировочные расходы"
PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL = "actual"
PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION = "calculation"
PROPOSAL_SUMMARY_TOTAL_LABEL = "ИТОГО, по расчёту"
PROPOSAL_SUMMARY_WITH_TRAVEL_TOTAL_LABEL = "ИТОГО, евро с командировочными по расчёту"
PROPOSAL_RUB_TOTAL_LABEL = "ИТОГО, рубли без НДС"
PROPOSAL_RUB_DISCOUNTED_LABEL = "ИТОГО, рубли без НДС с учетом скидки"
PROPOSAL_CONTRACT_TOTAL_LABEL = "ИТОГО в договор, рубли без НДС с учётом доп. скидки"


def _is_proposal_travel_expenses_name(value) -> bool:
    name = str(value or "").strip()
    return name in {PROPOSAL_TRAVEL_EXPENSES_LABEL, PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY}


def _parse_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _sum_day_counts(values) -> int:
    total = 0
    for value in values:
        try:
            total += int(str(value or "").strip() or "0")
        except (TypeError, ValueError):
            continue
    return total


def _sum_decimal_values(values) -> Decimal:
    total = Decimal("0")
    for value in values:
        parsed = _parse_decimal(str(value or "").strip().replace(",", "."))
        if parsed is not None:
            total += parsed
    return total


def _proposal_multi_asset_column_widths_pct(asset_count: int) -> list[float]:
    if asset_count <= 0:
        return []
    fixed_columns = [Decimal("15.5"), Decimal("40"), Decimal("7")]
    trailing_columns = [Decimal("6"), Decimal("10")]
    fixed_total = sum(fixed_columns + trailing_columns, Decimal("0"))
    asset_width = (Decimal("100.0") - fixed_total) / Decimal(str(asset_count))
    widths = fixed_columns + [asset_width] * asset_count + trailing_columns
    return [float(width) for width in widths]


def _proposal_multistage_column_widths_pct(day_column_count: int) -> list[float]:
    if day_column_count <= 0:
        return []
    fixed_columns = [Decimal("15.5"), Decimal("40"), Decimal("7")]
    trailing_columns = [Decimal("10")]
    fixed_total = sum(fixed_columns + trailing_columns, Decimal("0"))
    day_width = (Decimal("100.0") - fixed_total) / Decimal(str(day_column_count))
    widths = fixed_columns + [day_width] * day_column_count + trailing_columns
    return [float(width) for width in widths]


def _normalize_proposal_travel_expenses_mode(value) -> str:
    mode = str(value or "").strip()
    if mode in {PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL, PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION}:
        return mode
    return ""


def _round_to_hundred_thousand(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return (value // Decimal("100000")) * Decimal("100000")


def _proposal_day_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return _parse_decimal(str(value).strip().replace(",", "."))


def _format_day_count(value) -> str:
    parsed = _proposal_day_decimal(value)
    if parsed is None or parsed == Decimal("0"):
        return ""
    return _format_decimal(parsed, precision=2, strip_trailing_zeros=True)


def _proposal_multistage_budget_table(proposal) -> dict | None:
    stage_payloads = [item for item in (getattr(proposal, "stage_payloads_json", None) or []) if isinstance(item, dict)]
    products = list(proposal.ordered_products()) if hasattr(proposal, "ordered_products") else []
    if len(stage_payloads) <= 1 and len(products) <= 1:
        return None
    if not stage_payloads:
        return None

    offers = list(proposal.commercial_offers.order_by("position", "id"))
    saved_travel_offer = next(
        (
            item
            for item in offers
            if _is_proposal_travel_expenses_name(getattr(item, "service_name", ""))
        ),
        None,
    )
    saved_regular_offers = [
        item
        for item in offers
        if not _is_proposal_travel_expenses_name(getattr(item, "service_name", ""))
    ]
    asset_labels = [
        str(getattr(asset, "short_name", "") or "").strip()
        for asset in proposal.assets.order_by("position", "id")
    ]
    max_asset_count = max(
        [
            len(item.get("asset_day_counts") or [])
            for stage in stage_payloads
            for item in (stage.get("commercial_offer_payload") or [])
            if isinstance(item, dict)
        ],
        default=0,
    )
    asset_count = max(len(asset_labels), max_asset_count, 1)
    show_asset_columns = asset_count > 1
    while len(asset_labels) < asset_count:
        asset_labels.append(f"Актив {len(asset_labels) + 1}")
    asset_labels = [label or f"Актив {index + 1}" for index, label in enumerate(asset_labels)]

    stage_count = len(stage_payloads)
    day_column_count = stage_count * (asset_count if show_asset_columns else 1) + 1

    def product_for_stage(index: int, payload: dict):
        if index < len(products):
            return products[index]
        product_id = str(payload.get("product_id") or "").strip()
        return next((product for product in products if str(getattr(product, "pk", "") or "") == product_id), None)

    stage_labels = []
    for index, payload in enumerate(stage_payloads, start=1):
        product = product_for_stage(index - 1, payload)
        short_name = str(getattr(product, "short_name", "") or "").strip()
        stage_labels.append(f"Этап {index} {short_name}".strip())

    def header_cell(text, **extra):
        return {
            "text": text,
            "bold": True,
            "align": extra.pop("align", "center"),
            "header": True,
            "vertical_align": "center",
            "no_wrap": True,
            **extra,
        }

    if show_asset_columns:
        rows: list[list[dict[str, object]]] = [
            [
                header_cell("Специалист", align="left", rowspan=2),
                header_cell("Должность/направление", align="left", rowspan=2),
                header_cell("Ставка,\n€/дн", align="right", rowspan=2),
                *[
                    header_cell(f"{label}: кол-во дней", colspan=asset_count)
                    for label in stage_labels
                ],
                header_cell("Кол-во дней", colspan=1),
                header_cell("Итого,\n€ без НДС", align="right", rowspan=2),
            ],
            [
                *[
                    header_cell(asset_label)
                    for _stage_label in stage_labels
                    for asset_label in asset_labels
                ],
                header_cell("Всего"),
            ],
        ]
    else:
        rows = [
            [
                header_cell("Специалист", align="left"),
                header_cell("Должность/направление", align="left"),
                header_cell("Ставка,\n€/дн", align="right"),
                *[header_cell(f"{label}: кол-во дней") for label in stage_labels],
                header_cell("Всего"),
                header_cell("Итого,\n€ без НДС", align="right"),
            ]
        ]

    grouped_rows: dict[tuple[str, str], dict[str, object]] = {}
    grouped_order: list[tuple[str, str]] = []
    stage_day_totals = [[Decimal("0") for _ in range(asset_count)] for _ in range(stage_count)]
    travel_stage_day_totals = [[Decimal("0") for _ in range(asset_count)] for _ in range(stage_count)]
    travel_total = Decimal("0")
    has_travel_calculation = False
    has_travel_actual = False
    has_travel_data = False

    def normalized_day_values(raw_values) -> list[Decimal]:
        values = []
        for raw_value in list(raw_values or [])[:asset_count]:
            values.append(_proposal_day_decimal(raw_value) or Decimal("0"))
        while len(values) < asset_count:
            values.append(Decimal("0"))
        return values

    for stage_index, stage in enumerate(stage_payloads):
        totals_state = stage.get("commercial_totals_json") or {}
        travel_mode = (
            _normalize_proposal_travel_expenses_mode(totals_state.get("travel_expenses_mode"))
            or PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
        )
        for item in stage.get("commercial_offer_payload") or []:
            if not isinstance(item, dict):
                continue
            day_values = normalized_day_values(item.get("asset_day_counts") or [])
            if _is_proposal_travel_expenses_name(item.get("service_name") or ""):
                item_total = _proposal_day_decimal(item.get("total_eur_without_vat")) or Decimal("0")
                travel_total += item_total
                if item_total or any(value for value in day_values):
                    has_travel_data = True
                if travel_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                    has_travel_calculation = True
                    for asset_index, value in enumerate(day_values):
                        travel_stage_day_totals[stage_index][asset_index] += value
                else:
                    has_travel_actual = True
                continue

            key = (
                str(item.get("specialist") or "").strip(),
                str(item.get("job_title") or "").strip(),
            )
            if key not in grouped_rows:
                grouped_rows[key] = {
                    "specialist": key[0],
                    "job_title": key[1],
                    "professional_status": str(item.get("professional_status") or "").strip(),
                    "rate_eur_per_day": item.get("rate_eur_per_day"),
                    "stage_asset_day_counts": [[Decimal("0") for _ in range(asset_count)] for _ in range(stage_count)],
                    "fallback_total": Decimal("0"),
                }
                grouped_order.append(key)
            bucket = grouped_rows[key]
            for asset_index, value in enumerate(day_values):
                bucket["stage_asset_day_counts"][stage_index][asset_index] += value
                stage_day_totals[stage_index][asset_index] += value
            bucket["fallback_total"] += _proposal_day_decimal(item.get("total_eur_without_vat")) or Decimal("0")

    if saved_travel_offer is not None:
        has_travel_data = True
        saved_travel_total = _proposal_day_decimal(getattr(saved_travel_offer, "total_eur_without_vat", None))
        if saved_travel_total is not None:
            travel_total = saved_travel_total

    summary_total = Decimal("0")
    if saved_regular_offers:
        source_rows = []
        for item in saved_regular_offers:
            key = (
                str(getattr(item, "specialist", "") or "").strip(),
                str(getattr(item, "job_title", "") or "").strip(),
            )
            bucket = grouped_rows.get(key)
            raw_asset_day_counts = list(getattr(item, "asset_day_counts", []) or [])
            source_rows.append(
                {
                    "specialist": key[0],
                    "job_title": key[1],
                    "professional_status": str(getattr(item, "professional_status", "") or "").strip(),
                    "rate_eur_per_day": getattr(item, "rate_eur_per_day", None),
                    "stage_asset_day_counts": (
                        bucket["stage_asset_day_counts"]
                        if bucket is not None
                        else [[Decimal("0") for _ in range(asset_count)] for _ in range(stage_count)]
                    ),
                    "asset_day_counts": normalized_day_values(raw_asset_day_counts),
                    "has_saved_day_count_values": any(
                        value not in (None, "") and str(value).strip() != ""
                        for value in raw_asset_day_counts
                    ),
                    "fallback_total": _proposal_day_decimal(getattr(item, "total_eur_without_vat", None)) or Decimal("0"),
                }
            )
    else:
        source_rows = []
        for key in grouped_order:
            bucket = grouped_rows[key]
            stage_counts = bucket["stage_asset_day_counts"]
            source_rows.append(
                {
                    "specialist": str(bucket["specialist"] or "").strip(),
                    "job_title": str(bucket["job_title"] or "").strip(),
                    "professional_status": str(bucket["professional_status"] or "").strip(),
                    "rate_eur_per_day": bucket["rate_eur_per_day"],
                    "stage_asset_day_counts": stage_counts,
                    "asset_day_counts": [
                        sum(stage_counts[stage_index][asset_index] for stage_index in range(stage_count))
                        for asset_index in range(asset_count)
                    ],
                    "has_saved_day_count_values": True,
                    "fallback_total": bucket["fallback_total"],
                }
            )

    def effective_asset_totals(source: dict[str, object]) -> list[Decimal]:
        saved_totals = list(source.get("asset_day_counts") or [])
        while len(saved_totals) < asset_count:
            saved_totals.append(Decimal("0"))
        if any(value for value in saved_totals) or source.get("has_saved_day_count_values"):
            return saved_totals[:asset_count]
        stage_counts = source.get("stage_asset_day_counts") or []
        stage_totals = [
            sum(stage_counts[stage_index][asset_index] for stage_index in range(stage_count))
            for asset_index in range(asset_count)
        ]
        if source.get("fallback_total") != Decimal("0"):
            return saved_totals[:asset_count]
        return stage_totals if sum(stage_totals, Decimal("0")) else saved_totals[:asset_count]

    for source in source_rows:
        stage_counts = source["stage_asset_day_counts"]
        asset_totals = effective_asset_totals(source)
        total_days = sum(asset_totals, Decimal("0"))
        rate = _proposal_day_decimal(source["rate_eur_per_day"])
        row_total = (rate * total_days) if rate is not None and total_days else source["fallback_total"]
        summary_total += row_total
        direction = ", ".join(
            value
            for value in [
                str(source["job_title"] or "").strip(),
                str(source["professional_status"] or "").strip(),
            ]
            if value
        )
        rows.append(
            [
                {"text": str(source["specialist"] or "").strip()},
                {"text": direction, "no_wrap": True},
                {"text": _format_money(rate), "align": "right"},
                *[
                    {"text": _format_day_count(stage_counts[stage_index][asset_index]), "align": "right"}
                    for stage_index in range(stage_count)
                    for asset_index in (range(asset_count) if show_asset_columns else [0])
                ],
                {"text": _format_day_count(total_days), "align": "right"},
                {"text": _format_money(row_total), "align": "right"},
            ]
        )

    displayed_stage_day_totals = [[Decimal("0") for _ in range(asset_count)] for _ in range(stage_count)]
    for source in source_rows:
        stage_counts = source["stage_asset_day_counts"]
        for stage_index in range(stage_count):
            for asset_index in range(asset_count):
                displayed_stage_day_totals[stage_index][asset_index] += stage_counts[stage_index][asset_index]

    totals_state = getattr(proposal, "commercial_totals_json", {}) or {}
    travel_expenses_mode = (
        PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
        if has_travel_calculation and not has_travel_actual
        else PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
    )
    if not has_travel_data:
        travel_expenses_mode = _normalize_proposal_travel_expenses_mode(totals_state.get("travel_expenses_mode")) or travel_expenses_mode

    def flatten_stage_values(matrix, *, include_values=True) -> list[str]:
        if not include_values:
            return ["" for _ in range(stage_count * (asset_count if show_asset_columns else 1))]
        return [
            _format_day_count(matrix[stage_index][asset_index])
            for stage_index in range(stage_count)
            for asset_index in (range(asset_count) if show_asset_columns else [0])
        ]

    def append_fixed_row(label, *, rate="", day_values=None, total="", total_days=None):
        current_day_values = list(day_values or [])
        while len(current_day_values) < stage_count * (asset_count if show_asset_columns else 1):
            current_day_values.append("")
        total_days_text = (
            _format_day_count(total_days)
            if total_days is not None
            else _format_day_count(sum((_proposal_day_decimal(value) or Decimal("0")) for value in current_day_values))
        )
        rows.append(
            [
                {"text": label, "colspan": 2, "bold": True},
                {"text": str(rate or ""), "align": "right"},
                *[
                    {"text": str(value or ""), "align": "right"}
                    for value in current_day_values
                ],
                {"text": total_days_text, "align": "right"},
                {"text": str(total or ""), "align": "right"},
            ]
        )

    summary_total_days = sum(sum(effective_asset_totals(source), Decimal("0")) for source in source_rows)
    append_fixed_row(
        PROPOSAL_SUMMARY_TOTAL_LABEL,
        day_values=flatten_stage_values(displayed_stage_day_totals),
        total=_format_money(summary_total),
        total_days=summary_total_days,
    )
    if has_travel_data:
        append_fixed_row(
            PROPOSAL_TRAVEL_EXPENSES_LABEL,
            rate="расчёт" if travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION else "по факту",
            day_values=flatten_stage_values(
                travel_stage_day_totals,
                include_values=travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION,
            ),
            total=_format_money(travel_total),
        )
    summary_with_travel_total = summary_total + travel_total
    exchange_rate = _parse_decimal(totals_state.get("exchange_rate"))
    discount_percent = _parse_decimal(totals_state.get("discount_percent"))
    rub_total = (summary_with_travel_total * exchange_rate) if exchange_rate is not None else None
    discounted_total = (
        rub_total - (rub_total * (discount_percent / Decimal("100")))
        if rub_total is not None and discount_percent is not None
        else rub_total
    )
    contract_total = _parse_decimal(totals_state.get("contract_total"))
    contract_total_auto = _parse_decimal(totals_state.get("contract_total_auto"))
    if contract_total in (None, Decimal("0")):
        contract_total = contract_total_auto or _round_to_hundred_thousand(discounted_total)

    append_fixed_row(PROPOSAL_SUMMARY_WITH_TRAVEL_TOTAL_LABEL, total=_format_money(summary_with_travel_total))
    append_fixed_row(
        PROPOSAL_RUB_TOTAL_LABEL,
        rate=_format_decimal(exchange_rate, precision=4, strip_trailing_zeros=True),
        total=_format_money(rub_total),
    )
    append_fixed_row(
        PROPOSAL_RUB_DISCOUNTED_LABEL,
        rate=_format_percent(discount_percent, strip_trailing_zeros=True),
        total=_format_money(discounted_total),
    )
    append_fixed_row(PROPOSAL_CONTRACT_TOTAL_LABEL, total=_format_money(contract_total))

    return {
        "rows": rows,
        "font_size_pt": 7,
        "style": "Table Grid",
        "column_widths_pct": _proposal_multistage_column_widths_pct(day_column_count),
    }


def _proposal_budget_table(proposal) -> dict:
    multistage_table = _proposal_multistage_budget_table(proposal)
    if multistage_table is not None:
        return multistage_table

    offers = list(proposal.commercial_offers.order_by("position", "id"))
    travel_offer = next(
        (
            item
            for item in offers
            if _is_proposal_travel_expenses_name(getattr(item, "service_name", ""))
        ),
        None,
    )
    regular_offers = [
        item
        for item in offers
        if not _is_proposal_travel_expenses_name(getattr(item, "service_name", ""))
    ]

    asset_labels = [
        str(getattr(asset, "short_name", "") or "").strip()
        for asset in proposal.assets.order_by("position", "id")
    ]
    max_asset_count = max(
        [len(getattr(item, "asset_day_counts", []) or []) for item in offers],
        default=0,
    )
    asset_count = max(len(asset_labels), max_asset_count, 1)
    show_asset_columns = asset_count > 1
    show_total_days_column = True
    while len(asset_labels) < asset_count:
        asset_labels.append(f"Актив {len(asset_labels) + 1}")
    asset_labels = [label or f"Актив {index + 1}" for index, label in enumerate(asset_labels)]

    rows: list[list[dict[str, object]]] = [
        [
            {"text": "Специалист", "bold": True, "align": "left", "header": True, "vertical_align": "center"},
            {"text": "Должность/направление", "bold": True, "align": "left", "header": True, "vertical_align": "center", "no_wrap": True},
            {"text": "Ставка,\n€/дн", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
            *(
                [
                    {
                        "text": label,
                        "bold": True,
                        "align": "center",
                        "header": True,
                        "vertical_align": "center",
                        "margins_cm": {
                            "top": 0,
                            "right": 0,
                            "bottom": 0,
                            "left": 0,
                        },
                    }
                    for label in asset_labels
                ]
                if show_asset_columns
                else []
            ),
            {"text": "Кол-во\nдней", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
            {"text": "Итого,\n€ без НДС", "bold": True, "align": "right", "header": True, "vertical_align": "center"},
        ],
    ]

    def build_day_values(raw_values) -> list[str]:
        normalized = [str(value or "").strip() for value in list(raw_values or [])[:asset_count]]
        while len(normalized) < asset_count:
            normalized.append("")
        return normalized

    for item in regular_offers:
        day_values = build_day_values(getattr(item, "asset_day_counts", []) or [])
        direction = ", ".join(
            [
                value
                for value in [
                    str(getattr(item, "job_title", "") or "").strip(),
                    str(getattr(item, "professional_status", "") or "").strip(),
                ]
                if value
            ]
        )
        rows.append(
            [
                {"text": str(getattr(item, "specialist", "") or "").strip()},
                {"text": direction, "no_wrap": True},
                {"text": _format_money(getattr(item, "rate_eur_per_day", None)), "align": "right"},
                *(
                    [
                        {"text": value, "align": "right"}
                        for value in day_values
                    ]
                    if show_asset_columns
                    else []
                ),
                {"text": str(_sum_day_counts(day_values)) if _sum_day_counts(day_values) else "", "align": "right"},
                {"text": _format_money(getattr(item, "total_eur_without_vat", None)), "align": "right"},
            ]
        )

    summary_day_values = [
        str(value) if value else ""
        for value in (
            [
                sum(
                    int(str((getattr(item, "asset_day_counts", []) or [""])[index] or "").strip() or "0")
                    for item in regular_offers
                    if index < len(getattr(item, "asset_day_counts", []) or [])
                )
                for index in range(asset_count)
            ]
            if asset_count
            else []
        )
    ]
    summary_total = sum(
        (_parse_decimal(getattr(item, "total_eur_without_vat", None)) or Decimal("0"))
        for item in regular_offers
    )
    travel_total = Decimal("0")
    travel_day_values = []
    if travel_offer is not None:
        travel_day_values = build_day_values(getattr(travel_offer, "asset_day_counts", []) or [])
        travel_total = _sum_decimal_values(travel_day_values)
        if travel_total == Decimal("0"):
            travel_total = _parse_decimal(getattr(travel_offer, "total_eur_without_vat", None)) or Decimal("0")
    summary_with_travel_total = summary_total + travel_total
    totals_state = getattr(proposal, "commercial_totals_json", {}) or {}
    travel_expenses_mode = _normalize_proposal_travel_expenses_mode(totals_state.get("travel_expenses_mode"))
    if not travel_expenses_mode:
        travel_expenses_mode = (
            PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
            if travel_total or any(str(value or "").strip() for value in travel_day_values)
            else PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
        )
    exchange_rate = _parse_decimal(totals_state.get("exchange_rate"))
    discount_percent = _parse_decimal(totals_state.get("discount_percent"))
    rub_total = (summary_with_travel_total * exchange_rate) if exchange_rate is not None else None
    discounted_total = (
        rub_total - (rub_total * (discount_percent / Decimal("100")))
        if rub_total is not None and discount_percent is not None
        else rub_total
    )
    contract_total = _parse_decimal(totals_state.get("contract_total"))
    contract_total_auto = _parse_decimal(totals_state.get("contract_total_auto"))
    if contract_total in (None, Decimal("0")):
        contract_total = contract_total_auto or _round_to_hundred_thousand(discounted_total)

    def append_fixed_row(label, *, rate="", day_values=None, total="", label_colspan=2):
        current_day_values = list(day_values or [])
        while len(current_day_values) < asset_count:
            current_day_values.append("")
        rows.append(
            [
                {"text": label, "colspan": label_colspan, "bold": True},
                {"text": str(rate or ""), "align": "right"},
                *(
                    [
                        {"text": str(value or ""), "align": "right"}
                        for value in current_day_values
                    ]
                    if show_asset_columns
                    else []
                ),
                {"text": str(_sum_day_counts(current_day_values)) if _sum_day_counts(current_day_values) else "", "align": "right"},
                {"text": str(total or ""), "align": "right"},
            ]
        )

    append_fixed_row(
        PROPOSAL_SUMMARY_TOTAL_LABEL,
        rate="",
        day_values=summary_day_values,
        total=_format_money(summary_total),
    )
    if travel_offer is not None:
        append_fixed_row(
            PROPOSAL_TRAVEL_EXPENSES_LABEL,
            rate="расчёт" if travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION else "по факту",
            day_values=travel_day_values,
            total=_format_money(travel_total),
        )
    append_fixed_row(
        PROPOSAL_SUMMARY_WITH_TRAVEL_TOTAL_LABEL,
        rate="",
        day_values=[],
        total=_format_money(summary_with_travel_total),
    )
    append_fixed_row(
        PROPOSAL_RUB_TOTAL_LABEL,
        rate=_format_decimal(exchange_rate, precision=4, strip_trailing_zeros=True),
        day_values=[],
        total=_format_money(rub_total),
    )
    append_fixed_row(
        PROPOSAL_RUB_DISCOUNTED_LABEL,
        rate=_format_percent(discount_percent, strip_trailing_zeros=True),
        day_values=[],
        total=_format_money(discounted_total),
    )
    append_fixed_row(
        PROPOSAL_CONTRACT_TOTAL_LABEL,
        rate="",
        day_values=[],
        total=_format_money(contract_total),
    )

    return {
        "rows": rows,
        "font_size_pt": 8 if not show_asset_columns else 7,
        "style": "Table Grid",
        "column_widths_pct": [18, 46, 12, 12, 12] if not show_asset_columns else _proposal_multi_asset_column_widths_pct(asset_count),
    }


def _proposal_evaluation_date(proposal) -> str:
    return _format_date(proposal.evaluation_date)


def _parse_proposal_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return date.fromisoformat(text) if fmt == "%Y-%m-%d" else date(
                int(text[6:10]),
                int(text[3:5]),
                int(text[0:2]),
            )
        except (TypeError, ValueError):
            continue
    return None


def _add_whole_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_decimal_months(value: date, months: Decimal) -> date:
    safe_months = max(months, Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(((safe_months - whole_months) * Decimal("30")) + Decimal("0.5"))
    return _add_whole_months(value, whole_months) + timedelta(days=fractional_days)


def _subtract_decimal_months(value: date, months: Decimal) -> date:
    safe_months = max(months, Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(((safe_months - whole_months) * Decimal("30")) + Decimal("0.5"))
    base = value - timedelta(days=fractional_days)
    return _add_whole_months(base, -whole_months)


def _subtract_decimal_weeks(value: date, weeks: Decimal) -> date:
    safe_weeks = max(weeks, Decimal("0"))
    return value - timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _add_decimal_weeks(value: date, weeks: Decimal) -> date:
    safe_weeks = max(weeks, Decimal("0"))
    return value + timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _proposal_base_start_date() -> date:
    current = _today() + timedelta(days=14)
    previous_monday = current - timedelta(days=current.weekday())
    next_monday = previous_monday + timedelta(days=7)
    if (current - previous_monday) <= (next_monday - current):
        return previous_monday
    return next_monday


def _decimal_months_between(start: date, end: date) -> Decimal:
    if end <= start:
        return Decimal("0")
    whole_months = (end.year - start.year) * 12 + (end.month - start.month)
    whole_date = _add_whole_months(start, whole_months)
    while whole_months > 0 and whole_date > end:
        whole_months -= 1
        whole_date = _add_whole_months(start, whole_months)
    remainder_days = max(0, (end - whole_date).days)
    return Decimal(whole_months) + (Decimal(remainder_days) / Decimal("30"))


def _proposal_service_term_months(proposal) -> str:
    return _format_decimal(proposal.service_term_months, precision=1)


def _format_month_term_short(months: Decimal) -> str:
    rounded = months.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{_format_decimal(rounded, precision=1, strip_trailing_zeros=True)} мес."


def _format_week_term_short(weeks: Decimal) -> str:
    rounded = weeks.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{_format_decimal(rounded, precision=1, strip_trailing_zeros=True)} нед."


def _proposal_preliminary_report_term_month(proposal) -> str:
    if getattr(proposal, "service_term_months", None) in (None, ""):
        return ""
    try:
        months = Decimal(str(proposal.service_term_months))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if months == Decimal("1"):
        suffix = "месяц"
    elif months < Decimal("5"):
        suffix = "месяца"
    else:
        suffix = "месяцев"
    return f"{_format_decimal(months, precision=1, strip_trailing_zeros=True)} {suffix}"


def _proposal_last_stage_final_report_date(proposal) -> date | None:
    stage_payloads = [
        item
        for item in (getattr(proposal, "stage_payloads_json", None) or [])
        if isinstance(item, dict)
    ]
    for payload in reversed(stage_payloads):
        parsed = _parse_proposal_date(payload.get("final_report_date"))
        if parsed:
            return parsed
    return _parse_proposal_date(getattr(proposal, "final_report_date", None))


def _proposal_first_stage_start_date(proposal) -> date | None:
    stage_payloads = [
        item
        for item in (getattr(proposal, "stage_payloads_json", None) or [])
        if isinstance(item, dict)
    ]
    sources = stage_payloads or [proposal]
    source = sources[0]
    if isinstance(source, dict):
        preliminary_report_date = _parse_proposal_date(source.get("preliminary_report_date"))
        final_report_date = _parse_proposal_date(source.get("final_report_date"))
        service_term_months = _parse_decimal(source.get("service_term_months"))
        final_report_term_weeks = _parse_decimal(source.get("final_report_term_weeks"))
    else:
        preliminary_report_date = _parse_proposal_date(getattr(source, "preliminary_report_date", None))
        final_report_date = _parse_proposal_date(getattr(source, "final_report_date", None))
        service_term_months = _parse_decimal(getattr(source, "service_term_months", None))
        final_report_term_weeks = _parse_decimal(getattr(source, "final_report_term_weeks", None))

    if not preliminary_report_date and final_report_date and final_report_term_weeks is not None:
        preliminary_report_date = _subtract_decimal_weeks(final_report_date, final_report_term_weeks)
    if preliminary_report_date and service_term_months is not None:
        return _subtract_decimal_months(preliminary_report_date, service_term_months)
    return None


def _proposal_final_report_term_month(proposal) -> str:
    final_report_date = _proposal_last_stage_final_report_date(proposal)
    if not final_report_date:
        return ""
    start_date = _proposal_first_stage_start_date(proposal) or _proposal_base_start_date()
    months = _decimal_months_between(start_date, final_report_date)
    return _format_month_term_short(months)


def _proposal_stages(proposal) -> str:
    products = list(proposal.ordered_products()) if hasattr(proposal, "ordered_products") else []
    if not products and getattr(proposal, "type_id", None):
        products = [proposal.type]
    count = len(products)
    if count == 1:
        suffix = "этап"
    elif 2 <= count <= 4:
        suffix = "этапа"
    else:
        suffix = "этапов"
    return f"{count} {suffix}"


def _proposal_preliminary_report_date(proposal) -> str:
    return _format_date(proposal.preliminary_report_date)


def _proposal_final_report_term_weeks(proposal) -> str:
    return _format_decimal(proposal.final_report_term_weeks, precision=1)


def _proposal_final_report_date(proposal) -> str:
    return _format_date(proposal.final_report_date)


def _proposal_report_languages(proposal) -> str:
    return proposal.report_languages or ""


def _proposal_service_cost(proposal) -> str:
    service_cost = _parse_decimal(getattr(proposal, "service_cost", None))
    if service_cost not in (None, Decimal("0")):
        return _format_money(service_cost)
    totals_state = getattr(proposal, "commercial_totals_json", {}) or {}
    contract_total = _parse_decimal(totals_state.get("contract_total"))
    if contract_total not in (None, Decimal("0")):
        return _format_money(contract_total)
    contract_total_auto = _parse_decimal(totals_state.get("contract_total_auto"))
    return _format_money(contract_total_auto)


def _proposal_currency(proposal) -> str:
    if not proposal.currency_id:
        return ""
    return proposal.currency.code_alpha or str(proposal.currency)


def _proposal_advance_percent(proposal) -> str:
    return _format_percent(proposal.advance_percent, strip_trailing_zeros=True)


def _proposal_advance_term_days(proposal) -> str:
    return str(proposal.advance_term_days or "")


def _proposal_preliminary_report_percent(proposal) -> str:
    return _format_percent(proposal.preliminary_report_percent, strip_trailing_zeros=True)


def _proposal_preliminary_payment_percentage_full(proposal) -> str:
    try:
        advance = Decimal(str(getattr(proposal, "advance_percent", "") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        advance = Decimal("0")
    try:
        preliminary = Decimal(str(getattr(proposal, "preliminary_report_percent", "") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        preliminary = Decimal("0")
    return _format_percent(advance + preliminary, strip_trailing_zeros=True)


def _proposal_preliminary_report_term_days(proposal) -> str:
    return str(proposal.preliminary_report_term_days or "")


def _proposal_final_report_percent(proposal) -> str:
    return _format_percent(proposal.final_report_percent, strip_trailing_zeros=True)


def _proposal_final_report_term_days(proposal) -> str:
    return str(proposal.final_report_term_days or "")


def _source_value(source, key: str, attr: str | None = None):
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, attr or key, None)


def _proposal_stage_term_sources(proposal) -> list[dict[str, object]]:
    products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
    if not products and getattr(proposal, "type_id", None):
        products = [proposal.type]
    stage_payloads = [
        item
        for item in (getattr(proposal, "stage_payloads_json", None) or [])
        if isinstance(item, dict)
    ]
    if not products and stage_payloads:
        products = [None for _ in stage_payloads]
    if len(products) <= 1:
        return [{"product": products[0] if products else getattr(proposal, "type", None), "source": stage_payloads[0] if stage_payloads else proposal}]

    payload_by_product_id = {}
    for payload in stage_payloads:
        product_id = str(payload.get("product_id") or "").strip()
        if product_id and product_id not in payload_by_product_id:
            payload_by_product_id[product_id] = payload

    result = []
    for index, product in enumerate(products, start=1):
        product_id = str(getattr(product, "pk", "") or "")
        indexed_source = stage_payloads[index - 1] if index - 1 < len(stage_payloads) else {}
        if indexed_source and (not product_id or str(indexed_source.get("product_id") or "") == product_id):
            source = indexed_source
        else:
            source = payload_by_product_id.get(product_id) or indexed_source or proposal
        result.append({"product": product, "source": source})
    return result


def _proposal_stage_term_values(source, fallback_start_date: date | None = None) -> dict[str, object]:
    months = _parse_decimal(_source_value(source, "service_term_months")) or Decimal("0")
    weeks = _parse_decimal(_source_value(source, "final_report_term_weeks")) or Decimal("0")
    preliminary_date = _parse_proposal_date(_source_value(source, "preliminary_report_date"))
    final_date = _parse_proposal_date(_source_value(source, "final_report_date"))

    start_date = None
    if preliminary_date:
        start_date = _subtract_decimal_months(preliminary_date, months)
    elif final_date:
        preliminary_date = _subtract_decimal_weeks(final_date, weeks)
        start_date = _subtract_decimal_months(preliminary_date, months)
    elif fallback_start_date:
        start_date = fallback_start_date

    if start_date and not preliminary_date:
        preliminary_date = _add_decimal_months(start_date, months)
    if preliminary_date and not final_date:
        final_date = _add_decimal_weeks(preliminary_date, weeks)

    if start_date and preliminary_date:
        months = _decimal_months_between(start_date, preliminary_date)
    if preliminary_date and final_date:
        weeks = Decimal(max(0, (final_date - preliminary_date).days)) / Decimal("7")
    total_months = _decimal_months_between(start_date, final_date) if start_date and final_date else Decimal("0")
    return {
        "start_date": start_date,
        "preliminary_date": preliminary_date,
        "final_date": final_date,
        "preliminary_months": months,
        "final_weeks": weeks,
        "total_months": total_months,
        "next_stage_delay_days": _parse_decimal(_source_value(source, "next_stage_delay_days")) or Decimal("0"),
    }


def _proposal_stage_terms(proposal) -> list[dict[str, object]]:
    sources = _proposal_stage_term_sources(proposal)
    result: list[dict[str, object]] = []
    rolling_start_date = _proposal_first_stage_start_date(proposal) or _proposal_base_start_date()
    has_multiple_stages = len(sources) > 1
    bullet_format = {"list_type": "bullet"}

    for index, item in enumerate(sources, start=1):
        values = _proposal_stage_term_values(item["source"], rolling_start_date)
        if has_multiple_stages:
            result.append(
                {
                    "runs": [
                        {
                            "text": f"Этап {index}: {_format_month_term_short(values['total_months'])}",
                        }
                    ]
                }
            )
        result.append(
            {
                "runs": [
                    {
                        "text": (
                            "сдача Предварительного отчёта — в течение "
                            f"{_format_month_term_short(values['preliminary_months'])} до "
                            f"{_format_date(values['preliminary_date'])},"
                        )
                    }
                ],
                **bullet_format,
            }
        )
        result.append(
            {
                "runs": [
                    {
                        "text": (
                            "сдача Итогового отчёта — в течение "
                            f"{_format_week_term_short(values['final_weeks'])} до "
                            f"{_format_date(values['final_date'])}."
                        )
                    }
                ],
                **bullet_format,
            }
        )

        stage_end_date = values["final_date"] or values["preliminary_date"] or values["start_date"]
        if stage_end_date:
            rolling_start_date = stage_end_date + timedelta(days=int(values["next_stage_delay_days"]))

    return result


def _payment_schedule_decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _payment_schedule_days(value) -> str:
    return "" if value in (None, "") else str(value)


def _payment_schedule_product_name(product) -> str:
    product_id = getattr(product, "pk", None)
    name = _service_goal_report_value(product_id, "product_name")
    if name:
        return name
    return (
        str(getattr(product, "name_ru", "") or "").strip()
        or str(getattr(product, "short_name", "") or "").strip()
        or str(product or "").strip()
    )


def _proposal_product_name_list(proposal) -> list[str]:
    products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
    if not products and getattr(proposal, "type_id", None):
        products = [proposal.type]

    total = len(products)
    result: list[str] = []
    for index, product in enumerate(products, start=1):
        product_name = _payment_schedule_product_name(product)
        if total == 1:
            text = f"{product_name}."
        else:
            ending = "." if index == total else ";"
            text = f"Этап {index} — {product_name}{ending}"
        result.append(text)
    return result


def _payment_schedule_values(source) -> dict[str, str]:
    advance_percent = source.get("advance_percent") if isinstance(source, dict) else getattr(source, "advance_percent", None)
    advance_term_days = source.get("advance_term_days") if isinstance(source, dict) else getattr(source, "advance_term_days", None)
    preliminary_percent = (
        source.get("preliminary_report_percent")
        if isinstance(source, dict)
        else getattr(source, "preliminary_report_percent", None)
    )
    preliminary_term_days = (
        source.get("preliminary_report_term_days")
        if isinstance(source, dict)
        else getattr(source, "preliminary_report_term_days", None)
    )
    final_percent = source.get("final_report_percent") if isinstance(source, dict) else getattr(source, "final_report_percent", None)
    final_term_days = source.get("final_report_term_days") if isinstance(source, dict) else getattr(source, "final_report_term_days", None)
    return {
        "prepayment_payment_percentage": _format_percent(advance_percent, strip_trailing_zeros=True),
        "prepayment_payment_days": _payment_schedule_days(advance_term_days),
        "preliminary_payment_percentage": _format_percent(preliminary_percent, strip_trailing_zeros=True),
        "preliminary_payment_days": _payment_schedule_days(preliminary_term_days),
        "preliminary_payment_percentage_full": _format_percent(
            _payment_schedule_decimal(advance_percent) + _payment_schedule_decimal(preliminary_percent),
            strip_trailing_zeros=True,
        ),
        "final_payment_percentage": _format_percent(final_percent, strip_trailing_zeros=True),
        "final_payment_days": _payment_schedule_days(final_term_days),
    }


def _payment_schedule_payment_paragraphs(source) -> list[dict[str, object]]:
    values = _payment_schedule_values(source)
    paragraph_format = {
        "paragraph_style": "list_paragraph",
        "left_indent_cm": 1.0,
        "contextual_spacing": True,
    }
    return [
        {
            "runs": [
                {
                    "text": (
                        f"{values['prepayment_payment_percentage']} — предоплата при подписании контракта — "
                        f"в течение {values['prepayment_payment_days']} календарных дней."
                    )
                }
            ],
            **paragraph_format,
        },
        {
            "runs": [
                {
                    "text": (
                        f"{values['preliminary_payment_percentage']} — в течение "
                        f"{values['preliminary_payment_days']} календарных дней после предоставления "
                        "Предварительного отчёта и подписания Акта № 1 на "
                        f"{values['preliminary_payment_percentage_full']} суммы договора."
                    )
                }
            ],
            **paragraph_format,
        },
        {
            "runs": [
                {
                    "text": (
                        f"{values['final_payment_percentage']} — после сдачи Итогового отчёта — "
                        f"в течение {values['final_payment_days']} календарных дней после подписания "
                        "Акта №\u00a02 на оставшуюся сумму."
                    )
                }
            ],
            **paragraph_format,
        },
    ]


def _proposal_payment_schedule(proposal) -> list[dict[str, object]]:
    products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
    if not products and getattr(proposal, "type_id", None):
        products = [proposal.type]
    stage_payloads = [item for item in (getattr(proposal, "stage_payloads_json", None) or []) if isinstance(item, dict)]
    is_common = not any(payload.get("payment_schedule_common") is False for payload in stage_payloads)
    if len(products) <= 1:
        source = stage_payloads[0] if stage_payloads and not is_common else proposal
        return _payment_schedule_payment_paragraphs(source)

    result: list[dict[str, object]] = []
    if is_common:
        result.append({"runs": [{"text": "общий для всех этапов:"}], "left_indent_cm": 1.0})
        result.extend(_payment_schedule_payment_paragraphs(proposal))
        return result

    payload_by_product_id = {}
    for payload in stage_payloads:
        product_id = str(payload.get("product_id") or "").strip()
        if product_id and product_id not in payload_by_product_id:
            payload_by_product_id[product_id] = payload
    for index, product in enumerate(products, start=1):
        product_id = str(getattr(product, "pk", "") or "")
        indexed_source = stage_payloads[index - 1] if index - 1 < len(stage_payloads) else {}
        if indexed_source and (not product_id or str(indexed_source.get("product_id") or "") == product_id):
            source = indexed_source
        else:
            source = payload_by_product_id.get(product_id) or indexed_source
        result.append({"runs": [{"text": f"Этап {index} — {_payment_schedule_product_name(product)}:"}]})
        result.extend(_payment_schedule_payment_paragraphs(source))
    return result


def _computed_year(_proposal) -> str:
    return str(_today().year)


def _computed_day(_proposal) -> str:
    return f"{_today().day:02d}"


def _computed_month(_proposal) -> str:
    from core.dates import MONTHS_RU_GENITIVE

    return MONTHS_RU_GENITIVE[_today().month]


FIELD_MAP = {
    ("proposals", "registry", "number"): _proposal_number,
    ("proposals", "registry", "sub_number"): _proposal_sub_number,
    ("proposals", "registry", "group"): _proposal_group,
    ("proposals", "registry", "tkp_id"): _proposal_tkp_id,
    ("proposals", "registry", "type"): _proposal_type,
    ("proposals", "registry", "name"): _proposal_name,
    ("proposals", "registry", "kind"): _proposal_kind,
    ("proposals", "registry", "status"): _proposal_status,
    ("proposals", "registry", "year"): _proposal_year,
    ("proposals", "registry", "customer"): _proposal_customer,
    ("proposals", "registry", "country"): _proposal_country,
    ("proposals", "registry", "country_full_name"): _proposal_country_full_name,
    ("proposals", "registry", "identifier"): _proposal_identifier,
    ("proposals", "registry", "registration_number"): _proposal_registration_number,
    ("proposals", "registry", "registration_region"): _proposal_registration_region,
    ("proposals", "registry", "date"): _proposal_date,
    ("proposals", "registry", "asset_owner"): _proposal_asset_owner,
    ("proposals", "registry", "asset_owner_country"): _proposal_asset_owner_country,
    ("proposals", "registry", "asset_owner_identifier"): _proposal_asset_owner_identifier,
    ("proposals", "registry", "asset_owner_registration_number"): _proposal_asset_owner_registration_number,
    ("proposals", "registry", "asset_owner_region"): _proposal_asset_owner_region,
    ("proposals", "registry", "asset_owner_registration_date"): _proposal_asset_owner_registration_date,
    ("proposals", "registry", "proposal_project_name"): _proposal_project_name,
    ("proposals", "registry", "purpose"): _proposal_purpose,
    ("proposals", "registry", "service_composition"): _proposal_service_composition,
    ("proposals", "registry", "evaluation_date"): _proposal_evaluation_date,
    ("proposals", "registry", "effective_date"): _proposal_evaluation_date,
    ("proposals", "registry", "term"): _proposal_service_term_months,
    ("proposals", "registry", "preliminary_report_date"): _proposal_preliminary_report_date,
    ("proposals", "registry", "final_report_term_weeks"): _proposal_final_report_term_weeks,
    ("proposals", "registry", "final_report_term_month"): _proposal_final_report_term_month,
    ("proposals", "registry", "final_report_date"): _proposal_final_report_date,
    ("proposals", "registry", "report_languages"): _proposal_report_languages,
    ("proposals", "registry", "service_cost"): _proposal_service_cost,
    ("proposals", "registry", "total_price"): _proposal_service_cost,
    ("proposals", "registry", "currency"): _proposal_currency,
    ("proposals", "registry", "advance_percent"): _proposal_advance_percent,
    ("proposals", "registry", "advance_term"): _proposal_advance_term_days,
    ("proposals", "registry", "preliminary_report_percent"): _proposal_preliminary_report_percent,
    ("proposals", "registry", "preliminary_report_term"): _proposal_preliminary_report_term_days,
    ("proposals", "registry", "final_report_percent"): _proposal_final_report_percent,
    ("proposals", "registry", "final_report_term"): _proposal_final_report_term_days,
    ("products", "service_goals_and_report_titles", "service_goal"): _proposal_service_goal,
    ("products", "service_goals_and_report_titles", "service_goal_genitive"): _proposal_service_goal_genitive,
    ("products", "service_goals_and_report_titles", "report_title"): _proposal_report_title,
    ("products", "service_goals_and_report_titles", "product_name"): _proposal_product_name,
}


COMPUTED_MAP = {
    "{{year}}": _computed_year,
    "{{day}}": _computed_day,
    "{{month}}": _computed_month,
    "{{client_country_full_name}}": _proposal_country_full_name,
    "{{client_owner_name}}": _proposal_client_owner_name,
    "{{service_type_short}}": _proposal_service_type_short,
    "{{service_goal_genitive}}": _proposal_service_goal_genitive,
    "{{tkp_preliminary}}": _proposal_tkp_preliminary,
    "{{preliminary_payment_percentage_full}}": _proposal_preliminary_payment_percentage_full,
    "{{preliminary_report_term_month}}": _proposal_preliminary_report_term_month,
    "{{final_report_term_month}}": _proposal_final_report_term_month,
    "{{stages}}": _proposal_stages,
    "{{owner_country_full_name}}": _proposal_asset_owner_country_full_name,
    "{{country_full_name}}": _proposal_country_full_name,
    "{{effective_date}}": _proposal_evaluation_date,
    "{{total_price}}": _proposal_service_cost,
}

COMPUTED_LIST_MAP = {
    "[[actives_name]]": _proposal_actives_name_list,
    "[[scope_of_work]]": _proposal_scope_of_work,
    "[[payment_schedule]]": _proposal_payment_schedule,
    "[[product_name]]": _proposal_product_name_list,
    "[[stage_terms]]": _proposal_stage_terms,
}

COMPUTED_TABLE_MAP = {
    "[[budget_table]]": _proposal_budget_table,
}

VARIABLE_ALIASES = {
    "{{client_country_full_name}}": ["{{country_full_name}}"],
    "{{country_full_name}}": ["{{client_country_full_name}}"],
    "{{evaluation_date}}": ["{{effective_date}}"],
    "{{effective_date}}": ["{{evaluation_date}}"],
    "{{service_cost}}": ["{{total_price}}"],
    "{{total_price}}": ["{{service_cost}}"],
}


def resolve_variables(proposal, variables) -> tuple[dict[str, str], dict, dict]:
    replacements: dict[str, str] = {}
    list_replacements: dict[str, list[str]] = {}
    table_replacements: dict[str, dict] = {}
    for variable in variables:
        if getattr(variable, "is_computed", False):
            computed_table_resolver = COMPUTED_TABLE_MAP.get(variable.key)
            if computed_table_resolver:
                table_replacements[variable.key] = computed_table_resolver(proposal) or {}
                continue
            computed_list_resolver = COMPUTED_LIST_MAP.get(variable.key)
            if computed_list_resolver:
                list_replacements[variable.key] = list(computed_list_resolver(proposal) or [])
                continue
            computed_resolver = COMPUTED_MAP.get(variable.key)
            if computed_resolver:
                value = str(computed_resolver(proposal) or "")
                replacements[variable.key] = value
                for alias in VARIABLE_ALIASES.get(variable.key, []):
                    replacements[alias] = value
            continue
        key = (
            variable.source_section or "",
            variable.source_table or "",
            variable.source_column or "",
        )
        resolver = FIELD_MAP.get(key)
        if not resolver:
            continue
        value = str(resolver(proposal) or "")
        replacements[variable.key] = value
        for alias in VARIABLE_ALIASES.get(variable.key, []):
            replacements[alias] = value
    return replacements, list_replacements, table_replacements
