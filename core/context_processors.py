from django.urls import reverse, NoReverseMatch
from .navigation import NAV_ITEMS

def nav_items(request):
    items = []
    path = request.path
    for raw in NAV_ITEMS:
        item = raw.copy()
        try:
            url = reverse(item["url_name"])
        except NoReverseMatch:
            # если урл пока не объявлен — пропускаем
            continue
        item["url"] = url
        item["active"] = path.startswith(url)
        items.append(item)
    return {"NAV_ITEMS": items}

# Добавляем продукты для второго сайдбара раздела "Шаблоны"
from policy_app.models import Product  # безопасный импорт модели
from policy_app.models import TypicalSection

def templates_products(request):
    try:
        qs = Product.objects.only("id", "name_en", "short_name", "position").order_by("position", "id")
    except Exception:
        qs = Product.objects.none()
    return {"TEMPLATES_PRODUCTS": qs}

def templates_sections_map(request):
    """
    Карта: short_name продукта -> список названий разделов (name_ru)
    Используется для построения вкладок в разделе «Шаблоны».
    """
    try:
        sections = (
            TypicalSection.objects.select_related("product")
            .only("id", "name_ru", "product__short_name")
            .order_by("name_ru")
        )
        mapping = {}
        for s in sections:
            key = (getattr(s.product, "short_name", "") or "").strip().upper()
            if not key:
                continue
            mapping.setdefault(key, []).append({"id": s.id, "name_ru": s.name_ru})
    except Exception:
        mapping = {}
    return {"TEMPLATES_SECTIONS_MAP": mapping}
