from django.urls import path
from . import views

urlpatterns = [
    path("projects/partial/", views.projects_partial, name="projects_partial"),

    path("projects/registration/create/", views.registration_form_create, name="registration_form_create"),
    path("projects/registration/<int:pk>/edit/", views.registration_form_edit, name="registration_form_edit"),
    path("projects/registration/<int:pk>/delete/", views.registration_delete, name="registration_delete"),
    path("projects/registration/<int:pk>/move-up/", views.registration_move_up, name="registration_move_up"),
    path("projects/registration/<int:pk>/move-down/", views.registration_move_down, name="registration_move_down"),

    path("projects/work/create/", views.work_form_create, name="work_form_create"),
    path("projects/work/<int:pk>/edit/",  views.work_form_edit, name="work_form_edit"),
    path("projects/work/<int:pk>/delete/", views.work_delete, name="work_delete"),
    path("projects/work/<int:pk>/move-up/", views.work_move_up, name="work_move_up"),
    path("projects/work/<int:pk>/move-down/", views.work_move_down, name="work_move_down"),

    path("projects/performers/partial/", views.performers_partial, name="performers_partial"),
    path("projects/performers/create/", views.performer_form_create, name="performer_form_create"),
    path("projects/performers/<int:pk>/edit/", views.performer_form_edit, name="performer_form_edit"),
    path("projects/performers/<int:pk>/delete/", views.performer_delete, name="performer_delete"),
    path("projects/performers/<int:pk>/move-up/", views.performer_move_up, name="performer_move_up"),
    path("projects/performers/<int:pk>/move-down/", views.performer_move_down, name="performer_move_down"),

    path("projects/legal-entities/create/", views.legal_entity_form_create, name="legal_entity_form_create"),
    path("projects/legal-entities/<int:pk>/edit/", views.legal_entity_form_edit, name="legal_entity_form_edit"),
    path("projects/legal-entities/<int:pk>/delete/", views.legal_entity_delete, name="legal_entity_delete"),
    path("projects/legal-entities/<int:pk>/move-up/", views.legal_entity_move_up, name="legal_entity_move_up"),
    path("projects/legal-entities/<int:pk>/move-down/", views.legal_entity_move_down, name="legal_entity_move_down"),
    path("projects/legal-entities/work-deps/", views.legal_entity_work_deps, name="legal_entity_work_deps"),

    path("projects/work/deps/", views.work_deps, name="work_deps"),
]
