from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.classifiers_partial, name="classifiers_partial"),
    path("country-code/", views.country_code_lookup, name="country_code_lookup"),
    # ОКСМ
    path("oksm/table/", views.oksm_table_partial, name="oksm_table_partial"),
    path("oksm/create/", views.oksm_form_create, name="oksm_form_create"),
    path("oksm/<int:pk>/edit/", views.oksm_form_edit, name="oksm_form_edit"),
    path("oksm/<int:pk>/delete/", views.oksm_delete, name="oksm_delete"),
    path("oksm/<int:pk>/move-up/", views.oksm_move_up, name="oksm_move_up"),
    path("oksm/<int:pk>/move-down/", views.oksm_move_down, name="oksm_move_down"),
    # ОКВ
    path("okv/table/", views.okv_table_partial, name="okv_table_partial"),
    path("okv/create/", views.okv_form_create, name="okv_form_create"),
    path("okv/<int:pk>/edit/", views.okv_form_edit, name="okv_form_edit"),
    path("okv/<int:pk>/delete/", views.okv_delete, name="okv_delete"),
    path("okv/<int:pk>/move-up/", views.okv_move_up, name="okv_move_up"),
    path("okv/<int:pk>/move-down/", views.okv_move_down, name="okv_move_down"),
    # КАТД
    path("katd/table/", views.katd_table_partial, name="katd_table_partial"),
    path("katd/create/", views.katd_form_create, name="katd_form_create"),
    path("katd/<int:pk>/edit/", views.katd_form_edit, name="katd_form_edit"),
    path("katd/<int:pk>/delete/", views.katd_delete, name="katd_delete"),
    path("katd/<int:pk>/move-up/", views.katd_move_up, name="katd_move_up"),
    path("katd/<int:pk>/move-down/", views.katd_move_down, name="katd_move_down"),
    # Величина прожиточного минимума
    path("lw/table/", views.lw_table_partial, name="lw_table_partial"),
    path("lw/regions/", views.lw_regions_for_country, name="lw_regions_for_country"),
    path("lw/currency/", views.lw_currency_for_country, name="lw_currency_for_country"),
    path("lw/create/", views.lw_form_create, name="lw_form_create"),
    path("lw/<int:pk>/edit/", views.lw_form_edit, name="lw_form_edit"),
    path("lw/<int:pk>/delete/", views.lw_delete, name="lw_delete"),
    path("lw/<int:pk>/move-up/", views.lw_move_up, name="lw_move_up"),
    path("lw/<int:pk>/move-down/", views.lw_move_down, name="lw_move_down"),
]
