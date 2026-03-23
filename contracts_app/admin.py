from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ContractTemplate, ContractVariable, ContractSubject,
    ContractProjectWork, ContractSigningWork,
)


class ContractVariableInline(admin.TabularInline):
    model = ContractVariable
    extra = 0
    fields = ("position", "key", "description", "is_computed", "source_section", "source_table", "source_column")


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "position",
        "sample_name",
        "contract_type",
        "party",
        "country_name",
        "group_member",
        "product",
        "version",
        "has_file",
        "is_all_sections",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("sample_name",)
    list_filter = ("contract_type", "party", "is_all_sections", "product")
    search_fields = ("sample_name", "country_name", "version", "group_member__short_name", "product__short_name")
    autocomplete_fields = ("product",)
    raw_id_fields = ("group_member",)
    ordering = ("position", "id")

    fieldsets = (
        (None, {
            "fields": (
                "sample_name", "version", "position",
            ),
        }),
        ("Классификация", {
            "fields": (
                ("contract_type", "party"),
                ("country_name", "country_code"),
                ("group_member", "product"),
            ),
        }),
        ("Файл и разделы", {
            "fields": (
                "file",
                "is_all_sections",
                "typical_sections_json",
            ),
        }),
    )

    @admin.display(boolean=True, description="Файл")
    def has_file(self, obj):
        return bool(obj.file)


@admin.register(ContractVariable)
class ContractVariableAdmin(admin.ModelAdmin):
    list_display = (
        "position",
        "key",
        "description",
        "is_computed",
        "source_section",
        "source_table",
        "source_column",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("key",)
    list_filter = ("is_computed",)
    search_fields = ("key", "description", "source_section", "source_table", "source_column")
    ordering = ("position", "id")

    fieldsets = (
        (None, {
            "fields": ("key", "description", "is_computed", "position"),
        }),
        ("Привязка к данным", {
            "fields": ("source_section", "source_table", "source_column"),
            "description": "Заполняется для переменных, берущих значение из столбца таблицы.",
        }),
    )


@admin.register(ContractSubject)
class ContractSubjectAdmin(admin.ModelAdmin):
    list_display = ("position", "product_name", "subject_text_short", "updated_at")
    list_editable = ("position",)
    list_display_links = ("subject_text_short",)
    list_filter = ("product",)
    search_fields = ("subject_text", "product__short_name")
    autocomplete_fields = ("product",)
    ordering = ("position", "id")

    @admin.display(description="Продукт", ordering="product__short_name")
    def product_name(self, obj):
        return getattr(obj.product, "short_name", "")

    @admin.display(description="Предмет договора")
    def subject_text_short(self, obj):
        text = obj.subject_text or ""
        return text[:120] + "…" if len(text) > 120 else text


# ---------------------------------------------------------------------------
#  В работе — proxy-модели над Performer
# ---------------------------------------------------------------------------

class _PerformerProxyMixin:
    """Общие поля для list-отображения proxy-моделей Performer."""

    list_select_related = ("registration", "typical_section")
    search_fields = (
        "executor", "asset_name", "contract_number",
        "registration__number", "registration__group",
    )
    ordering = ("position", "id")

    @admin.display(description="Проект", ordering="registration__short_uid")
    def registration_short_uid(self, obj):
        return getattr(obj.registration, "short_uid", "")

    @admin.display(description="Тип. раздел")
    def section_code(self, obj):
        return getattr(obj.typical_section, "code", "")


@admin.register(ContractProjectWork)
class ContractProjectWorkAdmin(_PerformerProxyMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "registration_short_uid",
        "asset_name",
        "executor",
        "contract_number",
        "contract_batch_id",
        "contract_project_created",
        "contract_conclusion_status",
        "contract_signing_date",
    )
    list_filter = (
        "contract_project_created",
        "contract_is_addendum",
        "contract_conclusion_status",
        "typical_section__product",
    )

    fieldsets = (
        ("Исполнитель", {
            "fields": (
                "registration", "work_item",
                "asset_name", "executor", "employee",
                "grade", "grade_name", "typical_section",
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
    )


@admin.register(ContractSigningWork)
class ContractSigningWorkAdmin(_PerformerProxyMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "registration_short_uid",
        "asset_name",
        "executor",
        "contract_number",
        "has_employee_scan",
        "has_signed_scan",
        "contract_signed_scan_upload_date",
    )
    list_filter = (
        "typical_section__product",
        "contract_is_addendum",
    )

    fieldsets = (
        ("Исполнитель", {
            "fields": (
                "registration", "work_item",
                "asset_name", "executor", "employee",
                "grade", "grade_name", "typical_section",
            ),
        }),
        ("Договор", {
            "fields": (
                ("contract_number", "contract_batch_id"),
                ("contract_signing_date", "contract_date"),
            ),
        }),
        ("Скан с подписью сотрудника", {
            "fields": (
                "contract_employee_scan",
                "contract_scan_document",
                "contract_employee_scan_link",
                ("contract_upload_date", "contract_send_date"),
            ),
        }),
        ("Подписанный договор", {
            "fields": (
                "contract_signed_scan_file",
                "contract_signed_scan",
                "contract_signed_scan_link",
                "contract_signed_scan_upload_date",
            ),
        }),
    )

    @admin.display(boolean=True, description="Скан сотрудника")
    def has_employee_scan(self, obj):
        return bool(obj.contract_employee_scan)

    @admin.display(boolean=True, description="Подписанный договор")
    def has_signed_scan(self, obj):
        return bool(obj.contract_signed_scan_file or obj.contract_signed_scan)
