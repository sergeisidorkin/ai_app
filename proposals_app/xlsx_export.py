import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .variable_resolver import _proposal_budget_direction


TRAVEL_LABELS = {"Командировочные расходы", "Командировочные расходы, евро"}
MAX_STAGES = 20
MAX_ASSETS = 50
MAX_ROWS_PER_BLOCK = 500
SPECIALIST_COL = 1
DIRECTION_COL = 2
SEPARATOR_ROW_HEIGHT = 3.75
SPECIALTY_COL = 3
STATUS_COL = 4
CODE_COL = 5
SERVICE_COL = 6
RATE_COL = 7
HIDDEN_SOURCE_COLUMNS = (SPECIALTY_COL, STATUS_COL, CODE_COL, SERVICE_COL)
RUB_TOTAL_LABEL = "ИТОГО, рубли без НДС"
DISCOUNTED_TOTAL_LABEL = "ИТОГО, рубли без НДС с учетом скидки"
DAY_COUNT_FORMAT = "0"


def _text(value, limit=1000):
    return str(value or "").strip()[:limit]


def _excel_text(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def _number(value):
    raw = _text(value).replace("\xa0", "").replace(" ", "").replace(",", ".").replace("%", "")
    if not raw:
        return None
    try:
        return float(Decimal(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_true(value):
    if value is True:
        return True
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _is_travel(row):
    return _text(row.get("service_name")) in TRAVEL_LABELS


def _direction_text(row):
    return _proposal_budget_direction(
        row.get("job_title"),
        row.get("professional_status"),
        row.get("service_name"),
    )


def _direction_text_width(text, *, bold=False):
    """Ширина столбца Excel в символах «0» шрифта Calibri 11, чтобы строка не переносилась."""
    units = 0.0
    for char in str(text or ""):
        if char.isspace():
            units += 0.6
        elif ord(char) > 127 or char.isupper():
            units += 1.3
        else:
            units += 1.05
    if bold:
        units *= 1.1
    return units + 3


def _group_key(row):
    code = "" if _is_true(row.get("merge_without_code")) else _text(row.get("code"), 100)
    return (
        _text(row.get("specialist"), 255),
        _text(row.get("job_title"), 255),
        code,
    )


def _formula_sum(cells):
    refs = [str(cell) for cell in cells if cell]
    if not refs:
        return ""
    if len(refs) == 1:
        return refs[0]
    return f"SUM({','.join(refs)})"


def _formula_nonzero_sum(cells):
    expression = _formula_sum(cells)
    return f'=IF({expression}=0,"",{expression})' if expression else ""


def _normalize_rows(value, asset_count):
    if not isinstance(value, list):
        raise ValueError("Строки коммерческого предложения переданы в некорректном формате.")
    if len(value) > MAX_ROWS_PER_BLOCK:
        raise ValueError("Слишком много строк коммерческого предложения.")
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        day_counts = item.get("asset_day_counts")
        if not isinstance(day_counts, list):
            day_counts = []
        rows.append(
            {
                "specialist": _text(item.get("specialist"), 255),
                "job_title": _text(item.get("job_title"), 255),
                "professional_status": _text(item.get("professional_status"), 255),
                "code": _text(item.get("code"), 100),
                "service_name": _text(item.get("service_name"), 500),
                "merge_without_code": _is_true(item.get("merge_without_code")),
                "rate_eur_per_day": _number(item.get("rate_eur_per_day")),
                "asset_day_counts": [
                    _number(day_counts[index]) if index < len(day_counts) else None
                    for index in range(asset_count)
                ],
                "total_eur_without_vat": _number(item.get("total_eur_without_vat")),
            }
        )
    return rows


def normalize_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("Данные для экспорта переданы в некорректном формате.")
    assets_raw = payload.get("assets")
    if not isinstance(assets_raw, list):
        assets_raw = []
    if len(assets_raw) > MAX_ASSETS:
        raise ValueError("Слишком много активов для экспорта.")
    assets = [_text(value, 255) or f"Актив {index + 1}" for index, value in enumerate(assets_raw)]
    if not assets:
        assets = ["Актив 1"]

    stages_raw = payload.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ValueError("Нет этапов для экспорта.")
    if len(stages_raw) > MAX_STAGES:
        raise ValueError("Слишком много этапов для экспорта.")

    stages = []
    for index, item in enumerate(stages_raw):
        if not isinstance(item, dict):
            raise ValueError("Этап передан в некорректном формате.")
        totals = item.get("totals") if isinstance(item.get("totals"), dict) else {}
        stages.append(
            {
                "label": _text(item.get("label"), 500) or f"Коммерческое предложение: Этап {index + 1}",
                "product_label": _text(item.get("product_label"), 255),
                "rows": _normalize_rows(item.get("rows"), len(assets)),
                "totals": {
                    "exchange_rate": _number(totals.get("exchange_rate")),
                    "discount_percent": _number(totals.get("discount_percent")),
                    "contract_total": _number(totals.get("contract_total")),
                    "contract_total_auto": _number(totals.get("contract_total_auto")),
                    "rub_total_service_text": _text(totals.get("rub_total_service_text"), 500),
                    "discounted_total_service_text": _text(totals.get("discounted_total_service_text"), 500),
                    "travel_expenses_mode": _text(totals.get("travel_expenses_mode"), 20) or "actual",
                },
            }
        )

    summary = None
    summary_raw = payload.get("summary")
    if len(stages) > 1 and not isinstance(summary_raw, dict):
        raise ValueError("Нет сводного блока коммерческого предложения.")
    if len(stages) > 1 and isinstance(summary_raw, dict):
        totals = summary_raw.get("totals") if isinstance(summary_raw.get("totals"), dict) else {}
        summary = {
            "label": _text(summary_raw.get("label"), 500) or "Коммерческое предложение: все этапы",
            "rows": _normalize_rows(summary_raw.get("rows"), len(assets)),
            "totals": {
                "exchange_rate": _number(totals.get("exchange_rate")),
                "discount_percent": _number(totals.get("discount_percent")),
                "contract_total": _number(totals.get("contract_total")),
                "contract_total_auto": _number(totals.get("contract_total_auto")),
                "rub_total_service_text": _text(totals.get("rub_total_service_text"), 500),
                "discounted_total_service_text": _text(totals.get("discounted_total_service_text"), 500),
                "travel_expenses_mode": _text(totals.get("travel_expenses_mode"), 20) or "actual",
            },
        }

    return {
        "proposal_label": _text(payload.get("proposal_label"), 255),
        "assets": assets,
        "stages": stages,
        "summary": summary,
    }


class CommercialWorkbookBuilder:
    def __init__(self, snapshot):
        self.snapshot = normalize_snapshot(snapshot)
        self.workbook = Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "Коммерческое предложение"
        self.row = 1
        self.stage_layouts = []
        self.thin_border = Border(
            left=Side(style="thin", color="000000"),
            right=Side(style="thin", color="000000"),
            top=Side(style="thin", color="000000"),
            bottom=Side(style="thin", color="000000"),
        )
        self.header_fill = PatternFill("solid", fgColor="E8EEF6")
        self.total_fill = PatternFill("solid", fgColor="F3F6FA")
        self.body_alignment = Alignment(wrap_text=False, vertical="center")
        self.direction_alignment = Alignment(wrap_text=False, vertical="center")
        self.header_right = Alignment(horizontal="right", vertical="center", wrap_text=True)
        self.header_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        self.header_direction = Alignment(horizontal="left", vertical="center", wrap_text=False)
        self.header_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.header_vertical = Alignment(vertical="center", wrap_text=True)
        self.day_alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
        self.center_alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
        self.day_cells = set()
        self.percent_cells = set()

    def _style_row(self, row, first_col, last_col, *, fill=None, bold=False, day_cols=None):
        for column in range(first_col, last_col + 1):
            cell = self.sheet.cell(row=row, column=column)
            cell.border = self.thin_border
            cell.alignment = self.direction_alignment if column == DIRECTION_COL else self.body_alignment
            if fill:
                cell.fill = fill
            if bold:
                cell.font = Font(bold=True)
        for column in day_cols or ():
            cell = self.sheet.cell(row=row, column=column)
            cell.alignment = self.day_alignment
            cell.number_format = DAY_COUNT_FORMAT
            self.day_cells.add((row, column))

    def _align_actual_travel_label(self, row, rate_col):
        cell = self.sheet.cell(row=row, column=rate_col)
        if cell.value == "по факту":
            cell.alignment = self.center_alignment

    def _write_blank_title_row(self):
        self.row += 1

    def _write_separator_row(self):
        self.sheet.row_dimensions[self.row].height = SEPARATOR_ROW_HEIGHT
        self.row += 1

    def _count_columns(self, columns):
        return [*columns["day_cols"], columns["total_days_col"]]

    def _apply_header_alignment(self, row, columns):
        centered = set(columns["day_cols"]) | {columns["total_days_col"]}
        right_aligned = {columns["rate_col"], columns["total_col"]}
        for column in range(1, columns["last_col"] + 1):
            cell = self.sheet.cell(row=row, column=column)
            if column in centered:
                cell.alignment = self.header_center
            elif column == DIRECTION_COL:
                cell.alignment = self.header_direction
            elif column == SPECIALIST_COL:
                cell.alignment = self.header_left
            elif column in right_aligned:
                cell.alignment = self.header_right
            else:
                cell.alignment = self.header_vertical

    def _write_headers(self, day_headers):
        headers = [
            "Специалист",
            "Должность/направление",
            "Специальность",
            "Профессиональный статус",
            "Код",
            "Услуги",
            "Ставка, евро / день",
            *day_headers,
            "Всего",
            "Итого, евро без НДС",
        ]
        for column, value in enumerate(headers, 1):
            self.sheet.cell(self.row, column, value)
        day_start = RATE_COL + 1
        day_cols = list(range(day_start, day_start + len(day_headers)))
        columns = {
            "direction_col": DIRECTION_COL,
            "service_col": SERVICE_COL,
            "rate_col": RATE_COL,
            "day_cols": day_cols,
            "total_days_col": day_start + len(day_headers),
            "total_col": day_start + len(day_headers) + 1,
            "last_col": len(headers),
        }
        self._style_row(self.row, 1, len(headers), fill=self.header_fill, bold=True, day_cols=self._count_columns(columns))
        self._apply_header_alignment(self.row, columns)
        self.row += 1
        return columns

    def _write_common_values(self, excel_row, row_data, *, service_in_direction=False):
        direction = row_data["service_name"] if service_in_direction else _direction_text(row_data)
        service_name = "" if service_in_direction else row_data["service_name"]
        values = [
            row_data["specialist"],
            direction,
            row_data["job_title"],
            row_data["professional_status"],
            row_data["code"],
            service_name,
            row_data["rate_eur_per_day"],
        ]
        for column, value in enumerate(values, 1):
            self.sheet.cell(excel_row, column, _excel_text(value) if column < RATE_COL else value)

    def _write_financial_rows(self, columns, totals, data_rows, travel_layout):
        total_col_letter = get_column_letter(columns["total_col"])
        day_letters = [get_column_letter(column) for column in columns["day_cols"]]
        data_excel_rows = [item["excel_row"] for item in data_rows]

        summary_row = self.row
        self.sheet.cell(summary_row, columns["direction_col"], "ИТОГО, по расчёту")
        for column, letter in zip(columns["day_cols"], day_letters):
            self.sheet.cell(summary_row, column, _formula_nonzero_sum(f"{letter}{r}" for r in data_excel_rows))
        day_range = f"{day_letters[0]}{summary_row}:{day_letters[-1]}{summary_row}"
        self.sheet.cell(summary_row, columns["total_days_col"], f'=IF(SUM({day_range})=0,"",SUM({day_range}))')
        total_refs = [f"{total_col_letter}{r}" for r in data_excel_rows]
        self.sheet.cell(summary_row, columns["total_col"], _formula_nonzero_sum(total_refs))
        self._style_row(summary_row, 1, columns["last_col"], day_cols=self._count_columns(columns))
        self.row += 1
        self._write_separator_row()

        with_travel_row = self.row
        self.sheet.cell(with_travel_row, columns["direction_col"], "ИТОГО, евро с командировочными по расчёту")
        self.sheet.cell(
            with_travel_row,
            columns["total_col"],
            f'=IF(SUM({total_col_letter}{summary_row},{total_col_letter}{travel_layout["excel_row"]})=0,"",'
            f'SUM({total_col_letter}{summary_row},{total_col_letter}{travel_layout["excel_row"]}))',
        )
        self._style_row(
            with_travel_row,
            1,
            columns["last_col"],
            fill=self.total_fill,
            bold=True,
            day_cols=self._count_columns(columns),
        )
        self.row += 1

        rub_row = self.row
        self.sheet.cell(rub_row, columns["direction_col"], RUB_TOTAL_LABEL)
        self.sheet.cell(rub_row, columns["rate_col"], totals["exchange_rate"])
        self.sheet.cell(
            rub_row,
            columns["total_col"],
            f'=IF(OR({total_col_letter}{with_travel_row}="",{get_column_letter(columns["rate_col"])}{rub_row}=""),"",'
            f'{total_col_letter}{with_travel_row}*{get_column_letter(columns["rate_col"])}{rub_row})',
        )
        self._style_row(rub_row, 1, columns["last_col"], fill=self.total_fill, bold=True, day_cols=self._count_columns(columns))
        self.row += 1

        discounted_row = self.row
        self.sheet.cell(discounted_row, columns["direction_col"], DISCOUNTED_TOTAL_LABEL)
        discount_percent = totals["discount_percent"] if totals["discount_percent"] is not None else 5
        discount_cell = self.sheet.cell(discounted_row, columns["rate_col"], discount_percent / 100)
        discount_cell.number_format = "0%"
        self.percent_cells.add((discounted_row, columns["rate_col"]))
        rate_letter = get_column_letter(columns["rate_col"])
        self.sheet.cell(
            discounted_row,
            columns["total_col"],
            f'=IF({total_col_letter}{rub_row}="","",{total_col_letter}{rub_row}*(1-{rate_letter}{discounted_row}))',
        )
        self._style_row(
            discounted_row,
            1,
            columns["last_col"],
            fill=self.total_fill,
            bold=True,
            day_cols=self._count_columns(columns),
        )
        self.row += 1

        contract_row = self.row
        self.sheet.cell(
            contract_row,
            columns["direction_col"],
            "ИТОГО в договор, рубли без НДС с учётом дополнительной скидки",
        )
        contract_total = totals["contract_total"]
        contract_auto = totals["contract_total_auto"]
        is_manual = contract_total is not None and (
            contract_auto is None or Decimal(str(contract_total)) != Decimal(str(contract_auto))
        )
        if is_manual:
            contract_value = contract_total
        else:
            contract_value = (
                f'=IF({total_col_letter}{discounted_row}="","",'
                f'ROUNDDOWN({total_col_letter}{discounted_row}/100000,0)*100000)'
            )
        self.sheet.cell(contract_row, columns["total_col"], contract_value)
        self._style_row(
            contract_row,
            1,
            columns["last_col"],
            fill=self.total_fill,
            bold=True,
            day_cols=self._count_columns(columns),
        )
        self.row += 1
        return {
            "summary_row": summary_row,
            "with_travel_row": with_travel_row,
            "rub_row": rub_row,
            "discounted_row": discounted_row,
            "contract_row": contract_row,
        }

    def _write_stage(self, stage, stage_index):
        assets = self.snapshot["assets"]
        self._write_blank_title_row()
        columns = self._write_headers(assets)
        data_rows = []
        travel_data = next((item for item in stage["rows"] if _is_travel(item)), None)

        for row_data in (item for item in stage["rows"] if not _is_travel(item)):
            excel_row = self.row
            self._write_common_values(excel_row, row_data)
            for column, value in zip(columns["day_cols"], row_data["asset_day_counts"]):
                self.sheet.cell(excel_row, column, value)
            day_start = get_column_letter(columns["day_cols"][0])
            day_end = get_column_letter(columns["day_cols"][-1])
            rate = get_column_letter(columns["rate_col"])
            day_total = get_column_letter(columns["total_days_col"])
            self.sheet.cell(excel_row, columns["total_days_col"], f'=IF(SUM({day_start}{excel_row}:{day_end}{excel_row})=0,"",SUM({day_start}{excel_row}:{day_end}{excel_row}))')
            self.sheet.cell(excel_row, columns["total_col"], f'=IF(OR({rate}{excel_row}="",{day_total}{excel_row}=""),"",{rate}{excel_row}*{day_total}{excel_row})')
            self._style_row(excel_row, 1, columns["last_col"], day_cols=self._count_columns(columns))
            data_rows.append({"data": row_data, "excel_row": excel_row})
            self.row += 1

        travel_data = travel_data or {
            "specialist": "",
            "job_title": "",
            "professional_status": "",
            "code": "",
            "service_name": "Командировочные расходы, евро",
            "rate_eur_per_day": None,
            "asset_day_counts": [None] * len(assets),
            "total_eur_without_vat": None,
        }
        self._write_separator_row()
        travel_row = self.row
        self._write_common_values(travel_row, travel_data, service_in_direction=True)
        mode = stage["totals"]["travel_expenses_mode"]
        if mode == "calculation":
            for column, value in zip(columns["day_cols"], travel_data["asset_day_counts"]):
                self.sheet.cell(travel_row, column, value)
            day_start = get_column_letter(columns["day_cols"][0])
            day_end = get_column_letter(columns["day_cols"][-1])
            sum_formula = f"SUM({day_start}{travel_row}:{day_end}{travel_row})"
            self.sheet.cell(travel_row, columns["total_days_col"], f'=IF({sum_formula}=0,"",{sum_formula})')
            self.sheet.cell(travel_row, columns["total_col"], f'=IF({sum_formula}=0,"",{sum_formula})')
        else:
            self.sheet.cell(travel_row, columns["rate_col"], "по факту")
            self.sheet.cell(travel_row, columns["total_col"], travel_data["total_eur_without_vat"])
        self._style_row(travel_row, 1, columns["last_col"], day_cols=self._count_columns(columns))
        self._align_actual_travel_label(travel_row, columns["rate_col"])
        self.row += 1
        self._write_separator_row()

        fixed_rows = self._write_financial_rows(
            columns,
            stage["totals"],
            data_rows,
            {"data": travel_data, "excel_row": travel_row},
        )
        layout = {
            "stage_index": stage_index,
            "columns": columns,
            "data_rows": data_rows,
            "travel": {"data": travel_data, "excel_row": travel_row},
            **fixed_rows,
        }
        self.stage_layouts.append(layout)
        self.row += 2

    def _summary_matches(self, summary_row):
        key = _group_key(summary_row)
        matches = []
        for layout in self.stage_layouts:
            for item in layout["data_rows"]:
                if _group_key(item["data"]) == key:
                    matches.append((layout, item))
        return matches

    def _write_summary(self, summary):
        assets = self.snapshot["assets"]
        day_specs = [
            (stage_index, asset_index)
            for stage_index in range(len(self.stage_layouts))
            for asset_index in range(len(assets))
        ]
        day_headers = []
        for stage_index, asset_index in day_specs:
            stage_label = self.snapshot["stages"][stage_index]["product_label"] or f"Этап {stage_index + 1}"
            day_headers.append(f"{stage_label}: {assets[asset_index]}")
        self._write_blank_title_row()
        columns = self._write_headers(day_headers)
        data_rows = []
        travel_data = next((item for item in summary["rows"] if _is_travel(item)), None)

        for row_data in (item for item in summary["rows"] if not _is_travel(item)):
            excel_row = self.row
            self._write_common_values(excel_row, row_data)
            matches = self._summary_matches(row_data)
            if matches:
                first_layout, first_item = matches[0]
                first_rate_cell = (
                    f'{get_column_letter(first_layout["columns"]["rate_col"])}{first_item["excel_row"]}'
                )
                self.sheet.cell(excel_row, columns["rate_col"], f"={first_rate_cell}")
            for target_column, (stage_index, asset_index) in zip(columns["day_cols"], day_specs):
                refs = []
                for layout, item in matches:
                    if layout["stage_index"] != stage_index:
                        continue
                    source_column = layout["columns"]["day_cols"][asset_index]
                    refs.append(f"{get_column_letter(source_column)}{item['excel_row']}")
                self.sheet.cell(excel_row, target_column, _formula_nonzero_sum(refs))
            first_day = get_column_letter(columns["day_cols"][0])
            last_day = get_column_letter(columns["day_cols"][-1])
            rate_col = get_column_letter(columns["rate_col"])
            total_days_col = get_column_letter(columns["total_days_col"])
            self.sheet.cell(excel_row, columns["total_days_col"], f'=IF(SUM({first_day}{excel_row}:{last_day}{excel_row})=0,"",SUM({first_day}{excel_row}:{last_day}{excel_row}))')
            self.sheet.cell(excel_row, columns["total_col"], f'=IF(OR({rate_col}{excel_row}="",{total_days_col}{excel_row}=""),"",{rate_col}{excel_row}*{total_days_col}{excel_row})')
            self._style_row(excel_row, 1, columns["last_col"], day_cols=self._count_columns(columns))
            data_rows.append({"data": row_data, "excel_row": excel_row})
            self.row += 1

        travel_data = travel_data or {
            "specialist": "",
            "job_title": "",
            "professional_status": "",
            "code": "",
            "service_name": "Командировочные расходы, евро",
            "rate_eur_per_day": None,
            "asset_day_counts": [None] * len(assets),
            "total_eur_without_vat": None,
        }
        self._write_separator_row()
        travel_row = self.row
        self._write_common_values(travel_row, travel_data, service_in_direction=True)
        travel_total_refs = []
        for target_column, (stage_index, asset_index) in zip(columns["day_cols"], day_specs):
            source_layout = self.stage_layouts[stage_index]
            source_day_column = source_layout["columns"]["day_cols"][asset_index]
            source_ref = f"{get_column_letter(source_day_column)}{source_layout['travel']['excel_row']}"
            if summary["totals"]["travel_expenses_mode"] == "calculation":
                self.sheet.cell(travel_row, target_column, f"={source_ref}")
            travel_total_refs.append(
                f'{get_column_letter(source_layout["columns"]["total_col"])}{source_layout["travel"]["excel_row"]}'
            )
        first_day = get_column_letter(columns["day_cols"][0])
        last_day = get_column_letter(columns["day_cols"][-1])
        if summary["totals"]["travel_expenses_mode"] == "calculation":
            self.sheet.cell(travel_row, columns["total_days_col"], f'=IF(SUM({first_day}{travel_row}:{last_day}{travel_row})=0,"",SUM({first_day}{travel_row}:{last_day}{travel_row}))')
        else:
            self.sheet.cell(travel_row, columns["rate_col"], "по факту")
        self.sheet.cell(travel_row, columns["total_col"], _formula_nonzero_sum(travel_total_refs))
        self._style_row(travel_row, 1, columns["last_col"], day_cols=self._count_columns(columns))
        self._align_actual_travel_label(travel_row, columns["rate_col"])
        self.row += 1
        self._write_separator_row()

        self._write_financial_rows(
            columns,
            summary["totals"],
            data_rows,
            {"data": travel_data, "excel_row": travel_row},
        )

    def _finish(self):
        self.sheet.freeze_panes = "A3"
        widths = {1: 20, 3: 24, 4: 24, 5: 12, 6: 28, 7: 20}
        for column, width in widths.items():
            self.sheet.column_dimensions[get_column_letter(column)].width = width
        self.sheet.column_dimensions[get_column_letter(DIRECTION_COL)].width = self._direction_column_width()
        for column in HIDDEN_SOURCE_COLUMNS:
            self.sheet.column_dimensions[get_column_letter(column)].hidden = True
        for column in range(RATE_COL + 1, self.sheet.max_column + 1):
            self.sheet.column_dimensions[get_column_letter(column)].width = 18
        for row in self.sheet.iter_rows():
            for cell in row:
                if (cell.row, cell.column) in self.day_cells or (cell.row, cell.column) in self.percent_cells:
                    continue
                if cell.column >= RATE_COL and (isinstance(cell.value, (int, float)) or (isinstance(cell.value, str) and cell.value.startswith("="))):
                    cell.number_format = '#,##0.00'
        self.sheet.auto_filter.ref = None
        self.workbook.calculation.calcMode = "auto"
        self.workbook.calculation.fullCalcOnLoad = True
        self.workbook.calculation.forceFullCalc = True

    def _direction_column_width(self):
        widest = _direction_text_width("Должность/направление", bold=True)
        for (cell,) in self.sheet.iter_rows(min_col=DIRECTION_COL, max_col=DIRECTION_COL):
            value = cell.value
            if not isinstance(value, str) or not value or value.startswith(("=", "'")):
                continue
            bold = bool(cell.font and cell.font.bold)
            for line in value.splitlines():
                widest = max(widest, _direction_text_width(line, bold=bold))
        return min(widest, 255)

    def build(self):
        for index, stage in enumerate(self.snapshot["stages"]):
            self._write_stage(stage, index)
        if self.snapshot["summary"]:
            self._write_summary(self.snapshot["summary"])
        self._finish()
        return self.workbook


def build_commercial_xlsx(snapshot):
    workbook = CommercialWorkbookBuilder(snapshot).build()
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


HEADER_SPECIALIST = "Специалист"
HEADER_DIRECTION = "Должность/направление"
HEADER_RATE = "Ставка, евро / день"
HEADER_TOTAL_DAYS = "Всего"
HEADER_TOTAL = "Итого, евро без НДС"
HEADER_SPECIALTY = "Специальность"
HEADER_STATUS = "Профессиональный статус"
HEADER_CODE = "Код"
HEADER_SERVICE = "Услуги"
ACTUAL_TRAVEL_LABEL = "по факту"
IMPORT_SHEET_TITLE = "Коммерческое предложение"


def _cell_text(cell):
    value = cell.value
    if value is None or (isinstance(value, str) and value.startswith("=")):
        return ""
    return _text(value)


def _plain_number(value, *, integer=False, places="0.0001"):
    if value is None or (isinstance(value, str) and (not str(value).strip() or str(value).startswith("="))):
        return ""
    if isinstance(value, str):
        number = _number(value)
        if number is None:
            return ""
        decimal_value = Decimal(str(number))
    elif isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, bool):
        return ""
    elif isinstance(value, (int, float)):
        decimal_value = Decimal(str(value))
    else:
        return ""
    if integer:
        return str(int(decimal_value.to_integral_value(rounding=ROUND_HALF_UP)))
    quantized = decimal_value.quantize(Decimal(places))
    text = format(quantized, "f").rstrip("0").rstrip(".")
    return text or "0"


def _split_direction(text):
    raw = _text(text)
    if not raw:
        return "", "", ""
    service = ""
    head = raw
    separator = "; " if "; " in raw else (";" if ";" in raw else "")
    if separator:
        head, service = raw.split(separator, 1)
        head = head.strip()
        service = service.strip()
    parts = [part.strip() for part in head.split(", ") if part.strip()]
    job_title = parts[0] if parts else ""
    status = ", ".join(parts[1:]) if len(parts) > 1 else ""
    return job_title, status, service


def _header_columns(sheet, header_row):
    labels = {}
    for column in range(1, (sheet.max_column or 0) + 1):
        label = _cell_text(sheet.cell(header_row, column))
        if label and label not in labels:
            labels[label] = column
    rate_col = labels.get(HEADER_RATE)
    total_days_col = labels.get(HEADER_TOTAL_DAYS)
    if not rate_col or not total_days_col or total_days_col <= rate_col + 1:
        raise ValueError("Не удалось прочитать заголовки таблицы коммерческого предложения.")
    day_cols = list(range(rate_col + 1, total_days_col))
    assets = [_cell_text(sheet.cell(header_row, column)) for column in day_cols]
    if not assets or any(not name for name in assets):
        raise ValueError("В таблице есть пустой заголовок актива.")
    return {
        "rate_col": rate_col,
        "day_cols": day_cols,
        "total_col": labels.get(HEADER_TOTAL, total_days_col + 1),
        "assets": assets,
        "specialty_col": labels.get(HEADER_SPECIALTY),
        "status_col": labels.get(HEADER_STATUS),
        "code_col": labels.get(HEADER_CODE),
        "service_col": labels.get(HEADER_SERVICE),
    }


def _row_has_values(sheet, row_index, columns):
    watched = [SPECIALIST_COL, DIRECTION_COL, columns["rate_col"], *columns["day_cols"]]
    for key in ("specialty_col", "status_col", "code_col", "service_col"):
        if columns.get(key):
            watched.append(columns[key])
    for column in watched:
        cell = sheet.cell(row_index, column)
        if _cell_text(cell) or _plain_number(cell.value):
            return True
    return False


def _specialist_row(sheet, row_index, columns):
    job_title = _cell_text(sheet.cell(row_index, columns["specialty_col"])) if columns.get("specialty_col") else ""
    status = _cell_text(sheet.cell(row_index, columns["status_col"])) if columns.get("status_col") else ""
    code = _cell_text(sheet.cell(row_index, columns["code_col"])) if columns.get("code_col") else ""
    service_name = _cell_text(sheet.cell(row_index, columns["service_col"])) if columns.get("service_col") else ""
    if not any((job_title, status, service_name)):
        parsed_title, parsed_status, parsed_service = _split_direction(_cell_text(sheet.cell(row_index, DIRECTION_COL)))
        job_title = job_title or parsed_title
        status = status or parsed_status
        service_name = service_name or parsed_service
    return {
        "specialist": _cell_text(sheet.cell(row_index, SPECIALIST_COL)),
        "job_title": job_title,
        "professional_status": status,
        "code": code,
        "service_name": service_name,
        "merge_without_code": False,
        "rate_eur_per_day": _plain_number(sheet.cell(row_index, columns["rate_col"]).value, places="0.01"),
        "asset_day_counts": [
            _plain_number(sheet.cell(row_index, column).value, integer=True)
            for column in columns["day_cols"]
        ],
    }


def _travel_row(sheet, row_index, columns):
    rate_cell = sheet.cell(row_index, columns["rate_col"])
    actual = _cell_text(rate_cell).casefold() == ACTUAL_TRAVEL_LABEL
    if actual:
        day_counts = [""] * len(columns["day_cols"])
        total = _plain_number(sheet.cell(row_index, columns["total_col"]).value, places="0.01")
        mode = "actual"
    else:
        day_counts = [
            _plain_number(sheet.cell(row_index, column).value, places="0.01")
            for column in columns["day_cols"]
        ]
        total = ""
        mode = "calculation"
    return {
        "row": {
            "specialist": "",
            "job_title": "",
            "professional_status": "",
            "code": "",
            "service_name": "Командировочные расходы, евро",
            "merge_without_code": False,
            "rate_eur_per_day": "",
            "asset_day_counts": day_counts,
            "total_eur_without_vat": total,
        },
        "travel_expenses_mode": mode,
    }


def _percent_points(cell):
    number = _plain_number(cell.value, places="0.0001")
    if not number:
        return ""
    if "%" in str(cell.number_format or ""):
        points = (Decimal(number) * Decimal("100")).quantize(Decimal("0.01"))
        return format(points, "f").rstrip("0").rstrip(".") or "0"
    return number


def _read_block(sheet, header_row, end_row):
    columns = _header_columns(sheet, header_row)
    rows = []
    travel = None
    rub_row = None
    discount_row = None
    contract_row = None
    for row_index in range(header_row + 1, end_row):
        direction = _cell_text(sheet.cell(row_index, DIRECTION_COL))
        service = _cell_text(sheet.cell(row_index, columns["service_col"])) if columns.get("service_col") else ""
        if direction in TRAVEL_LABELS or service in TRAVEL_LABELS:
            if travel is not None:
                raise ValueError("В блоке этапа несколько строк командировочных расходов.")
            travel = _travel_row(sheet, row_index, columns)
            continue
        if travel is None:
            if not _row_has_values(sheet, row_index, columns):
                continue
            rows.append(_specialist_row(sheet, row_index, columns))
            if len(rows) > MAX_ROWS_PER_BLOCK:
                raise ValueError("Слишком много строк коммерческого предложения.")
            continue
        if direction == RUB_TOTAL_LABEL:
            rub_row = row_index
        elif direction == DISCOUNTED_TOTAL_LABEL:
            discount_row = row_index
        elif direction.startswith("ИТОГО в договор"):
            contract_row = row_index
    if travel is None:
        raise ValueError("В блоке этапа нет строки командировочных расходов.")
    if rub_row is None or discount_row is None:
        raise ValueError("В блоке этапа нет обязательных итоговых строк.")
    contract_value = ""
    contract_manual = False
    if contract_row is not None:
        contract_cell = sheet.cell(contract_row, columns["total_col"])
        if not (isinstance(contract_cell.value, str) and contract_cell.value.startswith("=")):
            contract_value = _plain_number(contract_cell.value, places="0.01")
            contract_manual = bool(contract_value) and Decimal(contract_value) != 0
            if not contract_manual:
                contract_value = ""
    rows.append(travel["row"])
    return {
        "assets": columns["assets"],
        "rows": rows,
        "totals": {
            "exchange_rate": _plain_number(sheet.cell(rub_row, columns["rate_col"]).value, places="0.0001"),
            "discount_percent": _percent_points(sheet.cell(discount_row, columns["rate_col"])),
            "contract_total": contract_value if contract_manual else "",
            "contract_total_manual": contract_manual,
            "travel_expenses_mode": travel["travel_expenses_mode"],
        },
    }


def _commercial_sheet(workbook):
    if IMPORT_SHEET_TITLE in workbook.sheetnames:
        return workbook[IMPORT_SHEET_TITLE]
    return workbook.active


def parse_commercial_xlsx(content, *, assets, stage_count):
    if not isinstance(assets, list) or not assets:
        raise ValueError("Нет активов для загрузки.")
    if len(assets) > MAX_ASSETS:
        raise ValueError("Слишком много активов для загрузки.")
    expected_assets = [_text(value, 255) or f"Актив {index + 1}" for index, value in enumerate(assets)]
    try:
        stage_count = int(stage_count)
    except (TypeError, ValueError):
        raise ValueError("Нет этапов для загрузки.") from None
    if stage_count < 1:
        raise ValueError("Нет этапов для загрузки.")
    if stage_count > MAX_STAGES:
        raise ValueError("Слишком много этапов для загрузки.")

    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        workbook = load_workbook(io.BytesIO(content), data_only=False)
    except (InvalidFileException, OSError, ValueError, KeyError):
        raise ValueError("Не удалось прочитать файл Excel.") from None
    sheet = _commercial_sheet(workbook)
    if (sheet.max_row or 0) > 5000:
        raise ValueError("Файл коммерческого предложения слишком большой.")
    header_rows = [
        row_index
        for row_index in range(1, (sheet.max_row or 0) + 1)
        if _cell_text(sheet.cell(row_index, SPECIALIST_COL)) == HEADER_SPECIALIST
        and _cell_text(sheet.cell(row_index, DIRECTION_COL)) == HEADER_DIRECTION
    ]
    if not header_rows:
        raise ValueError("В файле нет таблицы коммерческого предложения.")
    blocks = []
    for index, header_row in enumerate(header_rows):
        end_row = header_rows[index + 1] if index + 1 < len(header_rows) else (sheet.max_row or header_row) + 1
        blocks.append(_read_block(sheet, header_row, end_row))
    if blocks and blocks[-1]["assets"] != expected_assets:
        blocks = blocks[:-1]
    if len(blocks) != stage_count:
        raise ValueError("Число этапов в файле не совпадает с проектом.")
    for block in blocks:
        if block["assets"] != expected_assets:
            raise ValueError("Заголовки активов в файле не совпадают с активами проекта.")
    return {
        "stages": [
            {
                "rows": block["rows"],
                "totals": block["totals"],
            }
            for block in blocks
        ]
    }
