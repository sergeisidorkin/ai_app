from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def grade_stars(performer):
    raw = getattr(performer, "grade", "") or ""
    if "/" in raw:
        parts = raw.split("/", 1)
        try:
            qual, levels = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return ""
    elif raw.isdigit():
        qual, levels = int(raw), 5
    else:
        return ""
    if levels <= 0:
        return ""
    filled = '<i class="bi bi-star-fill text-warning"></i>'
    empty = '<i class="bi bi-star-fill" style="color:#dee2e6;"></i>'
    return mark_safe("".join(filled if i < qual else empty for i in range(levels)))

@register.filter
def comma_decimal(value, precision=1):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    formatted = f"{number:.{int(precision)}f}"
    return formatted.replace(".", ",")


@register.filter
def money_fmt(value):
    """Format a number as financial: 1 234 567,89 (space-separated groups, comma decimal)."""
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if d < 0 else ""
    d = abs(d)
    integer_part = int(d)
    frac = f"{d - integer_part:.2f}"[1:]  # ".XX"
    int_str = f"{integer_part:,}".replace(",", "\u00a0")
    return f"{sign}{int_str}{frac}".replace(".", ",")


@register.filter
def short_fio(value):
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""

    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


@register.filter
def short_fio_no_dots(value):
    """Фамилия ИО (without dots after initials)."""
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    parts = raw.split(" ")
    last_name = parts[0]
    initials = "".join(part[0] for part in parts[1:3] if part)
    return f"{last_name} {initials}".strip()


@register.filter
def typical_section_short(section):
    if not section:
        return ""
    code = getattr(section, "code", "") or ""
    short_name_ru = getattr(section, "short_name_ru", "") or ""
    return " ".join(part for part in (code, short_name_ru) if part).strip()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


@register.filter
def disk_folder_url(path):
    """Convert Yandex.Disk API path (disk:/…) to a web-client URL."""
    if not path:
        return ""
    from urllib.parse import quote
    clean = path.removeprefix("disk:")
    return "https://disk.yandex.ru/client/disk" + quote(clean)