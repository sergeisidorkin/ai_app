from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from users_app.models import Employee


@login_required
def profile_view(request):
    employee = Employee.objects.filter(user=request.user).first()
    return render(request, "userprofile_app/profile.html", {"employee": employee})


@login_required
@require_POST
def profile_edit(request):
    user = request.user
    employee, _ = Employee.objects.get_or_create(user=user)

    user.first_name = request.POST.get("first_name", user.first_name)
    user.last_name = request.POST.get("last_name", user.last_name)
    user.save(update_fields=["first_name", "last_name"])

    employee.patronymic = request.POST.get("patronymic", employee.patronymic)
    employee.phone = request.POST.get("phone", employee.phone)
    if not user.is_staff:
        employee.organization = request.POST.get("organization", employee.organization)
    employee.job_title = request.POST.get("job_title", employee.job_title)

    if "password" in request.POST and request.POST["password"].strip():
        user.set_password(request.POST["password"])
        user.save(update_fields=["password"])

    employee.save()
    return redirect("user_profile")


@login_required
@require_POST
def avatar_upload(request):
    if "avatar" in request.FILES:
        employee, _ = Employee.objects.get_or_create(user=request.user)
        if employee.avatar:
            employee.avatar.delete(save=False)
        employee.avatar = request.FILES["avatar"]
        employee.save(update_fields=["avatar"])
    return redirect("user_profile")


@login_required
@require_POST
def avatar_delete(request):
    employee = Employee.objects.filter(user=request.user).first()
    if employee and employee.avatar:
        employee.avatar.delete(save=False)
        employee.avatar = ""
        employee.save(update_fields=["avatar"])
    return redirect("user_profile")


@login_required
@require_POST
def profile_delete(request):
    user = request.user
    logout(request)
    user.delete()
    return redirect("login")
