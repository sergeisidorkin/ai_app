from django.urls import path
from . import views

urlpatterns = [
    path("policy/partial/", views.policy_partial, name="policy_partial"),
    path("policy/product/create/", views.product_form_create, name="product_form_create"),
    path("policy/product/<int:pk>/edit/", views.product_form_edit, name="product_form_edit"),
    path("policy/product/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("products/<int:pk>/move-up/", views.product_move_up, name="product_move_up"),
    path("products/<int:pk>/move-down/", views.product_move_down, name="product_move_down"),
    path("policy/section/create/", views.section_form_create, name="section_form_create"),
    path("policy/section/<int:pk>/edit/", views.section_form_edit, name="section_form_edit"),
    path("policy/section/<int:pk>/delete/", views.section_delete, name="section_delete"),
    path("sections/<int:pk>/move-up/", views.section_move_up, name="section_move_up"),
    path("sections/<int:pk>/move-down/", views.section_move_down, name="section_move_down"),
    path("policy/structure/create/", views.structure_form_create, name="structure_form_create"),
    path("policy/structure/<int:pk>/edit/", views.structure_form_edit, name="structure_form_edit"),
    path("policy/structure/<int:pk>/delete/", views.structure_delete, name="structure_delete"),
    path("structures/<int:pk>/move-up/", views.structure_move_up, name="structure_move_up"),
    path("structures/<int:pk>/move-down/", views.structure_move_down, name="structure_move_down"),
]
