from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.contracts_partial, name="contracts_partial"),
    path("<int:pk>/edit/", views.contract_form_edit, name="contracts_edit"),
    path("signing/<int:pk>/edit/", views.contract_signing_edit, name="contracts_signing_edit"),
    path("signing/<int:pk>/upload-scan/", views.contract_scan_upload, name="contract_scan_upload"),
    path("signing/send-scan/", views.send_scan, name="signing_send_scan"),

    # Contract templates ("Образцы шаблонов")
    path("templates/partial/", views.contract_templates_partial, name="ct_partial"),
    path("templates/create/", views.ct_form_create, name="ct_form_create"),
    path("templates/<int:pk>/edit/", views.ct_form_edit, name="ct_form_edit"),
    path("templates/<int:pk>/delete/", views.ct_delete, name="ct_delete"),
    path("templates/<int:pk>/move-up/", views.ct_move_up, name="ct_move_up"),
    path("templates/<int:pk>/move-down/", views.ct_move_down, name="ct_move_down"),
    path("templates/<int:pk>/download/", views.ct_download, name="ct_download"),

    # Contract variables ("Доступные переменные")
    path("variables/create/", views.ctv_form_create, name="ctv_form_create"),
    path("variables/<int:pk>/edit/", views.ctv_form_edit, name="ctv_form_edit"),
    path("variables/<int:pk>/delete/", views.ctv_delete, name="ctv_delete"),
    path("variables/<int:pk>/move-up/", views.ctv_move_up, name="ctv_move_up"),
    path("variables/<int:pk>/move-down/", views.ctv_move_down, name="ctv_move_down"),

    # Field parameters / Contract subject ("Предмет договора")
    path("field-params/partial/", views.field_params_partial, name="fp_partial"),
    path("field-params/subject/create/", views.cs_form_create, name="cs_form_create"),
    path("field-params/subject/<int:pk>/edit/", views.cs_form_edit, name="cs_form_edit"),
    path("field-params/subject/<int:pk>/delete/", views.cs_delete, name="cs_delete"),
    path("field-params/subject/<int:pk>/move-up/", views.cs_move_up, name="cs_move_up"),
    path("field-params/subject/<int:pk>/move-down/", views.cs_move_down, name="cs_move_down"),
]
