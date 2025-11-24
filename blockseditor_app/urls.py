from django.urls import path
from . import views

app_name = "blockseditor_app"

urlpatterns = [
    path("<int:block_id>/", views.editor, name="editor"),
    path("<int:block_id>/partial/", views.editor_partial, name="editor_partial"),
    path(
        "<int:block_id>/nodes/<slug:slug>/position/",
        views.update_node_position,
        name="node_position",
    ),
]