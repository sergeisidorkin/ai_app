from django.urls import path

from . import views

app_name = "learning_app"

urlpatterns = [
    path("panel/", views.panel, name="panel"),
    path("open/", views.launch, name="launch"),
]
