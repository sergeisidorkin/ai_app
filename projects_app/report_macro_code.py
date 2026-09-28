"""Сборка и разбор кода макроса или навыка: КУРС-СЕКЦИЯ-РАЗДЕЛ.НОМЕР."""

from __future__ import annotations

import re

TITLE_RE = re.compile(r"^([A-Z]{4})-([A-Z]{2})-(\d{2})\.(\d{2})(?:\s+(.*))?$")
COURSE_RE = re.compile(r"^[A-Z]{4}$")
SECTION_RE = re.compile(r"^[A-Z]{2}$")
PART_RE = re.compile(r"^\d{2}$")

# Первый в каталоге оставляет .00, следующие получают свободный номер.
DUPLICATE_NUMBERS = {
    "TMPL-SS-00.00 Сноски без угловых скобок": "01",
    "TMPL-SS-00.00 Табуляция после «Источник:»": "02",
    "DOCX-SS-00.00 Ссылка на ближайший объект": "01",
    "TMPL-SN-00.00 Скобки NextCloud-сноски": "01",
    "TMPL-SN-00.00 Пробел перед сноской в скобках": "02",
}


def format_macro_code(course: str, section: str, part: str, number: str) -> str:
    course = (course or "").strip()
    section = (section or "").strip()
    part = (part or "").strip()
    number = (number or "").strip()
    if not (course and section and part and number):
        return ""
    return f"{course}-{section}-{part}.{number}"


def format_macro_label(course: str, section: str, part: str, number: str, name: str) -> str:
    code = format_macro_code(course, section, part, number)
    title = (name or "").strip()
    if code and title:
        return f"{code} {title}"
    return title or code


def split_catalog_title(title: str) -> tuple[str, str, str, str, str] | None:
    raw = (title or "").strip()
    match = TITLE_RE.match(raw)
    if not match:
        return None
    course, section, part, number, name = match.groups()
    number = DUPLICATE_NUMBERS.get(raw, number)
    return course, section, part, number, (name or "").strip()


def code_parts_are_valid(course: str, section: str, part: str, number: str) -> bool:
    return bool(
        COURSE_RE.fullmatch(course or "")
        and SECTION_RE.fullmatch(section or "")
        and PART_RE.fullmatch(part or "")
        and PART_RE.fullmatch(number or "")
    )


def allocate_number(course: str, section: str, part: str, preferred: str, used: set[str]) -> str:
    preferred = preferred if PART_RE.fullmatch(preferred or "") else "00"
    key = format_macro_code(course, section, part, preferred)
    if key not in used:
        used.add(key)
        return preferred
    for index in range(100):
        candidate = f"{index:02d}"
        key = format_macro_code(course, section, part, candidate)
        if key not in used:
            used.add(key)
            return candidate
    raise ValueError(f"Нет свободного номера для {course}-{section}-{part}.")
