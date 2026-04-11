from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from projects_app.models import Performer

from .forms import WorktimeEditForm

WORKTIME_PARTIAL_TEMPLATE = "worktime_app/worktime_partial.html"
WORKTIME_FORM_TEMPLATE = "worktime_app/worktime_timesheet_form.html"


def staff_required(user):
    return user.is_staff


def _worktime_queryset(user, personal_only=False):
    items = (
        Performer.objects
        .select_related("registration", "registration__type", "employee", "employee__user")
        .order_by("registration__number", "registration__id", "position", "id")
    )
    if personal_only:
        filters = Q(employee__user=user)
        employee = getattr(user, "employee_profile", None)
        employee_name = Performer.employee_full_name(employee)
        if employee_name:
            filters |= Q(employee__isnull=True, executor=employee_name)
        items = items.filter(filters)
    return items


def _worktime_context(user, personal_only=False):
    return {
        "items": _worktime_queryset(user, personal_only=personal_only),
        "show_executor_column": not personal_only,
    }


@login_required
@require_http_methods(["GET"])
def worktime_partial(request):
    return render(request, WORKTIME_PARTIAL_TEMPLATE, _worktime_context(request.user))


@login_required
@require_http_methods(["GET"])
def personal_worktime_partial(request):
    return render(
        request,
        WORKTIME_PARTIAL_TEMPLATE,
        _worktime_context(request.user, personal_only=True),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def worktime_form_edit(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related("registration", "registration__type"),
        pk=pk,
    )
    if request.method == "POST":
        form = WorktimeEditForm(request.POST, instance=performer)
        if form.is_valid():
            form.save()
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "worktime-updated"
            return response
    else:
        form = WorktimeEditForm(instance=performer)

    return render(
        request,
        WORKTIME_FORM_TEMPLATE,
        {
            "form": form,
            "performer": performer,
        },
    )
