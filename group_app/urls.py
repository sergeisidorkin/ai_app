from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.group_partial, name="group_partial"),
    path("create/", views.member_form_create, name="gm_form_create"),
    path("<int:pk>/edit/", views.member_form_edit, name="gm_form_edit"),
    path("<int:pk>/delete/", views.member_delete, name="gm_delete"),
    path("<int:pk>/move-up/", views.member_move_up, name="gm_move_up"),
    path("<int:pk>/move-down/", views.member_move_down, name="gm_move_down"),
    path("org/create/", views.org_form_create, name="org_form_create"),
    path("org/<int:pk>/edit/", views.org_form_edit, name="org_form_edit"),
    path("org/<int:pk>/delete/", views.org_delete, name="org_delete"),
    path("org/<int:pk>/move-up/", views.org_move_up, name="org_move_up"),
    path("org/<int:pk>/move-down/", views.org_move_down, name="org_move_down"),
]
