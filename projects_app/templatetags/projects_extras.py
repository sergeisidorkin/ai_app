from django import template

register = template.Library()

@register.filter
def comma_decimal(value, precision=1):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    formatted = f"{number:.{int(precision)}f}"
    return formatted.replace(".", ",")


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
def typical_section_short(section):
    if not section:
        return ""
    code = getattr(section, "code", "") or ""
    short_name_ru = getattr(section, "short_name_ru", "") or ""
    return " ".join(part for part in (code, short_name_ru) if part).strip()