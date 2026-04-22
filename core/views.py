from datetime import date

from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect

from learning_app.services import build_learning_overview
from nextcloud_app.services import build_nextcloud_overview
from policy_app.models import (
    DEPARTMENT_HEAD_GROUP,
    EXPERT_GROUP,
    LAWYER_GROUP,
    PROJECTS_HEAD_GROUP,
)
from users_app.models import Employee


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
    is_expert = request.user.groups.filter(name=EXPERT_GROUP).exists()
    is_lawyer = request.user.groups.filter(name=LAWYER_GROUP).exists()
    employee_role = getattr(employee, "role", "") or ""
    is_department_head = employee_role == DEPARTMENT_HEAD_GROUP
    can_access_connections = (not is_expert) or (
        employee_role in {PROJECTS_HEAD_GROUP, DEPARTMENT_HEAD_GROUP}
    )
    smtp_only_connections = is_department_head
    context = {
        "employee": employee,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
        "is_department_head": is_department_head,
        "can_access_connections": can_access_connections,
        "smtp_only_connections": smtp_only_connections,
        "ler_date_filter": date.today().isoformat(),
        "bei_date_filter": date.today().isoformat(),
        "bei_duplicates_filter": "all",
        "bea_date_filter": date.today().isoformat(),
    }
    context.update(build_learning_overview(request.user))
    context.update(build_nextcloud_overview(request.user))
    return render(request, "index.html", context)