# logs_app/urls.py
from django.urls import path
from logs_app.views_ingest import api_logs_ingest

from . import views

app_name = "logs_app"

urlpatterns = [
    path("", views.logs_list, name="logs_list"),        # /logs/
    path("<int:pk>/", views.log_detail, name="detail"), # /logs/123/
    path("api/logs/ingest", api_logs_ingest, name="logs_ingest"),
]