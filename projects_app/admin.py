from django.contrib import admin
from .models import LegalEntity, Performer, ProjectRegistration, ProjectRegistrationProduct, WorkVolume

@admin.register(ProjectRegistration)
class ProjectRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "position", "number", "group_display_value", "agreement_type", "agreement_number",
        "short_uid", "type_value", "name", "status", "year", "customer",
    )
    list_editable = ("position",)
    list_display_links = ("number", "name")
    search_fields = ("=number", "short_uid", "agreement_number", "name", "customer", "registration_number", "project_manager")
    list_filter = ("group_member", "agreement_type", "status", "type", "year")
    readonly_fields = ("short_uid",)

    @admin.display(description="Группа", ordering="group")
    def group_display_value(self, obj):
        return obj.group_display

    @admin.display(description="Тип")
    def type_value(self, obj):
        return obj.type_short_display


@admin.register(ProjectRegistrationProduct)
class ProjectRegistrationProductAdmin(admin.ModelAdmin):
    list_display = ("registration", "product", "rank")
    list_select_related = ("registration", "product")
    ordering = ("registration__position", "rank", "id")

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
    list_display = (
        "id", "registration_short_uid", "asset_name", "executor", "grade",
        "section_code", "contract_number", "contract_batch_id", "position",
    )
    list_select_related = ("registration", "typical_section")
    search_fields = ("executor", "grade", "asset_name", "contract_number", "registration__number", "registration__group")
    list_filter = ("typical_section__product", "contract_is_addendum", "contract_project_created")
    ordering = ("position", "id")

    fieldsets = (
        (None, {
            "fields": (
                "position", "registration", "work_item",
                "asset_name", "executor", "employee",
                "grade", "grade_name", "currency", "typical_section",
            ),
        }),
        ("Финансы", {
            "fields": (
                ("actual_costs", "estimated_costs"),
                ("agreed_amount", "prepayment", "final_payment"),
            ),
        }),
        ("Участие и согласование", {
            "classes": ("collapse",),
            "fields": (
                ("participation_request_sent_at", "participation_deadline_at"),
                ("participation_response", "participation_response_at"),
                ("info_request_sent_at", "info_request_deadline_at"),
                ("info_approval_status", "info_approval_at"),
            ),
        }),
        ("Заключение договора", {
            "fields": (
                ("contract_number", "contract_batch_id"),
                ("contract_is_addendum", "contract_addendum_number"),
                ("contract_sent_at", "contract_deadline_at"),
                ("contract_signing_date", "contract_date"),
                ("contract_conclusion_status", "contract_signing_note"),
                "contract_term",
                ("contract_project_created", "contract_project_created_at"),
                ("contract_project_link", "contract_project_disk_folder"),
                "contract_file",
            ),
        }),
        ("Подписание договора — скан сотрудника", {
            "fields": (
                "contract_employee_scan",
                "contract_scan_document",
                "contract_employee_scan_link",
                ("contract_upload_date", "contract_send_date"),
            ),
        }),
        ("Подписание договора — подписанный договор", {
            "fields": (
                "contract_signed_scan_file",
                "contract_signed_scan",
                "contract_signed_scan_link",
                "contract_signed_scan_upload_date",
            ),
        }),
    )

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