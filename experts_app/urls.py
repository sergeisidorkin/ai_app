from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.experts_partial, name="experts_partial"),
    path("contract-requisites/partial/", views.contract_requisites_partial, name="contract_requisites_partial"),
    # ExpertSpecialty
    path("create/", views.specialty_form_create, name="esp_form_create"),
    path("<int:pk>/edit/", views.specialty_form_edit, name="esp_form_edit"),
    path("<int:pk>/delete/", views.specialty_delete, name="esp_delete"),
    path("<int:pk>/move-up/", views.specialty_move_up, name="esp_move_up"),
    path("<int:pk>/move-down/", views.specialty_move_down, name="esp_move_down"),
    path("specialty/csv-download/", views.esp_csv_download, name="esp_csv_download"),
    path("specialty/csv-upload/", views.esp_csv_upload, name="esp_csv_upload"),
    # ExpertProfile
    path("profile/<int:pk>/edit/", views.profile_form_edit, name="epr_form_edit"),
    path("profile/<int:pk>/move-up/", views.profile_move_up, name="epr_move_up"),
    path("profile/<int:pk>/move-down/", views.profile_move_down, name="epr_move_down"),
    path("profile/csv-download/", views.epr_csv_download, name="epr_csv_download"),
    path("profile/csv-upload/", views.epr_csv_upload, name="epr_csv_upload"),
    # Contract Details
    path("profile/<int:pk>/contract-details/", views.contract_details_form_edit, name="epr_contract_details_edit"),
    path("profile/<int:pk>/contract-details/facsimile/download/", views.contract_facsimile_download, name="epr_contract_facsimile_download"),
]
