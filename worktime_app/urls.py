from django.urls import path

from . import views


urlpatterns = [
    path("partial/", views.worktime_partial, name="worktime_partial"),
    path("<int:pk>/edit/", views.worktime_form_edit, name="worktime_edit"),
]
