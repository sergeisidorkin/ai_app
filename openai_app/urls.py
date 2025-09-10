from django.urls import path
from . import views

urlpatterns = [
    # Новый «правильный» URL для сохранения ключа
    path("save-key/", views.save_key, name="openai_save_key"),
    # DEPRECATED: оставить как алиас на переходный период, чтобы не ломать старые ссылки
    path("save", views.save_key, name="openai_save"),
    path("delete", views.delete_key, name="openai_delete"),
]