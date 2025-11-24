from typing import Optional
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.http import require_GET

from projects_app.models import Performer, ProjectRegistration


@require_GET
def project_meta(request, pk: int):
    """
    API: вернуть assets/sections для выбранной регистрации проекта.
    """
    asset = (request.GET.get("asset") or "").strip() or None
    return JsonResponse(_project_meta(pk, asset))


def _product_short_label(product) -> str:
    """
    Возвращает короткое имя типа продукта (DD/BB и т.п.), если есть.
    Пытаемся по разным полям, затем str(product).
    """
    if not product:
        return ""
    for attr in ("short_name", "short", "code", "name_en", "name"):
        try:
            val = getattr(product, attr)
            if val:
                return str(val)
        except Exception:
            continue
    return str(product)


def _format_project_label(reg: ProjectRegistration) -> str:
    """
    Отображение проекта: "44441RU DD Название".
    Приоритет: short_uid → number+group. Остальные поля через пробел.
    """
    def s(v):
        try:
            return str(v).strip()
        except Exception:
            return ""

    uid = s(getattr(reg, "short_uid", ""))
    if not uid:
        num = s(getattr(reg, "number", ""))
        grp = s(getattr(reg, "group", ""))
        uid = f"{num}{grp}".strip()

    typ = s(_product_short_label(getattr(reg, "type", None)))
    name = s(getattr(reg, "name", ""))

    tail = " ".join(x for x in (typ, name) if x).strip()
    return f"{uid} {tail}".strip()

def _project_meta(registration_id: int, asset_name: Optional[str] = None) -> dict:
    """
    Возвращает:
      - assets: список всех уникальных непустых 'asset_name' (в порядке position,id)
      - asset: выбранный актив (asset_name) — либо из параметра, либо первый из списка
      - sections: список типовых разделов для выбранного актива
    """
    qs = (
        Performer.objects
        .filter(registration_id=registration_id)
        .exclude(asset_name="")
        .select_related("typical_section")
        .order_by("position", "id")
    )

    # уникальные активы (в порядке появления)
    assets, seen = [], set()
    for p in qs:
        a = (p.asset_name or "").strip()
        if a and a not in seen:
            seen.add(a)
            assets.append(a)

    selected_asset = asset_name if (asset_name and asset_name in seen) else (assets[0] if assets else "")

    # типовые разделы для выбранного актива
    sections = []
    if selected_asset:
        sec_seen = set()
        for p in qs:
            if (p.asset_name or "").strip() != selected_asset:
                continue
            ts = getattr(p, "typical_section", None)
            if ts and ts.id not in sec_seen:
                sec_seen.add(ts.id)
                sections.append({"id": ts.id, "name": str(ts)})

    return {"assets": assets, "asset": selected_asset, "sections": sections}

def panel(request):
    """
    Рендер панели отладки.
    Возвращает данные для селекторов и URL для загрузки карточек блоков.
    """
    regs = list(ProjectRegistration.objects.select_related("type").order_by("position", "id"))

    def _s(v):
        try:
            return str(v).strip()
        except Exception:
            return ""

    project_options = []
    for r in regs:
        short_uid = _s(getattr(r, "short_uid", ""))
        if not short_uid:
            number = _s(getattr(r, "number", ""))
            group = _s(getattr(r, "group", ""))
            short_uid = f"{number}{group}".upper()

        project_options.append({
            "id": r.id,
            "label": _format_project_label(r),
            "short_uid": short_uid,
            "product_short": _product_short_label(getattr(r, "type", None)),
            "product_id": getattr(getattr(r, "type", None), "id", None),
        })

    selected_project_id = project_options[0]["id"] if project_options else None
    meta = _project_meta(selected_project_id) if selected_project_id else {"assets": [], "asset": "", "sections": []}

    try:
        blocks_dashboard_url = reverse("blocks_app:dashboard_partial")
    except NoReverseMatch:
        blocks_dashboard_url = "/blocks/"

    return render(request, "debugger_app/panel.html", {
        "project_options": project_options,
        "selected_project_id": selected_project_id,
        "asset_options": meta["assets"],
        "selected_asset": meta["asset"],
        "section_options": meta["sections"],
        "blocks_dashboard_url": blocks_dashboard_url,
    })