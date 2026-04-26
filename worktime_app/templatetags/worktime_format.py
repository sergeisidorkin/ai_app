from decimal import Decimal, ROUND_HALF_UP

from django import template

register = template.Library()


def _coerce_decimal(value):
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return None


def _format_hours_value(value, *, decimal_separator=","):
    if value in (None, ""):
        return ""
    decimal_value = _coerce_decimal(value)
    if decimal_value is None:
        return value
    rounded_value = decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = format(rounded_value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return (text or "0").replace(".", decimal_separator)


@register.filter
def worktime_hours(value):
    return _format_hours_value(value, decimal_separator=",")


@register.filter
def worktime_hours_input(value):
    return _format_hours_value(value, decimal_separator=".")
