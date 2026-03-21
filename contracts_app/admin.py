from django.contrib import admin
from django.utils.html import format_html

from .models import ContractTemplate, ContractVariable, ContractSubject


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
