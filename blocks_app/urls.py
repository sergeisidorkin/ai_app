from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_partial, name="blocks_dashboard_partial"),
    path("blocks/create/", views.block_create, name="blocks_create"),
    path("blocks/<int:pk>/update/", views.block_update, name="blocks_update"),
    path("blocks/<int:pk>/set-model/", views.block_set_model, name="blocks_set_model"),
    path("blocks/<int:pk>/run/", views.block_run, name="blocks_run"),
    path("blocks/<int:pk>/delete/", views.block_delete, name="blocks_delete"),
]