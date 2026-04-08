from django.urls import path

from . import views


urlpatterns = [
    path("prs/table/", views.prs_table_partial, name="prs_table_partial"),
    path("prs/create/", views.prs_form_create, name="prs_form_create"),
    path("prs/<int:pk>/edit/", views.prs_form_edit, name="prs_form_edit"),
    path("prs/<int:pk>/delete/", views.prs_delete, name="prs_delete"),
    path("prs/<int:pk>/move-up/", views.prs_move_up, name="prs_move_up"),
    path("prs/<int:pk>/move-down/", views.prs_move_down, name="prs_move_down"),
    path("psn/table/", views.psn_table_partial, name="psn_table_partial"),
    path("psn/create/", views.psn_form_create, name="psn_form_create"),
    path("psn/<int:pk>/edit/", views.psn_form_edit, name="psn_form_edit"),
    path("psn/<int:pk>/delete/", views.psn_delete, name="psn_delete"),
    path("psn/<int:pk>/move-up/", views.psn_move_up, name="psn_move_up"),
    path("psn/<int:pk>/move-down/", views.psn_move_down, name="psn_move_down"),
]
