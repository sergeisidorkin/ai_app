from django.urls import path
from . import views

app_name = "checklists_app"

urlpatterns = [
    path("partial/panel/", views.panel, name="panel_partial"),
    path("project-meta/<slug:uid>/", views.project_meta, name="project_meta"),
    path("partial/table/", views.table_partial, name="table_partial"),
    path("status/update/", views.update_status, name="update_status"),
    path("note/update/", views.update_note, name="update_note"),
    path("comment/add/", views.add_comment, name="add_comment"),
    # ChecklistItem CRUD
    path("item/form/create/", views.item_form_create, name="item_form_create"),
    path("item/form/edit/<int:pk>/", views.item_form_edit, name="item_form_edit"),
    path("item/check-number/", views.item_check_number, name="item_check_number"),
    path("item/create/", views.item_create, name="item_create"),
    path("item/update/<int:pk>/", views.item_update, name="item_update"),
    path("item/delete/<int:pk>/", views.item_delete, name="item_delete"),
    path("item/move/<int:pk>/<str:direction>/", views.item_move, name="item_move"),
    # XLSX export
    path("export/xlsx/", views.export_xlsx, name="export_xlsx"),
    # Shared links API
    path("shared-link/create/", views.shared_link_create_or_get, name="shared_link_create"),
    path("shared-link/update/", views.shared_link_update, name="shared_link_update"),
    # Public shared pages
    path("shared/<str:token>/", views.shared_page, name="shared_page"),
    path("shared/<str:token>/meta/", views.shared_project_meta, name="shared_project_meta"),
    path("shared/<str:token>/table/", views.shared_table_partial, name="shared_table_partial"),
    path("shared/<str:token>/status/update/", views.shared_update_status, name="shared_update_status"),
    path("shared/<str:token>/note/update/", views.shared_update_note, name="shared_update_note"),
    path("shared/<str:token>/comment/add/", views.shared_add_comment, name="shared_add_comment"),
    path("shared/<str:token>/export/xlsx/", views.shared_export_xlsx, name="shared_export_xlsx"),
]
