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