from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.http import HttpResponse

from django.contrib.auth.views import LoginView, LogoutView
from core.views import home_entry


urlpatterns = [
    path("", home_entry, name="home"),
#   path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("policy/", include("policy_app.urls")),
    path("blocks/", include("blocks_app.urls")),
    path("onedrive/", include("onedrive_app.urls")),
    path("openai/", include("openai_app.urls")),
    # Auth
    path("accounts/login/", LoginView.as_view(template_name="core/signin.html", redirect_authenticated_user=True),
         name="login"),
    path("accounts/logout/", LogoutView.as_view(next_page="home"), name="logout"),
    path("admin/", admin.site.urls),
    path("health/", lambda r: HttpResponse("OK")),
]