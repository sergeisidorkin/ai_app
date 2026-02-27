from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.classifiers_partial, name="classifiers_partial"),
    path("oksm/create/", views.oksm_form_create, name="oksm_form_create"),
    path("oksm/<int:pk>/edit/", views.oksm_form_edit, name="oksm_form_edit"),
    path("oksm/<int:pk>/delete/", views.oksm_delete, name="oksm_delete"),
    path("oksm/<int:pk>/move-up/", views.oksm_move_up, name="oksm_move_up"),
    path("oksm/<int:pk>/move-down/", views.oksm_move_down, name="oksm_move_down"),
]
