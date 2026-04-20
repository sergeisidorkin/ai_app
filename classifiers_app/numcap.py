import re
from dataclasses import dataclass

from .models import NumcapRecord


PHONE_CODE_LENGTHS = (5, 4, 3)
SUBSCRIBER_PATTERNS = {
    7: (3, 2, 2),
    6: (2, 2, 2),
    5: (1, 2, 2),
}


@dataclass(frozen=True)
class NumcapLookupResult:
    digits: str = ""
    area_code: str = ""
    subscriber_digits: str = ""
    subscriber_length: int = 0
    region: str = ""
    operator: str = ""
    formatted_number: str = ""
    unique: bool = False
    exact: bool = False
    match_count: int = 0


def _display_region(value):
    return str(value or "").replace("|", ", ").strip(" ,")


def normalize_ru_landline_digits(raw_value):
    digits = re.sub(r"\D+", "", str(raw_value or ""))
    if len(digits) > 10 and digits[:1] in {"7", "8"}:
        digits = digits[1:]
    return digits


def _subscriber_length(record):
    return max(len(str(record.begin or "").strip()), len(str(record.end or "").strip()))


def _common_subscriber_length(records):
    lengths = {_subscriber_length(record) for record in records}
    return lengths.pop() if len(lengths) == 1 else 0


def _normalize_range_value(value, width):
    return str(value or "").strip().zfill(width)


def _record_matches_prefix(record, subscriber_prefix):
    prefix = str(subscriber_prefix or "").strip()
    width = _subscriber_length(record)
    if len(prefix) > width:
        return False
    begin = _normalize_range_value(record.begin, width)
    end = _normalize_range_value(record.end, width)
    if not prefix:
        return True
    lower_bound = prefix.ljust(width, "0")
    upper_bound = prefix.ljust(width, "9")
    return not (upper_bound < begin or lower_bound > end)


def _record_matches_exact(record, subscriber_digits):
    digits = str(subscriber_digits or "").strip()
    width = _subscriber_length(record)
    if len(digits) != width:
        return False
    normalized = digits.zfill(width)
    begin = _normalize_range_value(record.begin, width)
    end = _normalize_range_value(record.end, width)
    return begin <= normalized <= end


def _format_subscriber_digits(subscriber_digits, expected_length):
    digits = re.sub(r"\D+", "", str(subscriber_digits or ""))[:expected_length]
    if not digits:
        return ""
    groups = SUBSCRIBER_PATTERNS.get(expected_length)
    if not groups:
        return digits
    parts = []
    cursor = 0
    for size in groups:
        chunk = digits[cursor:cursor + size]
        if not chunk:
            break
        parts.append(chunk)
        cursor += size
    return "-".join(parts)


def format_ru_landline_number(area_code, subscriber_digits, subscriber_length):
    code = re.sub(r"\D+", "", str(area_code or ""))
    if not code:
        return re.sub(r"\D+", "", str(subscriber_digits or ""))
    subscriber = _format_subscriber_digits(subscriber_digits, subscriber_length)
    return f"({code}) {subscriber}".rstrip()


def lookup_ru_landline(raw_value):
    digits = normalize_ru_landline_digits(raw_value)
    if not digits:
        return NumcapLookupResult()

    prefixes = {
        code_length: digits[:code_length]
        for code_length in PHONE_CODE_LENGTHS
        if len(digits) > code_length
    }
    if not prefixes:
        return NumcapLookupResult(digits=digits)

    records_by_code = {}
    queryset = NumcapRecord.objects.filter(code__in=list(prefixes.values())).order_by("position", "id")
    for record in queryset:
        records_by_code.setdefault(record.code, []).append(record)

    for code_length in PHONE_CODE_LENGTHS:
        area_code = prefixes.get(code_length, "")
        if not area_code:
            continue
        subscriber_digits = digits[code_length:]
        candidates = [
            record
            for record in records_by_code.get(area_code, [])
            if _record_matches_prefix(record, subscriber_digits)
        ]
        if not candidates:
            continue

        unique = len(candidates) == 1
        record = candidates[0] if unique else None
        subscriber_length = _subscriber_length(record) if record is not None else _common_subscriber_length(candidates)
        if not subscriber_length:
            subscriber_length = 10 - code_length
        exact = bool(record and _record_matches_exact(record, subscriber_digits))
        formatted_number = format_ru_landline_number(area_code, subscriber_digits, subscriber_length)
        return NumcapLookupResult(
            digits=digits,
            area_code=area_code,
            subscriber_digits=subscriber_digits,
            subscriber_length=subscriber_length,
            region=_display_region(record.region) if exact else "",
            operator=record.operator if exact else "",
            formatted_number=formatted_number,
            unique=unique,
            exact=exact,
            match_count=len(candidates),
        )

    return NumcapLookupResult(digits=digits)
