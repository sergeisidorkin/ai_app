import csv
import copy
import io
import json
import calendar
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from zipfile import BadZipFile

from docx.opc.exceptions import PackageNotFoundError
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import IntegerField, Max, Q, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse, QueryDict
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from experts_app.models import ExpertProfile, ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from .models import (
    ConsultingDirection,
    ConsultingDirectionType,
    ConsultingServiceSubtype,
    ConsultingServiceType,
    Product,
    SYSTEM_DSC_SECTION_CODE,
    TypicalSection,
    TypicalSectionSpecialty,
    SectionStructure,
    ReportStructure,
    ServiceGoalReport,
    TypicalServiceComposition,
    TypicalServiceTerm,
    ExpertiseDirection,
    Grade,
    SpecialtyTariff,
    Tariff,
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUPS,
    MANAGER_GROUPS,
    build_consulting_catalog_meta,
    ensure_system_dsc_section,
    is_system_dsc_code,
)
from .forms import (
    ConsultingDirectionForm,
    OWNER_GROUP_VALUE,
    ProductForm,
    TypicalSectionForm,
    SectionStructureForm,
    _policy_section_display_label,
    _policy_section_option_label,
    ReportStructureForm,
    ServiceGoalReportForm,
    TypicalServiceCompositionForm,
    TypicalServiceTermForm,
    ExpertiseDirectionForm,
    GradeForm,
    SpecialtyTariffForm,
    TariffForm,
)
from .docx_service_compositions import (
    build_typical_service_compositions_docx,
    parse_typical_service_compositions_docx,
)
from .cache import (
    get_or_build_policy_catalog,
    schedule_policy_cache_invalidation,
)
from .querysets import (
    ordered_owner_display_prefetch,
    ordered_specialties_display_prefetch,
    policy_consulting_directions_queryset,
)

# Вынесенные константы для единообразия шаблонов/заголовков
POLICY_PARTIAL_TEMPLATE = "policy_app/policy_partial.html"
POLICY_EXPERTISE_DIRECTIONS_TABLE_TEMPLATE = "policy_app/policy_expertise_directions_table.html"
POLICY_CONSULTING_DIRECTIONS_TABLE_TEMPLATE = "policy_app/policy_consulting_directions_table.html"
POLICY_PRODUCTS_TABLE_TEMPLATE = "policy_app/policy_products_table.html"
POLICY_SERVICE_GOAL_REPORTS_TABLE_TEMPLATE = "policy_app/policy_service_goal_reports_table.html"
POLICY_TYPICAL_SECTIONS_TABLE_TEMPLATE = "policy_app/policy_typical_sections_table.html"
POLICY_SECTION_STRUCTURES_TABLE_TEMPLATE = "policy_app/policy_section_structures_table.html"
POLICY_REPORT_STRUCTURES_TABLE_TEMPLATE = "policy_app/policy_report_structures_table.html"
POLICY_TYPICAL_SERVICE_COMPOSITIONS_TABLE_TEMPLATE = "policy_app/policy_typical_service_compositions_table.html"
POLICY_TYPICAL_SERVICE_TERMS_TABLE_TEMPLATE = "policy_app/policy_typical_service_terms_table.html"
POLICY_GRADES_TABLE_TEMPLATE = "policy_app/policy_grades_table.html"
POLICY_EXPERT_SPECIALTIES_TABLE_TEMPLATE = "policy_app/policy_expert_specialties_table.html"
POLICY_SPECIALTY_TARIFFS_TABLE_TEMPLATE = "policy_app/policy_specialty_tariffs_table.html"
POLICY_TARIFFS_TABLE_TEMPLATE = "policy_app/policy_tariffs_table.html"
PRODUCT_WORKSPACE_TEMPLATE = "policy_app/product_workspace.html"
PRODUCT_FORM_TEMPLATE = "policy_app/product_form.html"
SECTION_FORM_TEMPLATE = "policy_app/section_form.html"
STRUCTURE_FORM_TEMPLATE = "policy_app/structure_form.html"
REPORT_STRUCTURE_FORM_TEMPLATE = "policy_app/report_structure_form.html"
SERVICE_GOAL_REPORT_FORM_TEMPLATE = "policy_app/service_goal_report_form.html"
TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE = "policy_app/typical_service_composition_form.html"
TYPICAL_SERVICE_TERM_FORM_TEMPLATE = "policy_app/typical_service_term_form.html"
EXPERTISE_DIR_FORM_TEMPLATE = "policy_app/expertise_direction_form.html"
CONSULTING_DIR_FORM_TEMPLATE = "policy_app/consulting_direction_form.html"
GRADE_FORM_TEMPLATE = "policy_app/grade_form.html"
SPECIALTY_TARIFF_FORM_TEMPLATE = "policy_app/specialty_tariff_form.html"
TARIFF_FORM_TEMPLATE = "policy_app/tariff_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_POLICY_UPDATED_EVENT = "policy-updated"
POLICY_TABLE_PAGE_SIZE = 25
POLICY_TABLE_PAGE_SIZE_OPTIONS = (25, 50, 100)
PRODUCT_CSV_HEADERS = [
    "Краткое имя",
    "Наименование на английском языке",
    "Наименование на русском языке",
    "Отображаемое в системе имя",
    "Вид консалтинга",
    "Тип услуг",
    "Код",
    "Подтип услуги",
    "Владелец",
]
SERVICE_GOAL_REPORT_CSV_HEADERS = [
    "Продукт",
    "Цели оказания услуг",
    "Цели оказания услуг в родительном падеже",
    "Титул отчета/ТКП",
    "Название продукта",
]
STRUCTURE_CSV_HEADERS = [
    "Продукт",
    "Код",
    "Раздел (услуга)",
    "Подразделы",
]
REPORT_STRUCTURE_CSV_HEADERS = [
    "Продукт",
    "Уровень",
    "Номер",
    "Код",
    "Наименование отчета, раздела (подраздела)",
]
TYPICAL_SERVICE_COMPOSITION_CSV_HEADERS = [
    "Продукт",
    "Код",
    "Раздел (услуга)",
    "Состав услуг",
]
TYPICAL_SERVICE_COMPOSITION_XLSX_HEADERS = [
    "Продукт",
    "Код",
    "Раздел (услуга)",
    "Состав услуг",
]
TYPICAL_SERVICE_COMPOSITION_EDITOR_STATE_HEADER = "Состояние редактора (JSON)"
TYPICAL_SERVICE_TERM_CSV_HEADERS = [
    "Продукт",
    "Сроки предоставления исходных данных",
    "Единица срока предоставления исходных данных",
    "Срок подготовки Предварительного отчёта",
    "Единица срока подготовки Предварительного отчёта",
    "Срок подготовки Итогового отчёта",
    "Единица срока подготовки Итогового отчёта",
]
TYPICAL_SERVICE_TERM_GANTT_VERSION = 1
TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE = "service_section"
TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT = "abstract"
TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR = "executor"
TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE = "resource_name"
TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT = {
    "source_data": "Исходные данные",
    "source_data_asset": "Актив",
    "preliminary_report": "Предварительный отчёт",
    "preliminary_report_asset": "Актив",
    "preliminary_report_submission": "Отправка Предварительного отчёта",
    "final_report": "Итоговый отчёт",
}
TARIFF_CSV_HEADERS = [
    "Продукт",
    "Код",
    "Раздел (услуга)",
    "Базовая ставка в ВПМ",
    "Объем услуг в часах",
    "Объем услуг в днях для ТКП",
    "Руководитель направления",
]
SECTION_CSV_HEADERS = [
    "Продукт",
    "Код",
    "Краткое имя EN",
    "Краткое имя RU",
    "Наименование раздела (услуги) EN",
    "Наименование раздела (услуги) RU",
    "Тип учета",
    "Исполнитель",
    "Экспертиза",
    "Подразделение",
    "ТКП",
]


def _render_form_with_errors(request, template, context):
    response = render(request, template, context)
    response["HX-Retarget"] = "#policy-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


def _is_department_head(user):
    return user.groups.filter(name__in=MANAGER_GROUPS).exists()


def _get_grades_for_user(user):
    qs = Grade.objects.select_related("created_by", "created_by__employee_profile", "currency")
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs


def _get_tariffs_for_user(user):
    qs = Tariff.objects.select_related(
        "product",
        "product__consulting_type_ref",
        "product__service_category_ref",
        "product__service_subtype_ref",
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
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs


def _get_specialty_tariffs_for_user(user):
    qs = SpecialtyTariff.objects.select_related(
        "currency", "created_by", "created_by__employee_profile"
    ).prefetch_related(ordered_specialties_display_prefetch())
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs

def staff_required(user):
    return user.is_authenticated and user.is_staff


def _csv_lookup_key(value):
    return str(value or "").strip().lower()


def _csv_header_index(headers, header_name):
    lookup_name = _csv_lookup_key(header_name)
    for idx, value in enumerate(headers):
        if _csv_lookup_key(value) == lookup_name:
            return idx
    return None


def _csv_row_value(row, index):
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _csv_required_columns_present(row, indexes):
    return all(index is not None and index < len(row) for index in indexes)


def _resolve_section_from_import(sections_by_product, product_id, section_code, section_name):
    lookup = sections_by_product[product_id]
    section_code = str(section_code or "").strip()
    section_name = str(section_name or "").strip()
    if section_code:
        section = lookup.get(_csv_lookup_key(section_code))
        if section:
            return section
    if section_name:
        return lookup.get(_csv_lookup_key(section_name))
    return None


def _split_csv_list_value(value, lookup=None):
    raw = str(value or "").strip()
    if not raw or raw in {"—", "-"}:
        return []
    lookup = lookup or {}
    if _csv_lookup_key(raw) in lookup:
        return [raw]

    values = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        parts = [line]
        for separator in (",", ";", "|"):
            parts = [
                chunk
                for part in parts
                for chunk in (
                    [part] if _csv_lookup_key(part) in lookup else part.split(separator)
                )
            ]
        values.extend(
            item.strip()
            for item in parts
            if item.strip() and item.strip() not in {"—", "-"}
        )
    return values


def _csv_truthy(value):
    return _csv_lookup_key(value) in {"1", "true", "yes", "y", "да", "д", "on", "checked", "истина", "+", "x", "✓"}


def _coerce_report_level(value):
    try:
        level = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return level if 0 <= level <= 9 else None


def _report_structure_number_for_level(counters, level):
    if level == 0:
        counters.clear()
        return "0"
    if len(counters) < level:
        counters.extend([0] * (level - len(counters)))
    else:
        del counters[level:]
    counters[level - 1] += 1
    return ".".join(str(value) for value in counters[:level])


def _build_report_structure_numbers(items):
    counters_by_product = defaultdict(list)
    numbers = {}
    for item in items:
        product_id = item["product_id"] if isinstance(item, dict) else item.product_id
        level = _coerce_report_level(item["level"] if isinstance(item, dict) else item.level)
        if product_id is None or level is None:
            continue
        number = _report_structure_number_for_level(counters_by_product[product_id], level)
        key = item.get("key") if isinstance(item, dict) else getattr(item, "pk", None)
        if key is not None:
            numbers[key] = number
    return numbers


def _ordered_report_structures_queryset():
    return ReportStructure.objects.select_related(
        "product",
        "product__consulting_type_ref",
        "product__service_category_ref",
        "product__service_subtype_ref",
    ).order_by("product__position", "product_id", "position", "id")


def _report_structure_items_by_product_json():
    grouped = defaultdict(list)
    for item in ReportStructure.objects.order_by("product__position", "product_id", "position", "id").only("id", "product_id", "level", "position"):
        grouped[item.product_id].append({
            "id": item.pk,
            "level": item.level,
            "position": item.position,
        })
    return json.dumps(grouped, ensure_ascii=False)


def _report_structure_number_preview(product_id, level, report_structure=None):
    product_id = _positive_int(product_id)
    level = _coerce_report_level(level)
    if product_id is None or level is None:
        return ""
    preview_key = "__preview__"
    items = []
    inserted = False
    current_id = report_structure.pk if report_structure and report_structure.pk else None
    original_product_id = report_structure.product_id if report_structure and report_structure.pk else None
    for item in ReportStructure.objects.filter(product_id=product_id).order_by("position", "id").only("id", "product_id", "level", "position"):
        if current_id and item.pk == current_id:
            if original_product_id == product_id:
                items.append({"key": preview_key, "product_id": product_id, "level": level})
                inserted = True
            continue
        items.append(item)
    if not inserted:
        items.append({"key": preview_key, "product_id": product_id, "level": level})
    return _build_report_structure_numbers(items).get(preview_key, "")


def _report_structure_form_initial_number(form, report_structure=None):
    if form.is_bound:
        product_id = form.data.get("product")
        level = form.data.get("level")
    elif report_structure and report_structure.pk:
        product_id = report_structure.product_id
        level = report_structure.level
    else:
        product_id = form.initial.get("product")
        level = form.initial.get("level", 0)
    return _report_structure_number_preview(product_id, level, report_structure)

def _policy_expertise_directions_context(request):
    return {
        "expertise_directions": ExpertiseDirection.objects.prefetch_related(
            ordered_owner_display_prefetch()
        ).order_by("position", "id"),
    }


def _policy_consulting_directions_context(request):
    return {"consulting_directions": policy_consulting_directions_queryset()}


def _policy_products_queryset():
    return (
        Product.objects.select_related(
            "consulting_type_ref", "service_category_ref", "service_subtype_ref"
        )
        .prefetch_related(ordered_owner_display_prefetch())
        .order_by("position", "id")
    )


def _policy_products_context(request):
    return {"products": _policy_products_queryset()}


def _policy_service_goal_reports_queryset():
    return (
        ServiceGoalReport.objects.select_related(
            "product",
            "product__consulting_type_ref",
            "product__service_category_ref",
            "product__service_subtype_ref",
        ).order_by("position", "id")
    )


def _policy_service_goal_reports_context(request):
    return {"service_goal_reports": _policy_service_goal_reports_queryset()}


def _policy_typical_sections_queryset():
    return (
        TypicalSection.objects.select_related(
            "product",
            "product__consulting_type_ref",
            "product__service_category_ref",
            "product__service_subtype_ref",
            "expertise_dir",
            "expertise_direction",
        )
        .prefetch_related("ranked_specialties", "ranked_specialties__specialty")
        .order_by("product__short_name", "position", "id")
    )


def _policy_typical_sections_context(request):
    return {"sections": _policy_typical_sections_queryset()}


def _is_policy_workspace_request(request):
    value = str(request.GET.get("workspace") or "").strip().lower()
    return value in {"1", "true", "yes"}


def _policy_filter_query_without_page(request):
    filter_query = request.GET.copy()
    filter_query.pop("page", None)
    filter_query.pop("page_size", None)
    filter_query.pop("workspace", None)
    return filter_query


def _policy_unpaged_context(request, queryset):
    objects = list(queryset)
    return {
        "policy_pagination_enabled": False,
        "page_obj": SimpleNamespace(object_list=objects, number=1),
        "paginator": None,
        "policy_pagination_pages": [],
        "policy_pagination_previous_url": "",
        "policy_pagination_next_url": "",
        "policy_pagination_start": 1 if objects else 0,
        "policy_pagination_end": len(objects),
        "policy_page_size": len(objects) or POLICY_TABLE_PAGE_SIZE,
        "policy_page_size_options": POLICY_TABLE_PAGE_SIZE_OPTIONS,
        "policy_page_size_url": "",
        "policy_filter_query": _policy_filter_query_without_page(request).urlencode(),
        "policy_workspace": True,
    }


def _policy_pagination_context(request, queryset):
    if _is_policy_workspace_request(request):
        return _policy_unpaged_context(request, queryset)
    try:
        page_size = int(request.GET.get("page_size", POLICY_TABLE_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = POLICY_TABLE_PAGE_SIZE
    if page_size not in POLICY_TABLE_PAGE_SIZE_OPTIONS:
        page_size = POLICY_TABLE_PAGE_SIZE

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = _policy_filter_query_without_page(request)

    def page_url(page_number):
        page_query = filter_query.copy()
        page_query["page_size"] = page_size
        page_query["page"] = page_number
        return f"{request.path}?{page_query.urlencode()}"

    page_size_query = filter_query.copy()
    page_size_query["page"] = 1
    page_size_url = f"{request.path}?{page_size_query.urlencode()}"

    pagination_pages = []
    for page_number in paginator.get_elided_page_range(page_obj.number):
        if page_number == paginator.ELLIPSIS:
            pagination_pages.append({"ellipsis": True})
        else:
            pagination_pages.append(
                {
                    "number": page_number,
                    "url": page_url(page_number),
                    "current": page_number == page_obj.number,
                }
            )

    return {
        "policy_pagination_enabled": True,
        "page_obj": page_obj,
        "paginator": paginator,
        "policy_pagination_pages": pagination_pages,
        "policy_pagination_previous_url": page_url(page_obj.previous_page_number())
        if page_obj.has_previous()
        else "",
        "policy_pagination_next_url": page_url(page_obj.next_page_number())
        if page_obj.has_next()
        else "",
        "policy_pagination_start": page_obj.start_index(),
        "policy_pagination_end": page_obj.end_index(),
        "policy_page_size": page_size,
        "policy_page_size_options": POLICY_TABLE_PAGE_SIZE_OPTIONS,
        "policy_page_size_url": page_size_url,
        "policy_filter_query": filter_query.urlencode(),
        "policy_workspace": False,
    }


def _typical_section_inline_options():
    departments = OrgUnit.objects.filter(
        Q(unit_type="expertise") | Q(unit_type="administrative", level=1)
    ).order_by("department_name", "id")
    return {
        "accounting_types": [
            {"value": value, "label": label}
            for value, label in TypicalSection.ACCOUNTING_TYPE_CHOICES
        ],
        "expertise_dirs": [
            {"id": item.pk, "label": item.short_name}
            for item in ExpertiseDirection.objects.order_by("position", "id")
        ],
        "departments": [
            {"id": item.pk, "label": item.department_name}
            for item in departments
        ],
        "specialties": _section_specialty_options(),
    }


def _policy_typical_sections_table_context(request):
    sections = _apply_policy_master_product_filters(
        _policy_typical_sections_queryset(),
        request,
    )
    context = _policy_pagination_context(request, sections)
    context["sections"] = context["page_obj"].object_list
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        context["policy_inline_options_json"] = json.dumps(
            _typical_section_inline_options(),
            ensure_ascii=False,
        )
    return context


def _policy_section_structures_queryset():
    return (
        SectionStructure.objects.select_related(
            "product",
            "product__consulting_type_ref",
            "product__service_category_ref",
            "product__service_subtype_ref",
            "section",
        ).order_by("position", "id")
    )


def _policy_section_structures_context(request):
    return {"structures": _policy_section_structures_queryset()}


def _policy_report_structures_context(request):
    report_structures = list(_ordered_report_structures_queryset())
    report_structure_numbers = _build_report_structure_numbers(report_structures)
    for report_structure in report_structures:
        report_structure.display_number = report_structure_numbers.get(report_structure.pk, "")
    return {"report_structures": report_structures}


def _policy_typical_service_compositions_queryset():
    return (
        TypicalServiceComposition.objects.select_related(
            "product",
            "product__consulting_type_ref",
            "product__service_category_ref",
            "product__service_subtype_ref",
            "section",
        ).order_by("position", "id")
    )


def _policy_typical_service_compositions_context(request):
    return {
        "typical_service_compositions": _policy_typical_service_compositions_queryset(),
    }


def _policy_typical_service_terms_queryset():
    return (
        TypicalServiceTerm.objects.select_related(
            "product",
            "product__consulting_type_ref",
            "product__service_category_ref",
            "product__service_subtype_ref",
        ).order_by("position", "id")
    )


def _policy_typical_service_terms_context(request):
    return {"typical_service_terms": _policy_typical_service_terms_queryset()}


def _policy_grades_context(request):
    return {
        "grades": _get_grades_for_user(request.user),
        "is_admin": request.user.is_superuser,
        "is_dept_head": _is_department_head(request.user),
    }


def _policy_expert_specialties_context(request):
    from experts_app.views import _specialties_queryset

    return {"specialties": _specialties_queryset()}


def _policy_expert_specialties_table_context(request):
    from experts_app.views import _specialties_queryset

    context = _policy_pagination_context(request, _specialties_queryset())
    context["specialties"] = context["page_obj"].object_list
    return context


def _policy_specialty_tariffs_context(request):
    return {
        "specialty_tariffs": _get_specialty_tariffs_for_user(request.user),
        "is_admin": request.user.is_superuser,
    }


def _policy_tariffs_context(request):
    return {
        "tariffs": _get_tariffs_for_user(request.user),
        "is_admin": request.user.is_superuser,
    }


def _policy_paginated_table_context(
    request,
    queryset,
    context_key,
    *,
    products=False,
):
    if products:
        filtered = _apply_policy_master_filters_to_products(queryset, request)
    else:
        filtered = _apply_policy_master_product_filters(queryset, request)
    context = _policy_pagination_context(request, filtered)
    context[context_key] = context["page_obj"].object_list
    return context


def _policy_products_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _policy_products_queryset(),
        "products",
        products=True,
    )
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        context["policy_inline_options_json"] = json.dumps(
            {
                "catalog": build_consulting_catalog_meta(),
                "owners": list(GroupMember.objects.order_by("position", "id").values("pk", "short_name")),
            },
            ensure_ascii=False,
        )
        for product in context["products"]:
            product.inline_owner_ids_json = json.dumps(_product_inline_owner_ids(product), ensure_ascii=False)
    return context


def _policy_service_goal_reports_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _policy_service_goal_reports_queryset(),
        "service_goal_reports",
    )
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
    return context


def _section_structure_inline_options(product_id):
    qs = TypicalSection.objects.none()
    if product_id:
        qs = TypicalSection.objects.filter(product_id=product_id).order_by("position", "id")
    return {
        "sections": [
            {
                "id": section.pk,
                "code": section.code or "",
                "label": _policy_section_option_label(section),
                "displayLabel": _policy_section_display_label(section),
            }
            for section in qs
        ]
    }


def _policy_section_structures_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _policy_section_structures_queryset(),
        "structures",
    )
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        context["policy_inline_options_json"] = json.dumps(
            _section_structure_inline_options(_positive_int(request.GET.get("product"))),
            ensure_ascii=False,
        )
    return context


def _policy_report_structures_table_context(request):
    filtered = _apply_policy_master_product_filters(
        _ordered_report_structures_queryset(),
        request,
    )
    context = _policy_pagination_context(request, filtered)
    number_items = (
        {"key": item["id"], "product_id": item["product_id"], "level": item["level"]}
        for item in filtered.values("id", "product_id", "level")
    )
    report_structure_numbers = _build_report_structure_numbers(number_items)
    report_structures = context["page_obj"].object_list
    for report_structure in report_structures:
        report_structure.display_number = report_structure_numbers.get(report_structure.pk, "")
    context["report_structures"] = report_structures
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
    return context


def _policy_typical_service_compositions_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _policy_typical_service_compositions_queryset(),
        "typical_service_compositions",
    )
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        context["policy_inline_options_json"] = json.dumps(
            _section_structure_inline_options(_positive_int(request.GET.get("product"))),
            ensure_ascii=False,
        )
        for item in context.get("typical_service_compositions") or []:
            state = item.service_composition_editor_state or {}
            if not isinstance(state, dict):
                state = {}
            item.inline_editor_state_json = json.dumps(
                {
                    "html": str(state.get("html") or ""),
                    "plain_text": str(state.get("plain_text") or item.service_composition or ""),
                },
                ensure_ascii=False,
            )
    return context


def _typical_service_term_inline_options():
    return {
        "units": [
            {"value": value, "label": label}
            for value, label in TypicalServiceTerm.TermUnit.choices
        ]
    }


def _policy_typical_service_terms_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _policy_typical_service_terms_queryset(),
        "typical_service_terms",
    )
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        context["policy_inline_options_json"] = json.dumps(
            _typical_service_term_inline_options(),
            ensure_ascii=False,
        )
    return context


def _tariff_inline_owner_options(extra_user_ids=None):
    user_model = get_user_model()
    group_q = Q(groups__name__in=(DEPARTMENT_HEAD_GROUP, *DIRECTOR_GROUPS))
    extra_ids = [int(uid) for uid in (extra_user_ids or []) if uid]
    qs = user_model.objects.filter(group_q)
    if extra_ids:
        qs = user_model.objects.filter(group_q | Q(pk__in=extra_ids))
    return [
        {
            "id": user.pk,
            "label": _tariff_owner_label(user),
        }
        for user in qs.select_related("employee_profile").distinct().order_by(
            "last_name", "first_name", "username"
        )
    ]


def _tariff_inline_options(product_id, extra_owner_ids=None):
    options = _section_structure_inline_options(product_id)
    options["owners"] = _tariff_inline_owner_options(extra_owner_ids)
    return options


def _policy_tariffs_table_context(request):
    context = _policy_paginated_table_context(
        request,
        _get_tariffs_for_user(request.user),
        "tariffs",
    )
    context["is_admin"] = request.user.is_superuser
    if context.get("policy_workspace") and getattr(request.user, "is_staff", False):
        context["policy_inline_edit"] = True
        extra_owner_ids = [
            item.created_by_id
            for item in context.get("tariffs") or []
            if getattr(item, "created_by_id", None)
        ]
        context["policy_inline_options_json"] = json.dumps(
            _tariff_inline_options(
                _positive_int(request.GET.get("product")),
                extra_owner_ids,
            ),
            ensure_ascii=False,
        )
    return context


# Вспомогательная функция для полной компоновки панели.
def _policy_context(request):
    context = {}
    for builder in (
        _policy_expertise_directions_context,
        _policy_consulting_directions_context,
        _policy_products_context,
        _policy_service_goal_reports_context,
        _policy_typical_sections_context,
        _policy_section_structures_context,
        _policy_report_structures_context,
        _policy_typical_service_compositions_context,
        _policy_typical_service_terms_context,
        _policy_grades_context,
        _policy_expert_specialties_context,
        _policy_specialty_tariffs_context,
        _policy_tariffs_context,
    ):
        context.update(builder(request))
    return context


def _policy_filter_catalog_data():
    products = Product.objects.select_related(
        "consulting_type_ref",
        "service_category_ref",
        "service_subtype_ref",
    ).order_by("position", "id")
    product_items = []
    options = {
        "consulting": [],
        "category": [],
        "subtype": [],
        "product": [],
    }
    seen = {key: set() for key in ("consulting", "category", "subtype")}

    for product in products:
        label = " ".join(part for part in (product.short_name, product.display_name) if part)
        item = {
            "id": product.pk,
            "label": label,
            "consulting": product.consulting_type_display,
            "category": product.service_category_display,
            "subtype": product.service_subtype_display,
            "consulting_ref_id": product.consulting_type_ref_id,
            "category_ref_id": product.service_category_ref_id,
            "subtype_ref_id": product.service_subtype_ref_id,
        }
        product_items.append(item)
        options["product"].append({"id": product.pk, "label": label})
        for key in ("consulting", "category", "subtype"):
            value = item[key]
            if value and value not in seen[key]:
                seen[key].add(value)
                options[key].append(value)

    return {"products": product_items, "options": options}


def _render_policy_legacy_updated(request):
    response = render(request, POLICY_PARTIAL_TEMPLATE, _policy_context(request))
    response[HX_TRIGGER_HEADER] = HX_POLICY_UPDATED_EVENT
    return response


def _is_htmx_request(request):
    return request.headers.get("HX-Request", "").lower() == "true"


POLICY_MUTATION_DEPENDENCIES = {
    "consulting-direction": {
        "tables": (
            "consulting-directions",
            "products",
            "service-goal-reports",
            "typical-sections",
            "section-structures",
            "report-structures",
            "typical-service-compositions",
            "typical-service-terms",
            "tariffs",
        ),
        "refresh_filters": True,
    },
    "product": {
        "tables": (
            "consulting-directions",
            "products",
            "service-goal-reports",
            "typical-sections",
            "section-structures",
            "report-structures",
            "typical-service-compositions",
            "typical-service-terms",
            "tariffs",
        ),
        "refresh_filters": True,
    },
    "product-defaults": {"tables": ("products",)},
    "expertise-direction": {
        "tables": ("expertise-directions", "typical-sections", "specialty-tariffs"),
    },
    "typical-section": {
        "tables": (
            "typical-sections",
            "section-structures",
            "typical-service-compositions",
            "tariffs",
        ),
    },
    "section-structure": {"tables": ("section-structures",)},
    "report-structure": {"tables": ("report-structures",)},
    "service-goal-report": {"tables": ("service-goal-reports",)},
    "typical-service-composition": {"tables": ("typical-service-compositions",)},
    "typical-service-term": {"tables": ("typical-service-terms",)},
    "grade": {"tables": ("grades",)},
    "expert-specialty": {
        "tables": ("expert-specialties", "specialty-tariffs", "typical-sections"),
    },
    "specialty-tariff": {"tables": ("specialty-tariffs",)},
    "tariff": {"tables": ("tariffs",)},
}

POLICY_MUTATION_URL_ENTITY = {
    url_name: entity
    for entity, url_names in {
        "consulting-direction": (
            "consulting_dir_form_create", "consulting_dir_form_edit", "consulting_dir_delete",
            "consulting_dir_move_up", "consulting_dir_move_down",
        ),
        "product": (
            "product_form_create", "product_form_edit", "product_delete", "product_csv_upload",
            "product_move_up", "product_move_down", "product_workspace_save",
        ),
        "typical-section": (
            "section_form_create", "section_form_edit", "section_delete", "section_csv_upload",
            "section_move_up", "section_move_down",
        ),
        "section-structure": (
            "structure_form_create", "structure_form_edit", "structure_delete", "structure_csv_upload",
            "structure_move_up", "structure_move_down",
        ),
        "report-structure": (
            "report_structure_form_create", "report_structure_form_edit", "report_structure_delete",
            "report_structure_csv_upload", "report_structure_move_up", "report_structure_move_down",
        ),
        "service-goal-report": (
            "service_goal_report_form_create", "service_goal_report_form_edit",
            "service_goal_report_delete", "service_goal_report_csv_upload",
            "service_goal_report_move_up", "service_goal_report_move_down",
        ),
        "typical-service-composition": (
            "typical_service_composition_form_create", "typical_service_composition_form_edit",
            "typical_service_composition_delete", "typical_service_composition_csv_upload",
            "typical_service_composition_docx_upload", "typical_service_composition_xlsx_upload",
            "typical_service_composition_move_up", "typical_service_composition_move_down",
        ),
        "typical-service-term": (
            "typical_service_term_form_create", "typical_service_term_form_edit",
            "typical_service_term_gantt", "typical_service_term_delete",
            "typical_service_term_csv_upload", "typical_service_term_move_up",
            "typical_service_term_move_down",
        ),
        "expertise-direction": (
            "expertise_dir_form_create", "expertise_dir_form_edit", "expertise_dir_delete",
            "expertise_dir_move_up", "expertise_dir_move_down",
        ),
        "grade": (
            "grade_form_create", "grade_form_edit", "grade_delete", "grade_move_up", "grade_move_down",
        ),
        "expert-specialty": (
            "esp_form_create", "esp_form_edit", "esp_delete", "esp_csv_upload",
            "esp_move_up", "esp_move_down",
        ),
        "specialty-tariff": (
            "specialty_tariff_form_create", "specialty_tariff_form_edit", "specialty_tariff_delete",
            "specialty_tariff_move_up", "specialty_tariff_move_down",
        ),
        "tariff": (
            "tariff_form_create", "tariff_form_edit", "tariff_delete", "tariff_csv_upload",
            "tariff_move_up", "tariff_move_down",
        ),
    }.items()
    for url_name in url_names
}

POLICY_PRODUCT_REORDER_URL_NAMES = {"product_move_up", "product_move_down"}

POLICY_ENTITY_TABLE_KEY = {
    "consulting-direction": "consulting-directions",
    "product": "products",
    "typical-section": "typical-sections",
    "section-structure": "section-structures",
    "report-structure": "report-structures",
    "service-goal-report": "service-goal-reports",
    "typical-service-composition": "typical-service-compositions",
    "typical-service-term": "typical-service-terms",
    "expertise-direction": "expertise-directions",
    "grade": "grades",
    "expert-specialty": "expert-specialties",
    "specialty-tariff": "specialty-tariffs",
    "tariff": "tariffs",
}

POLICY_REORDER_URL_NAMES = {
    url_name
    for url_name in POLICY_MUTATION_URL_ENTITY
    if url_name.endswith(("_move_up", "_move_down"))
}


def _policy_mutation_detail(request, entity=None):
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    entity = entity or POLICY_MUTATION_URL_ENTITY.get(url_name)
    dependency = POLICY_MUTATION_DEPENDENCIES[entity]
    detail = {
        "tables": list(dependency["tables"]),
        "refreshFilters": bool(dependency.get("refresh_filters", False)),
    }
    if url_name in POLICY_REORDER_URL_NAMES:
        detail["reorderedTable"] = POLICY_ENTITY_TABLE_KEY[entity]
    if url_name in POLICY_PRODUCT_REORDER_URL_NAMES:
        detail["productsReordered"] = True
    return detail


def _render_policy_mutation_updated(request, entity=None):
    schedule_policy_cache_invalidation()
    if not _is_htmx_request(request):
        return _render_policy_legacy_updated(request)
    response = HttpResponse()
    response["HX-Reswap"] = "none"
    response[HX_TRIGGER_HEADER] = json.dumps(
        {HX_POLICY_UPDATED_EVENT: _policy_mutation_detail(request, entity)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return response


def _render_policy_updated(request):
    return _render_policy_mutation_updated(request)


def _policy_import_success_response(request, **payload):
    schedule_policy_cache_invalidation()
    payload["policyUpdate"] = _policy_mutation_detail(request)
    return JsonResponse(payload)


def _consulting_catalog_lookup():
    consulting_types = list(ConsultingDirectionType.objects.order_by("position", "id"))
    service_types = list(
        ConsultingServiceType.objects.select_related("consulting_type").order_by(
            "consulting_type__position", "position", "id"
        )
    )
    service_subtypes = list(
        ConsultingServiceSubtype.objects.select_related("service_type", "service_type__consulting_type").order_by(
            "service_type__consulting_type__position", "service_type__position", "position", "id"
        )
    )
    return {
        "consulting_types_by_name": {item.name: item for item in consulting_types},
        "service_types_by_pair": {
            (item.consulting_type.name, item.name): item for item in service_types
        },
        "service_subtypes_by_triple": {
            (item.service_type.consulting_type.name, item.service_type.name, item.name): item
            for item in service_subtypes
        },
    }


def _consulting_direction_form_context(form, action, direction=None):
    ctx = {
        "form": form,
        "action": action,
        "consulting_catalog_initial_json": json.dumps(form.initial_catalog, ensure_ascii=False),
    }
    if direction:
        ctx["direction"] = direction
    return ctx

def _product_workspace_label(product):
    return " ".join(part for part in (product.short_name, product.display_name) if part)


def _product_inline_owner_ids(product):
    if product.is_group_owner:
        return [OWNER_GROUP_VALUE]
    owners = getattr(product, "_policy_owner_display_items", None)
    if owners is None:
        owners = product.owners.only("id").order_by("position", "id")
    return [str(owner.pk) for owner in owners]


def _product_workspace_save_product_payload(product):
    return {
        "id": product.pk,
        "consulting_type_ref": product.consulting_type_ref_id,
        "service_category_ref": product.service_category_ref_id,
        "service_subtype_ref": product.service_subtype_ref_id,
    }


def _product_workspace_form_data(product, fields):
    data = QueryDict(mutable=True)
    data["short_name"] = product.short_name
    data["name_en"] = product.name_en
    data["name_ru"] = product.name_ru
    data["display_name"] = product.display_name or ""
    if product.consulting_type_ref_id:
        data["consulting_type_ref"] = str(product.consulting_type_ref_id)
    if product.service_category_ref_id:
        data["service_category_ref"] = str(product.service_category_ref_id)
    if product.service_subtype_ref_id:
        data["service_subtype_ref"] = str(product.service_subtype_ref_id)
    for key in (
        "short_name",
        "name_en",
        "name_ru",
        "display_name",
        "consulting_type_ref",
        "service_category_ref",
        "service_subtype_ref",
    ):
        if key in fields:
            value = fields[key]
            data[key] = "" if value is None else str(value)
    if "owner_ids" in fields:
        owner_ids = fields.get("owner_ids")
        if not isinstance(owner_ids, list):
            owner_ids = [owner_ids] if owner_ids not in (None, "") else []
        for item in owner_ids:
            data.appendlist("owner_ids", str(item))
    elif product.is_group_owner:
        data.appendlist("owner_ids", OWNER_GROUP_VALUE)
    else:
        for owner_id in product.owners.values_list("pk", flat=True):
            data.appendlist("owner_ids", str(owner_id))
    return data


SERVICE_GOAL_REPORT_INLINE_FIELDS = (
    "service_goal",
    "service_goal_genitive",
    "report_title",
    "product_name",
)

TYPICAL_SECTION_INLINE_FIELDS = (
    "code",
    "short_name",
    "short_name_ru",
    "name_en",
    "name_ru",
    "accounting_type",
    "expertise_dir",
    "expertise_direction",
    "exclude_from_tkp_autofill",
)
TYPICAL_SECTION_INLINE_BOOL_FIELDS = frozenset({"exclude_from_tkp_autofill"})


def _workspace_table_rows(tables, key):
    rows = tables.get(key) or []
    return rows if isinstance(rows, list) else []


def _service_goal_report_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    for key in SERVICE_GOAL_REPORT_INLINE_FIELDS:
        current = getattr(item, key) or ""
        if key in fields:
            value = fields[key]
            current = "" if value is None else str(value)
        data[key] = current
    return data


def _inline_truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes", "да"}


def _typical_section_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    fk_fields = {"expertise_dir", "expertise_direction"}
    for key in TYPICAL_SECTION_INLINE_FIELDS:
        if key in TYPICAL_SECTION_INLINE_BOOL_FIELDS:
            continue
        if key in fk_fields:
            current = str(getattr(item, f"{key}_id") or "")
        else:
            current = "" if getattr(item, key) is None else str(getattr(item, key))
        if key in fields:
            value = fields[key]
            current = "" if value is None else str(value)
        data[key] = current
    checked = item.exclude_from_tkp_autofill
    if "exclude_from_tkp_autofill" in fields:
        checked = _inline_truthy(fields["exclude_from_tkp_autofill"])
    if checked:
        data["exclude_from_tkp_autofill"] = "on"
    return data


def _is_deleted_workspace_row(row):
    return isinstance(row, dict) and bool(row.get("deleted"))


def _is_new_workspace_row(row):
    if not isinstance(row, dict):
        return False
    if row.get("new"):
        return True
    row_id = row.get("id")
    return isinstance(row_id, str) and str(row_id).startswith("new-")


def _is_new_workspace_section_row(row):
    return _is_new_workspace_row(row)


def _resolve_workspace_after_id(raw, created_ids):
    if raw in (None, ""):
        return None
    raw = str(raw)
    if raw.startswith("new-"):
        return created_ids.get(raw)
    return _positive_int(raw)


def _resolve_section_after_id(raw, created_ids):
    return _resolve_workspace_after_id(raw, created_ids)


def _place_workspace_row_after(instance, after_id, queryset, *, missing_after="append"):
    siblings = list(queryset.exclude(pk=instance.pk).order_by("position", "id"))
    insert_at = 0 if missing_after == "start" else len(siblings)
    if after_id:
        insert_at = len(siblings)
        for index, sibling in enumerate(siblings):
            if sibling.pk == after_id:
                insert_at = index + 1
                break
    siblings.insert(insert_at, instance)
    changed = []
    for index, item in enumerate(siblings, start=1):
        if item.position != index:
            item.position = index
            changed.append(item)
    others = [item for item in changed if item.pk != instance.pk]
    if others:
        instance.__class__.objects.bulk_update(others, ["position"])
    instance.position = insert_at + 1
    update_fields = ["position"]
    if hasattr(instance, "updated_at"):
        update_fields.append("updated_at")
    instance.save(update_fields=update_fields)
    return instance


def _place_typical_section_after(section, after_id):
    return _place_workspace_row_after(
        section,
        after_id,
        TypicalSection.objects.filter(product_id=section.product_id),
    )


def _create_typical_section(form, *, specialties_callback=None, after_id=None):
    obj = form.save(commit=False)
    ensure_system_dsc_section(obj.product)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalSection, {"product": obj.product})
    obj.save()
    if specialties_callback:
        specialties_callback(obj)
    if after_id:
        _place_typical_section_after(obj, after_id)
    ensure_system_dsc_section(obj.product)
    return obj


def _create_section_structure(form, *, after_id=None, place=False):
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(SectionStructure)
    obj.save()
    if place:
        _place_workspace_row_after(
            obj,
            after_id,
            SectionStructure.objects.all(),
            missing_after="append",
        )
    return obj


def _create_typical_service_composition(form, *, after_id=None, place=False):
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalServiceComposition)
    obj.save()
    if place:
        _place_workspace_row_after(
            obj,
            after_id,
            TypicalServiceComposition.objects.all(),
            missing_after="append",
        )
    return obj


def _can_edit_workspace_tariff(user, tariff) -> bool:
    if user.is_superuser:
        return True
    return tariff.created_by_id == user.pk


def _create_workspace_tariff(form, *, request_user, after_id=None, place=False):
    obj = form.save(commit=False)
    owner = None
    if request_user.is_superuser:
        owner = form.cleaned_data.get("owner")
    obj.created_by = owner or request_user
    if not getattr(obj, "position", 0):
        obj.position = _next_position(Tariff, {"created_by": obj.created_by})
    obj.save()
    if place:
        _place_workspace_row_after(
            obj,
            after_id,
            Tariff.objects.filter(created_by=obj.created_by),
            missing_after="append",
        )
    return obj


def _section_structure_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    data["section"] = str(item.section_id or "")
    data["subsections"] = item.subsections or ""
    if "section" in fields:
        value = fields["section"]
        data["section"] = "" if value is None else str(value)
    if "subsections" in fields:
        value = fields["subsections"]
        data["subsections"] = "" if value is None else str(value)
    return data


def _report_structure_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    data["level"] = str(item.level)
    data["code"] = item.code or ""
    data["name"] = item.name or ""
    if "name" in fields:
        value = fields["name"]
        data["name"] = "" if value is None else str(value)
    return data


TYPICAL_SERVICE_TERM_INLINE_FIELDS = (
    "source_data_weeks",
    "source_data_term_unit",
    "preliminary_report_months",
    "preliminary_report_term_unit",
    "final_report_weeks",
    "final_report_term_unit",
)


def _typical_service_term_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    for key in TYPICAL_SERVICE_TERM_INLINE_FIELDS:
        current = getattr(item, key)
        if key in fields:
            value = fields[key]
            current = "" if value is None else str(value)
        data[key] = "" if current is None else str(current)
    return data


def _typical_service_composition_editor_state_payload(value, fallback_plain=""):
    state = value if isinstance(value, dict) else {}
    if not state and isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = {"html": "", "plain_text": raw}
            state = parsed if isinstance(parsed, dict) else {}
    html = str(state.get("html") or "").strip()
    plain = str(state.get("plain_text") or fallback_plain or "").strip()
    return {"html": html, "plain_text": plain}


def _typical_service_composition_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    data["section"] = str(item.section_id or "")
    state = _typical_service_composition_editor_state_payload(
        item.service_composition_editor_state,
        item.service_composition or "",
    )
    if "section" in fields:
        value = fields["section"]
        data["section"] = "" if value is None else str(value)
    if "service_composition_editor_state" in fields:
        state = _typical_service_composition_editor_state_payload(
            fields["service_composition_editor_state"],
            item.service_composition or "",
        )
    elif "service_composition" in fields:
        plain = "" if fields["service_composition"] is None else str(fields["service_composition"])
        state = {"html": str(state.get("html") or ""), "plain_text": plain}
    data["service_composition"] = state.get("plain_text") or ""
    data["service_composition_editor_state"] = json.dumps(state, ensure_ascii=False)
    return data


def _tariff_form_data(item, fields):
    data = QueryDict(mutable=True)
    data["product"] = str(item.product_id)
    data["section"] = str(item.section_id or "")
    data["base_rate_vpm"] = "" if item.base_rate_vpm is None else str(item.base_rate_vpm)
    data["service_hours"] = "" if item.service_hours is None else str(item.service_hours)
    data["service_days_tkp"] = "" if item.service_days_tkp is None else str(item.service_days_tkp)
    if "section" in fields:
        value = fields["section"]
        data["section"] = "" if value is None else str(value)
    for key in ("base_rate_vpm", "service_hours", "service_days_tkp"):
        if key in fields:
            value = fields[key]
            data[key] = "" if value is None else str(value)
    if "owner" in fields:
        value = fields["owner"]
        data["owner"] = "" if value is None else str(value)
    return data


def _product_form_inline_errors(form, product_id):
    return _inline_form_errors(form, "products", product_id)


def _inline_form_errors(form, table, row_id):
    errors = []
    for field, messages in form.errors.items():
        mapped_field = "" if field == "__all__" else field
        for message in messages:
            errors.append(
                {
                    "table": table,
                    "id": row_id,
                    "field": mapped_field,
                    "message": str(message),
                }
            )
    return errors


def _product_form_page_context(extra: dict) -> dict:
    ctx = {
        "product_service_meta_json": json.dumps(
            build_consulting_catalog_meta(),
            ensure_ascii=False,
        ),
    }
    ctx.update(extra)
    return ctx


def _positive_int(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _prefill_product_from_request(request):
    product_id = _positive_int(request.GET.get("product"))
    if not product_id:
        return None
    return (
        Product.objects.select_related(
            "consulting_type_ref",
            "service_category_ref",
            "service_subtype_ref",
        )
        .filter(pk=product_id)
        .first()
    )


def _product_field_initial_from_request(request):
    product = _prefill_product_from_request(request)
    return {"product": product.pk} if product else {}


def _workspace_product_form_extras(request, form, instance=None):
    extras = {"policy_form_query": ""}
    if form is None or "product" not in getattr(form, "fields", {}):
        return extras
    product = None
    if _is_policy_workspace_request(request):
        product = _prefill_product_from_request(request)
        if product is None and instance is not None:
            product = getattr(instance, "product", None)
    if product is None:
        return extras
    field = form.fields["product"]
    field.disabled = True
    field.queryset = Product.objects.filter(pk=product.pk)
    widget_attrs = dict(getattr(field.widget, "attrs", {}) or {})
    classes = [part for part in str(widget_attrs.get("class", "") or "").split() if part]
    if "readonly-field" not in classes:
        classes.append("readonly-field")
    widget_attrs["class"] = " ".join(classes)
    field.widget.attrs = widget_attrs
    form.initial["product"] = product.pk
    extras["policy_workspace"] = True
    extras["policy_workspace_product_id"] = product.pk
    extras["policy_form_query"] = f"?workspace=1&product={product.pk}"
    return extras


def _with_workspace_product_lock(request, context, form, instance=None):
    context.update(_workspace_product_form_extras(request, form, instance))
    return context


def _lock_workspace_product_field(request, form, instance=None):
    _workspace_product_form_extras(request, form, instance)
    return form


def _product_ref_initial_from_request(request):
    product = _prefill_product_from_request(request)
    if product:
        return {
            "consulting_type_ref": product.consulting_type_ref_id,
            "service_category_ref": product.service_category_ref_id,
            "service_subtype_ref": product.service_subtype_ref_id,
        }
    return {
        key: value
        for key in ("consulting_type_ref", "service_category_ref", "service_subtype_ref")
        if (value := _positive_int(request.GET.get(key)))
    }


def _next_position(model, filters: dict | None = None) -> int:
    """
    Возвращает следующую позицию (last+1) для списка объектов.
    filters — при необходимости ограничивает область (например, внутри продукта).
    """
    qs = model.objects
    if filters:
        qs = qs.filter(**filters)
    last = qs.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1

@login_required
@require_http_methods(["GET"])
def policy_partial(request):
    if _is_htmx_request(request):
        return render(request, POLICY_PARTIAL_TEMPLATE, {"policy_lazy_shell": True})
    return render(request, POLICY_PARTIAL_TEMPLATE, _policy_context(request))


@login_required
@require_http_methods(["GET"])
def policy_filter_catalog(request):
    payload, cache_status = get_or_build_policy_catalog(
        request,
        _policy_filter_catalog_data,
    )
    response = JsonResponse(payload)
    response["X-Policy-Cache"] = cache_status
    response["Server-Timing"] = (
        f'policy-cache;desc="{cache_status.lower()}"'
    )
    return response


@login_required
@require_http_methods(["GET"])
def policy_expertise_directions_table(request):
    return render(
        request,
        POLICY_EXPERTISE_DIRECTIONS_TABLE_TEMPLATE,
        _policy_expertise_directions_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_consulting_directions_table(request):
    return render(
        request,
        POLICY_CONSULTING_DIRECTIONS_TABLE_TEMPLATE,
        _policy_consulting_directions_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_products_table(request):
    return render(request, POLICY_PRODUCTS_TABLE_TEMPLATE, _policy_products_table_context(request))


@login_required
@require_http_methods(["GET"])
def policy_service_goal_reports_table(request):
    return render(
        request,
        POLICY_SERVICE_GOAL_REPORTS_TABLE_TEMPLATE,
        _policy_service_goal_reports_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_typical_sections_table(request):
    return render(
        request,
        POLICY_TYPICAL_SECTIONS_TABLE_TEMPLATE,
        _policy_typical_sections_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_section_structures_table(request):
    return render(
        request,
        POLICY_SECTION_STRUCTURES_TABLE_TEMPLATE,
        _policy_section_structures_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_report_structures_table(request):
    return render(
        request,
        POLICY_REPORT_STRUCTURES_TABLE_TEMPLATE,
        _policy_report_structures_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_typical_service_compositions_table(request):
    return render(
        request,
        POLICY_TYPICAL_SERVICE_COMPOSITIONS_TABLE_TEMPLATE,
        _policy_typical_service_compositions_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_typical_service_terms_table(request):
    return render(
        request,
        POLICY_TYPICAL_SERVICE_TERMS_TABLE_TEMPLATE,
        _policy_typical_service_terms_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_grades_table(request):
    return render(request, POLICY_GRADES_TABLE_TEMPLATE, _policy_grades_context(request))


@login_required
@require_http_methods(["GET"])
def policy_expert_specialties_table(request):
    return render(
        request,
        POLICY_EXPERT_SPECIALTIES_TABLE_TEMPLATE,
        _policy_expert_specialties_table_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_specialty_tariffs_table(request):
    return render(
        request,
        POLICY_SPECIALTY_TARIFFS_TABLE_TEMPLATE,
        _policy_specialty_tariffs_context(request),
    )


@login_required
@require_http_methods(["GET"])
def policy_tariffs_table(request):
    return render(request, POLICY_TARIFFS_TABLE_TEMPLATE, _policy_tariffs_table_context(request))


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def product_workspace(request, pk: int):
    product = get_object_or_404(
        Product.objects.only(
            "id",
            "short_name",
            "display_name",
            "consulting_type_ref_id",
            "service_category_ref_id",
            "service_subtype_ref_id",
        ),
        pk=pk,
    )
    return render(
        request,
        PRODUCT_WORKSPACE_TEMPLATE,
        {
            "product": product,
            "policy_workspace_label": _product_workspace_label(product),
        },
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST"])
def product_workspace_save(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "errors": [{"table": "", "id": pk, "field": "", "message": "Некорректный JSON."}],
            },
            status=400,
        )

    tables = payload.get("tables") if isinstance(payload, dict) else None
    if not isinstance(tables, dict):
        return JsonResponse(
            {
                "ok": False,
                "errors": [{"table": "", "id": pk, "field": "", "message": "Ожидался объект tables."}],
            },
            status=400,
        )

    errors = []
    saved_tables = []

    product_rows = _workspace_table_rows(tables, "products")
    target_row = None
    for row in product_rows:
        if not isinstance(row, dict):
            continue
        row_id = _positive_int(row.get("id"))
        if row_id != product.pk:
            errors.append(
                {
                    "table": "products",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Можно сохранить только текущий продукт.",
                }
            )
            continue
        target_row = row

    product_form = None
    if target_row is not None:
        fields = target_row.get("fields") if isinstance(target_row.get("fields"), dict) else {}
        product_form = ProductForm(_product_workspace_form_data(product, fields), instance=product)
        if not product_form.is_valid():
            errors.extend(_product_form_inline_errors(product_form, product.pk))

    goal_forms = []
    for row in _workspace_table_rows(tables, "service-goal-reports"):
        if not isinstance(row, dict):
            continue
        row_id = _positive_int(row.get("id"))
        item = ServiceGoalReport.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "service-goal-reports",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        form = ServiceGoalReportForm(
            _service_goal_report_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "service-goal-reports", item.pk))
            continue
        goal_forms.append(form)

    section_forms = []
    created_ids = {}
    sections_to_delete = []
    for row in _workspace_table_rows(tables, "typical-sections"):
        if not isinstance(row, dict):
            continue
        if _is_deleted_workspace_row(row):
            row_id = _positive_int(row.get("id"))
            item = TypicalSection.objects.filter(pk=row_id, product=product).first() if row_id else None
            if item is None:
                errors.append(
                    {
                        "table": "typical-sections",
                        "id": row_id or 0,
                        "field": "id",
                        "message": "Строка не относится к текущему продукту.",
                    }
                )
                continue
            if item.is_system_dsc:
                errors.append(
                    {
                        "table": "typical-sections",
                        "id": item.pk,
                        "field": "",
                        "message": "Системный раздел DSC нельзя удалить.",
                    }
                )
                continue
            sections_to_delete.append(item)
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        if _is_new_workspace_section_row(row):
            temp_id = str(row.get("id") or "new")
            item = TypicalSection(product=product)
            form = TypicalSectionForm(
                _typical_section_form_data(item, fields),
                instance=item,
            )
            if not form.is_valid():
                errors.extend(_inline_form_errors(form, "typical-sections", temp_id))
                continue
            section_forms.append(
                (
                    form,
                    fields["specialty_ids"] if "specialty_ids" in fields else None,
                    "specialty_ids" in fields,
                    {
                        "temp_id": temp_id,
                        "after_id": row.get("after_id"),
                    },
                )
            )
            continue
        row_id = _positive_int(row.get("id"))
        item = TypicalSection.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "typical-sections",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        if item.is_system_dsc:
            errors.append(
                {
                    "table": "typical-sections",
                    "id": item.pk,
                    "field": "",
                    "message": "Системный раздел DSC нельзя изменить.",
                }
            )
            continue
        form = TypicalSectionForm(
            _typical_section_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "typical-sections", item.pk))
            continue
        section_forms.append(
            (
                form,
                fields["specialty_ids"] if "specialty_ids" in fields else None,
                "specialty_ids" in fields,
                None,
            )
        )

    deleted_section_ids = {item.pk for item in sections_to_delete}

    structure_forms = []
    structure_creates = []
    created_structure_ids = {}
    for row in _workspace_table_rows(tables, "section-structures"):
        if not isinstance(row, dict):
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        if _is_new_workspace_row(row):
            temp_id = str(row.get("id") or "new")
            item = SectionStructure(product=product)
            form = SectionStructureForm(
                _section_structure_form_data(item, fields),
                instance=item,
            )
            if not form.is_valid():
                errors.extend(_inline_form_errors(form, "section-structures", temp_id))
                continue
            structure_creates.append((form, {"temp_id": temp_id, "after_id": row.get("after_id")}))
            continue
        row_id = _positive_int(row.get("id"))
        item = SectionStructure.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "section-structures",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        if item.section_id in deleted_section_ids:
            continue
        form = SectionStructureForm(
            _section_structure_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "section-structures", item.pk))
            continue
        structure_forms.append(form)

    report_structure_forms = []
    for row in _workspace_table_rows(tables, "report-structures"):
        if not isinstance(row, dict):
            continue
        row_id = _positive_int(row.get("id"))
        item = ReportStructure.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "report-structures",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        form = ReportStructureForm(
            _report_structure_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "report-structures", item.pk))
            continue
        report_structure_forms.append(form)

    term_forms = []
    for row in _workspace_table_rows(tables, "typical-service-terms"):
        if not isinstance(row, dict):
            continue
        row_id = _positive_int(row.get("id"))
        item = TypicalServiceTerm.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "typical-service-terms",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        form = TypicalServiceTermForm(
            _typical_service_term_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "typical-service-terms", item.pk))
            continue
        term_forms.append(form)

    composition_forms = []
    composition_creates = []
    created_composition_ids = {}
    for row in _workspace_table_rows(tables, "typical-service-compositions"):
        if not isinstance(row, dict):
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        if _is_new_workspace_row(row):
            temp_id = str(row.get("id") or "new")
            item = TypicalServiceComposition(product=product)
            form = TypicalServiceCompositionForm(
                _typical_service_composition_form_data(item, fields),
                instance=item,
            )
            if not form.is_valid():
                errors.extend(_inline_form_errors(form, "typical-service-compositions", temp_id))
                continue
            composition_creates.append((form, {"temp_id": temp_id, "after_id": row.get("after_id")}))
            continue
        row_id = _positive_int(row.get("id"))
        item = (
            TypicalServiceComposition.objects.filter(pk=row_id, product=product).first()
            if row_id
            else None
        )
        if item is None:
            errors.append(
                {
                    "table": "typical-service-compositions",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        if item.section_id in deleted_section_ids:
            continue
        form = TypicalServiceCompositionForm(
            _typical_service_composition_form_data(item, fields),
            instance=item,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "typical-service-compositions", item.pk))
            continue
        composition_forms.append(form)

    tariff_forms = []
    tariff_creates = []
    created_tariff_ids = {}
    for row in _workspace_table_rows(tables, "tariffs"):
        if not isinstance(row, dict):
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        if _is_new_workspace_row(row):
            temp_id = str(row.get("id") or "new")
            item = Tariff(product=product)
            form = TariffForm(
                _tariff_form_data(item, fields),
                instance=item,
                request_user=request.user,
            )
            if not form.is_valid():
                errors.extend(_inline_form_errors(form, "tariffs", temp_id))
                continue
            tariff_creates.append((form, {"temp_id": temp_id, "after_id": row.get("after_id")}))
            continue
        row_id = _positive_int(row.get("id"))
        item = Tariff.objects.filter(pk=row_id, product=product).first() if row_id else None
        if item is None:
            errors.append(
                {
                    "table": "tariffs",
                    "id": row_id or 0,
                    "field": "id",
                    "message": "Строка не относится к текущему продукту.",
                }
            )
            continue
        if not _can_edit_workspace_tariff(request.user, item):
            errors.append(
                {
                    "table": "tariffs",
                    "id": item.pk,
                    "field": "id",
                    "message": "Нет прав на изменение этой строки.",
                }
            )
            continue
        if item.section_id in deleted_section_ids:
            continue
        form = TariffForm(
            _tariff_form_data(item, fields),
            instance=item,
            request_user=request.user,
        )
        if not form.is_valid():
            errors.extend(_inline_form_errors(form, "tariffs", item.pk))
            continue
        tariff_forms.append(form)

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    saved = product
    with transaction.atomic():
        if product_form is not None:
            saved = product_form.save()
            ensure_system_dsc_section(saved)
            saved_tables.append("products")
        for form in goal_forms:
            form.save()
        if goal_forms:
            saved_tables.append("service-goal-reports")
        created_typical_section = False
        deleted_typical_section = False
        for form, specialty_ids, update_specialties, extra in section_forms:
            if extra:
                after_id = _resolve_section_after_id(extra.get("after_id"), created_ids)
                instance = _create_typical_section(
                    form,
                    specialties_callback=(
                        (lambda section, ids=specialty_ids: _replace_section_specialties(section, ids))
                        if update_specialties
                        else None
                    ),
                    after_id=after_id,
                )
                created_ids[extra["temp_id"]] = instance.pk
                created_typical_section = True
                continue
            instance = form.save()
            if update_specialties:
                _replace_section_specialties(instance, specialty_ids)
        if sections_to_delete:
            for item in sections_to_delete:
                item.delete()
            deleted_typical_section = True
        if section_forms or deleted_typical_section:
            ensure_system_dsc_section(saved)
            saved_tables.append("typical-sections")
        if created_typical_section or deleted_typical_section:
            for table_key in POLICY_MUTATION_DEPENDENCIES["typical-section"]["tables"]:
                if table_key not in saved_tables:
                    saved_tables.append(table_key)
        for form, extra in structure_creates:
            after_id = _resolve_workspace_after_id(extra.get("after_id"), created_structure_ids)
            instance = _create_section_structure(form, after_id=after_id, place=True)
            created_structure_ids[extra["temp_id"]] = instance.pk
        for form in structure_forms:
            form.save()
        if structure_forms or structure_creates:
            saved_tables.append("section-structures")
        for form in report_structure_forms:
            form.save()
        if report_structure_forms:
            saved_tables.append("report-structures")
        for form in term_forms:
            form.save()
        if term_forms:
            saved_tables.append("typical-service-terms")
        for form, extra in composition_creates:
            after_id = _resolve_workspace_after_id(extra.get("after_id"), created_composition_ids)
            instance = _create_typical_service_composition(form, after_id=after_id, place=True)
            created_composition_ids[extra["temp_id"]] = instance.pk
        for form in composition_forms:
            form.save()
        if composition_forms or composition_creates:
            saved_tables.append("typical-service-compositions")
        for form, extra in tariff_creates:
            after_id = _resolve_workspace_after_id(extra.get("after_id"), created_tariff_ids)
            instance = _create_workspace_tariff(
                form,
                request_user=request.user,
                after_id=after_id,
                place=True,
            )
            created_tariff_ids[extra["temp_id"]] = instance.pk
        for form in tariff_forms:
            obj = form.save(commit=False)
            if request.user.is_superuser:
                owner = form.cleaned_data.get("owner")
                if owner:
                    obj.created_by = owner
            obj.save()
        if tariff_forms or tariff_creates:
            saved_tables.append("tariffs")

    schedule_policy_cache_invalidation()
    return JsonResponse(
        {
            "ok": True,
            "label": _product_workspace_label(saved),
            "product": _product_workspace_save_product_payload(saved),
            "tables": saved_tables or ["products"],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def product_form_create(request):
    if request.method == "GET":
        form = ProductForm(initial=_product_ref_initial_from_request(request))
        return render(request, PRODUCT_FORM_TEMPLATE, _product_form_page_context({"form": form, "action": "create"}))
    # POST
    form = ProductForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(
            request, PRODUCT_FORM_TEMPLATE, _product_form_page_context({"form": form, "action": "create"})
        )
    if not form.instance.position:
        form.instance.position = _next_position(Product)
    product = form.save()
    ensure_system_dsc_section(product)
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def product_form_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "GET":
        form = ProductForm(instance=product)
        return render(
            request,
            PRODUCT_FORM_TEMPLATE,
            _product_form_page_context({"form": form, "action": "edit", "product": product}),
        )
    # POST
    form = ProductForm(request.POST, instance=product)
    if not form.is_valid():
        return _render_form_with_errors(
            request,
            PRODUCT_FORM_TEMPLATE,
            _product_form_page_context({"form": form, "action": "edit", "product": product}),
        )
    product = form.save()
    ensure_system_dsc_section(product)
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def product_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    catalog_lookup = _consulting_catalog_lookup()
    valid_consulting_types = set(catalog_lookup["consulting_types_by_name"].keys())
    valid_service_categories = {name for _kind, name in catalog_lookup["service_types_by_pair"].keys()}
    owners_by_short_name = {
        member.short_name.strip().lower(): member
        for member in GroupMember.objects.exclude(short_name="").all()
    }

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 8:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 8-9: "
                "Краткое имя, Наименование EN, Наименование RU, Отображаемое имя, Вид консалтинга, "
                "Тип услуг, Код, Подтип услуги, [Владелец])."
            )
            continue

        short_name = row[0].strip()
        name_en = row[1].strip()
        name_ru = row[2].strip()
        display_name = row[3].strip() if len(row) > 3 else ""
        consulting_type = row[4].strip() if len(row) > 4 else ""
        service_category = row[5].strip() if len(row) > 5 else ""
        csv_code = row[6].strip() if len(row) > 6 else ""
        service_subtype = row[7].strip() if len(row) > 7 else ""
        owner_raw = row[8].strip() if len(row) > 8 else ""

        missing = []
        if not short_name:
            missing.append("Краткое имя")
        if not name_en:
            missing.append("Наименование EN")
        if not name_ru:
            missing.append("Наименование RU")
        if not consulting_type:
            missing.append("Вид консалтинга")
        if not service_category:
            missing.append("Тип услуг")
        if not service_subtype:
            missing.append("Подтип услуги")
        if missing:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: {', '.join(missing)}.")
            continue

        if consulting_type not in valid_consulting_types:
            warnings.append(
                f"Строка {i}: неизвестный вид консалтинга «{consulting_type}». "
                f"Допустимые: {', '.join(valid_consulting_types)}."
            )
            continue

        if service_category not in valid_service_categories:
            warnings.append(
                f"Строка {i}: неизвестный тип услуг «{service_category}». "
                f"Допустимые: {', '.join(valid_service_categories)}."
            )
            continue

        service_type_obj = catalog_lookup["service_types_by_pair"].get((consulting_type, service_category))
        if service_type_obj is None:
            warnings.append(
                f"Строка {i}: тип услуг «{service_category}» недопустим для вида консалтинга "
                f"«{consulting_type}»."
            )
            continue

        service_subtype_obj = catalog_lookup["service_subtypes_by_triple"].get(
            (consulting_type, service_category, service_subtype)
        )
        if service_subtype_obj is None:
            warnings.append(
                f"Строка {i}: подтип услуги «{service_subtype}» недопустим для типа услуг "
                f"«{service_category}»."
            )
            continue

        derived_code = service_type_obj.code or ""
        if csv_code and csv_code != derived_code:
            warnings.append(
                f"Строка {i}: код «{csv_code}» не соответствует типу услуг «{service_category}». "
                f"Использован код «{derived_code}»."
            )

        is_group_owner = not owner_raw or owner_raw == "Группа"
        owner_ids = []
        if not is_group_owner:
            owner_names = [item.strip() for item in owner_raw.split(",") if item.strip()]
            missing_owners = [name for name in owner_names if name.lower() not in owners_by_short_name]
            if missing_owners:
                warnings.append(f"Строка {i}: владельцы не найдены: {', '.join(missing_owners)}.")
                continue
            owner_ids = [owners_by_short_name[name.lower()].pk for name in owner_names]

        try:
            product = Product.objects.create(
                short_name=short_name,
                name_en=name_en,
                display_name=display_name,
                name_ru=name_ru,
                consulting_type_ref=service_type_obj.consulting_type,
                service_category_ref=service_type_obj,
                service_subtype_ref=service_subtype_obj,
                is_group_owner=is_group_owner,
                position=_next_position(Product),
            )
            if owner_ids:
                product.owners.set(owner_ids)
            ensure_system_dsc_section(product)
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def product_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(PRODUCT_CSV_HEADERS)

    products = _apply_policy_master_filters_to_products(
        _policy_products_queryset(),
        request,
    )
    for product in products:
        writer.writerow(
            [
                product.short_name,
                product.name_en,
                product.name_ru,
                product.display_name,
                product.consulting_type_display,
                product.service_category_display,
                product.service_code,
                product.service_subtype_display,
                product.owner_display,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="typical_products.csv"'
    return response

# --- Типовые разделы ---

def _section_specialty_options():
    return [
        {"id": s.pk, "label": s.specialty}
        for s in ExpertSpecialty.objects.exclude(specialty="").order_by("position")
    ]


def _section_form_context(form, action, section=None):
    spec_options = _section_specialty_options()
    ranked = []
    if section and section.pk:
        ranked = [
            {"rank": link.rank, "specialty_id": link.specialty_id}
            for link in TypicalSectionSpecialty.objects.filter(section=section).order_by("rank")
        ]
    ctx = {
        "form": form,
        "action": action,
        "specialty_options": spec_options,
        "specialty_options_json": json.dumps(spec_options, ensure_ascii=False),
        "ranked_specialties": ranked,
        "is_system_section": bool(section and section.is_system_dsc),
    }
    if section:
        ctx["section"] = section
    return ctx


def _replace_section_specialties(section, raw_ids):
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids] if raw_ids not in (None, "") else []
    ids = []
    seen = set()
    for raw in raw_ids:
        pk = _positive_int(raw)
        if not pk or pk in seen:
            continue
        seen.add(pk)
        ids.append(pk)
    valid = set(
        ExpertSpecialty.objects.filter(pk__in=ids).values_list("pk", flat=True)
    )
    TypicalSectionSpecialty.objects.filter(section=section).delete()
    TypicalSectionSpecialty.objects.bulk_create(
        [
            TypicalSectionSpecialty(section=section, specialty_id=pk, rank=rank)
            for rank, pk in enumerate(ids, start=1)
            if pk in valid
        ]
    )


def _save_section_specialties(section, post_data):
    specialty_ids = post_data.getlist("specialty_id")
    TypicalSectionSpecialty.objects.filter(section=section).delete()
    to_create = []
    for rank, raw_id in enumerate(specialty_ids, start=1):
        if raw_id:
            try:
                sid = int(raw_id)
            except (ValueError, TypeError):
                continue
            to_create.append(TypicalSectionSpecialty(
                section=section, specialty_id=sid, rank=rank,
            ))
    if to_create:
        TypicalSectionSpecialty.objects.bulk_create(to_create)


def _typical_sections_by_product_json():
    data = defaultdict(list)
    sections = TypicalSection.objects.select_related("product").order_by("product_id", "position", "id")
    for section in sections:
        section_name = section.name_ru or section.name_en
        section_code = section.code or ""
        data[str(section.product_id)].append({
            "id": section.pk,
            "code": section_code,
            "label": " ".join(part for part in (section_code, section_name) if part),
            "displayLabel": section_name,
        })
    return json.dumps(data, ensure_ascii=False)


def _typical_service_composition_form_context(form, action, composition=None):
    ctx = {
        "form": form,
        "action": action,
        "sections_by_product_json": _typical_sections_by_product_json(),
    }
    if composition:
        ctx["composition"] = composition
    return ctx


def _typical_service_term_form_context(form, action, term=None):
    ctx = {
        "form": form,
        "action": action,
    }
    if term:
        ctx["term"] = term
    return ctx


def _structure_form_context(form, action, structure=None):
    ctx = {
        "form": form,
        "action": action,
        "sections_by_product_json": _typical_sections_by_product_json(),
    }
    if structure:
        ctx["structure"] = structure
    return ctx


def _report_structure_form_context(form, action, report_structure=None):
    number = _report_structure_form_initial_number(form, report_structure)
    form.fields["number"].initial = number
    ctx = {
        "form": form,
        "action": action,
        "report_structure_items_by_product_json": _report_structure_items_by_product_json(),
        "current_report_structure_id": report_structure.pk if report_structure and report_structure.pk else None,
        "current_report_structure_product_id": report_structure.product_id if report_structure and report_structure.pk else None,
    }
    if report_structure:
        ctx["report_structure"] = report_structure
    return ctx


def _specialty_tariff_specialty_options():
    return [
        {
            "id": specialty.pk,
            "label": specialty.specialty,
            "expertise_direction": (
                ""
                if (getattr(specialty.expertise_dir, "short_name", "") or "").strip() == "—"
                else (getattr(specialty.expertise_dir, "short_name", "") or "").strip()
            ),
        }
        for specialty in ExpertSpecialty.objects.exclude(specialty="").select_related("expertise_dir").order_by("position", "id")
    ]


def _specialty_tariff_form_context(form, action, tariff=None):
    selected_specialty_ids = []
    if form.is_bound:
        selected_specialty_ids = [str(value) for value in form.data.getlist("specialties") if value]
    elif tariff and tariff.pk:
        selected_specialty_ids = [str(value) for value in tariff.specialties.values_list("pk", flat=True)]

    specialty_options = _specialty_tariff_specialty_options()
    ctx = {
        "form": form,
        "action": action,
        "specialty_options": specialty_options,
        "specialty_options_json": json.dumps(specialty_options, ensure_ascii=False),
        "selected_specialty_ids_json": json.dumps(selected_specialty_ids, ensure_ascii=False),
    }
    if tariff:
        ctx["tariff"] = tariff
    return ctx


def _specialty_tariff_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_create(request):
    if request.method == "GET":
        form = TypicalSectionForm(initial=_product_field_initial_from_request(request))
        return render(
            request,
            SECTION_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _section_form_context(form, "create"), form),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalSectionForm(request.POST, initial=_product_field_initial_from_request(request)),
    )
    if not form.is_valid():
        return render(
            request,
            SECTION_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _section_form_context(form, "create"), form),
        )
    _create_typical_section(
        form,
        specialties_callback=lambda section: _save_section_specialties(section, request.POST),
    )
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_edit(request, pk: int):
    section = get_object_or_404(TypicalSection, pk=pk)
    if request.method == "GET":
        form = TypicalSectionForm(instance=section)
        return render(
            request,
            SECTION_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _section_form_context(form, "edit", section), form, section),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalSectionForm(
            request.POST,
            instance=section,
            initial=_product_field_initial_from_request(request),
        ),
        section,
    )
    if not form.is_valid():
        return render(
            request,
            SECTION_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _section_form_context(form, "edit", section), form, section),
        )
    if section.is_system_dsc:
        ensure_system_dsc_section(section.product)
    else:
        form.save()
        _save_section_specialties(section, request.POST)
        ensure_system_dsc_section(section.product)
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def section_delete(request, pk: int):
    section = get_object_or_404(TypicalSection, pk=pk)
    if section.is_system_dsc:
        return JsonResponse({"ok": False, "error": "Системный раздел DSC нельзя удалить."}, status=400)
    product = section.product
    section.delete()
    ensure_system_dsc_section(product)
    return _render_policy_updated(request)

def _normalize_product_positions():
    """
    Гарантирует сквозную нумерацию позиций (1..N) в порядке текущей сортировки.
    """
    products = list(
        Product.objects.select_for_update()
        .order_by("position", "id")
        .only("id", "position")
    )
    changed = []
    for idx, p in enumerate(products, start=1):
        if p.position != idx:
            p.position = idx
            changed.append(p)
    if changed:
        Product.objects.bulk_update(changed, ["position"])
    return products

def _normalize_section_positions(product_id: int | None = None):
    """
    Гарантирует сквозную нумерацию позиций разделов внутри каждого продукта.
    Если product_id задан, нормализует только для одного продукта.
    """
    qs = TypicalSection.objects.select_for_update().only(
        "id",
        "position",
        "product_id",
        "code",
        "is_system",
    )
    if product_id:
        groups = {product_id: list(qs.filter(product_id=product_id).order_by("position", "id"))}
    else:
        # группируем по продукту
        groups = {}
        for sec in qs.order_by("product_id", "position", "id"):
            groups.setdefault(sec.product_id, []).append(sec)
    normalized_groups = {}
    for pid, items in groups.items():
        items = sorted(items, key=lambda item: (0 if item.is_system_dsc else 1, item.position, item.id))
        changed = []
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                it.position = idx
                changed.append(it)
        if changed:
            TypicalSection.objects.bulk_update(changed, ["position"])
        normalized_groups[pid] = items
    if product_id:
        return normalized_groups.get(product_id, [])
    return normalized_groups

@require_http_methods(["POST", "GET"])
@login_required
def product_move_up(request, pk: int):
    with transaction.atomic():
        items = _normalize_product_positions()
        idx = next((i for i, it in enumerate(items) if it.id == pk), None)
        if idx is not None and idx > 0:
            cur = items[idx]
            prev = items[idx - 1]
            cur.position, prev.position = prev.position, cur.position
            Product.objects.bulk_update([cur, prev], ["position"])
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def product_move_down(request, pk: int):
    with transaction.atomic():
        items = _normalize_product_positions()
        idx = next((i for i, it in enumerate(items) if it.id == pk), None)
        if idx is not None and idx < len(items) - 1:
            cur = items[idx]
            nxt = items[idx + 1]
            cur.position, nxt.position = nxt.position, cur.position
            Product.objects.bulk_update([cur, nxt], ["position"])
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def section_move_up(request, pk: int):
    sec = get_object_or_404(TypicalSection, pk=pk)
    if sec.is_system_dsc:
        return _render_policy_updated(request)
    pid = sec.product_id
    with transaction.atomic():
        items = _normalize_section_positions(product_id=pid)
        idx = next((i for i, it in enumerate(items) if it.id == pk), None)
        if idx is not None and idx > 0:
            cur = items[idx]
            prev = items[idx - 1]
            if not prev.is_system_dsc:
                cur.position, prev.position = prev.position, cur.position
                TypicalSection.objects.bulk_update([cur, prev], ["position"])
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def section_move_down(request, pk: int):
    sec = get_object_or_404(TypicalSection, pk=pk)
    if sec.is_system_dsc:
        return _render_policy_updated(request)
    pid = sec.product_id
    with transaction.atomic():
        items = _normalize_section_positions(product_id=pid)
        idx = next((i for i, it in enumerate(items) if it.id == pk), None)
        if idx is not None and idx < len(items) - 1:
            cur = items[idx]
            nxt = items[idx + 1]
            cur.position, nxt.position = nxt.position, cur.position
            TypicalSection.objects.bulk_update([cur, nxt], ["position"])
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def section_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    expertise_dirs = {}
    for direction in ExpertiseDirection.objects.all():
        for label in (direction.short_name, direction.name):
            key = _csv_lookup_key(label)
            if key:
                expertise_dirs[key] = direction
    expertise_units = {
        key: u
        for u in OrgUnit.objects.filter(Q(unit_type="expertise") | Q(unit_type="administrative", level=1))
        for key in {_csv_lookup_key(u.department_name), _csv_lookup_key(u.short_name)}
        if key
    }
    specialties_by_name = {
        _csv_lookup_key(s.specialty): s
        for s in ExpertSpecialty.objects.exclude(specialty="").all()
    }
    data_rows = rows[1:]
    created = 0
    updated = 0
    warnings = []

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 7:
            warnings.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 7-9: Продукт, Код, Краткое имя EN, Краткое имя RU, Наименование EN, Наименование RU, Тип учета, [Направление экспертизы]).")
            continue

        product_name = row[0].strip()
        code = row[1].strip()
        short_name = row[2].strip()
        short_name_ru = row[3].strip() if len(row) > 3 else ""
        name_en = row[4].strip() if len(row) > 4 else ""
        name_ru = row[5].strip() if len(row) > 5 else ""
        accounting_type = row[6].strip() if len(row) > 6 else "Раздел"
        executor_raw = ""
        expertise_dir_name = ""
        tkp_raw = ""
        if len(row) >= len(SECTION_CSV_HEADERS):
            executor_raw = row[7].strip()
            expertise_dir_name = row[8].strip()
            expertise_name = row[9].strip()
            tkp_raw = row[10].strip()
        elif len(row) > 8:
            executor_raw = row[7].strip()
            expertise_name = row[8].strip()
        else:
            expertise_name = row[7].strip() if len(row) > 7 else ""

        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        if not code:
            warnings.append(f"Строка {i}: отсутствует код раздела.")
            continue

        if is_system_dsc_code(code):
            ensure_system_dsc_section(product)
            warnings.append(
                f"Строка {i}: раздел DSC является системным; строка CSV пропущена, системная запись создана/обновлена автоматически."
            )
            continue

        missing = []
        if not short_name:
            missing.append("Краткое имя EN")
        if not name_en:
            missing.append("Наименование EN")
        if not name_ru:
            missing.append("Наименование RU")
        if missing:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: {', '.join(missing)}.")
            continue

        if accounting_type not in dict(TypicalSection.ACCOUNTING_TYPE_CHOICES):
            warnings.append(f"Строка {i}: неизвестный тип учета «{accounting_type}». Допустимые: {', '.join(dict(TypicalSection.ACCOUNTING_TYPE_CHOICES).keys())}. Установлено «Раздел».")
            accounting_type = "Раздел"

        expertise_dir = None
        if expertise_dir_name:
            expertise_dir = expertise_dirs.get(_csv_lookup_key(expertise_dir_name))
            if not expertise_dir:
                warnings.append(f"Строка {i}: экспертиза «{expertise_dir_name}» не найдена. Поле оставлено пустым.")

        expertise_direction = None
        if expertise_name:
            expertise_direction = expertise_units.get(_csv_lookup_key(expertise_name))
            if not expertise_direction:
                warnings.append(f"Строка {i}: подразделение «{expertise_name}» не найдено. Поле оставлено пустым.")

        try:
            with transaction.atomic():
                ensure_system_dsc_section(product)
                section = TypicalSection.objects.filter(product=product, code=code).first()
                was_created = section is None
                if was_created:
                    section = TypicalSection.objects.create(
                        product=product,
                        code=code,
                        short_name=short_name,
                        short_name_ru=short_name_ru,
                        name_en=name_en,
                        name_ru=name_ru,
                        accounting_type=accounting_type,
                        expertise_dir=expertise_dir,
                        expertise_direction=expertise_direction,
                        exclude_from_tkp_autofill=_csv_truthy(tkp_raw),
                        position=_next_position(TypicalSection, {"product": product}),
                    )
                else:
                    section.short_name = short_name
                    section.short_name_ru = short_name_ru
                    section.name_en = name_en
                    section.name_ru = name_ru
                    section.accounting_type = accounting_type
                    section.expertise_dir = expertise_dir
                    section.expertise_direction = expertise_direction
                    section.exclude_from_tkp_autofill = _csv_truthy(tkp_raw)
                    section.save(
                        update_fields=[
                            "short_name",
                            "short_name_ru",
                            "name_en",
                            "name_ru",
                            "accounting_type",
                            "expertise_dir",
                            "expertise_direction",
                            "exclude_from_tkp_autofill",
                            "updated_at",
                        ]
                    )
                    TypicalSectionSpecialty.objects.filter(section=section).delete()
                missing_specialties = []
                for rank, specialty_name in enumerate(_split_csv_list_value(executor_raw, specialties_by_name), start=1):
                    specialty = specialties_by_name.get(_csv_lookup_key(specialty_name))
                    if not specialty:
                        missing_specialties.append(specialty_name)
                        continue
                    TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=rank)
            if missing_specialties:
                warnings.append(f"Строка {i}: исполнители не найдены: {', '.join(missing_specialties)}.")
            if was_created:
                created += 1
            else:
                updated += 1
            ensure_system_dsc_section(product)
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, updated=updated, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def section_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(SECTION_CSV_HEADERS)

    sections = _apply_policy_master_product_filters(
        _policy_typical_sections_queryset(),
        request,
    )
    for section in sections:
        executor = "\n".join(
            rs.specialty.specialty
            for rs in section.ranked_specialties.all()
            if rs.specialty and rs.specialty.specialty
        )
        writer.writerow(
            [
                section.product.short_name,
                section.code,
                section.short_name,
                section.short_name_ru,
                section.name_en,
                section.name_ru,
                section.accounting_type,
                executor,
                section.expertise_dir.short_name if section.expertise_dir else "",
                section.expertise_direction.department_name if section.expertise_direction else "",
                "Да" if section.exclude_from_tkp_autofill else "Нет",
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="typical_sections.csv"'
    return response


# --- Типовая структура раздела ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def structure_form_create(request):
    if request.method == "GET":
        form = SectionStructureForm(initial=_product_field_initial_from_request(request))
        return render(
            request,
            STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _structure_form_context(form, "create"), form),
        )
    form = _lock_workspace_product_field(
        request,
        SectionStructureForm(request.POST, initial=_product_field_initial_from_request(request)),
    )
    if not form.is_valid():
        return render(
            request,
            STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _structure_form_context(form, "create"), form),
        )
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(SectionStructure)
    obj.save()
    return _render_policy_mutation_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def structure_form_edit(request, pk: int):
    structure = get_object_or_404(SectionStructure, pk=pk)
    if request.method == "GET":
        form = SectionStructureForm(instance=structure)
        return render(
            request,
            STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _structure_form_context(form, "edit", structure), form, structure
            ),
        )
    form = _lock_workspace_product_field(
        request,
        SectionStructureForm(
            request.POST,
            instance=structure,
            initial=_product_field_initial_from_request(request),
        ),
        structure,
    )
    if not form.is_valid():
        return render(
            request,
            STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _structure_form_context(form, "edit", structure), form, structure
            ),
        )
    form.save()
    return _render_policy_mutation_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def structure_delete(request, pk: int):
    structure = get_object_or_404(SectionStructure, pk=pk)
    structure.delete()
    return _render_policy_mutation_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def structure_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    sections_by_product = defaultdict(dict)
    for section in TypicalSection.objects.select_related("product").all():
        lookup = sections_by_product[section.product_id]
        for label in (section.name_ru, section.name_en, section.code, section.short_name, section.short_name_ru):
            key = _csv_lookup_key(label)
            if key:
                lookup.setdefault(key, section)

    created = 0
    warnings = []
    headers = rows[0]
    product_col = _csv_header_index(headers, "Продукт")
    code_col = _csv_header_index(headers, "Код")
    section_col = _csv_header_index(headers, "Раздел (услуга)")
    subsections_col = _csv_header_index(headers, "Подразделы")
    if product_col is None:
        product_col = 0
    if section_col is None:
        section_col = 2 if code_col is not None else 1
    if subsections_col is None:
        subsections_col = 3 if code_col is not None else 2

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if not _csv_required_columns_present(row, [product_col, section_col, subsections_col]):
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается "
                "Продукт, Код, Раздел (услуга), Подразделы)."
            )
            continue

        product_name = _csv_row_value(row, product_col)
        section_code = _csv_row_value(row, code_col)
        section_name = _csv_row_value(row, section_col)
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        section = _resolve_section_from_import(sections_by_product, product.pk, section_code, section_name)
        if not section:
            section_label = section_code or section_name
            warnings.append(f"Строка {i}: раздел «{section_label}» не найден для продукта «{product.short_name}».")
            continue

        try:
            SectionStructure.objects.create(
                product=product,
                section=section,
                subsections=_csv_row_value(row, subsections_col),
                position=_next_position(SectionStructure),
            )
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def structure_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(STRUCTURE_CSV_HEADERS)

    structures = _apply_policy_master_product_filters(
        _policy_section_structures_queryset(),
        request,
    )
    for structure in structures:
        writer.writerow(
            [
                structure.product.short_name,
                structure.section.code,
                structure.section.name_ru or structure.section.name_en,
                structure.subsections,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="section_structures.csv"'
    return response


def _normalize_structure_positions():
    items = SectionStructure.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            SectionStructure.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def structure_move_up(request, pk: int):
    _normalize_structure_positions()
    items = list(SectionStructure.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        SectionStructure.objects.filter(pk=cur.id).update(position=prev_pos)
        SectionStructure.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_structure_positions()
    return _render_policy_mutation_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def structure_move_down(request, pk: int):
    _normalize_structure_positions()
    items = list(SectionStructure.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        SectionStructure.objects.filter(pk=cur.id).update(position=next_pos)
        SectionStructure.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_structure_positions()
    return _render_policy_mutation_updated(request)


# --- Типовая структура отчета ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_structure_form_create(request):
    if request.method == "GET":
        initial = {"level": 0}
        initial.update(_product_field_initial_from_request(request))
        form = ReportStructureForm(initial=initial)
        return render(
            request,
            REPORT_STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _report_structure_form_context(form, "create"), form),
        )
    form = _lock_workspace_product_field(
        request,
        ReportStructureForm(request.POST, initial=_product_field_initial_from_request(request)),
    )
    if not form.is_valid():
        return render(
            request,
            REPORT_STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _report_structure_form_context(form, "create"), form),
        )
    obj = form.save(commit=False)
    obj.position = _next_position(ReportStructure, {"product": obj.product})
    obj.save()
    _normalize_report_structure_positions(obj.product_id)
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_structure_form_edit(request, pk: int):
    report_structure = get_object_or_404(ReportStructure, pk=pk)
    old_product_id = report_structure.product_id
    if request.method == "GET":
        form = ReportStructureForm(instance=report_structure)
        return render(
            request,
            REPORT_STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                _report_structure_form_context(form, "edit", report_structure),
                form,
                report_structure,
            ),
        )
    form = _lock_workspace_product_field(
        request,
        ReportStructureForm(
            request.POST,
            instance=report_structure,
            initial=_product_field_initial_from_request(request),
        ),
        report_structure,
    )
    if not form.is_valid():
        return render(
            request,
            REPORT_STRUCTURE_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                _report_structure_form_context(form, "edit", report_structure),
                form,
                report_structure,
            ),
        )
    obj = form.save(commit=False)
    if obj.product_id != old_product_id:
        obj.position = _next_position(ReportStructure, {"product": obj.product})
    obj.save()
    _normalize_report_structure_positions(old_product_id)
    if obj.product_id != old_product_id:
        _normalize_report_structure_positions(obj.product_id)
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_structure_delete(request, pk: int):
    report_structure = get_object_or_404(ReportStructure, pk=pk)
    product_id = report_structure.product_id
    report_structure.delete()
    _normalize_report_structure_positions(product_id)
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_structure_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    created = 0
    warnings = []
    headers = rows[0]
    product_col = _csv_header_index(headers, "Продукт")
    level_col = _csv_header_index(headers, "Уровень")
    number_col = _csv_header_index(headers, "Номер")
    code_col = _csv_header_index(headers, "Код")
    name_col = _csv_header_index(headers, "Наименование отчета, раздела (подраздела)")
    if product_col is None:
        product_col = 0
    if level_col is None:
        level_col = 1
    if code_col is None:
        code_col = 3 if number_col is not None else 2
    if name_col is None:
        name_col = 4 if number_col is not None else 3

    changed_product_ids = set()
    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if not _csv_required_columns_present(row, [product_col, level_col]):
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается "
                "Продукт, Уровень, Номер, Код, Наименование отчета, раздела (подраздела))."
            )
            continue

        product_name = _csv_row_value(row, product_col)
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        raw_level = _csv_row_value(row, level_col)
        level = _coerce_report_level(raw_level)
        if level is None:
            warnings.append(f"Строка {i}: уровень «{raw_level}» должен быть целым числом от 0 до 9.")
            continue

        try:
            ReportStructure.objects.create(
                product=product,
                level=level,
                code=_csv_row_value(row, code_col),
                name=_csv_row_value(row, name_col),
                position=_next_position(ReportStructure, {"product": product}),
            )
            changed_product_ids.add(product.pk)
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    for product_id in changed_product_ids:
        _normalize_report_structure_positions(product_id)
    return _policy_import_success_response(
        request, ok=True, created=created, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def report_structure_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(REPORT_STRUCTURE_CSV_HEADERS)

    report_structures = list(_apply_policy_master_product_filters(_ordered_report_structures_queryset(), request))
    report_structure_numbers = _build_report_structure_numbers(report_structures)
    for report_structure in report_structures:
        writer.writerow(
            [
                report_structure.product.short_name,
                report_structure.level,
                report_structure_numbers.get(report_structure.pk, ""),
                report_structure.code,
                report_structure.name,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="report_structures.csv"'
    return response


def _normalize_report_structure_positions(product_id: int | None = None):
    qs = ReportStructure.objects.only("id", "position", "product_id")
    if product_id:
        groups = {product_id: list(qs.filter(product_id=product_id).order_by("position", "id"))}
    else:
        groups = {}
        for item in qs.order_by("product_id", "position", "id"):
            groups.setdefault(item.product_id, []).append(item)
    for items in groups.values():
        for idx, item in enumerate(items, start=1):
            if item.position != idx:
                ReportStructure.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def report_structure_move_up(request, pk: int):
    report_structure = get_object_or_404(ReportStructure, pk=pk)
    product_id = report_structure.product_id
    _normalize_report_structure_positions(product_id)
    items = list(ReportStructure.objects.filter(product_id=product_id).order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ReportStructure.objects.filter(pk=cur.id).update(position=prev_pos)
        ReportStructure.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_report_structure_positions(product_id)
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def report_structure_move_down(request, pk: int):
    report_structure = get_object_or_404(ReportStructure, pk=pk)
    product_id = report_structure.product_id
    _normalize_report_structure_positions(product_id)
    items = list(ReportStructure.objects.filter(product_id=product_id).order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ReportStructure.objects.filter(pk=cur.id).update(position=next_pos)
        ReportStructure.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_report_structure_positions(product_id)
    return _render_policy_updated(request)


# --- Цели услуг и названия отчетов ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def service_goal_report_form_create(request):
    if request.method == "GET":
        form = ServiceGoalReportForm(initial=_product_field_initial_from_request(request))
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            _with_workspace_product_lock(request, {"form": form, "action": "create"}, form),
        )
    form = _lock_workspace_product_field(
        request,
        ServiceGoalReportForm(request.POST, initial=_product_field_initial_from_request(request)),
    )
    if not form.is_valid():
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            _with_workspace_product_lock(request, {"form": form, "action": "create"}, form),
        )
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ServiceGoalReport)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def service_goal_report_form_edit(request, pk: int):
    service_goal_report = get_object_or_404(ServiceGoalReport, pk=pk)
    if request.method == "GET":
        form = ServiceGoalReportForm(instance=service_goal_report)
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                {"form": form, "action": "edit", "service_goal_report": service_goal_report},
                form,
                service_goal_report,
            ),
        )
    form = _lock_workspace_product_field(
        request,
        ServiceGoalReportForm(
            request.POST,
            instance=service_goal_report,
            initial=_product_field_initial_from_request(request),
        ),
        service_goal_report,
    )
    if not form.is_valid():
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                {"form": form, "action": "edit", "service_goal_report": service_goal_report},
                form,
                service_goal_report,
            ),
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def service_goal_report_delete(request, pk: int):
    service_goal_report = get_object_or_404(ServiceGoalReport, pk=pk)
    service_goal_report.delete()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def service_goal_report_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    created = 0
    updated = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 5:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 5: "
                "Продукт, Цели оказания услуг, Цели оказания услуг в родительном падеже, "
                "Титул отчета/ТКП, Название продукта)."
            )
            continue

        product_name = row[0].strip()
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        try:
            item = ServiceGoalReport.objects.filter(product=product).order_by("position", "id").first()
            was_created = item is None
            if was_created:
                item = ServiceGoalReport(product=product, position=_next_position(ServiceGoalReport))
            item.service_goal = row[1].strip()
            item.service_goal_genitive = row[2].strip()
            item.report_title = row[3].strip()
            item.product_name = row[4].strip()
            item.save()
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, updated=updated, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def service_goal_report_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(SERVICE_GOAL_REPORT_CSV_HEADERS)

    items = _apply_policy_master_product_filters(
        _policy_service_goal_reports_queryset(),
        request,
    )
    for item in items:
        writer.writerow(
            [
                item.product.short_name,
                item.service_goal,
                item.service_goal_genitive,
                item.report_title,
                item.product_name,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="service_goal_reports.csv"'
    return response


def _normalize_service_goal_report_positions():
    items = ServiceGoalReport.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ServiceGoalReport.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def service_goal_report_move_up(request, pk: int):
    _normalize_service_goal_report_positions()
    items = list(
        ServiceGoalReport.objects
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ServiceGoalReport.objects.filter(pk=cur.id).update(position=prev_pos)
        ServiceGoalReport.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_service_goal_report_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def service_goal_report_move_down(request, pk: int):
    _normalize_service_goal_report_positions()
    items = list(
        ServiceGoalReport.objects
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ServiceGoalReport.objects.filter(pk=cur.id).update(position=next_pos)
        ServiceGoalReport.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_service_goal_report_positions()
    return _render_policy_updated(request)


# --- Типовой состав услуг ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_composition_form_create(request):
    if request.method == "GET":
        form = TypicalServiceCompositionForm(initial=_product_field_initial_from_request(request))
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_composition_form_context(form, "create"), form
            ),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalServiceCompositionForm(
            request.POST,
            initial=_product_field_initial_from_request(request),
        ),
    )
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_composition_form_context(form, "create"), form
            ),
        )
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalServiceComposition)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_composition_form_edit(request, pk: int):
    composition = get_object_or_404(TypicalServiceComposition, pk=pk)
    if request.method == "GET":
        form = TypicalServiceCompositionForm(instance=composition)
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                _typical_service_composition_form_context(form, "edit", composition),
                form,
                composition,
            ),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalServiceCompositionForm(
            request.POST,
            instance=composition,
            initial=_product_field_initial_from_request(request),
        ),
        composition,
    )
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request,
                _typical_service_composition_form_context(form, "edit", composition),
                form,
                composition,
            ),
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_composition_delete(request, pk: int):
    composition = get_object_or_404(TypicalServiceComposition, pk=pk)
    composition.delete()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_composition_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name, sections_by_product = _typical_service_composition_import_lookups()

    created = 0
    warnings = []
    headers = rows[0]
    product_col = _csv_header_index(headers, "Продукт")
    code_col = _csv_header_index(headers, "Код")
    section_col = _csv_header_index(headers, "Раздел (услуга)")
    service_col = _csv_header_index(headers, "Состав услуг")
    if product_col is None:
        product_col = 0
    if section_col is None:
        section_col = 2 if code_col is not None else 1
    if service_col is None:
        service_col = 3 if code_col is not None else 2

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if not _csv_required_columns_present(row, [product_col, section_col, service_col]):
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается "
                "Продукт, Код, Раздел (услуга), Состав услуг)."
            )
            continue

        product_name = _csv_row_value(row, product_col)
        section_code = _csv_row_value(row, code_col)
        section_name = _csv_row_value(row, section_col)
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        section = _resolve_section_from_import(sections_by_product, product.pk, section_code, section_name)
        if not section:
            section_label = section_code or section_name
            warnings.append(f"Строка {i}: раздел «{section_label}» не найден для продукта «{product.short_name}».")
            continue

        service_composition = _csv_row_value(row, service_col)
        try:
            TypicalServiceComposition.objects.create(
                product=product,
                section=section,
                service_composition=service_composition,
                service_composition_editor_state={
                    "html": "",
                    "plain_text": service_composition,
                },
                position=_next_position(TypicalServiceComposition),
            )
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, warnings=warnings
    )


def _typical_service_composition_import_lookups():
    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    sections_by_product = defaultdict(dict)
    for section in TypicalSection.objects.select_related("product").all():
        lookup = sections_by_product[section.product_id]
        for label in (section.name_ru, section.name_en, section.code, section.short_name, section.short_name_ru):
            key = _csv_lookup_key(label)
            if key:
                lookup.setdefault(key, section)
    return products_by_name, sections_by_product


def _normalize_typical_service_composition_editor_state(value, plain_text=""):
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = {}
        else:
            parsed = {}
    elif isinstance(value, dict):
        parsed = value
    else:
        parsed = {}

    fallback_plain_text = str(plain_text or "").strip()
    return {
        "html": str(parsed.get("html") or "").strip(),
        "plain_text": str(parsed.get("plain_text") or fallback_plain_text).strip(),
    }


def _xlsx_cell_value(cell):
    return str(cell.value or "").strip()


def _find_header_column(headers, header_name):
    lookup_name = _csv_lookup_key(header_name)
    for idx, value in enumerate(headers, start=1):
        if _csv_lookup_key(value) == lookup_name:
            return idx
    return None


def _product_display_field_q(char_field, ref_field, values, *, prefix="product__"):
    if not values:
        return Q()
    return Q(**{f"{prefix}{ref_field}__name__in": values}) | Q(
        **{f"{prefix}{ref_field}__isnull": True, f"{prefix}{char_field}__in": values}
    )


def _apply_policy_master_product_filters(qs, request):
    product_ids = [_positive_int(value) for value in request.GET.getlist("product")]
    product_ids = [value for value in product_ids if value]
    if product_ids:
        qs = qs.filter(product_id__in=product_ids)

    consulting = [value.strip() for value in request.GET.getlist("consulting") if value and value.strip()]
    category = [value.strip() for value in request.GET.getlist("category") if value and value.strip()]
    subtype = [value.strip() for value in request.GET.getlist("subtype") if value and value.strip()]

    if consulting:
        qs = qs.filter(_product_display_field_q("consulting_type", "consulting_type_ref", consulting))
    if category:
        qs = qs.filter(_product_display_field_q("service_category", "service_category_ref", category))
    if subtype:
        qs = qs.filter(_product_display_field_q("service_subtype", "service_subtype_ref", subtype))

    return qs


def _apply_policy_master_filters_to_products(qs, request):
    product_ids = [_positive_int(value) for value in request.GET.getlist("product")]
    product_ids = [value for value in product_ids if value]
    if product_ids:
        qs = qs.filter(pk__in=product_ids)

    consulting = [value.strip() for value in request.GET.getlist("consulting") if value and value.strip()]
    category = [value.strip() for value in request.GET.getlist("category") if value and value.strip()]
    subtype = [value.strip() for value in request.GET.getlist("subtype") if value and value.strip()]

    if consulting:
        qs = qs.filter(_product_display_field_q("consulting_type", "consulting_type_ref", consulting, prefix=""))
    if category:
        qs = qs.filter(_product_display_field_q("service_category", "service_category_ref", category, prefix=""))
    if subtype:
        qs = qs.filter(_product_display_field_q("service_subtype", "service_subtype_ref", subtype, prefix=""))

    return qs


def _filter_typical_service_compositions_queryset(request):
    return _apply_policy_master_product_filters(
        _policy_typical_service_compositions_queryset(),
        request,
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def typical_service_composition_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(TYPICAL_SERVICE_COMPOSITION_CSV_HEADERS)

    compositions = _filter_typical_service_compositions_queryset(request)
    for composition in compositions:
        writer.writerow(
            [
                composition.product.short_name,
                composition.section.code,
                composition.section.name_ru or composition.section.name_en,
                composition.service_composition,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="typical_service_compositions.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def typical_service_composition_docx_download(request):
    rows = []
    compositions = _filter_typical_service_compositions_queryset(request)
    for composition in compositions:
        editor_state = _normalize_typical_service_composition_editor_state(
            composition.service_composition_editor_state,
            composition.service_composition,
        )
        rows.append(
            {
                "id": composition.pk,
                "product": composition.product.short_name,
                "section_code": composition.section.code,
                "section": composition.section.name_ru or composition.section.name_en,
                "html": editor_state["html"],
                "plain_text": editor_state["plain_text"] or composition.service_composition,
            }
        )

    content = build_typical_service_compositions_docx(rows)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = 'attachment; filename="typical_service_compositions.docx"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_composition_docx_upload(request):
    docx_file = request.FILES.get("docx_file") or request.FILES.get("csv_file")
    if not docx_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not docx_file.name.lower().endswith(".docx"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы DOCX."}, status=400)

    try:
        rows = parse_typical_service_compositions_docx(docx_file)
    except (BadZipFile, PackageNotFoundError, OSError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": f"Не удалось прочитать DOCX: {exc}"}, status=400)

    products_by_name, sections_by_product = _typical_service_composition_import_lookups()
    created = 0
    updated = 0
    warnings = []

    for row in rows:
        row_number = row.get("row_number")
        row_label = f"Строка {row_number}"
        raw_id = str(row.get("id") or "").strip()
        product_name = str(row.get("product") or "").strip()
        section_code = str(row.get("section_code") or "").strip()
        section_name = str(row.get("section") or "").strip()
        editor_state = _normalize_typical_service_composition_editor_state(
            row.get("editor_state"),
            "",
        )
        service_composition = editor_state["plain_text"]

        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"{row_label}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        section = _resolve_section_from_import(sections_by_product, product.pk, section_code, section_name)
        if not section:
            section_label = section_code or section_name
            warnings.append(f"{row_label}: раздел «{section_label}» не найден для продукта «{product.short_name}».")
            continue

        try:
            with transaction.atomic():
                if raw_id:
                    if not raw_id.isdigit():
                        warnings.append(f"{row_label}: некорректный ID «{raw_id}»; строка пропущена.")
                        continue
                    composition = TypicalServiceComposition.objects.filter(pk=int(raw_id)).first()
                    if not composition:
                        warnings.append(f"{row_label}: строка с ID «{raw_id}» не найдена; строка пропущена.")
                        continue
                    composition.product = product
                    composition.section = section
                    composition.service_composition = service_composition
                    composition.service_composition_editor_state = editor_state
                    composition.save(
                        update_fields=[
                            "product",
                            "section",
                            "service_composition",
                            "service_composition_editor_state",
                            "updated_at",
                        ]
                    )
                    updated += 1
                else:
                    TypicalServiceComposition.objects.create(
                        product=product,
                        section=section,
                        service_composition=service_composition,
                        service_composition_editor_state=editor_state,
                        position=_next_position(TypicalServiceComposition),
                    )
                    created += 1
        except Exception as exc:
            warnings.append(f"{row_label}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, updated=updated, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def typical_service_composition_xlsx_download(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Типовой состав услуг"

    hidden_state_col = len(TYPICAL_SERVICE_COMPOSITION_XLSX_HEADERS) + 1
    ws.append(TYPICAL_SERVICE_COMPOSITION_XLSX_HEADERS + [TYPICAL_SERVICE_COMPOSITION_EDITOR_STATE_HEADER])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="top", wrap_text=True)

    compositions = _filter_typical_service_compositions_queryset(request)
    for composition in compositions:
        editor_state = _normalize_typical_service_composition_editor_state(
            composition.service_composition_editor_state,
            composition.service_composition,
        )
        ws.append(
            [
                composition.product.short_name,
                composition.section.code,
                composition.section.name_ru or composition.section.name_en,
                editor_state["plain_text"] or composition.service_composition,
                json.dumps(editor_state, ensure_ascii=False),
            ]
        )

    widths = {
        1: 18,
        2: 16,
        3: 28,
        4: 80,
        hidden_state_col: 80,
    }
    for col_idx, width in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.column_dimensions[get_column_letter(hidden_state_col)].hidden = True
    ws.freeze_panes = "A2"

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="typical_service_compositions.xlsx"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_composition_xlsx_upload(request):
    xlsx_file = request.FILES.get("xlsx_file") or request.FILES.get("csv_file")
    if not xlsx_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not xlsx_file.name.lower().endswith(".xlsx"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы XLSX."}, status=400)

    try:
        wb = load_workbook(xlsx_file, data_only=False)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": f"Не удалось прочитать XLSX: {exc}"}, status=400)

    ws = wb.active
    if ws.max_row < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    headers = [_xlsx_cell_value(cell) for cell in ws[1]]
    product_col = _find_header_column(headers, "Продукт") or 1
    code_col = _find_header_column(headers, "Код")
    section_col = _find_header_column(headers, "Раздел (услуга)") or (3 if code_col else 2)
    service_col = _find_header_column(headers, "Состав услуг") or (4 if code_col else 3)
    editor_state_col = _find_header_column(headers, TYPICAL_SERVICE_COMPOSITION_EDITOR_STATE_HEADER)

    products_by_name, sections_by_product = _typical_service_composition_import_lookups()
    created = 0
    warnings = []

    for row_idx in range(2, ws.max_row + 1):
        product_name = _xlsx_cell_value(ws.cell(row=row_idx, column=product_col))
        section_code = _xlsx_cell_value(ws.cell(row=row_idx, column=code_col)) if code_col else ""
        section_name = _xlsx_cell_value(ws.cell(row=row_idx, column=section_col))
        service_composition = _xlsx_cell_value(ws.cell(row=row_idx, column=service_col))
        editor_state_raw = (
            ws.cell(row=row_idx, column=editor_state_col).value
            if editor_state_col
            else None
        )

        if not any([product_name, section_name, service_composition, str(editor_state_raw or "").strip()]):
            continue

        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {row_idx}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        section = _resolve_section_from_import(sections_by_product, product.pk, section_code, section_name)
        if not section:
            section_label = section_code or section_name
            warnings.append(f"Строка {row_idx}: раздел «{section_label}» не найден для продукта «{product.short_name}».")
            continue

        try:
            editor_state = _normalize_typical_service_composition_editor_state(
                editor_state_raw,
                service_composition,
            )
            if (
                editor_state_raw
                and service_composition
                and editor_state["plain_text"]
                and editor_state["plain_text"] != service_composition
            ):
                editor_state = {"html": "", "plain_text": service_composition}
                warnings.append(
                    f"Строка {row_idx}: видимый текст отличается от скрытого состояния редактора; "
                    "форматирование для этой строки сброшено."
                )
            service_composition_plain = editor_state["plain_text"] or service_composition
            TypicalServiceComposition.objects.create(
                product=product,
                section=section,
                service_composition=service_composition_plain,
                service_composition_editor_state=editor_state,
                position=_next_position(TypicalServiceComposition),
            )
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {row_idx}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, warnings=warnings
    )


def _normalize_typical_service_composition_positions():
    items = TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            TypicalServiceComposition.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_composition_move_up(request, pk: int):
    _normalize_typical_service_composition_positions()
    items = list(
        TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        TypicalServiceComposition.objects.filter(pk=cur.id).update(position=prev_pos)
        TypicalServiceComposition.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_typical_service_composition_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_composition_move_down(request, pk: int):
    _normalize_typical_service_composition_positions()
    items = list(
        TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        TypicalServiceComposition.objects.filter(pk=cur.id).update(position=next_pos)
        TypicalServiceComposition.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_typical_service_composition_positions()
    return _render_policy_updated(request)


# --- Типовые сроки оказания услуг ---

def _typical_service_term_gantt_base_date():
    return date.today().replace(month=1, day=1)


def _add_typical_service_term_gantt_months(start_date, months):
    safe_months = max(Decimal(months or 0), Decimal("0"))
    whole_months = int(safe_months)
    fractional_months = safe_months - Decimal(whole_months)
    month_index = start_date.month - 1 + whole_months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    whole_date = date(year, month, day)
    extra_days = int((fractional_months * Decimal("30")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return whole_date + timedelta(days=extra_days)


def _normalize_typical_service_term_unit(value, default):
    raw = str(value or "").strip()
    return raw if raw in TypicalServiceTerm.TermUnit.values else default


def _typical_service_term_duration_days(value, unit):
    term_value = max(Decimal(value or 0), Decimal("0"))
    unit = _normalize_typical_service_term_unit(unit, TypicalServiceTerm.TermUnit.WEEKS)
    if unit == TypicalServiceTerm.TermUnit.DAYS:
        return int(term_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if unit == TypicalServiceTerm.TermUnit.MONTHS:
        return int((term_value * Decimal("30")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((term_value * Decimal("7")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _add_typical_service_term_gantt_term(start_date, value, unit):
    unit = _normalize_typical_service_term_unit(unit, TypicalServiceTerm.TermUnit.WEEKS)
    if unit == TypicalServiceTerm.TermUnit.MONTHS:
        return _add_typical_service_term_gantt_months(start_date, value)
    return start_date + timedelta(days=_typical_service_term_duration_days(value, unit))


def _typical_service_term_days_to_value(days, unit):
    safe_days = max(int(days or 0), 0)
    unit = _normalize_typical_service_term_unit(unit, TypicalServiceTerm.TermUnit.WEEKS)
    if unit == TypicalServiceTerm.TermUnit.DAYS:
        return Decimal(safe_days)
    if unit == TypicalServiceTerm.TermUnit.MONTHS:
        return (Decimal(safe_days) / Decimal("30")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return (Decimal(safe_days) / Decimal("7")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _serialize_typical_service_term_gantt_date(value):
    return value.isoformat()


def _default_typical_service_term_gantt_data(term):
    base_date = _typical_service_term_gantt_base_date()
    source_data_end = _add_typical_service_term_gantt_term(
        base_date,
        getattr(term, "source_data_weeks", 0),
        getattr(term, "source_data_term_unit", TypicalServiceTerm.TermUnit.WEEKS),
    )
    preliminary_end = _add_typical_service_term_gantt_term(
        source_data_end,
        term.preliminary_report_months,
        getattr(term, "preliminary_report_term_unit", TypicalServiceTerm.TermUnit.MONTHS),
    )
    final_end = _add_typical_service_term_gantt_term(
        preliminary_end,
        term.final_report_weeks,
        getattr(term, "final_report_term_unit", TypicalServiceTerm.TermUnit.WEEKS),
    )
    prefix = f"typical-service-term-{term.pk}"
    return {
        "data": [
            {
                "id": f"{prefix}-source-data",
                "text": "Исходные данные",
                "start_date": _serialize_typical_service_term_gantt_date(base_date),
                "end_date": _serialize_typical_service_term_gantt_date(source_data_end),
                "progress": 0,
                "system_key": "source_data",
                "type": "project",
                "is_report_bar": True,
                "$open": True,
            },
            {
                "id": f"{prefix}-source-data-asset",
                "text": "Актив",
                "start_date": _serialize_typical_service_term_gantt_date(base_date),
                "end_date": _serialize_typical_service_term_gantt_date(source_data_end),
                "progress": 0,
                "system_key": "source_data_asset",
                "type": "task",
                "parent": f"{prefix}-source-data",
                "is_report_bar": True,
            },
            {
                "id": f"{prefix}-preliminary-report",
                "text": "Предварительный отчёт",
                "start_date": _serialize_typical_service_term_gantt_date(source_data_end),
                "end_date": _serialize_typical_service_term_gantt_date(preliminary_end),
                "progress": 0,
                "system_key": "preliminary_report",
                "type": "project",
                "is_report_bar": True,
                "$open": True,
            },
            {
                "id": f"{prefix}-preliminary-report-asset",
                "text": "Актив",
                "start_date": _serialize_typical_service_term_gantt_date(source_data_end),
                "end_date": _serialize_typical_service_term_gantt_date(preliminary_end),
                "progress": 0,
                "system_key": "preliminary_report_asset",
                "type": "task",
                "parent": f"{prefix}-preliminary-report",
                "is_report_bar": True,
            },
            {
                "id": f"{prefix}-preliminary-report-submission",
                "text": "Отправка Предварительного отчёта",
                "start_date": _serialize_typical_service_term_gantt_date(preliminary_end),
                "end_date": _serialize_typical_service_term_gantt_date(preliminary_end),
                "progress": 0,
                "system_key": "preliminary_report_submission",
                "type": "milestone",
                "is_report_bar": True,
            },
            {
                "id": f"{prefix}-final-report",
                "text": "Итоговый отчёт",
                "start_date": _serialize_typical_service_term_gantt_date(preliminary_end),
                "end_date": _serialize_typical_service_term_gantt_date(final_end),
                "progress": 0,
                "system_key": "final_report",
                "type": "task",
                "is_report_bar": True,
            },
        ],
        "links": [
            {
                "id": f"{prefix}-source-data-to-preliminary",
                "source": f"{prefix}-source-data",
                "target": f"{prefix}-preliminary-report",
                "type": "0",
            },
            {
                "id": f"{prefix}-preliminary-to-submission",
                "source": f"{prefix}-preliminary-report",
                "target": f"{prefix}-preliminary-report-submission",
                "type": "0",
            },
            {
                "id": f"{prefix}-submission-to-final",
                "source": f"{prefix}-preliminary-report-submission",
                "target": f"{prefix}-final-report",
                "type": "0",
            }
        ],
        "meta": {
            "base_date": _serialize_typical_service_term_gantt_date(base_date),
            "project_start": _serialize_typical_service_term_gantt_date(base_date),
            "project_end": _serialize_typical_service_term_gantt_date(final_end),
            "calendar_kind": TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT,
            "executor_display": TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE,
            "version": TYPICAL_SERVICE_TERM_GANTT_VERSION,
        },
    }


def _parse_typical_service_term_gantt_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _task_end_date(task, start_date):
    end_date = _parse_typical_service_term_gantt_date(task.get("end_date"))
    if end_date:
        return end_date
    try:
        duration = int(Decimal(str(task.get("duration", 0))))
    except (InvalidOperation, ValueError, TypeError):
        duration = 0
    return start_date + timedelta(days=max(duration, 0))


def _unique_typical_service_term_gantt_task_id(tasks, preferred_id):
    existing = {str(task.get("id")) for task in tasks if task.get("id") is not None}
    candidate = str(preferred_id or "task").strip() or "task"
    if candidate not in existing:
        return candidate
    suffix = 1
    while f"{candidate}-{suffix}" in existing:
        suffix += 1
    return f"{candidate}-{suffix}"


def _sync_typical_service_term_gantt_asset_task(tasks, parent_system_key="preliminary_report", asset_system_key="preliminary_report_asset"):
    tasks_by_id = {
        str(task.get("id")): task
        for task in tasks
        if task.get("id") is not None
    }
    parent = next(
        (
            task for task in tasks
            if str(task.get("system_key") or "").strip() == parent_system_key
        ),
        None,
    )
    if parent is None or parent.get("id") is None:
        return None

    parent_id = str(parent.get("id"))
    asset = next(
        (
            task for task in tasks
            if str(task.get("system_key") or "").strip() == asset_system_key
        ),
        None,
    )
    if asset is None:
        asset = next(
            (
                task for task in tasks
                if str(task.get("parent") or "").strip() == parent_id
                and str(task.get("text") or "").strip() == "Актив"
            ),
            None,
        )
        if asset is None:
            asset = {
                "id": _unique_typical_service_term_gantt_task_id(
                    tasks,
                    f"{parent_id}-asset",
                ),
                "progress": 0,
                "type": "task",
                "is_report_bar": True,
            }
            try:
                insert_at = tasks.index(parent) + 1
            except ValueError:
                insert_at = len(tasks)
            tasks.insert(insert_at, asset)

    start_date = _parse_typical_service_term_gantt_date(parent.get("start_date"))
    if start_date:
        end_date = _task_end_date(parent, start_date)
        asset["start_date"] = _serialize_typical_service_term_gantt_date(start_date)
        asset["end_date"] = _serialize_typical_service_term_gantt_date(end_date)
        asset["duration"] = max((end_date - start_date).days, 0)
    asset["system_key"] = asset_system_key
    asset["text"] = TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT[asset_system_key]
    asset["parent"] = parent_id
    asset["type"] = "task"
    asset["is_report_bar"] = True
    parent["$open"] = True
    if str(parent.get("type") or "").strip() != TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE:
        parent["type"] = "project"
    # Drop impossible self-parenting or stale parent references if the row was
    # repurposed from an existing user task.
    if str(asset.get("id")) == parent_id:
        asset["id"] = _unique_typical_service_term_gantt_task_id(
            [task for task in tasks if task is not asset],
            f"{parent_id}-asset",
        )
    return asset


def _sync_typical_service_term_gantt_system_tasks(tasks):
    preliminary = next(
        (
            task for task in tasks
            if str(task.get("system_key") or "").strip() == "preliminary_report"
            and task.get("id") is not None
        ),
        None,
    )
    source_data = next(
        (
            task for task in tasks
            if str(task.get("system_key") or "").strip() == "source_data"
            and task.get("id") is not None
        ),
        None,
    )
    if source_data is None and preliminary is not None:
        preliminary_start = _parse_typical_service_term_gantt_date(preliminary.get("start_date"))
        preferred_id = f"{preliminary.get('id')}-source-data"
        source_data = {
            "id": _unique_typical_service_term_gantt_task_id(tasks, preferred_id),
            "text": TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT["source_data"],
            "start_date": _serialize_typical_service_term_gantt_date(preliminary_start) if preliminary_start else preliminary.get("start_date"),
            "end_date": _serialize_typical_service_term_gantt_date(preliminary_start) if preliminary_start else preliminary.get("start_date"),
            "duration": 0,
            "progress": 0,
            "system_key": "source_data",
            "type": "project",
            "is_report_bar": True,
            "$open": True,
        }
        try:
            insert_at = tasks.index(preliminary)
        except ValueError:
            insert_at = 0
        tasks.insert(insert_at, source_data)
    submission = next(
        (
            task for task in tasks
            if str(task.get("system_key") or "").strip() == "preliminary_report_submission"
            and task.get("id") is not None
        ),
        None,
    )
    if submission is None and preliminary is not None:
        preliminary_start = _parse_typical_service_term_gantt_date(preliminary.get("start_date"))
        preliminary_end = _task_end_date(preliminary, preliminary_start) if preliminary_start else None
        preferred_id = f"{preliminary.get('id')}-submission"
        submission = {
            "id": _unique_typical_service_term_gantt_task_id(tasks, preferred_id),
            "text": TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT["preliminary_report_submission"],
            "start_date": _serialize_typical_service_term_gantt_date(preliminary_end) if preliminary_end else preliminary.get("end_date") or preliminary.get("start_date"),
            "end_date": _serialize_typical_service_term_gantt_date(preliminary_end) if preliminary_end else preliminary.get("end_date") or preliminary.get("start_date"),
            "duration": 0,
            "progress": 0,
            "system_key": "preliminary_report_submission",
            "type": "milestone",
            "is_report_bar": True,
        }
        preliminary_id = str(preliminary.get("id") or "")
        descendant_ids = {preliminary_id}
        changed = True
        while changed:
            changed = False
            for task in tasks:
                task_id = str(task.get("id") or "")
                if task_id and task_id not in descendant_ids and str(task.get("parent") or "") in descendant_ids:
                    descendant_ids.add(task_id)
                    changed = True
        insert_at = max(
            (index for index, task in enumerate(tasks) if str(task.get("id") or "") in descendant_ids),
            default=-1,
        ) + 1
        tasks.insert(insert_at, submission)
    for system_key in ("source_data", "preliminary_report", "preliminary_report_submission", "final_report"):
        task = next(
            (
                item for item in tasks
                if str(item.get("system_key") or "").strip() == system_key
            ),
            None,
        )
        if task is not None:
            task["text"] = TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT[system_key]
            if system_key == "preliminary_report_submission":
                task["type"] = "milestone"
    _sync_typical_service_term_gantt_asset_task(tasks, "source_data", "source_data_asset")
    _sync_typical_service_term_gantt_asset_task(tasks, "preliminary_report", "preliminary_report_asset")


def _roll_up_typical_service_term_gantt_parent_dates(tasks):
    tasks_by_id = {str(task.get("id")): task for task in tasks if task.get("id") is not None}
    children_by_parent = defaultdict(list)
    for task in tasks:
        parent_id = task.get("parent")
        if parent_id in (None, "", 0, "0"):
            continue
        children_by_parent[str(parent_id)].append(task)

    resolved = {}
    resolving = set()

    def resolve_dates(task):
        task_id = str(task.get("id"))
        if task_id in resolved:
            return resolved[task_id]
        if task_id in resolving:
            raise ValueError("В диаграмме обнаружена циклическая связь родительских задач.")

        resolving.add(task_id)
        try:
            start_date = _parse_typical_service_term_gantt_date(task.get("start_date"))
            if not start_date:
                resolved[task_id] = (None, None)
                return resolved[task_id]
            end_date = _task_end_date(task, start_date)

            child_dates = [
                resolve_dates(child)
                for child in children_by_parent.get(task_id, [])
            ]
            child_dates = [
                (child_start, child_end)
                for child_start, child_end in child_dates
                if child_start and child_end
            ]
            if child_dates:
                start_date = min(child_start for child_start, _ in child_dates)
                end_date = max(child_end for _, child_end in child_dates)
                task["start_date"] = _serialize_typical_service_term_gantt_date(start_date)
                task["end_date"] = _serialize_typical_service_term_gantt_date(end_date)
                task["duration"] = max((end_date - start_date).days, 0)
                if task.get("type") not in {"milestone", TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE}:
                    task["type"] = "project"

            resolved[task_id] = (start_date, end_date)
            return resolved[task_id]
        finally:
            resolving.discard(task_id)

    for task in tasks_by_id.values():
        resolve_dates(task)


def _normalize_typical_service_term_gantt_payload(
    payload,
    allowed_section_names=None,
    section_specialties_by_name=None,
    allowed_specialties=None,
    allowed_executors=None,
):
    if not isinstance(payload, dict):
        raise ValueError("Некорректный формат диаграммы.")
    tasks = payload.get("data", payload.get("tasks", []))
    links = payload.get("links", [])
    if not isinstance(tasks, list):
        raise ValueError("Список задач диаграммы должен быть массивом.")
    if not isinstance(links, list):
        raise ValueError("Список связей диаграммы должен быть массивом.")

    allowed_section_names = set(allowed_section_names or [])
    section_specialties_by_name = section_specialties_by_name or {}
    allowed_specialties = set(allowed_specialties or [])
    executor_specialties_by_key = {}
    executor_legacy_labels = defaultdict(list)
    for item in allowed_executors or []:
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            key = str(item.get("value") or item.get("id") or label).strip()
            specialties = {
                str(value or "").strip()
                for value in item.get("specialties", [])
                if str(value or "").strip()
            }
        else:
            label = str(item or "").strip()
            key = label
            specialties = set()
        if key:
            executor_specialties_by_key[key] = specialties
        if label and key:
            executor_legacy_labels[label].append(key)
    ambiguous_executor_labels = {
        label
        for label, count in Counter(
            str(item.get("label") or "").strip()
            for item in allowed_executors or []
            if isinstance(item, dict) and str(item.get("label") or "").strip()
        ).items()
        if count > 1
    }
    for label, keys in executor_legacy_labels.items():
        if label not in ambiguous_executor_labels and len(keys) == 1:
            executor_specialties_by_key[label] = executor_specialties_by_key[keys[0]]
    allowed_executor_keys = set(executor_specialties_by_key)
    normalized_tasks = [dict(task) for task in tasks if isinstance(task, dict)]
    normalized_links = [dict(link) for link in links if isinstance(link, dict)]
    _sync_typical_service_term_gantt_system_tasks(normalized_tasks)
    normalized_task_ids = {
        str(task.get("id")).strip()
        for task in normalized_tasks
        if task.get("id") is not None and str(task.get("id")).strip()
    }
    parent_task_ids = set()
    for task in normalized_tasks:
        parent_id = str(task.get("parent") or "").strip()
        if parent_id and parent_id not in {"0", "null", "None"} and parent_id in normalized_task_ids:
            parent_task_ids.add(parent_id)
    for link in normalized_links:
        lag_mode = str(link.get("lag_mode") or "").strip().lower()
        link["lag_mode"] = "auto" if lag_mode == "auto" else "fixed"
    meta = dict(payload.get("meta") or {}) if isinstance(payload.get("meta"), dict) else {}
    def validate_executor_specialty(executor, specialty):
        if executor and (not specialty or specialty not in executor_specialties_by_key.get(executor, set())):
            raise ValueError("Выберите исполнителя, связанного с выбранной специальностью.")

    for task in normalized_tasks:
        task_id = str(task.get("id")).strip() if task.get("id") is not None else ""
        is_parent_task = task_id in parent_task_ids
        system_key = str(task.get("system_key") or "").strip()
        if system_key in TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT:
            task["system_key"] = system_key
            task["text"] = TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_TEXT[system_key]
        specialty = str(task.get("specialty") or "").strip()
        executor = str(task.get("executor") or "").strip()
        if is_parent_task:
            specialty = ""
            executor = ""
            task.pop("resource_id", None)
            task.pop("resource_name", None)
        if specialty and specialty not in allowed_specialties:
            raise ValueError("Выберите специальность из списка.")
        if executor and executor not in allowed_executor_keys:
            raise ValueError("Выберите исполнителя из списка.")
        task["specialty"] = specialty
        task["executor"] = executor
        if str(task.get("type") or "").strip() != TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE:
            if not is_parent_task:
                validate_executor_specialty(executor, specialty)
            continue
        section_name = str(task.get("service_section_name") or task.get("section_name") or "").strip()
        display_name = str(task.get("text") or "").strip()
        if not section_name and display_name in allowed_section_names:
            section_name = display_name
        if not section_name or section_name not in allowed_section_names:
            raise ValueError("Выберите раздел (услугу) из списка для выбранного продукта.")
        task["service_section_name"] = section_name
        task["text"] = display_name or section_name
        if is_parent_task:
            task["specialty"] = ""
            task["executor"] = ""
            continue
        section_specialties = section_specialties_by_name.get(section_name, [])
        section_specialty_labels = [item["label"] for item in section_specialties if item.get("label")]
        if section_specialty_labels:
            if specialty and specialty not in section_specialty_labels:
                raise ValueError("Выберите специальность из списка раздела (услуги).")
            task["specialty"] = specialty or section_specialty_labels[0]
        else:
            task["specialty"] = ""
        validate_executor_specialty(executor, task["specialty"])

    task_ids = normalized_task_ids
    tasks_by_id = {
        str(task.get("id")).strip(): task
        for task in normalized_tasks
        if task.get("id") is not None and str(task.get("id")).strip()
    }

    def task_section_name(task):
        if not task:
            return ""
        explicit = str(task.get("service_section_name") or task.get("section_name") or "").strip()
        if explicit in allowed_section_names:
            return explicit
        text = str(task.get("text") or "").strip()
        if text in allowed_section_names:
            return text
        visited = set()
        parent_id = str(task.get("parent") or "").strip()
        while parent_id and parent_id not in {"0", "null", "None"} and parent_id not in visited:
            visited.add(parent_id)
            parent = tasks_by_id.get(parent_id)
            if not parent:
                return ""
            explicit = str(parent.get("service_section_name") or parent.get("section_name") or "").strip()
            if explicit in allowed_section_names:
                return explicit
            text = str(parent.get("text") or "").strip()
            if text in allowed_section_names:
                return text
            parent_id = str(parent.get("parent") or "").strip()
        return ""

    raw_resources = meta.get("resources", [])
    if raw_resources in (None, ""):
        raw_resources = []
    if not isinstance(raw_resources, list):
        raise ValueError("Список ресурсов проекта должен быть массивом.")
    normalized_resources = []
    seen_resource_ids = set()
    seen_resource_task_ids = set()
    seen_resource_pairs = set()
    resource_numbers_by_executor = {}
    next_resource_number = 1
    for index, resource in enumerate(raw_resources, start=1):
        if not isinstance(resource, dict):
            continue
        resource_id = str(resource.get("id") or f"resource-{index}").strip()
        if not resource_id:
            resource_id = f"resource-{index}"
        if resource_id in seen_resource_ids:
            base_resource_id = resource_id
            suffix = 2
            while resource_id in seen_resource_ids:
                resource_id = f"{base_resource_id}-{suffix}"
                suffix += 1
        seen_resource_ids.add(resource_id)
        specialty = str(resource.get("specialty") or "").strip()
        executor = str(resource.get("executor") or "").strip()
        if specialty and specialty not in allowed_specialties:
            raise ValueError("Выберите специальность ресурса из списка.")
        if executor and executor not in allowed_executor_keys:
            raise ValueError("Выберите исполнителя ресурса из списка.")
        validate_executor_specialty(executor, specialty)
        resource_pair = (specialty, executor)
        if specialty and executor:
            if resource_pair in seen_resource_pairs:
                raise ValueError("Ресурс с такой специальностью и ФИО уже есть в таблице.")
            seen_resource_pairs.add(resource_pair)
        resource_number_key = f"executor:{executor}" if executor else f"resource:{resource_id}"
        if resource_number_key not in resource_numbers_by_executor:
            resource_numbers_by_executor[resource_number_key] = next_resource_number
            next_resource_number += 1
        resource_name = f"Сотрудник {resource_numbers_by_executor[resource_number_key]}"
        raw_task_ids = resource.get("task_ids", resource.get("taskIds", []))
        if raw_task_ids in (None, ""):
            raw_task_ids = []
        if not isinstance(raw_task_ids, list):
            raise ValueError("Список задач ресурса должен быть массивом.")
        task_id_list = []
        for raw_task_id in raw_task_ids:
            task_id = str(raw_task_id or "").strip()
            if not task_id:
                continue
            if task_id not in task_ids:
                raise ValueError("Выберите задачу ресурса из списка задач диаграммы.")
            if task_id in parent_task_ids:
                raise ValueError("Родительскую задачу нельзя назначить ресурсу проекта.")
            task = tasks_by_id.get(task_id)
            section_name = task_section_name(task)
            section_specialty_labels = [
                item["label"]
                for item in section_specialties_by_name.get(section_name, [])
                if item.get("label")
            ]
            if specialty and section_specialty_labels and specialty not in section_specialty_labels:
                raise ValueError("Выберите задачу из раздела (услуги), доступного выбранной специальности ресурса.")
            if task_id in seen_resource_task_ids:
                raise ValueError("Одна задача не может быть назначена нескольким ресурсам.")
            seen_resource_task_ids.add(task_id)
            task_id_list.append(task_id)
        normalized_resources.append({
            "id": resource_id,
            "specialty": specialty,
            "executor": executor,
            "resource_name": resource_name,
            "task_ids": task_id_list,
            "position": index,
        })
    for resource in normalized_resources:
        for task_id in resource["task_ids"]:
            task = tasks_by_id.get(task_id)
            if not task:
                continue
            task["specialty"] = resource["specialty"]
            task["executor"] = resource["executor"]
            task["resource_id"] = resource["id"]
            task["resource_name"] = resource["resource_name"]
    meta["resources"] = normalized_resources
    _roll_up_typical_service_term_gantt_parent_dates(normalized_tasks)
    _sync_typical_service_term_gantt_system_tasks(normalized_tasks)
    _roll_up_typical_service_term_gantt_parent_dates(normalized_tasks)

    dated_tasks = []
    for task in normalized_tasks:
        start_date = _parse_typical_service_term_gantt_date(task.get("start_date"))
        if not start_date:
            continue
        end_date = _task_end_date(task, start_date)
        task["start_date"] = _serialize_typical_service_term_gantt_date(start_date)
        task["end_date"] = _serialize_typical_service_term_gantt_date(end_date)
        dated_tasks.append((task, start_date, end_date))

    if not dated_tasks:
        raise ValueError("В диаграмме должна быть хотя бы одна задача с датой начала.")

    base_date = _parse_typical_service_term_gantt_date(meta.get("base_date"))
    if not base_date:
        base_date = min(start_date for _, start_date, _ in dated_tasks)
    meta["base_date"] = _serialize_typical_service_term_gantt_date(base_date)
    project_start = _parse_typical_service_term_gantt_date(meta.get("project_start"))
    if not project_start:
        project_start = min(start_date for _, start_date, _ in dated_tasks)
    project_end = _parse_typical_service_term_gantt_date(meta.get("project_end"))
    if not project_end:
        project_end = max(end_date for _, _, end_date in dated_tasks)
    if project_end < project_start:
        project_end = project_start
    meta["project_start"] = _serialize_typical_service_term_gantt_date(project_start)
    meta["project_end"] = _serialize_typical_service_term_gantt_date(project_end)
    executor_display = str(meta.get("executor_display") or "").strip()
    if executor_display not in {
        TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR,
        TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE,
    }:
        executor_display = (
            TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
            if str(meta.get("calendar_kind") or "").strip() == "abstract"
            else TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR
        )
    meta["executor_display"] = executor_display
    meta["version"] = TYPICAL_SERVICE_TERM_GANTT_VERSION

    return {"data": normalized_tasks, "links": normalized_links, "meta": meta}, dated_tasks, base_date


def _find_typical_service_term_system_task(dated_tasks, system_key):
    for task, start_date, end_date in dated_tasks:
        if task.get("system_key") == system_key:
            return task, start_date, end_date
    return None


def _calculate_typical_service_term_durations(
    dated_tasks,
    *,
    source_data_unit=TypicalServiceTerm.TermUnit.WEEKS,
    preliminary_unit=TypicalServiceTerm.TermUnit.MONTHS,
    final_unit=TypicalServiceTerm.TermUnit.WEEKS,
):
    source_data_task = _find_typical_service_term_system_task(dated_tasks, "source_data")
    preliminary_task = _find_typical_service_term_system_task(dated_tasks, "preliminary_report")
    final_task = _find_typical_service_term_system_task(dated_tasks, "final_report")
    if not source_data_task:
        raise ValueError("Не найдена задача «Исходные данные».")
    if not preliminary_task:
        raise ValueError("Не найдена задача «Предварительный отчёт».")
    if not final_task:
        raise ValueError("Не найдена задача «Итоговый отчёт».")

    _, source_data_start, source_data_end = source_data_task
    _, preliminary_start, preliminary_end = preliminary_task
    _, final_start, final_end = final_task
    source_data_days = max((source_data_end - source_data_start).days, 0)
    preliminary_days = max((preliminary_end - preliminary_start).days, 0)
    final_days = max((final_end - final_start).days, 0)
    source_data_value = _typical_service_term_days_to_value(source_data_days, source_data_unit)
    preliminary_value = _typical_service_term_days_to_value(preliminary_days, preliminary_unit)
    final_value = _typical_service_term_days_to_value(final_days, final_unit)
    return source_data_value, preliminary_value, final_value


def _typical_service_term_specialty_options():
    return [
        value
        for value in ExpertSpecialty.objects.order_by("position", "id").values_list("specialty", flat=True)
        if str(value or "").strip()
    ]


def _format_typical_service_term_executor_name(profile):
    user = profile.employee.user
    last_name = str(user.last_name or "").strip()
    first_name = str(user.first_name or "").strip()
    middle_name = str(profile.employee.patronymic or "").strip()
    initials = "".join(part[:1] + "." for part in (first_name, middle_name) if part)
    if last_name and initials:
        return f"{last_name} {initials}"
    return str(profile.full_name or "").strip()


def _typical_service_term_executor_value(profile):
    return f"expert-profile:{profile.pk}"


def _typical_service_term_executor_options():
    options = []
    for profile in (
        ExpertProfile.objects.select_related("employee__user")
        .prefetch_related("ranked_specialties", "ranked_specialties__specialty")
        .order_by("position", "id")
    ):
        label = _format_typical_service_term_executor_name(profile)
        if not label:
            continue
        option = {
            "id": profile.pk,
            "value": _typical_service_term_executor_value(profile),
            "label": label,
            "specialties": [],
        }
        seen_specialties = set()
        for link in profile.ranked_specialties.all():
            specialty = str(link.specialty.specialty or "").strip()
            if specialty and specialty not in seen_specialties:
                option["specialties"].append(specialty)
                seen_specialties.add(specialty)
        options.append(option)
    return options


def _typical_service_term_section_options(product_id):
    sections = (
        TypicalSection.objects.filter(product_id=product_id)
        .exclude(Q(is_system=True) | Q(code__iexact=SYSTEM_DSC_SECTION_CODE))
        .prefetch_related("ranked_specialties", "ranked_specialties__specialty")
        .order_by("position", "id")
    )
    options = []
    for section in sections:
        specialties = []
        seen = set()
        for link in section.ranked_specialties.all():
            label = str(link.specialty.specialty or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            specialties.append({"label": label, "rank": link.rank})
        options.append({"id": section.id, "label": section.name_ru, "specialties": specialties})
    return options


def _typical_service_term_gantt_response_payload(term):
    gantt_data = copy.deepcopy(term.gantt_data) if isinstance(term.gantt_data, dict) and term.gantt_data.get("data") else None
    if gantt_data is not None:
        meta = gantt_data.setdefault("meta", {})
        meta.setdefault("calendar_kind", TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT)
        meta.setdefault("executor_display", TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE)
        tasks = gantt_data.get("data")
        if isinstance(tasks, list):
            try:
                _sync_typical_service_term_gantt_system_tasks(tasks)
                _roll_up_typical_service_term_gantt_parent_dates(tasks)
                _sync_typical_service_term_gantt_system_tasks(tasks)
                _roll_up_typical_service_term_gantt_parent_dates(tasks)
            except ValueError:
                pass
    section_options = _typical_service_term_section_options(term.product_id)
    return {
        "ok": True,
        "gantt": gantt_data or _default_typical_service_term_gantt_data(term),
        "section_options": section_options,
        "specialty_options": _typical_service_term_specialty_options(),
        "executor_options": _typical_service_term_executor_options(),
        "term": {
            "id": term.pk,
            "product": term.product.short_name,
            "source_data_weeks": term.source_data_weeks,
            "source_data_term_unit": term.source_data_term_unit,
            "source_data_display": term.source_data_display,
            "preliminary_report_months": term.preliminary_report_months_display,
            "preliminary_report_term_unit": term.preliminary_report_term_unit,
            "preliminary_report_display": term.preliminary_report_display,
            "final_report_weeks": term.final_report_weeks,
            "final_report_term_unit": term.final_report_term_unit,
            "final_report_display": term.final_report_display,
        },
    }


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_term_form_create(request):
    if request.method == "GET":
        form = TypicalServiceTermForm(initial=_product_field_initial_from_request(request))
        return render(
            request,
            TYPICAL_SERVICE_TERM_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_term_form_context(form, "create"), form
            ),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalServiceTermForm(request.POST, initial=_product_field_initial_from_request(request)),
    )
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_TERM_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_term_form_context(form, "create"), form
            ),
        )
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalServiceTerm)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_term_form_edit(request, pk: int):
    term = get_object_or_404(TypicalServiceTerm, pk=pk)
    if request.method == "GET":
        form = TypicalServiceTermForm(instance=term)
        return render(
            request,
            TYPICAL_SERVICE_TERM_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_term_form_context(form, "edit", term), form, term
            ),
        )
    form = _lock_workspace_product_field(
        request,
        TypicalServiceTermForm(
            request.POST,
            instance=term,
            initial=_product_field_initial_from_request(request),
        ),
        term,
    )
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_TERM_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _typical_service_term_form_context(form, "edit", term), form, term
            ),
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_term_gantt(request, pk: int):
    term = get_object_or_404(TypicalServiceTerm.objects.select_related("product"), pk=pk)
    if request.method == "GET":
        return JsonResponse(_typical_service_term_gantt_response_payload(term))

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        for task in (payload.get("data") or []) if isinstance(payload, dict) else []:
            if not isinstance(task, dict):
                continue
            for key in (
                "managed_source",
                "managed_scope",
                "work_volume_id",
                "performer_id",
                "typical_section_id",
                "template_task_id",
                "asset_name",
            ):
                task.pop(key, None)
            if task.get("system_key") == "project_asset":
                task["system_key"] = "preliminary_report_asset"
            if task.get("system_key") == "source_data_project_asset":
                task["system_key"] = "source_data_asset"
        meta = payload.setdefault("meta", {}) if isinstance(payload, dict) else {}
        if isinstance(meta, dict):
            calendar_kind = str(meta.get("calendar_kind") or TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT).strip()
            if calendar_kind != TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT:
                raise ValueError("Типовая диаграмма должна сохраняться только в условном календаре.")
            meta["calendar_kind"] = TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
            meta["executor_display"] = TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
        section_options = _typical_service_term_section_options(term.product_id)
        section_names = [item["label"] for item in section_options]
        section_specialties_by_name = {
            item["label"]: item.get("specialties", [])
            for item in section_options
        }
        specialty_options = _typical_service_term_specialty_options()
        executor_options = _typical_service_term_executor_options()
        gantt_data, dated_tasks, base_date = _normalize_typical_service_term_gantt_payload(
            payload,
            section_names,
            section_specialties_by_name,
            specialty_options,
            executor_options,
        )
        source_data_weeks, preliminary_months, final_weeks = _calculate_typical_service_term_durations(
            dated_tasks,
            source_data_unit=term.source_data_term_unit,
            preliminary_unit=term.preliminary_report_term_unit,
            final_unit=term.final_report_term_unit,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    term.gantt_data = gantt_data
    term.source_data_weeks = source_data_weeks
    term.preliminary_report_months = preliminary_months
    term.final_report_weeks = final_weeks
    term.save(update_fields=["gantt_data", "source_data_weeks", "preliminary_report_months", "final_report_weeks", "updated_at"])
    response_payload = _typical_service_term_gantt_response_payload(term)
    response_payload["policyUpdate"] = _policy_mutation_detail(request)
    return JsonResponse(response_payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_term_delete(request, pk: int):
    term = get_object_or_404(TypicalServiceTerm, pk=pk)
    term.delete()
    return _render_policy_updated(request)


def _typical_service_term_unit_label(unit):
    return dict(TypicalServiceTerm.TermUnit.choices).get(unit, "")


def _parse_typical_service_term_csv_unit(raw, *, default, row_index, field_label):
    value = str(raw or "").strip().lower().replace("\u00a0", " ")
    value = " ".join(value.split())
    if not value:
        return default
    aliases = {
        "days": TypicalServiceTerm.TermUnit.DAYS,
        "day": TypicalServiceTerm.TermUnit.DAYS,
        "дн": TypicalServiceTerm.TermUnit.DAYS,
        "дн.": TypicalServiceTerm.TermUnit.DAYS,
        "день": TypicalServiceTerm.TermUnit.DAYS,
        "дни": TypicalServiceTerm.TermUnit.DAYS,
        "weeks": TypicalServiceTerm.TermUnit.WEEKS,
        "week": TypicalServiceTerm.TermUnit.WEEKS,
        "нед": TypicalServiceTerm.TermUnit.WEEKS,
        "нед.": TypicalServiceTerm.TermUnit.WEEKS,
        "неделя": TypicalServiceTerm.TermUnit.WEEKS,
        "недели": TypicalServiceTerm.TermUnit.WEEKS,
        "months": TypicalServiceTerm.TermUnit.MONTHS,
        "month": TypicalServiceTerm.TermUnit.MONTHS,
        "мес": TypicalServiceTerm.TermUnit.MONTHS,
        "мес.": TypicalServiceTerm.TermUnit.MONTHS,
        "месяц": TypicalServiceTerm.TermUnit.MONTHS,
        "месяцы": TypicalServiceTerm.TermUnit.MONTHS,
    }
    unit = aliases.get(value)
    if unit:
        return unit
    raise ValueError(f"Строка {row_index}: некорректная единица для поля «{field_label}» — «{raw}».")


def _parse_typical_service_term_csv_decimal(raw, *, unit, row_index, field_label):
    value = str(raw or "").strip().replace("\u00a0", "").replace(" ", "")
    if not value:
        value = "0"
    try:
        parsed = Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Строка {row_index}: некорректный срок «{field_label}» — «{raw}».")
    if parsed < 0:
        raise ValueError(f"Строка {row_index}: срок «{field_label}» не может быть отрицательным.")
    if unit == TypicalServiceTerm.TermUnit.DAYS and parsed != parsed.to_integral_value():
        raise ValueError(f"Строка {row_index}: срок «{field_label}» в днях должен быть целым числом.")
    return parsed.to_integral_value() if unit == TypicalServiceTerm.TermUnit.DAYS else parsed


def _format_typical_service_term_csv_decimal(value, unit):
    if unit == TypicalServiceTerm.TermUnit.DAYS:
        return str(int(Decimal(value or 0)))
    return format(Decimal(value or 0), ".1f").replace(".", ",")


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_term_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    created = 0
    updated = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 3:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 3, 4 или 7)."
            )
            continue

        product_name = row[0].strip()
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        try:
            if len(row) >= 7:
                source_data_raw = row[1].strip()
                source_data_unit = _parse_typical_service_term_csv_unit(
                    row[2],
                    default=TypicalServiceTerm.TermUnit.WEEKS,
                    row_index=i,
                    field_label="Сроки предоставления исходных данных",
                )
                preliminary_raw = row[3].strip()
                preliminary_unit = _parse_typical_service_term_csv_unit(
                    row[4],
                    default=TypicalServiceTerm.TermUnit.MONTHS,
                    row_index=i,
                    field_label="Срок подготовки Предварительного отчёта",
                )
                final_raw = row[5].strip()
                final_unit = _parse_typical_service_term_csv_unit(
                    row[6],
                    default=TypicalServiceTerm.TermUnit.WEEKS,
                    row_index=i,
                    field_label="Срок подготовки Итогового отчёта",
                )
            else:
                has_source_data_column = len(row) >= 4
                source_data_raw = row[1].strip() if has_source_data_column else "0"
                preliminary_raw = row[2].strip() if has_source_data_column else row[1].strip()
                final_raw = row[3].strip() if has_source_data_column else row[2].strip()
                source_data_unit = TypicalServiceTerm.TermUnit.WEEKS
                preliminary_unit = TypicalServiceTerm.TermUnit.MONTHS
                final_unit = TypicalServiceTerm.TermUnit.WEEKS

            source_data_weeks = _parse_typical_service_term_csv_decimal(
                source_data_raw,
                unit=source_data_unit,
                row_index=i,
                field_label="Сроки предоставления исходных данных",
            )
            preliminary_report_months = _parse_typical_service_term_csv_decimal(
                preliminary_raw,
                unit=preliminary_unit,
                row_index=i,
                field_label="Срок подготовки Предварительного отчёта",
            )
            final_report_weeks = _parse_typical_service_term_csv_decimal(
                final_raw,
                unit=final_unit,
                row_index=i,
                field_label="Срок подготовки Итогового отчёта",
            )
        except ValueError as exc:
            warnings.append(str(exc))
            continue

        try:
            item = TypicalServiceTerm.objects.filter(product=product).order_by("position", "id").first()
            was_created = item is None
            if was_created:
                item = TypicalServiceTerm(product=product, position=_next_position(TypicalServiceTerm))
            item.source_data_weeks = source_data_weeks
            item.source_data_term_unit = source_data_unit
            item.preliminary_report_months = preliminary_report_months
            item.preliminary_report_term_unit = preliminary_unit
            item.final_report_weeks = final_report_weeks
            item.final_report_term_unit = final_unit
            item.save()
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, updated=updated, warnings=warnings
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def typical_service_term_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(TYPICAL_SERVICE_TERM_CSV_HEADERS)

    terms = _apply_policy_master_product_filters(
        _policy_typical_service_terms_queryset(),
        request,
    )
    for term in terms:
        writer.writerow(
            [
                term.product.short_name,
                _format_typical_service_term_csv_decimal(term.source_data_weeks, term.source_data_term_unit),
                _typical_service_term_unit_label(term.source_data_term_unit),
                _format_typical_service_term_csv_decimal(
                    term.preliminary_report_months,
                    term.preliminary_report_term_unit,
                ),
                _typical_service_term_unit_label(term.preliminary_report_term_unit),
                _format_typical_service_term_csv_decimal(term.final_report_weeks, term.final_report_term_unit),
                _typical_service_term_unit_label(term.final_report_term_unit),
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="typical_service_terms.csv"'
    return response


def _normalize_typical_service_term_positions():
    items = TypicalServiceTerm.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            TypicalServiceTerm.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_term_move_up(request, pk: int):
    _normalize_typical_service_term_positions()
    items = list(TypicalServiceTerm.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        TypicalServiceTerm.objects.filter(pk=cur.id).update(position=prev_pos)
        TypicalServiceTerm.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_typical_service_term_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_term_move_down(request, pk: int):
    _normalize_typical_service_term_positions()
    items = list(TypicalServiceTerm.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        TypicalServiceTerm.objects.filter(pk=cur.id).update(position=next_pos)
        TypicalServiceTerm.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_typical_service_term_positions()
    return _render_policy_updated(request)


# --- Направления консалтинга ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def consulting_dir_form_create(request):
    if request.method == "GET":
        form = ConsultingDirectionForm()
        return render(
            request,
            CONSULTING_DIR_FORM_TEMPLATE,
            _consulting_direction_form_context(form, "create"),
        )
    form = ConsultingDirectionForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(
            request,
            CONSULTING_DIR_FORM_TEMPLATE,
            _consulting_direction_form_context(form, "create"),
        )
    if not form.instance.position:
        form.instance.position = _next_position(ConsultingDirection)
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def consulting_dir_form_edit(request, pk: int):
    direction = get_object_or_404(ConsultingDirection, pk=pk)
    if request.method == "GET":
        form = ConsultingDirectionForm(instance=direction)
        return render(
            request,
            CONSULTING_DIR_FORM_TEMPLATE,
            _consulting_direction_form_context(form, "edit", direction),
        )
    form = ConsultingDirectionForm(request.POST, instance=direction)
    if not form.is_valid():
        return _render_form_with_errors(
            request,
            CONSULTING_DIR_FORM_TEMPLATE,
            _consulting_direction_form_context(form, "edit", direction),
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def consulting_dir_delete(request, pk: int):
    direction = get_object_or_404(ConsultingDirection, pk=pk)
    direction.delete()
    return _render_policy_updated(request)


def _normalize_consulting_dir_positions():
    items = ConsultingDirection.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            ConsultingDirection.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def consulting_dir_move_up(request, pk: int):
    _normalize_consulting_dir_positions()
    items = list(ConsultingDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ConsultingDirection.objects.filter(pk=cur.id).update(position=prev_pos)
        ConsultingDirection.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_consulting_dir_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def consulting_dir_move_down(request, pk: int):
    _normalize_consulting_dir_positions()
    items = list(ConsultingDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ConsultingDirection.objects.filter(pk=cur.id).update(position=next_pos)
        ConsultingDirection.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_consulting_dir_positions()
    return _render_policy_updated(request)


# --- Направления экспертизы ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def expertise_dir_form_create(request):
    if request.method == "GET":
        form = ExpertiseDirectionForm()
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ExpertiseDirectionForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "create"})
    if not form.instance.position:
        form.instance.position = _next_position(ExpertiseDirection)
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def expertise_dir_form_edit(request, pk: int):
    direction = get_object_or_404(ExpertiseDirection, pk=pk)
    if request.method == "GET":
        form = ExpertiseDirectionForm(instance=direction)
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "edit", "direction": direction})
    form = ExpertiseDirectionForm(request.POST, instance=direction)
    if not form.is_valid():
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "edit", "direction": direction})
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def expertise_dir_delete(request, pk: int):
    direction = get_object_or_404(ExpertiseDirection, pk=pk)
    direction.delete()
    return _render_policy_updated(request)


def _normalize_expertise_dir_positions():
    items = ExpertiseDirection.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            ExpertiseDirection.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def expertise_dir_move_up(request, pk: int):
    _normalize_expertise_dir_positions()
    items = list(ExpertiseDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ExpertiseDirection.objects.filter(pk=cur.id).update(position=prev_pos)
        ExpertiseDirection.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_expertise_dir_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def expertise_dir_move_down(request, pk: int):
    _normalize_expertise_dir_positions()
    items = list(ExpertiseDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ExpertiseDirection.objects.filter(pk=cur.id).update(position=next_pos)
        ExpertiseDirection.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_expertise_dir_positions()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def products_apply_defaults(request):
    """
    Пакетное применение флагов is_default по отмеченным чекбоксам.
    В POST приходит несколько defaults=<id>. Для всех id из списка ставим True, для остальных — False.
    """
    ids_checked = request.POST.getlist("defaults")
    ids_checked = [int(x) for x in ids_checked if str(x).isdigit()]

    # Обновляем — сначала всем False, затем отмеченным True
    Product.objects.update(is_default=False)
    if ids_checked:
        Product.objects.filter(id__in=ids_checked).update(is_default=True)

    return _render_policy_mutation_updated(request, "product-defaults")


# --- Грейды ---

def _grade_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


@login_required
@require_http_methods(["GET", "POST"])
def grade_form_create(request):
    if request.method == "GET":
        form = GradeForm(request_user=request.user)
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    form = GradeForm(request.POST, request_user=request.user)
    if not form.is_valid():
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    obj.created_by = _grade_owner(request, form)
    obj.position = _next_position(Grade, {"created_by": obj.created_by})
    obj.save()
    if form.cleaned_data.get("qualification_levels"):
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(
            qualification_levels=obj.qualification_levels
        )
    if obj.is_base_rate:
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(is_base_rate=False)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["GET", "POST"])
def grade_form_edit(request, pk: int):
    grade = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and grade.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = GradeForm(instance=grade, request_user=request.user)
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "edit", "grade": grade,
            "is_admin": request.user.is_superuser,
        })
    form = GradeForm(request.POST, instance=grade, request_user=request.user)
    if not form.is_valid():
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "edit", "grade": grade,
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    if form.cleaned_data.get("qualification_levels"):
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(
            qualification_levels=obj.qualification_levels
        )
    if obj.is_base_rate:
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(is_base_rate=False)
    return _render_policy_updated(request)


@login_required
@require_POST
def grade_delete(request, pk: int):
    grade = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and grade.created_by != request.user:
        return _render_policy_updated(request)
    grade.delete()
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def grade_move_up(request, pk: int):
    obj = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Grade.objects.filter(created_by=obj.created_by)
    prev = qs.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Grade.objects.filter(pk=obj.pk).update(position=obj.position)
        Grade.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def grade_move_down(request, pk: int):
    obj = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Grade.objects.filter(created_by=obj.created_by)
    nxt = qs.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Grade.objects.filter(pk=obj.pk).update(position=obj.position)
        Grade.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_policy_updated(request)


# --- Тарифы специальностей ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_tariff_form_create(request):
    if request.method == "GET":
        form = SpecialtyTariffForm(request_user=request.user)
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "create"),
                "is_admin": request.user.is_superuser,
            },
        )
    form = SpecialtyTariffForm(request.POST, request_user=request.user)
    if not form.is_valid():
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "create"),
                "is_admin": request.user.is_superuser,
            },
        )
    obj = form.save(commit=False)
    obj.created_by = _specialty_tariff_owner(request, form)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(SpecialtyTariff, {"created_by": obj.created_by})
    obj.save()
    form.save_m2m()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_tariff_form_edit(request, pk: int):
    specialty_tariff = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and specialty_tariff.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = SpecialtyTariffForm(instance=specialty_tariff, request_user=request.user)
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "edit", specialty_tariff),
                "is_admin": request.user.is_superuser,
            },
        )
    form = SpecialtyTariffForm(request.POST, instance=specialty_tariff, request_user=request.user)
    if not form.is_valid():
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "edit", specialty_tariff),
                "is_admin": request.user.is_superuser,
            },
        )
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    form.save_m2m()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def specialty_tariff_delete(request, pk: int):
    specialty_tariff = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and specialty_tariff.created_by != request.user:
        return _render_policy_updated(request)
    specialty_tariff.delete()
    return _render_policy_updated(request)


def _normalize_specialty_tariff_positions():
    items = SpecialtyTariff.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            SpecialtyTariff.objects.filter(pk=item.pk).update(position=idx)


def _normalize_tariff_positions(created_by_id: int | None = None):
    qs = Tariff.objects.only("id", "position", "created_by_id")
    if created_by_id is not None:
        items = qs.filter(created_by_id=created_by_id).order_by("position", "id")
        for idx, item in enumerate(items, start=1):
            if item.position != idx:
                Tariff.objects.filter(pk=item.pk).update(position=idx)
        return
    items = qs.order_by("created_by_id", "position", "id")
    current_owner_id = object()
    idx = 0
    for item in items:
        if item.created_by_id != current_owner_id:
            current_owner_id = item.created_by_id
            idx = 1
        else:
            idx += 1
        if item.position != idx:
            Tariff.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def specialty_tariff_move_up(request, pk: int):
    obj = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = SpecialtyTariff.objects.filter(created_by=obj.created_by)
    prev = qs.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        SpecialtyTariff.objects.filter(pk=obj.pk).update(position=obj.position)
        SpecialtyTariff.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def specialty_tariff_move_down(request, pk: int):
    obj = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = SpecialtyTariff.objects.filter(created_by=obj.created_by)
    nxt = qs.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        SpecialtyTariff.objects.filter(pk=obj.pk).update(position=obj.position)
        SpecialtyTariff.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_policy_updated(request)


# --- Тарифы ---

def _tariff_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


def _tariff_owner_label(user):
    employee = getattr(user, "employee_profile", None)
    if employee and employee.job_title:
        return employee.job_title
    return user.get_full_name() or user.username


def _tariff_form_context(request, form, action, tariff=None):
    ctx = {
        "form": form,
        "action": action,
        "is_admin": request.user.is_superuser,
        "sections_by_product_json": _typical_sections_by_product_json(),
    }
    if tariff:
        ctx["tariff"] = tariff
    return ctx


@login_required
@require_http_methods(["GET", "POST"])
def tariff_form_create(request):
    if request.method == "GET":
        form = TariffForm(initial=_product_field_initial_from_request(request), request_user=request.user)
        return render(
            request,
            TARIFF_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _tariff_form_context(request, form, "create"), form),
        )
    form = _lock_workspace_product_field(
        request,
        TariffForm(
            request.POST,
            initial=_product_field_initial_from_request(request),
            request_user=request.user,
        ),
    )
    if not form.is_valid():
        return render(
            request,
            TARIFF_FORM_TEMPLATE,
            _with_workspace_product_lock(request, _tariff_form_context(request, form, "create"), form),
        )
    obj = form.save(commit=False)
    obj.created_by = _tariff_owner(request, form)
    obj.position = _next_position(Tariff, {"created_by": obj.created_by})
    obj.save()
    return _render_policy_updated(request)


@login_required
@require_http_methods(["GET", "POST"])
def tariff_form_edit(request, pk: int):
    tariff = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and tariff.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = TariffForm(instance=tariff, request_user=request.user)
        return render(
            request,
            TARIFF_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _tariff_form_context(request, form, "edit", tariff), form, tariff
            ),
        )
    form = _lock_workspace_product_field(
        request,
        TariffForm(
            request.POST,
            instance=tariff,
            initial=_product_field_initial_from_request(request),
            request_user=request.user,
        ),
        tariff,
    )
    if not form.is_valid():
        return render(
            request,
            TARIFF_FORM_TEMPLATE,
            _with_workspace_product_lock(
                request, _tariff_form_context(request, form, "edit", tariff), form, tariff
            ),
        )
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    return _render_policy_updated(request)


@login_required
@require_POST
def tariff_delete(request, pk: int):
    tariff = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and tariff.created_by != request.user:
        return _render_policy_updated(request)
    tariff.delete()
    return _render_policy_updated(request)


@login_required
@require_POST
def tariff_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    products_by_name = {_csv_lookup_key(p.short_name): p for p in Product.objects.all()}
    sections_by_product = defaultdict(dict)
    for section in TypicalSection.objects.select_related("product").all():
        lookup = sections_by_product[section.product_id]
        for label in (section.name_ru, section.name_en, section.code, section.short_name, section.short_name_ru):
            key = _csv_lookup_key(label)
            if key:
                lookup.setdefault(key, section)

    owners_by_label = {}
    if request.user.is_superuser:
        for user in get_user_model().objects.select_related("employee_profile").all():
            labels = [
                user.username,
                user.get_full_name(),
                _tariff_owner_label(user),
            ]
            for label in labels:
                key = _csv_lookup_key(label)
                if key:
                    owners_by_label.setdefault(key, user)

    created = 0
    updated = 0
    warnings = []
    headers = rows[0]
    product_col = _csv_header_index(headers, "Продукт")
    code_col = _csv_header_index(headers, "Код")
    section_col = _csv_header_index(headers, "Раздел (услуга)")
    base_rate_col = _csv_header_index(headers, "Базовая ставка в ВПМ")
    hours_col = _csv_header_index(headers, "Объем услуг в часах")
    days_col = _csv_header_index(headers, "Объем услуг в днях для ТКП")
    owner_col = _csv_header_index(headers, "Руководитель направления")
    if product_col is None:
        product_col = 0
    if section_col is None:
        section_col = 2 if code_col is not None else 1
    if base_rate_col is None:
        base_rate_col = 3 if code_col is not None else 2
    if hours_col is None:
        hours_col = 4 if code_col is not None else 3
    if days_col is None:
        days_col = 5 if code_col is not None else 4
    if owner_col is None and code_col is not None:
        owner_col = 6

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if not _csv_required_columns_present(row, [product_col, section_col, base_rate_col, hours_col, days_col]):
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 6-7: "
                "Продукт, Код, Раздел (услуга), Базовая ставка в ВПМ, Объем услуг в часах, "
                "Объем услуг в днях для ТКП, [Руководитель направления])."
            )
            continue

        product_name = _csv_row_value(row, product_col)
        section_code = _csv_row_value(row, code_col)
        section_name = _csv_row_value(row, section_col)
        product = products_by_name.get(_csv_lookup_key(product_name))
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        section = _resolve_section_from_import(sections_by_product, product.pk, section_code, section_name)
        if not section:
            section_label = section_code or section_name
            warnings.append(f"Строка {i}: раздел «{section_label}» не найден для продукта «{product.short_name}».")
            continue

        try:
            base_rate_value = _csv_row_value(row, base_rate_col)
            base_rate_vpm = Decimal(base_rate_value.replace(",", "."))
        except (InvalidOperation, ValueError):
            warnings.append(f"Строка {i}: некорректная базовая ставка «{_csv_row_value(row, base_rate_col)}».")
            continue
        if base_rate_vpm < 0:
            warnings.append(f"Строка {i}: базовая ставка не может быть отрицательной.")
            continue

        try:
            service_hours = int(_csv_row_value(row, hours_col))
        except (TypeError, ValueError):
            warnings.append(f"Строка {i}: некорректный объем услуг в часах «{_csv_row_value(row, hours_col)}».")
            continue
        if service_hours < 0:
            warnings.append(f"Строка {i}: объем услуг в часах не может быть отрицательным.")
            continue

        try:
            service_days_tkp = int(_csv_row_value(row, days_col))
        except (TypeError, ValueError):
            warnings.append(f"Строка {i}: некорректный объем услуг в днях для ТКП «{_csv_row_value(row, days_col)}».")
            continue
        if service_days_tkp < 0:
            warnings.append(f"Строка {i}: объем услуг в днях для ТКП не может быть отрицательным.")
            continue

        owner = request.user
        owner_name = _csv_row_value(row, owner_col)
        if request.user.is_superuser and owner_name:
            owner = owners_by_label.get(_csv_lookup_key(owner_name))
            if not owner:
                warnings.append(f"Строка {i}: руководитель «{owner_name}» не найден.")
                continue

        try:
            tariff = (
                Tariff.objects
                .filter(product=product, section=section, created_by=owner)
                .order_by("position", "id")
                .first()
            )
            was_created = tariff is None
            if was_created:
                tariff = Tariff(
                    product=product,
                    section=section,
                    created_by=owner,
                    position=_next_position(Tariff, {"created_by": owner}),
                )
            tariff.base_rate_vpm = base_rate_vpm
            tariff.service_hours = service_hours
            tariff.service_days_tkp = service_days_tkp
            tariff.save()
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return _policy_import_success_response(
        request, ok=True, created=created, updated=updated, warnings=warnings
    )


@login_required
@require_http_methods(["GET"])
def tariff_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(TARIFF_CSV_HEADERS)

    for tariff in _apply_policy_master_product_filters(_get_tariffs_for_user(request.user), request):
        writer.writerow(
            [
                tariff.product.short_name,
                tariff.section.code,
                tariff.section.name_ru or tariff.section.name_en,
                str(tariff.base_rate_vpm).replace(".", ","),
                tariff.service_hours,
                tariff.service_days_tkp,
                _tariff_owner_label(tariff.created_by),
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="section_tariffs.csv"'
    return response


@login_required
@require_http_methods(["POST", "GET"])
def tariff_move_up(request, pk: int):
    obj = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    _normalize_tariff_positions(created_by_id=obj.created_by_id)
    items = list(Tariff.objects.filter(created_by_id=obj.created_by_id).order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        Tariff.objects.filter(pk=cur.id).update(position=prev_pos)
        Tariff.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_tariff_positions(created_by_id=obj.created_by_id)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def tariff_move_down(request, pk: int):
    obj = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    _normalize_tariff_positions(created_by_id=obj.created_by_id)
    items = list(Tariff.objects.filter(created_by_id=obj.created_by_id).order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        Tariff.objects.filter(pk=cur.id).update(position=next_pos)
        Tariff.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_tariff_positions(created_by_id=obj.created_by_id)
    return _render_policy_updated(request)
