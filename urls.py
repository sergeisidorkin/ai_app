from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.http import HttpResponse

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("blocks/", include("blocks_app.urls")),
    path("onedrive/", include("onedrive_app.urls")),
    path("openai/", include("openai_app.urls")),
    path("admin/", admin.site.urls),
    path("health/", lambda r: HttpResponse("OK")),
]