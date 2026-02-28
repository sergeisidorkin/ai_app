from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import EmployeeForm
from .models import Employee

PARTIAL_TEMPLATE = "users_app/users_partial.html"
FORM_TEMPLATE = "users_app/employee_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "users-updated"


def staff_required(u):
    return u.is_active and u.is_staff


def _users_context():
    return {"employees": Employee.objects.select_related("user").all()}


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _users_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_position():
    mx = Employee.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _normalize_positions():
    for idx, obj in enumerate(Employee.objects.all()):
        if obj.position != idx:
            Employee.objects.filter(pk=obj.pk).update(position=idx)


@login_required
@require_http_methods(["GET"])
def users_partial(request):
    return render(request, PARTIAL_TEMPLATE, _users_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def employee_form_create(request):
    if request.method == "GET":
        form = EmployeeForm()
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    form = EmployeeForm(request.POST)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    emp = form.save()
    emp.position = _next_position()
    emp.save(update_fields=["position"])
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def employee_form_edit(request, pk: int):
    employee = get_object_or_404(Employee.objects.select_related("user"), pk=pk)
    if request.method == "GET":
        form = EmployeeForm(instance=employee)
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "employee": employee})
    form = EmployeeForm(request.POST, instance=employee)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "employee": employee})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_delete(request, pk: int):
    emp = get_object_or_404(Employee, pk=pk)
    emp.user.delete()
    _normalize_positions()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_move_up(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk)
    prev = Employee.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_move_down(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk)
    nxt = Employee.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)
