from django.urls import path
from . import views

urlpatterns = [
    path("projects/partial/", views.projects_partial, name="projects_partial"),

    path("projects/registration/create/", views.registration_form_create, name="registration_form_create"),
    path("projects/registration/<int:pk>/edit/", views.registration_form_edit, name="registration_form_edit"),
    path("projects/registration/<int:pk>/delete/", views.registration_delete, name="registration_delete"),
    path("projects/registration/<int:pk>/move-up/", views.registration_move_up, name="registration_move_up"),
    path("projects/registration/<int:pk>/move-down/", views.registration_move_down, name="registration_move_down"),
    path("projects/registration/create-workspace/", views.create_registration_workspace, name="create_registration_workspace"),
    path("projects/registration/workspace-folders/", views.workspace_folders_list, name="workspace_folders_list"),
    path("projects/registration/workspace-folders/save/", views.workspace_folders_save, name="workspace_folders_save"),
    path("projects/registration/workspace-folders/reset/", views.workspace_folders_reset, name="workspace_folders_reset"),

    path("projects/contract/<int:pk>/edit/", views.contract_form_edit, name="contract_form_edit"),

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
    path("projects/performers/request-confirmation/", views.participation_request, name="participation_request"),
    path("projects/performers/send-contract/", views.contract_request, name="contract_request"),
    path("projects/performers/request-info-approval/", views.info_request_approval, name="info_request_approval"),
    path("projects/performers/create-workspace/", views.create_workspace, name="create_workspace"),
    path("projects/performers/create-source-data-workspace/", views.create_source_data_workspace, name="create_source_data_workspace"),
    path("projects/performers/source-data-target-folder/", views.source_data_target_folder_load, name="source_data_target_folder_load"),
    path("projects/performers/source-data-target-folder/save/", views.source_data_target_folder_save, name="source_data_target_folder_save"),

    path("projects/legal-entities/create/", views.legal_entity_form_create, name="legal_entity_form_create"),
    path("projects/legal-entities/<int:pk>/edit/", views.legal_entity_form_edit, name="legal_entity_form_edit"),
    path("projects/legal-entities/<int:pk>/delete/", views.legal_entity_delete, name="legal_entity_delete"),
    path("projects/legal-entities/<int:pk>/move-up/", views.legal_entity_move_up, name="legal_entity_move_up"),
    path("projects/legal-entities/<int:pk>/move-down/", views.legal_entity_move_down, name="legal_entity_move_down"),
    path("projects/legal-entities/work-deps/", views.legal_entity_work_deps, name="legal_entity_work_deps"),

    path("projects/work/deps/", views.work_deps, name="work_deps"),
    path("projects/identifier-for-country/", views.identifier_for_country, name="identifier_for_country"),
]
