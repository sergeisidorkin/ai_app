import re
from django import template
from django.utils.safestring import mark_safe
from django.contrib.staticfiles import finders

register = template.Library()

@register.simple_tag
def svg_icon(name: str, cls: str = ""):
    """
    Вставляет SVG из static/core/icons/<name>.svg инлайном.
    Позволяет добавить CSS-класс к <svg>.
    """
    path = finders.find(f"core/icons/{name}.svg")
    if not path:
        return ""  # тихо игнорируем, чтобы не падать в шаблоне
    try:
        with open(path, "r", encoding="utf-8") as f:
            svg = f.read()
        if cls:
            # вставляем class в первый <svg ...>
            svg = re.sub(r"<svg\b", f'<svg class="{cls}"', svg, count=1)
        return mark_safe(svg)
    except Exception:
        return ""