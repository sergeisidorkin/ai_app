from django.apps import AppConfig


class ProjectsAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects_app"
    verbose_name = "Проекты"

    def ready(self):
        from .report_submission import start_report_check_recovery

        start_report_check_recovery()
