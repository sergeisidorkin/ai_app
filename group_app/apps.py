from django.apps import AppConfig


class GroupAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'group_app'

    def ready(self):
        from django.db.models.signals import post_save
        from policy_app.models import ExpertiseDirection

        from .expertise_management import ensure_mode_for_direction

        post_save.connect(
            ensure_mode_for_direction,
            sender=ExpertiseDirection,
            dispatch_uid="group_app.ensure_expertise_management_mode",
        )
