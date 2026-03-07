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
        qs = Product.objects.only("id", "name_en", "display_name", "short_name", "position").order_by("position", "id")
    except Exception:
        qs = Product.objects.none()
    return {"TEMPLATES_PRODUCTS": qs}

def templates_sections_map(request):
    """
    Карта: short_name продукта -> список разделов
    Используется для построения вкладок в разделах «Шаблоны» и «Запросы».
    """
    try:
        sections = (
            TypicalSection.objects.select_related("product")
            .only("id", "name_ru", "short_name_ru", "position", "product__short_name")
            .order_by("product__short_name", "position", "id")
        )
        mapping = {}
        for s in sections:
            key = (getattr(s.product, "short_name", "") or "").strip().upper()
            if not key:
                continue
            mapping.setdefault(key, []).append({
                "id": s.id,
                "name_ru": s.name_ru,
                "short_name_ru": s.short_name_ru or s.name_ru,
            })
    except Exception:
        mapping = {}
    return {"TEMPLATES_SECTIONS_MAP": mapping}


def notifications_counters(request):
    if not getattr(request.user, "is_authenticated", False):
        return {
            "NOTIFICATION_TOTAL_COUNT": 0,
            "NOTIFICATION_SECTION_COUNTS": {},
        }

    try:
        from notifications_app.services import build_notification_counters

        counters = build_notification_counters(request.user)
    except Exception:
        counters = {"total": 0, "sections": {}}

    return {
        "NOTIFICATION_TOTAL_COUNT": counters.get("total", 0),
        "NOTIFICATION_SECTION_COUNTS": counters.get("sections", {}),
    }
