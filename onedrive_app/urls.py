from django.urls import path
from . import views

urlpatterns = [
    path("connections/partial/", views.connections_partial, name="onedrive_connections_partial"),
    path("connect/", views.connect, name="onedrive_connect"),
    path("callback/", views.callback, name="onedrive_callback"),
    path("pick/", views.pick, name="onedrive_pick"),
    path("select/", views.select, name="onedrive_select"),
    path("clear/", views.clear_selection, name="onedrive_clear"),
]