from django.contrib import admin, messages
from django.middleware.csrf import get_token
from django.db.models import IntegerField, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from .models import (
    ExpertiseDirection,
    Grade,
    Product,
    SectionStructure,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalSectionSpecialty,
    TypicalServiceComposition,
    TypicalServiceTerm,
)
from users_app.models import Employee


class TimestampedAdmin(admin.ModelAdmin):
    readonly_fields = ("created_at", "updated_at")


class TypicalSectionSpecialtyInline(admin.TabularInline):
    model = TypicalSectionSpecialty
    extra = 0
    fields = ("rank", "specialty")
    ordering = ("rank", "id")


@admin.register(Product)
class ProductAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "short_name",
        "display_name",
        "name_en",
        "name_ru",
        "service_type",
        "owner_display",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("short_name",)
    search_fields = ("short_name", "display_name", "name_en", "name_ru", "service_type")
    filter_horizontal = ("owners",)
    ordering = ("position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                "short_name",
                "display_name",
                ("name_en", "name_ru"),
                "service_type",
            ),
        }),
        ("Владельцы", {
            "fields": ("is_group_owner", "owners"),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(TypicalSection)
class TypicalSectionAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "product",
        "code",
        "short_name",
        "short_name_ru",
        "name_ru",
        "accounting_type",
        "expertise_dir",
        "expertise_direction",
        "exclude_from_tkp_autofill",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("code",)
    list_select_related = ("product", "expertise_dir", "expertise_direction")
    list_filter = ("product", "accounting_type", "expertise_dir", "expertise_direction")
    search_fields = ("code", "short_name", "short_name_ru", "name_en", "name_ru", "product__short_name")
    ordering = ("product__short_name", "position", "id")
    inlines = (TypicalSectionSpecialtyInline,)
    fieldsets = (
        (None, {
            "fields": (
                "position",
                "product",
                ("code", "accounting_type"),
                ("short_name", "short_name_ru"),
                ("name_en", "name_ru"),
                ("expertise_dir", "expertise_direction"),
                "exclude_from_tkp_autofill",
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(TypicalSectionSpecialty)
class TypicalSectionSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("rank", "section", "specialty", "section_product")
    list_editable = ("rank",)
    list_display_links = ("section",)
    list_select_related = ("section", "section__product", "specialty")
    list_filter = ("section__product",)
    search_fields = (
        "section__code",
        "section__name_ru",
        "section__product__short_name",
        "specialty__specialty",
    )
    ordering = ("section__product__short_name", "section__position", "rank", "id")

    @admin.display(description="Продукт", ordering="section__product__short_name")
    def section_product(self, obj):
        return obj.section.product


@admin.register(SectionStructure)
class SectionStructureAdmin(TimestampedAdmin):
    list_display = ("position", "product", "section", "subsections", "updated_at")
    list_editable = ("position",)
    list_display_links = ("product",)
    list_select_related = ("product", "section")
    list_filter = ("product",)
    search_fields = ("product__short_name", "section__code", "section__name_ru", "subsections")
    ordering = ("product__short_name", "position", "id")
    fieldsets = (
        (None, {
            "fields": ("position", "product", "section", "subsections"),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(ServiceGoalReport)
class ServiceGoalReportAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "product",
        "service_goal",
        "service_goal_genitive",
        "report_title",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("product",)
    list_select_related = ("product",)
    list_filter = ("product",)
    search_fields = (
        "product__short_name",
        "service_goal",
        "service_goal_genitive",
        "report_title",
    )
    ordering = ("product__short_name", "position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                "product",
                "service_goal",
                "service_goal_genitive",
                "report_title",
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(TypicalServiceComposition)
class TypicalServiceCompositionAdmin(TimestampedAdmin):
    list_display = ("position", "product", "section", "service_composition", "updated_at")
    list_editable = ("position",)
    list_display_links = ("product",)
    list_select_related = ("product", "section")
    list_filter = ("product", "section")
    search_fields = ("product__short_name", "section__code", "section__name_ru", "service_composition")
    ordering = ("product__short_name", "position", "id")
    fieldsets = (
        (None, {
            "fields": ("position", "product", "section", "service_composition"),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(TypicalServiceTerm)
class TypicalServiceTermAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "product",
        "preliminary_report_months",
        "final_report_weeks",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("product",)
    list_select_related = ("product",)
    list_filter = ("product",)
    search_fields = ("product__short_name",)
    ordering = ("product__short_name", "position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                "product",
                "preliminary_report_months",
                "final_report_weeks",
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(ExpertiseDirection)
class ExpertiseDirectionAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "short_name",
        "name",
        "pricing_method",
        "owner_display",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("short_name",)
    search_fields = ("name", "short_name", "pricing_method")
    filter_horizontal = ("owners",)
    ordering = ("position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                ("short_name", "name"),
                "pricing_method",
            ),
        }),
        ("Владельцы", {
            "fields": ("is_group_owner", "owners"),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(Grade)
class GradeAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "grade_en",
        "grade_ru",
        "qualification_levels",
        "qualification",
        "is_base_rate",
        "base_rate_share",
        "hourly_rate",
        "currency",
        "created_by",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("grade_en",)
    list_select_related = ("currency", "created_by")
    list_filter = ("is_base_rate", "currency", "created_by")
    search_fields = ("grade_en", "grade_ru", "created_by__username")
    ordering = ("created_by", "position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                ("grade_en", "grade_ru"),
                ("qualification_levels", "qualification"),
                ("is_base_rate", "base_rate_share"),
                ("hourly_rate", "currency"),
                "created_by",
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(SpecialtyTariff)
class SpecialtyTariffAdmin(TimestampedAdmin):
    list_display = (
        "position",
        "specialty_group",
        "expertise_direction_display",
        "daily_rate_tkp_eur",
        "daily_rate_ss",
        "currency",
        "created_by",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("specialty_group",)
    list_select_related = ("currency", "created_by", "expertise_direction")
    list_filter = ("currency", "created_by")
    search_fields = ("specialty_group", "specialties__specialty", "created_by__username")
    filter_horizontal = ("specialties",)
    ordering = ("created_by", "position", "id")
    fieldsets = (
        (None, {
            "fields": (
                "position",
                "specialty_group",
                "specialties",
                "expertise_direction",
                ("daily_rate_tkp_eur", "daily_rate_ss"),
                ("currency", "created_by"),
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(Tariff)
class TariffAdmin(TimestampedAdmin):
    list_display = (
        "group_position",
        "position",
        "product",
        "section",
        "base_rate_vpm",
        "service_hours",
        "service_days_tkp",
        "created_by",
        "group_order_controls",
        "updated_at",
    )
    list_editable = ("position",)
    list_display_links = ("product",)
    list_select_related = ("product", "section", "created_by", "created_by__employee_profile")
    list_filter = ("product", "section", "created_by")
    search_fields = (
        "product__short_name",
        "section__code",
        "section__name_ru",
        "created_by__username",
    )
    fieldsets = (
        (None, {
            "fields": (
                "position",
                ("product", "section"),
                ("base_rate_vpm", "service_hours", "service_days_tkp"),
                "created_by",
            ),
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "product",
            "section",
            "created_by",
            "created_by__employee_profile",
        ).annotate(
            owner_group_position=Coalesce(
                "created_by__employee_profile__position",
                Value(1000000),
                output_field=IntegerField(),
            )
        ).order_by(
            "owner_group_position",
            "created_by__employee_profile__job_title",
            "created_by__username",
            "position",
            "id",
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:object_id>/move-owner-up/",
                self.admin_site.admin_view(require_POST(self.move_owner_up)),
                name="policy_app_tariff_move_owner_up",
            ),
            path(
                "<int:object_id>/move-owner-down/",
                self.admin_site.admin_view(require_POST(self.move_owner_down)),
                name="policy_app_tariff_move_owner_down",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        self._changelist_request = request
        return super().changelist_view(request, extra_context=extra_context)

    def _swap_owner_position(self, request, object_id: int, direction: str):
        tariff = get_object_or_404(
            Tariff.objects.select_related("created_by", "created_by__employee_profile"),
            pk=object_id,
        )
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Менять порядок групп может только суперпользователь.",
                level=messages.WARNING,
            )
            return redirect(reverse("admin:policy_app_tariff_changelist"))

        profile = getattr(tariff.created_by, "employee_profile", None)
        if profile is None:
            self.message_user(
                request,
                "У выбранного руководителя нет профиля сотрудника, порядок группы изменить нельзя.",
                level=messages.WARNING,
            )
            return redirect(reverse("admin:policy_app_tariff_changelist"))

        owner_ids = list(Tariff.objects.order_by().values_list("created_by_id", flat=True).distinct())
        profiles = list(
            Employee.objects.filter(user_id__in=owner_ids)
            .select_related("user")
            .order_by("position", "id")
        )
        current_idx = next((idx for idx, item in enumerate(profiles) if item.pk == profile.pk), None)
        if current_idx is None:
            self.message_user(
                request,
                "Профиль руководителя не найден в списке групп тарифов.",
                level=messages.WARNING,
            )
            return redirect(reverse("admin:policy_app_tariff_changelist"))

        neighbor_idx = current_idx - 1 if direction == "up" else current_idx + 1
        if neighbor_idx < 0 or neighbor_idx >= len(profiles):
            return redirect(reverse("admin:policy_app_tariff_changelist"))

        neighbor = profiles[neighbor_idx]
        profile.position, neighbor.position = neighbor.position, profile.position
        profile.save(update_fields=["position"])
        neighbor.save(update_fields=["position"])
        return redirect(reverse("admin:policy_app_tariff_changelist"))

    def move_owner_up(self, request, object_id: int):
        return self._swap_owner_position(request, object_id, "up")

    def move_owner_down(self, request, object_id: int):
        return self._swap_owner_position(request, object_id, "down")

    @admin.display(description="Позиция группы", ordering="owner_group_position")
    def group_position(self, obj):
        profile = getattr(obj.created_by, "employee_profile", None)
        return getattr(profile, "position", "—")

    @admin.display(description="Порядок группы")
    def group_order_controls(self, obj):
        if not obj.created_by_id:
            return "—"
        request = getattr(self, "_changelist_request", None)
        csrf_token = get_token(request) if request is not None else ""
        up_url = reverse("admin:policy_app_tariff_move_owner_up", args=[obj.pk])
        down_url = reverse("admin:policy_app_tariff_move_owner_down", args=[obj.pk])
        return format_html(
            '<form method="post" action="{}" style="display:inline-block; margin:0;">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" class="button" title="Поднять группу вверх">↑</button>'
            "</form>&nbsp;"
            '<form method="post" action="{}" style="display:inline-block; margin:0;">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" class="button" title="Опустить группу вниз">↓</button>'
            "</form>",
            up_url,
            csrf_token,
            down_url,
            csrf_token,
        )