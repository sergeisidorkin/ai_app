from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import Notification
from .services import (
    build_notification_counters,
    get_notification_queryset_for_user,
    mark_notification_as_read,
    process_participation_notification,
    serialize_notification_cards,
)


def staff_required(user):
    return user.is_authenticated and user.is_staff


NOTIFICATIONS_PARTIAL_TEMPLATE = "notifications_app/notifications_partial.html"


def _notifications_context(request):
    notifications = list(get_notification_queryset_for_user(request.user))
    return {
        "notification_cards": serialize_notification_cards(notifications),
    }


@login_required
@user_passes_test(staff_required)
@require_GET
def notifications_partial(request):
    return render(request, NOTIFICATIONS_PARTIAL_TEMPLATE, _notifications_context(request))


@login_required
@user_passes_test(staff_required)
@require_GET
def notifications_counters(request):
    return JsonResponse(build_notification_counters(request.user))


@login_required
@user_passes_test(staff_required)
@require_POST
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    mark_notification_as_read(notification, request.user)
    return JsonResponse({"ok": True, **build_notification_counters(request.user)})


@login_required
@user_passes_test(staff_required)
@require_POST
def notification_participation_action(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    action_choice = (request.POST.get("action") or "").strip()
    try:
        process_participation_notification(notification, request.user, action_choice)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, **build_notification_counters(request.user)})
