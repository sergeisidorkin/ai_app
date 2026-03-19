import json

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
def project_pending_notifications_partial(request):
    notifications = list(
        get_notification_queryset_for_user(request.user).filter(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            is_processed=False,
        )
    )
    return render(request, NOTIFICATIONS_PARTIAL_TEMPLATE, {
        "notification_cards": serialize_notification_cards(notifications),
        "hide_empty_state": True,
    })


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


@login_required
@user_passes_test(staff_required)
@require_POST
def notification_bulk_delete(request):
    try:
        ids = json.loads(request.body).get("ids", [])
    except (json.JSONDecodeError, AttributeError):
        ids = request.POST.getlist("ids")
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return JsonResponse({"ok": False, "error": "Не указаны уведомления."}, status=400)
    Notification.objects.filter(pk__in=ids, recipient=request.user, is_processed=True).delete()
    return JsonResponse({"ok": True, **build_notification_counters(request.user)})
