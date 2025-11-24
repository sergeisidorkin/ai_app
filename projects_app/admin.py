from django.contrib import admin
from .models import ProjectRegistration, WorkVolume, Performer, LegalEntity

@admin.register(ProjectRegistration)
class ProjectRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "position", "number", "group", "agreement_type", "agreement_number",
        "short_uid", "type", "name", "status", "year", "customer",
    )
    list_editable = ("position",)
    list_display_links = ("number", "name")
    search_fields = ("=number", "short_uid", "agreement_number", "name", "customer", "registration_number", "project_manager")
    list_filter = ("group", "agreement_type", "status", "type", "year")
    readonly_fields = ("short_uid",)

@admin.register(WorkVolume)
class WorkVolumeAdmin(admin.ModelAdmin):
    list_display = ("position", "project_short_uid", "type", "name", "asset_name", "registration_number", "manager")
    list_editable = ("position",)
    list_display_links = ("project_short_uid", "name")
    search_fields = ("project__short_uid", "name", "asset_name", "registration_number", "manager")
    list_filter = ("project__short_uid",)
    autocomplete_fields = ("project",)
    list_select_related = ("project",)
    ordering = ("project__position", "position", "id")
    readonly_fields = ("project_short_uid",)

    @admin.display(description="Проект ID", ordering="project__short_uid")
    def project_short_uid(self, obj):
        return getattr(obj.project, "short_uid", "")


@admin.register(Performer)
class PerformerAdmin(admin.ModelAdmin):
    list_display = ("id", "registration_short_uid", "asset_name", "executor", "grade", "section_code", "contract_number", "position")
    list_select_related = ("registration", "typical_section")
    search_fields = ("executor", "grade", "asset_name", "contract_number", "registration__number", "registration__group")
    list_filter = ("typical_section__product", )
    ordering = ("position", "id")

    @admin.display(description="Проект ID", ordering="registration__short_uid")
    def registration_short_uid(self, obj):
        return getattr(obj.registration, "short_uid", "")

    @admin.display(description="Тип. раздел")
    def section_code(self, obj):
        return getattr(obj.typical_section, "code", "")

@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ("position", "project_short_uid", "work_type", "work_name", "asset_name", "legal_name", "registration_number")
    list_editable = ("position",)
    list_display_links = ("project_short_uid", "legal_name")
    search_fields = ("legal_name", "registration_number", "project__short_uid", "work_item__asset_name")
    list_filter = ("project__short_uid",)
    list_select_related = ("project", "work_item", "work_item__project")
    ordering = ("project__position", "position", "id")

    @admin.display(description="Проект ID", ordering="project__short_uid")
    def project_short_uid(self, obj):
        return getattr(obj.project, "short_uid", "")

    @admin.display(description="Наименование актива", ordering="work_item__asset_name")
    def asset_name(self, obj):
        return getattr(obj.work_item, "asset_name", "")        