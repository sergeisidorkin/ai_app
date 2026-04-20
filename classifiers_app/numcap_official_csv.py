import csv
import io
import re
from pathlib import Path

from django.db import transaction

from .models import NumcapRecord


DEFAULT_FILENAMES = [
    "ABC-3xx.csv",
    "ABC-4xx.csv",
    "ABC-8xx.csv",
    "DEF-9xx.csv",
]
EXPECTED_FIELDS = {"АВС/ DEF", "От", "До", "Емкость", "Оператор", "Регион"}


def normalize_guillemets(value):
    text = value or ""
    if '"' not in text:
        return text
    out = []
    for char in text:
        if char == '"':
            prev = out[-1] if out else ""
            out.append("\u00AB" if (not prev or re.match(r"[\s(\[{\u00AB]", prev)) else "\u00BB")
        else:
            out.append(char)
    return "".join(out)


def extract_zone_codes(raw_code):
    value = str(raw_code or "").strip()
    if not value:
        return []
    tokens = []
    seen = set()
    for token in re.findall(r"\d{3,5}", value):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    if tokens:
        return tokens
    compact = re.sub(r"\D+", "", value)
    if 3 <= len(compact) <= 5:
        return [compact]
    return []


def _reader_for_source(source):
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve()
        fh = path.open("r", encoding="utf-8-sig", newline="")
        return csv.DictReader(fh, delimiter=";"), fh, path.name
    raw = source.read()
    if hasattr(source, "seek"):
        source.seek(0)
    text = raw.decode("utf-8-sig")
    fh = io.StringIO(text)
    name = Path(getattr(source, "name", "uploaded.csv")).name
    return csv.DictReader(fh, delimiter=";"), fh, name


def process_numcap_official_sources(
    sources,
    *,
    replace=False,
    batch_size=5000,
    progress_every=10000,
    report=None,
):
    if replace:
        with transaction.atomic():
            NumcapRecord.objects.all().delete()

    existing_keys = set(
        NumcapRecord.objects.values_list("code", "begin", "end", "operator", "region", "gar_territory", "inn")
    )
    next_position = (NumcapRecord.objects.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    processed_count = 0
    created_count = 0
    skipped_count = 0
    file_summaries = []

    def emit(message):
        if report:
            report(message)

    def flush_batch(batch):
        nonlocal created_count
        if not batch:
            return
        with transaction.atomic():
            NumcapRecord.objects.bulk_create(batch, batch_size=batch_size)
        created_count += len(batch)
        batch.clear()

    for source in sources:
        reader, fh, display_name = _reader_for_source(source)
        emit(f"Импорт CSV: {display_name}")
        file_processed = 0
        file_created_before = created_count
        batch = []
        try:
            if not reader.fieldnames or not EXPECTED_FIELDS.issubset(set(reader.fieldnames)):
                raise ValueError(f"Файл {display_name} имеет неожиданный заголовок: {reader.fieldnames!r}")
            for row in reader:
                processed_count += 1
                file_processed += 1
                raw_code = str(row.get("АВС/ DEF") or "").strip()
                begin = str(row.get("От") or "").strip()
                end = str(row.get("До") or "").strip()
                capacity = str(row.get("Емкость") or "").strip()
                operator = normalize_guillemets(str(row.get("Оператор") or "").strip())
                region = str(row.get("Регион") or "").strip()
                gar_territory = str(row.get("Территория ГАР") or "").strip()
                inn = str(row.get("ИНН") or "").strip()
                zone_codes = extract_zone_codes(raw_code)
                if not zone_codes or not begin or not end:
                    skipped_count += 1
                    continue
                for code in zone_codes:
                    dedupe_key = (code, begin, end, operator, region, gar_territory, inn)
                    if dedupe_key in existing_keys:
                        continue
                    batch.append(
                        NumcapRecord(
                            code=code,
                            begin=begin,
                            end=end,
                            capacity=capacity,
                            operator=operator,
                            region=region,
                            gar_territory=gar_territory,
                            inn=inn,
                            position=next_position,
                        )
                    )
                    existing_keys.add(dedupe_key)
                    next_position += 1
                    if len(batch) >= batch_size:
                        flush_batch(batch)
                if progress_every and processed_count % progress_every == 0:
                    emit(
                        f"  обработано строк: {processed_count}, добавлено записей: {created_count}, пропущено строк: {skipped_count}"
                    )
        finally:
            fh.close()
        flush_batch(batch)
        file_created = created_count - file_created_before
        file_summaries.append({"name": display_name, "processed": file_processed, "created": file_created})
        emit(f"Готово: {display_name} | строк файла: {file_processed} | добавлено записей: {file_created}")

    return {
        "processed": processed_count,
        "created": created_count,
        "skipped": skipped_count,
        "files": file_summaries,
    }
