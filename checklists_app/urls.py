from django.urls import path
from . import views

app_name = "checklists_app"

urlpatterns = [
    path("partial/panel/", views.panel, name="panel_partial"),
    path("project-meta/<slug:uid>/", views.project_meta, name="project_meta"),
    path("grid/data/", views.grid_data, name="grid_data"),
    path("partial/table/", views.table_partial, name="table_partial"),
    path("status/update/", views.update_status, name="update_status"),
    path("status/batch-update/", views.update_status_batch, name="update_status_batch"),
    path("note/update/", views.update_note, name="update_note"),
    path("comment/add/", views.add_comment, name="add_comment"),
    path("comment/modal/", views.comment_modal, name="comment_modal"),
    # ChecklistItem CRUD
    path("item/form/create/", views.item_form_create, name="item_form_create"),
    path("item/form/edit/<int:pk>/", views.item_form_edit, name="item_form_edit"),
    path("item/check-number/", views.item_check_number, name="item_check_number"),
    path("item/create/", views.item_create, name="item_create"),
    path("item/text-update/<int:pk>/", views.item_text_update, name="item_text_update"),
    path("item/update/<int:pk>/", views.item_update, name="item_update"),
    path("item/delete/<int:pk>/", views.item_delete, name="item_delete"),
    path("item/move/<int:pk>/<str:direction>/", views.item_move, name="item_move"),
    path("item/batch-edit/", views.item_batch_edit, name="item_batch_edit"),
    # XLSX export
    path("export/xlsx/", views.export_xlsx, name="export_xlsx"),
    # Info request approval
    path("approve-info-request/", views.approve_info_request, name="approve_info_request"),
    # Shared links API
    path("shared-link/create/", views.shared_link_create_or_get, name="shared_link_create"),
    path("shared-link/update/", views.shared_link_update, name="shared_link_update"),
    # Public shared pages
    path("shared/<str:token>/", views.shared_page, name="shared_page"),
    path("shared/<str:token>/meta/", views.shared_project_meta, name="shared_project_meta"),
    path("shared/<str:token>/grid/", views.shared_grid_data, name="shared_grid_data"),
    path("shared/<str:token>/table/", views.shared_table_partial, name="shared_table_partial"),
    path("shared/<str:token>/status/update/", views.shared_update_status, name="shared_update_status"),
    path("shared/<str:token>/status/batch-update/", views.shared_update_status_batch, name="shared_update_status_batch"),
    path("shared/<str:token>/item/text-update/<int:pk>/", views.shared_item_text_update, name="shared_item_text_update"),
    path("shared/<str:token>/note/update/", views.shared_update_note, name="shared_update_note"),
    path("shared/<str:token>/comment/add/", views.shared_add_comment, name="shared_add_comment"),
    path("shared/<str:token>/comment/modal/", views.shared_comment_modal, name="shared_comment_modal"),
    path("shared/<str:token>/export/xlsx/", views.shared_export_xlsx, name="shared_export_xlsx"),
]
