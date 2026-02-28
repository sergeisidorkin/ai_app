from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import GroupMemberForm
from .models import GroupMember

PARTIAL_TEMPLATE = "group_app/group_partial.html"
TABLE_TEMPLATE = "group_app/group_table_partial.html"
FORM_TEMPLATE = "group_app/member_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "group-updated"


def staff_required(u):
    return u.is_active and u.is_staff


def _group_context():
    return {"members": GroupMember.objects.all()}


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _group_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_position():
    mx = GroupMember.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _normalize_positions():
    for idx, obj in enumerate(GroupMember.objects.all()):
        if obj.position != idx:
            GroupMember.objects.filter(pk=obj.pk).update(position=idx)


# ---------------------------------------------------------------------------
#  Partials
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def group_partial(request):
    return render(request, PARTIAL_TEMPLATE, _group_context())


# ---------------------------------------------------------------------------
#  CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def member_form_create(request):
    if request.method == "GET":
        form = GroupMemberForm()
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    form = GroupMemberForm(request.POST)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    obj.position = _next_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def member_form_edit(request, pk: int):
    member = get_object_or_404(GroupMember, pk=pk)
    if request.method == "GET":
        form = GroupMemberForm(instance=member)
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "member": member})
    form = GroupMemberForm(request.POST, instance=member)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "member": member})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def member_delete(request, pk: int):
    get_object_or_404(GroupMember, pk=pk).delete()
    _normalize_positions()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  Move
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_POST
def member_move_up(request, pk: int):
    obj = get_object_or_404(GroupMember, pk=pk)
    prev = GroupMember.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        GroupMember.objects.filter(pk=obj.pk).update(position=obj.position)
        GroupMember.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def member_move_down(request, pk: int):
    obj = get_object_or_404(GroupMember, pk=pk)
    nxt = GroupMember.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        GroupMember.objects.filter(pk=obj.pk).update(position=obj.position)
        GroupMember.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)
