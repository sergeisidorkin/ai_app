from django.urls import path

from . import views


urlpatterns = [
    path("notifications/partial/", views.notifications_partial, name="notifications_partial"),
    path("notifications/counters/", views.notifications_counters, name="notifications_counters"),
    path("notifications/<int:pk>/mark-read/", views.notification_mark_read, name="notification_mark_read"),
    path(
        "notifications/<int:pk>/participation-action/",
        views.notification_participation_action,
        name="notification_participation_action",
    ),
]
