from django.urls import path
from . import views

app_name = "checklists_app"

urlpatterns = [
    path("partial/panel/", views.panel, name="panel_partial"),
    path("project-meta/<slug:uid>/", views.project_meta, name="project_meta"),
    path("partial/table/", views.table_partial, name="table_partial"),
    path("status/update/", views.update_status, name="update_status"),
    path("note/update/", views.update_note, name="update_note"),  # legacy
    path("comment/add/", views.add_comment, name="add_comment"),
]