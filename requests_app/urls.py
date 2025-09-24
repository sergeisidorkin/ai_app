from django.urls import path
from . import views

urlpatterns = [
    path("requests/partial/", views.requests_partial, name="requests_partial"),
    path("requests/form/create/", views.request_form_create, name="request_form_create"),
    path("requests/row/<int:pk>/edit/", views.request_form_edit, name="request_form_edit"),
    path("requests/row/<int:pk>/delete/", views.request_delete, name="request_delete"),
    path("requests/row/<int:pk>/up/", views.request_move_up, name="request_move_up"),
    path("requests/row/<int:pk>/down/", views.request_move_down, name="request_move_down"),
]