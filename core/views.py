from django.shortcuts import render, redirect

from users_app.models import Employee


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
    return render(request, "index.html", {"employee": employee})