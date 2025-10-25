from django.urls import path
from . import views

urlpatterns = [
    path("ping", views.ping, name="macroops_ping"),
    path("compile", views.compile_view, name="macroops_compile"),
    path("compile-enqueue", views.compile_enqueue_view, name="compile_enqueue"),
]