from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from projects_app.models import Performer

from .forms import WorktimeEditForm

WORKTIME_PARTIAL_TEMPLATE = "worktime_app/worktime_partial.html"
WORKTIME_FORM_TEMPLATE = "worktime_app/worktime_timesheet_form.html"


def staff_required(user):
    return user.is_staff


def _worktime_context():
    items = (
        Performer.objects
        .select_related("registration", "registration__type")
        .order_by("registration__number", "registration__id", "position", "id")
    )
    return {"items": items}


@login_required
@require_http_methods(["GET"])
def worktime_partial(request):
    return render(request, WORKTIME_PARTIAL_TEMPLATE, _worktime_context())


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
            response = render(request, WORKTIME_PARTIAL_TEMPLATE, _worktime_context())
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
