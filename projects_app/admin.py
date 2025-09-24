from django.contrib import admin
from .models import ProjectRegistration, WorkVolume, Performer

@admin.register(ProjectRegistration)
class ProjectRegistrationAdmin(admin.ModelAdmin):
    list_display = ("position", "number", "group", "type", "name", "status", "year", "customer")
    list_editable = ("position",)
    list_display_links = ("number", "name")
    # по числовому number — точный поиск:
    search_fields = ("=number", "name", "customer", "registration_number", "project_manager")
    list_filter = ("group", "status", "type", "year")
    autocomplete_fields = ("type",)  # если type стал FK на Product; иначе можно убрать
    ordering = ("position", "id")

@admin.register(WorkVolume)
class WorkVolumeAdmin(admin.ModelAdmin):
    list_display = ("position", "project", "name", "type", "manager")
    list_editable = ("position",)
    list_display_links = ("project", "name")
    search_fields = ("name", "asset_name", "registration_number", "manager")
    list_filter = ("project",)
    autocomplete_fields = ("project",)
    list_select_related = ("project",)
    ordering = ("project__position", "position", "id")

@admin.register(Performer)
class PerformerAdmin(admin.ModelAdmin):
    list_display = ("id", "registration_label", "asset_name", "executor", "grade", "section_code", "contract_number", "position")
    list_select_related = ("registration", "typical_section")
    search_fields = ("executor", "grade", "asset_name", "contract_number", "registration__number", "registration__group")
    list_filter = ("typical_section__product", )
    ordering = ("position", "id")

    @admin.display(description="Номер", ordering="registration__number")
    def registration_label(self, obj):
        r = obj.registration
        return f"{getattr(r,'number','')} {getattr(r,'group','')}".strip()

    @admin.display(description="Тип. раздел")
    def section_code(self, obj):
        return getattr(obj.typical_section, "code", "")