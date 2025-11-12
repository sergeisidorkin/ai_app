# ai_app/docops_queue/urls.py
from django.urls import path
from . import views
from docops_queue.views import job_detail

urlpatterns = [
    # агент тянет следующее задание
    path("api/agents/<str:agent_id>/pull", views.agent_pull, name="agent_pull"),

    # аддин спрашивает следующее задание для ОТКРЫТОГО документа
    path("api/docs/next", views.docs_next, name="docs_next"),

    # аддин завершил
    path("api/jobs/<uuid:job_id>/complete", views.job_complete, name="job_complete"),
    path("api/jobs/<uuid:job_id>", job_detail, name="job_detail"),

    # простейший enqueue для тестов
    path("api/jobs/enqueue", views.enqueue, name="enqueue"),
    path("api/jobs/reset-stale", views.reset_stale, name="reset_stale"),
    path("api/jobs/enqueue-from-pipeline", views.enqueue_from_pipeline, name="enqueue_from_pipeline"),
]
