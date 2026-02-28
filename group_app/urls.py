from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.group_partial, name="group_partial"),
    path("create/", views.member_form_create, name="gm_form_create"),
    path("<int:pk>/edit/", views.member_form_edit, name="gm_form_edit"),
    path("<int:pk>/delete/", views.member_delete, name="gm_delete"),
    path("<int:pk>/move-up/", views.member_move_up, name="gm_move_up"),
    path("<int:pk>/move-down/", views.member_move_down, name="gm_move_down"),
]
