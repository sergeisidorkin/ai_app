from django.contrib import admin
from django.db.models import Q, Sum
from .models import (
    LegalEntity,
    PaymentRequestPerformer,
    Performer,
    ProjectRegistration,
    ProjectRegistrationProduct,
    WorkVolume,
)

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
        ("Составление проекта договора", {
            "fields": (
                ("contract_number", "contract_batch_id"),
                ("contract_is_addendum", "contract_addendum_number"),
                ("contract_sent_at", "contract_deadline_at"),
                ("contract_signing_date", "contract_date"),
                ("contract_conclusion_status", "contract_signing_note"),
                "contract_term",
                ("contract_project_created", "contract_project_created_at"),
                ("contract_project_link", "contract_project_folder_link"),
                "contract_project_disk_folder",
                "contract_file",
                ("contract_pdf_file", "contract_pdf_link"),
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
                "contract_signed_pdf_file",
                "contract_signed_pdf_link",
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


@admin.register(PaymentRequestPerformer)
class PaymentRequestPerformerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "registration_short_uid",
        "contract_number",
        "executor",
        "section_code",
        "contract_total_price",
        "agreed_amount",
        "currency",
        "prepayment",
        "final_payment",
        "advance_payment_request_number",
        "advance_payment_request_sent_at",
        "advance_payment_paid",
        "final_payment_request_number",
        "final_payment_request_sent_at",
        "final_payment_paid",
        "payment_request_sender",
    )
    list_editable = (
        "agreed_amount",
        "prepayment",
        "final_payment",
        "advance_payment_request_number",
        "advance_payment_request_sent_at",
        "advance_payment_paid",
        "final_payment_request_number",
        "final_payment_request_sent_at",
        "final_payment_paid",
    )
    list_display_links = ("id", "registration_short_uid", "contract_number")
    list_select_related = ("registration", "typical_section", "currency")
    search_fields = (
        "executor",
        "contract_number",
        "registration__short_uid",
        "registration__agreement_number",
        "registration__name",
    )
    list_filter = (
        "currency",
        "advance_payment_paid",
        "final_payment_paid",
        "advance_payment_request_sent_at",
        "final_payment_request_sent_at",
    )
    ordering = ("registration__position", "executor", "position", "id")
    readonly_fields = (
        "registration_short_uid",
        "section_code",
        "contract_batch_id",
        "contract_total_price",
    )
    fieldsets = (
        ("Строка заявки", {
            "fields": (
                "registration_short_uid",
                "registration",
                "work_item",
                "typical_section",
                "section_code",
                "executor",
                "employee",
            ),
        }),
        ("Договор и сумма", {
            "fields": (
                "contract_number",
                "contract_batch_id",
                "contract_total_price",
                "agreed_amount",
                "currency",
                "prepayment",
                "final_payment",
            ),
        }),
        ("Заявка на аванс", {
            "fields": (
                "advance_payment_request_number",
                "advance_payment_request_sent_at",
                "advance_payment_request_sender",
                "advance_payment_paid",
                "advance_payment_paid_at",
            ),
        }),
        ("Заявка на окончательный платёж", {
            "fields": (
                "final_payment_request_number",
                "final_payment_request_sent_at",
                "final_payment_request_sender",
                "final_payment_paid",
                "final_payment_paid_at",
            ),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(contract_batch_id__isnull=False)

    @admin.display(description="Проект ID", ordering="registration__short_uid")
    def registration_short_uid(self, obj):
        return getattr(obj.registration, "short_uid", "")

    @admin.display(description="Тип. раздел")
    def section_code(self, obj):
        return getattr(obj.typical_section, "code", "")

    @admin.display(description="Цена договора")
    def contract_total_price(self, obj):
        if obj.participation_batch_id:
            addendum_number = obj.contract_addendum_number or 0
            number_filter = Q(contract_addendum_number=addendum_number)
            if not addendum_number:
                number_filter |= Q(contract_addendum_number__isnull=True)
            queryset = PaymentRequestPerformer.objects.filter(
                participation_batch_id=obj.participation_batch_id,
                executor=obj.executor,
                contract_batch_id__isnull=False,
                contract_is_addendum=obj.contract_is_addendum,
            ).filter(number_filter)
        elif obj.contract_batch_id:
            queryset = PaymentRequestPerformer.objects.filter(contract_batch_id=obj.contract_batch_id)
        else:
            queryset = PaymentRequestPerformer.objects.filter(pk=obj.pk)

        return queryset.aggregate(total=Sum("agreed_amount"))["total"]

    @admin.display(description="Отправитель")
    def payment_request_sender(self, obj):
        return obj.final_payment_request_sender or obj.advance_payment_request_sender


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