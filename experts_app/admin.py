from django.contrib import admin

from .models import ExpertContractDetails, ExpertProfile, PolicyExpertSpecialty


@admin.register(PolicyExpertSpecialty)
class ExpertSpecialtyAdmin(admin.ModelAdmin):
    list_display = (
        "specialty",
        "specialty_en",
        "specialization_area",
        "expertise_dir",
        "department_display",
        "organization_display",
        "owner_display",
        "created_by",
    )
    list_select_related = (
        "expertise_dir",
        "expertise_dir__department",
        "expertise_dir__department__company",
        "created_by",
    )
    search_fields = ("specialty", "specialty_en", "specialization_area", "created_by__username")
    ordering = ("position", "id")
    filter_horizontal = ("owners",)
    readonly_fields = (
        "department_display",
        "organization_display",
        "created_by",
        "created_at",
        "updated_at",
    )
    fields = (
        "specialty",
        "specialty_en",
        "specialization_area",
        "expertise_dir",
        "department_display",
        "organization_display",
        "is_group_owner",
        "owners",
        "created_by",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("owners")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Владелец")
    def owner_display(self, obj):
        return obj.owner_display or "—"

    @admin.display(description="Подразделение")
    def department_display(self, obj):
        return obj.department_display or "—"

    @admin.display(description="Организация")
    def organization_display(self, obj):
        return obj.organization_display or "—"


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
