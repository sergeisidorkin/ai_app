from django.urls import path
from . import views

app_name = "debugger_app"

urlpatterns = [
    path("partial/panel/", views.panel, name="panel_partial"),
    path("project-meta/<int:pk>/", views.project_meta, name="project_meta"),
]