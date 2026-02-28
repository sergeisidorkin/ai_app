from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView
from django.http import HttpResponse
from django.templatetags.static import static as static_url

from django.contrib.auth.views import LoginView, LogoutView
from core.views import home_entry

from openai_app import views as openai_views
from office_addin.views import manifest_xml
from logs_app.views_ingest import api_logs_ingest
from logs_app.views import logs_config

urlpatterns = [
    path("taskpane.html", TemplateView.as_view(template_name="taskpane.html"), name="taskpane"),
path("", home_entry, name="home"),
#   path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("policy/",    include("policy_app.urls")),
    path("blocks/",    include(("blocks_app.urls", "blocks_app"),   namespace="blocks_app")),
    path("onedrive/",  include("onedrive_app.urls")),
    path("openai/",    include("openai_app.urls")),
    path("gdrive/",    include("googledrive_app.urls")),
    path("debugger/",  include("debugger_app.urls", namespace="debugger_app")),
    path("checklists/", include(("checklists_app.urls", "checklists_app"), namespace="checklists_app")),
    path("api/addin/", include("office_addin.urls")),
    path("api/addin/push-llm/", openai_views.push_llm_to_addin, name="push_llm_to_addin"),
    path("addin/manifest.xml", manifest_xml, name="addin_manifest"),
    path("api/addin/", include("office_addin.urls")),
    path("", include("docops_queue.urls")),
    path("api/macroops/", include("macroops_app.urls")),
    path("logs/api/logs/ingest/", api_logs_ingest, name="logs_ingest"),
    path("logs/api/config", logs_config, name="logs_config"),
    path("api/logs/ingest/", api_logs_ingest),
    path("logs/",      include(("logs_app.urls", "logs_app"), namespace="logs_app")),
    path("yadisk/", include("yandexdisk_app.urls")),
    path("classifiers/", include("classifiers_app.urls")),
    path("group/", include("group_app.urls")),
    path(
        "addin/commands.html",
        TemplateView.as_view(template_name="docops_queue/commands.html"),
        name="addin_commands",
    ),
    path("blockseditor/", include(("blockseditor_app.urls", "blockseditor_app"), namespace="blockseditor_app")),

    # Auth
    path("accounts/login/", LoginView.as_view(template_name="core/signin.html", redirect_authenticated_user=True),
         name="login"),
    path("accounts/logout/", LogoutView.as_view(next_page="home"), name="logout"),
    path("admin/", admin.site.urls),
    path("health/", lambda r: HttpResponse("OK")),
    path("", include("projects_app.urls")),
    path("", include("requests_app.urls")),
]

urlpatterns += [
    path("favicon.ico", RedirectView.as_view(
        url=static_url("core/icons/favicon.ico"), permanent=False
    )),
]