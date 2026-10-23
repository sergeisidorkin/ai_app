"""Bulk row-order specs for the policy panel (see core.row_order).

Each spec mirrors the corresponding ``*_move_up/_move_down`` view: ordering scope,
permissions, the DSC system-section rule for typical sections and the
``policy-updated`` payload consumed by ``handlePolicyUpdated`` on the client.
"""
from core.row_order import RowOrderSpec, register_row_orders, staff_only, superuser_or_owner

from .cache import schedule_policy_cache_invalidation
from .models import (
    ConsultingDirection,
    ExpertiseDirection,
    Grade,
    Product,
    ReportStructure,
    SectionStructure,
    ServiceBlockClassifier,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalServiceComposition,
    TypicalServiceTerm,
)

HX_POLICY_UPDATED_EVENT = "policy-updated"
SYSTEM_SECTION_MESSAGE = "Системный раздел ДСХ нельзя переместить."


def _policy_events(entity):
    def _events(request, result):
        # Imported lazily: policy_app.views is heavy and must not be imported during app loading.
        from .views import POLICY_ENTITY_TABLE_KEY, POLICY_MUTATION_DEPENDENCIES

        dependency = POLICY_MUTATION_DEPENDENCIES[entity]
        detail = {
            "tables": list(dependency["tables"]),
            "refreshFilters": bool(dependency.get("refresh_filters", False)),
            "reorderedTable": POLICY_ENTITY_TABLE_KEY[entity],
        }
        if entity == "product":
            detail["productsReordered"] = True
        return {HX_POLICY_UPDATED_EVENT: detail}

    return _events


def _invalidate_policy_cache(request, result):
    schedule_policy_cache_invalidation()


def _policy_spec(key, model, entity, **kwargs):
    return RowOrderSpec(
        key=key,
        model=model,
        after_save=_invalidate_policy_cache,
        events=_policy_events(entity),
        **kwargs,
    )


def _is_system_dsc(section):
    return bool(section.is_system_dsc)


register_row_orders([
    _policy_spec("product", Product, "product"),
    _policy_spec(
        "typical-section",
        TypicalSection,
        "typical-section",
        scope_fields=("product_id",),
        full_rows=True,
        locked=_is_system_dsc,
        locked_message=SYSTEM_SECTION_MESSAGE,
    ),
    _policy_spec("section-structure", SectionStructure, "section-structure"),
    _policy_spec("report-structure", ReportStructure, "report-structure", scope_fields=("product_id",)),
    _policy_spec("service-goal-report", ServiceGoalReport, "service-goal-report", permission=staff_only),
    _policy_spec(
        "typical-service-composition",
        TypicalServiceComposition,
        "typical-service-composition",
        permission=staff_only,
    ),
    _policy_spec("typical-service-term", TypicalServiceTerm, "typical-service-term", permission=staff_only),
    _policy_spec("consulting-direction", ConsultingDirection, "consulting-direction"),
    _policy_spec("expertise-direction", ExpertiseDirection, "expertise-direction"),
    _policy_spec(
        "service-block-classifier",
        ServiceBlockClassifier,
        "service-block-classifier",
        permission=staff_only,
    ),
    _policy_spec(
        "grade",
        Grade,
        "grade",
        scope_fields=("created_by_id",),
        row_permission=superuser_or_owner("created_by_id"),
    ),
    _policy_spec(
        "specialty-tariff",
        SpecialtyTariff,
        "specialty-tariff",
        scope_fields=("created_by_id",),
        row_permission=superuser_or_owner("created_by_id"),
    ),
    _policy_spec(
        "tariff",
        Tariff,
        "tariff",
        scope_fields=("created_by_id",),
        row_permission=superuser_or_owner("created_by_id"),
    ),
])
