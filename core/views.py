from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect

from core.dsh import build_dsh_overview
from group_app.models import GroupMember
from core.section_labels import APP_SECTION_LABELS
from learning_app.services import build_learning_overview
from nextcloud_app.services import build_nextcloud_overview
from policy_app.models import (
    ADMIN_GROUP,
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUPS,
    EXPERT_GROUP,
    LAWYER_GROUP,
    PROJECTS_HEAD_GROUP,
)
from users_app.models import Employee
from worktime_app.services import is_worktime_eligible_employee


class RememberMeLoginView(LoginView):
    template_name = "core/signin.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)
            self.request.session.save()
        return response


def home_entry(request):
    """
    Точка входа:
    - анонимному пользователю показываем форму входа,
    - staff — основную страницу (index.html),
    - остальным — профиль пользователя.
    """
    if not request.user.is_authenticated:
        return render(request, "core/signin.html", {})
    if not request.user.is_staff:
        return redirect("user_profile")
    employee = Employee.objects.filter(user=request.user).first()
    employee_role = getattr(employee, "role", "") or ""
    is_expert = request.user.groups.filter(name=EXPERT_GROUP).exists() or employee_role == EXPERT_GROUP
    is_lawyer = request.user.groups.filter(name=LAWYER_GROUP).exists() or employee_role == LAWYER_GROUP
    is_contract_admin = (
        request.user.is_superuser
        or request.user.groups.filter(name=ADMIN_GROUP).exists()
        or employee_role == ADMIN_GROUP
    )
    is_department_head = employee_role == DEPARTMENT_HEAD_GROUP
    is_director_role = employee_role in DIRECTOR_GROUPS
    can_access_worktime = is_worktime_eligible_employee(employee)
    can_access_checklist_sort = (
        request.user.groups.filter(name=ADMIN_GROUP).exists()
        or employee_role == ADMIN_GROUP
    )
    can_access_connections = (not is_expert) or (
        employee_role in {PROJECTS_HEAD_GROUP, DEPARTMENT_HEAD_GROUP}
    )
    smtp_only_connections = is_department_head
    context = {
        "employee": employee,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
        "is_department_head": is_department_head,
        "is_director_role": is_director_role,
        "can_access_contract_requisites": (
            request.user.is_staff and (is_contract_admin or is_lawyer or not is_expert)
        ),
        "can_access_worktime": can_access_worktime,
        "can_access_checklist_sort": can_access_checklist_sort,
        "can_access_connections": can_access_connections,
        "can_access_dsh": is_contract_admin,
        "smtp_only_connections": smtp_only_connections,
        "ler_date_filter": date.today().isoformat(),
        "bei_date_filter": date.today().isoformat(),
        "bei_duplicates_filter": "all",
        "bea_date_filter": date.today().isoformat(),
        "worktime_company_filter_options": GroupMember.objects.exclude(short_name="").order_by("position", "id"),
        "APP_SECTION_LABELS": APP_SECTION_LABELS,
    }
    context.update(build_learning_overview(request.user))
    context.update(build_nextcloud_overview(request.user))
    context.update(build_dsh_overview(request))
    return render(request, "index.html", context)


def _user_can_open_dsh(user):
    if not user.is_authenticated or not user.is_staff:
        return False
    employee = Employee.objects.filter(user=user).first()
    employee_role = getattr(employee, "role", "") or ""
    return (
        user.is_superuser
        or employee_role == ADMIN_GROUP
        or user.groups.filter(name=ADMIN_GROUP).exists()
    )


@login_required
def dsh_open(request):
    if not _user_can_open_dsh(request.user):
        return HttpResponseForbidden("Недостаточно прав.")
    launch_url = build_dsh_overview(request).get("dsh_launch_url") or ""
    if "token=" not in launch_url:
        return HttpResponse(
            "Консоль ИИ не готова. Запустите локальный DSH "
            "(./scripts/dev_dsh.sh или ./scripts/dev_up.sh) и обновите страницу.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    return redirect(launch_url)