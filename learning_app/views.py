from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .launch import build_moodle_launch_url
from .services import build_learning_overview


def staff_required(user):
    return user.is_authenticated and user.is_staff


@login_required
@user_passes_test(staff_required)
@require_GET
def panel(request):
    return render(request, "learning_app/panel.html", build_learning_overview(request.user))


@login_required
@user_passes_test(staff_required)
@require_GET
def launch(request):
    moodle_base_url = (getattr(settings, "MOODLE_BASE_URL", "") or "").strip()
    if not moodle_base_url:
        return redirect(f"{reverse('home')}#learning")

    target_path = request.GET.get("next")
    return redirect(build_moodle_launch_url(target_path))
