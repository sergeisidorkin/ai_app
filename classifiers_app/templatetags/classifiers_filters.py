from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def format_money(value):
    """Format Decimal as '000 000,00' (space as thousands separator, comma as decimal)."""
    try:
        d = Decimal(str(value))
    except Exception:
        return value
    sign = "-" if d < 0 else ""
    d = abs(d)
    integer_part = int(d)
    decimal_part = f"{d - integer_part:.2f}"[2:]
    int_str = f"{integer_part:,}".replace(",", "\u00a0")
    return f"{sign}{int_str},{decimal_part}"
