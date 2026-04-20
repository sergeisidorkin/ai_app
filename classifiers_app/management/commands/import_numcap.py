import json
import re
import tempfile
from pathlib import Path
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from classifiers_app.models import NumcapRecord


NUMCAP_SOURCE_URLS = [
    "https://raw.githubusercontent.com/antirek/numcap/default/data/Kody_ABC-3kh.json",
    "https://raw.githubusercontent.com/antirek/numcap/default/data/Kody_ABC-4kh.json",
    "https://raw.githubusercontent.com/antirek/numcap/default/data/Kody_ABC-8kh.json",
    "https://raw.githubusercontent.com/antirek/numcap/default/data/Kody_DEF-9kh.json",
]
IMPORT_BATCH_SIZE = 5000
PROGRESS_EVERY = 10000
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_PROGRESS_STEP = 5 * 1024 * 1024


def _download_to_temp_file(url, stdout):
    downloaded = 0
    next_report_at = DOWNLOAD_PROGRESS_STEP
    with urlopen(url, timeout=60) as response:
        total_size = int(response.headers.get("Content-Length") or 0)
        with tempfile.NamedTemporaryFile(prefix="numcap_", suffix=".json", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                temp_file.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_report_at:
                    if total_size:
                        stdout.write(
                            f"  скачано: {downloaded / (1024 * 1024):.1f} MB из {total_size / (1024 * 1024):.1f} MB"
                        )
                    else:
                        stdout.write(f"  скачано: {downloaded / (1024 * 1024):.1f} MB")
                    stdout.flush()
                    next_report_at += DOWNLOAD_PROGRESS_STEP
    return temp_path


def _load_remote_records(url, stdout):
    stdout.write("  скачивание файла...")
    stdout.flush()
    temp_path = _download_to_temp_file(url, stdout)
    try:
        stdout.write("  парсинг JSON...")
        stdout.flush()
        with temp_path.open("r", encoding="utf-8") as temp_file:
            payload = json.load(temp_file)
    finally:
        temp_path.unlink(missing_ok=True)
    if not isinstance(payload, list):
        raise CommandError(f"Источник {url} вернул неожиданный формат данных.")
    return payload


def _extract_zone_codes(raw_code):
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


def _normalize_guillemets(value):
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


class Command(BaseCommand):
    help = "Загружает seed-данные numcap в классификатор numcap."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Полностью очистить таблицу numcap перед импортом.",
        )

    def handle(self, *args, **options):
        replace = options["replace"]
        if replace:
            with transaction.atomic():
                NumcapRecord.objects.all().delete()

        existing_keys = set(
            NumcapRecord.objects.values_list("code", "begin", "end", "operator", "region")
        )
        next_position = (NumcapRecord.objects.order_by("-position").values_list("position", flat=True).first() or 0) + 1
        created_count = 0
        skipped_count = 0
        processed_count = 0

        def flush_batch(batch):
            nonlocal created_count
            if not batch:
                return
            with transaction.atomic():
                NumcapRecord.objects.bulk_create(batch, batch_size=IMPORT_BATCH_SIZE)
            created_count += len(batch)
            batch.clear()

        for url in NUMCAP_SOURCE_URLS:
            self.stdout.write(f"Импорт: {url}")
            batch = []
            file_processed = 0
            file_created_before = created_count
            records = _load_remote_records(url, self.stdout)
            self.stdout.write(f"  записей в файле: {len(records)}")
            self.stdout.flush()
            for item in records:
                processed_count += 1
                file_processed += 1
                raw_code = str(item.get("code") or "").strip()
                begin = str(item.get("begin") or "").strip()
                end = str(item.get("end") or "").strip()
                operator = _normalize_guillemets(str(item.get("operator") or "").strip())
                region = str(item.get("region") or "").strip()
                capacity = str(item.get("capacity") or "").strip()
                zone_codes = _extract_zone_codes(raw_code)
                if not zone_codes or not begin or not end:
                    skipped_count += 1
                    continue
                for code in zone_codes:
                    dedupe_key = (code, begin, end, operator, region)
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
                            position=next_position,
                        )
                    )
                    existing_keys.add(dedupe_key)
                    next_position += 1
                    if len(batch) >= IMPORT_BATCH_SIZE:
                        flush_batch(batch)
                if processed_count % PROGRESS_EVERY == 0:
                    self.stdout.write(
                        f"  обработано строк: {processed_count}, добавлено записей: {created_count}, пропущено строк: {skipped_count}"
                    )
                    self.stdout.flush()
            flush_batch(batch)
            self.stdout.write(
                f"Готово: {url} | строк файла: {file_processed} | добавлено записей: {created_count - file_created_before}"
            )
            self.stdout.flush()

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт numcap завершён. Обработано строк: {processed_count}. "
                f"Добавлено записей: {created_count}. Пропущено исходных строк: {skipped_count}."
            )
        )
