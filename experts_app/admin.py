from django.contrib import admin

from .models import ExpertContractDetails, ExpertProfile, ExpertSpecialty


@admin.register(ExpertSpecialty)
class ExpertSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("id", "specialty", "expertise_direction", "position")
    search_fields = ("specialty", "specialty_en")
    ordering = ("position", "id")


@admin.register(ExpertProfile)
class ExpertProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "expertise_direction", "grade", "position")
    search_fields = ("employee__user__last_name", "employee__user__first_name", "employee__patronymic")
    ordering = ("position", "id")


@admin.register(ExpertContractDetails)
class ExpertContractDetailsAdmin(admin.ModelAdmin):
    list_display = ("id", "expert_profile", "citizenship_record", "citizenship", "updated_at")
    search_fields = (
        "expert_profile__employee__user__last_name",
        "expert_profile__employee__user__first_name",
        "expert_profile__employee__patronymic",
        "citizenship_record__identifier",
        "citizenship_record__number",
    )
    ordering = ("expert_profile__position", "citizenship_record__position", "id")
