from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from projects_app.models import Performer, ProjectRegistration
from .forms import ContractEditForm


def staff_required(user):
    return user.is_staff


CONTRACTS_PARTIAL_TEMPLATE = "contracts_app/contracts_partial.html"


def _contracts_context():
    all_performers = (
        Performer.objects
        .select_related(
            "registration", "registration__type", "typical_section",
            "employee", "employee__user", "currency",
        )
        .filter(contract_sent_at__isnull=False, contract_batch_id__isnull=False)
        .order_by("contract_batch_id", "position", "id")
    )

    seen_batches = set()
    contracts = []
    for p in all_performers:
        if p.contract_batch_id not in seen_batches:
            seen_batches.add(p.contract_batch_id)
            contracts.append(p)

    price_map = {}
    for row in (
        Performer.objects
        .filter(contract_batch_id__isnull=False, agreed_amount__isnull=False)
        .values("contract_batch_id")
        .annotate(total_agreed=Sum("agreed_amount"))
    ):
        price_map[row["contract_batch_id"]] = row["total_agreed"]

    for p in contracts:
        p.total_price = price_map.get(p.contract_batch_id)

    contract_project_ids = {p.registration_id for p in contracts}
    contract_projects = (
        ProjectRegistration.objects
        .filter(id__in=contract_project_ids)
        .order_by("-number", "-id")
    )

    return {
        "contracts": contracts,
        "contract_projects": contract_projects,
    }


@login_required
@require_http_methods(["GET"])
def contracts_partial(request):
    return render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_form_edit(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related(
            "registration", "registration__type", "currency",
        ),
        pk=pk,
        contract_sent_at__isnull=False,
    )
    if request.method == "POST":
        form = ContractEditForm(request.POST, instance=performer)
        if form.is_valid():
            obj = form.save()
            if obj.contract_batch_id:
                Performer.objects.filter(
                    contract_batch_id=obj.contract_batch_id,
                ).exclude(pk=obj.pk).update(
                    contract_number=obj.contract_number,
                    contract_file=obj.contract_file,
                )
            resp = render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context())
            resp["HX-Trigger"] = "contracts-updated"
            return resp
    else:
        form = ContractEditForm(instance=performer)

    batch_filter = (
        Q(contract_batch_id=performer.contract_batch_id)
        if performer.contract_batch_id
        else Q(registration_id=performer.registration_id, executor=performer.executor, contract_sent_at__isnull=False)
    )
    total_price = (
        Performer.objects
        .filter(batch_filter, agreed_amount__isnull=False)
        .aggregate(total=Sum("agreed_amount"))
        .get("total")
    )
    performer.total_price = total_price

    return render(request, "contracts_app/contract_form.html", {
        "form": form,
        "performer": performer,
    })
