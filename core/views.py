from datetime import date

from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect

from policy_app.models import EXPERT_GROUP, LAWYER_GROUP
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
    return render(request, "index.html", {
        "employee": employee,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
        "ler_date_filter": date.today().isoformat(),
    })