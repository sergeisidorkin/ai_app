from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Max
from .models import OKSMCountry
from .forms import OKSMCountryForm

PARTIAL_TEMPLATE = "classifiers_app/classifiers_partial.html"
FORM_TEMPLATE = "classifiers_app/oksm_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "classifiers-updated"


def staff_required(user):
    return user.is_authenticated and user.is_staff


def _classifiers_context():
    return {"oksm_countries": OKSMCountry.objects.all()}


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _classifiers_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_position():
    last = OKSMCountry.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


@login_required
@require_http_methods(["GET"])
def classifiers_partial(request):
    return render(request, PARTIAL_TEMPLATE, _classifiers_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def oksm_form_create(request):
    if request.method == "GET":
        form = OKSMCountryForm()
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    form = OKSMCountryForm(request.POST)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def oksm_form_edit(request, pk: int):
    country = get_object_or_404(OKSMCountry, pk=pk)
    if request.method == "GET":
        form = OKSMCountryForm(instance=country)
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "country": country})
    form = OKSMCountryForm(request.POST, instance=country)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "country": country})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def oksm_delete(request, pk: int):
    country = get_object_or_404(OKSMCountry, pk=pk)
    country.delete()
    return _render_updated(request)


def _normalize_positions():
    items = OKSMCountry.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            OKSMCountry.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def oksm_move_up(request, pk: int):
    _normalize_positions()
    items = list(OKSMCountry.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        OKSMCountry.objects.filter(pk=cur.id).update(position=prev_pos)
        OKSMCountry.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_positions()
    return _render_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def oksm_move_down(request, pk: int):
    _normalize_positions()
    items = list(OKSMCountry.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        OKSMCountry.objects.filter(pk=cur.id).update(position=next_pos)
        OKSMCountry.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_positions()
    return _render_updated(request)
