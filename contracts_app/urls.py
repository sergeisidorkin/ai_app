from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.contracts_partial, name="contracts_partial"),
    path("<int:pk>/edit/", views.contract_form_edit, name="contracts_edit"),

    # Contract templates ("Образцы шаблонов")
    path("templates/partial/", views.contract_templates_partial, name="ct_partial"),
    path("templates/create/", views.ct_form_create, name="ct_form_create"),
    path("templates/<int:pk>/edit/", views.ct_form_edit, name="ct_form_edit"),
    path("templates/<int:pk>/delete/", views.ct_delete, name="ct_delete"),
    path("templates/<int:pk>/move-up/", views.ct_move_up, name="ct_move_up"),
    path("templates/<int:pk>/move-down/", views.ct_move_down, name="ct_move_down"),
    path("templates/<int:pk>/download/", views.ct_download, name="ct_download"),
]
