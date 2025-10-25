from django.urls import path
from . import views
from office_addin import views as addin_views

urlpatterns = [
    path("ping/", views.ping),                 # проверка связи
    path("insert-demo/", views.insert_demo),   # заглушка под будущие вызовы
    path("push-test/", views.push_test),
    path("push-paragraph/", views.push_paragraph),
    path("push-raw/", views.push_raw),
    path("push-docops-text/", views.push_docops_text),
    # LLM → Word демо
    path("push-llm-demo/", views.push_llm_demo),
]