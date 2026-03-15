from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.contracts_partial, name="contracts_partial"),
    path("<int:pk>/edit/", views.contract_form_edit, name="contracts_edit"),
]
