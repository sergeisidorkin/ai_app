from django.urls import path
from . import views

urlpatterns = [
    path("connections/partial/", views.connections_partial, name="gdrive_connections_partial"),
    path("connect/", views.connect, name="gdrive_connect"),
    path("callback/", views.callback, name="gdrive_callback"),
    path("pick/", views.pick, name="gdrive_pick"),
    path("select/", views.select, name="gdrive_select"),
    path("disconnect/", views.disconnect, name="gdrive_disconnect"),
]

