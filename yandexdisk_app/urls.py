from django.urls import path
from . import views

urlpatterns = [
    path("connections/partial/", views.connections_partial, name="yadisk_connections_partial"),
    path("connect/", views.connect, name="yadisk_connect"),
    path("callback/", views.callback, name="yadisk_callback"),
    path("pick/", views.pick, name="yadisk_pick"),
    path("select/", views.select, name="yadisk_select"),
    path("clear/", views.clear_selection, name="yadisk_clear"),
    path("disconnect/", views.disconnect, name="yadisk_disconnect"),
]