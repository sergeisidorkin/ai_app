from django.urls import path
from . import views

urlpatterns = [
    path("save", views.save_key, name="openai_save"),
    path("delete", views.delete_key, name="openai_delete"),
]