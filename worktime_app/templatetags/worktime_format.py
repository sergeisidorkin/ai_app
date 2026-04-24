from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def worktime_hours(value):
    if value in (None, ""):
        return ""
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return value

    text = format(decimal_value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return (text or "0").replace(".", ",")
