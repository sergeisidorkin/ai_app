"""Generic bulk row-order endpoint shared by all selectable tables.

Every table that offers «Переместить вверх/вниз» registers a :class:`RowOrderSpec`
in ``<app>/row_order.py`` (auto-discovered in :meth:`core.apps.CoreConfig.ready`).
The client (``core/static/core/js/queued-row-order.js``) reorders rows in the DOM
immediately and posts the full displayed order once (debounced) to
``/core/row-order/<key>/``.

Payload (JSON)::

    {"ordered_ids": [...],      # ids in the order shown after the move
     "base_order_ids": [...],   # the same ids in the order shown before the move
     "scope": {...}}            # optional free-form context (currently unused)

The server treats the listed ids as a *partial* permutation inside each ordering
scope: rows of the scope that were not listed keep their slots, listed rows fill
their slots in the new order, and the whole scope is renumbered ``1..N``.  This
works both for tables that show a complete scope and for filtered tables.

Conflicts (someone else reordered the rows between render and save) are detected
by comparing ``base_order_ids`` with the current database order of the same rows
and reported with HTTP 409 so the client can refresh the table.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from django.db import transaction
from django.db.models import Model, Q, QuerySet
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

DEFAULT_CONFLICT_MESSAGE = "Порядок строк был изменен. Таблица будет обновлена."


def staff_only(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


def superuser_or_owner(owner_field: str) -> Callable[[HttpRequest, Model], bool]:
    def _check(request: HttpRequest, row: Model) -> bool:
        user = request.user
        if user.is_superuser:
            return True
        return getattr(row, owner_field) == getattr(user, "pk", None)

    return _check


@dataclass
class RowOrderScopeResult:
    """Per-scope outcome passed to ``validate`` / ``after_save`` hooks."""

    scope_key: tuple
    before: list  # scope rows in the order they had before the save
    after: list  # scope rows in the new order (same instances, positions already updated)
    moved_ids: list  # ids whose position changed


@dataclass
class RowOrderResult:
    request: HttpRequest
    spec: "RowOrderSpec"
    ordered_ids: list
    scopes: list  # list[RowOrderScopeResult]

    @property
    def moved_ids(self) -> list:
        ids: list = []
        for scope in self.scopes:
            ids.extend(scope.moved_ids)
        return ids

    @property
    def rows(self) -> list:
        rows: list = []
        for scope in self.scopes:
            rows.extend(scope.after)
        return rows


@dataclass
class RowOrderSpec:
    key: str
    model: type
    scope_fields: Sequence[str] = ()
    # Optional overrides for scopes that are not a plain tuple of field values:
    # scope_key(row) -> hashable tuple; scope_filter(scope_key) -> Q selecting the whole scope.
    scope_key: Optional[Callable[[Model], tuple]] = None
    scope_filter: Optional[Callable[[tuple], Q]] = None
    # Restrict the ordering universe (e.g. staff vs external employees).
    base_filter: Optional[Callable[[HttpRequest], Q] | Q | Mapping[str, Any]] = None
    login_required: bool = True
    permission: Optional[Callable[[HttpRequest], bool]] = None
    row_permission: Optional[Callable[[HttpRequest, Model], bool]] = None
    # validate(request, scope_result) -> error message or None. Called before positions are written.
    validate: Optional[Callable[[HttpRequest, RowOrderScopeResult], Optional[str]]] = None
    # after_save(request, result) -> None. Called inside the transaction after positions are written.
    after_save: Optional[Callable[[HttpRequest, RowOrderResult], None]] = None
    # Body events to trigger on the client after a successful save (name -> detail or callable).
    events: Optional[Callable[[HttpRequest, RowOrderResult], Mapping[str, Any]] | Mapping[str, Any]] = None
    position_field: str = "position"
    order_by: Sequence[str] = ("position", "id")
    extra_fields: Sequence[str] = ()
    # Load complete model instances (needed when hooks touch arbitrary fields/properties).
    full_rows: bool = False
    conflict_message: str = DEFAULT_CONFLICT_MESSAGE
    # Rows that must keep their index inside the scope (e.g. locked report folders).
    locked: Optional[Callable[[Model], bool]] = None
    locked_message: str = "Заблокированные строки нельзя переместить."

    def queryset(self, request: HttpRequest) -> QuerySet:
        qs = self.model._default_manager.all()
        base = self.base_filter
        if callable(base):
            base = base(request)
        if isinstance(base, Q):
            qs = qs.filter(base)
        elif isinstance(base, Mapping):
            qs = qs.filter(**base)
        return qs

    def only_fields(self) -> list:
        fields = ["id", self.position_field]
        for name in tuple(self.scope_fields) + tuple(self.extra_fields):
            try:
                name = self.model._meta.get_field(name).name
            except Exception:  # pragma: no cover - non-field attributes are passed through
                pass
            if name not in fields:
                fields.append(name)
        return fields

    def narrow(self, qs: QuerySet) -> QuerySet:
        if self.full_rows:
            return qs
        return qs.only(*self.only_fields())

    def scope_key_for(self, row: Model) -> tuple:
        if self.scope_key is not None:
            return tuple(self.scope_key(row))
        return tuple(getattr(row, name) for name in self.scope_fields)

    def scope_queryset(self, qs: QuerySet, scope_key: tuple) -> QuerySet:
        if self.scope_filter is not None:
            return qs.filter(self.scope_filter(scope_key))
        if not self.scope_fields:
            return qs
        return qs.filter(**{name: value for name, value in zip(self.scope_fields, scope_key)})


_REGISTRY: dict[str, RowOrderSpec] = {}


def register_row_order(spec: RowOrderSpec) -> RowOrderSpec:
    if not spec.key:
        raise ValueError("RowOrderSpec.key is required")
    existing = _REGISTRY.get(spec.key)
    if existing is not None and existing is not spec:
        raise ValueError(f"Row order key already registered: {spec.key!r}")
    _REGISTRY[spec.key] = spec
    return spec


def register_row_orders(specs: Iterable[RowOrderSpec]) -> None:
    for spec in specs:
        register_row_order(spec)


def get_row_order_spec(key: str) -> Optional[RowOrderSpec]:
    return _REGISTRY.get(str(key or ""))


def registered_row_order_keys() -> list[str]:
    return sorted(_REGISTRY)


def _json_error(message: str, status: int = 400, **extra: Any) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_ids(raw: Any) -> Optional[list[int]]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        return None
    try:
        return [int(value) for value in raw]
    except (TypeError, ValueError):
        return None


def _resolve_events(spec: RowOrderSpec, request: HttpRequest, result: RowOrderResult) -> dict:
    events = spec.events
    if callable(events):
        events = events(request, result)
    if not events:
        return {}
    resolved = {}
    for name, detail in dict(events).items():
        resolved[str(name)] = detail if detail is not None else True
    return resolved


def apply_row_order(request: HttpRequest, spec: RowOrderSpec, ordered_ids: list[int], base_order_ids: list[int]):
    """Apply the permutation; returns ``(result, error_response)``.

    Must be called inside ``transaction.atomic()``.
    """
    qs = spec.queryset(request)
    listed_rows = list(spec.narrow(qs.filter(pk__in=ordered_ids).select_for_update()))
    if len(listed_rows) != len(ordered_ids):
        current_ids = list(qs.order_by(*spec.order_by).values_list("pk", flat=True))
        return None, _json_error(spec.conflict_message, status=409, current_ids=current_ids)

    listed_set = set(ordered_ids)
    scope_keys: list[tuple] = []
    for row in listed_rows:
        key = spec.scope_key_for(row)
        if key not in scope_keys:
            scope_keys.append(key)

    scope_results: list[RowOrderScopeResult] = []
    position_field = spec.position_field
    model = spec.model

    for scope_key in scope_keys:
        scope_qs = spec.scope_queryset(qs, scope_key)
        before = list(spec.narrow(scope_qs.select_for_update().order_by(*spec.order_by)))
        before_ids = [row.pk for row in before]
        current_listed = [pk for pk in before_ids if pk in listed_set]
        desired_listed = [pk for pk in ordered_ids if pk in set(current_listed)]
        base_listed = [pk for pk in base_order_ids if pk in set(current_listed)] if base_order_ids else []

        if desired_listed == current_listed:
            scope_results.append(RowOrderScopeResult(scope_key, before, list(before), []))
            continue

        if base_listed and base_listed != current_listed:
            return None, _json_error(spec.conflict_message, status=409, current_ids=before_ids)

        rows_by_id = {row.pk: row for row in before}
        desired_iter = iter(desired_listed)
        after = [rows_by_id[next(desired_iter)] if row.pk in listed_set else row for row in before]

        displaced = [row for prev_row, row in zip(before, after) if prev_row.pk != row.pk]
        if spec.locked is not None:
            for prev_row, new_row in zip(before, after):
                if prev_row.pk != new_row.pk and (spec.locked(prev_row) or spec.locked(new_row)):
                    return None, _json_error(spec.locked_message, status=409, current_ids=before_ids)
        if spec.row_permission is not None:
            # Only rows whose slot actually changes need the permission (other owners' rows
            # may be listed because the table shows them, but they stay in place).
            for row in displaced:
                if not spec.row_permission(request, row):
                    return None, _json_error("Недостаточно прав для перемещения строки.", status=403)

        scope_result = RowOrderScopeResult(scope_key, before, after, [])
        if spec.validate is not None:
            error = spec.validate(request, scope_result)
            if error:
                return None, _json_error(str(error), status=409, current_ids=before_ids)

        changed = []
        for idx, row in enumerate(after, start=1):
            if getattr(row, position_field) != idx:
                setattr(row, position_field, idx)
                changed.append(row)
                scope_result.moved_ids.append(row.pk)
        if changed:
            model._default_manager.bulk_update(changed, [position_field])
        scope_results.append(scope_result)

    result = RowOrderResult(request=request, spec=spec, ordered_ids=list(ordered_ids), scopes=scope_results)
    if spec.after_save is not None:
        spec.after_save(request, result)
    return result, None


@require_POST
def row_order_save(request: HttpRequest, key: str):
    spec = get_row_order_spec(key)
    if spec is None:
        return _json_error("Неизвестная таблица.", status=404)
    if spec.login_required and not request.user.is_authenticated:
        return _json_error("Требуется вход в систему.", status=403)
    if spec.permission is not None and not spec.permission(request):
        return _json_error("Недостаточно прав.", status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return _json_error("Некорректный формат порядка строк.")
    if not isinstance(payload, dict):
        return _json_error("Некорректный формат порядка строк.")

    ordered_ids = _parse_ids(payload.get("ordered_ids"))
    base_order_ids = _parse_ids(payload.get("base_order_ids"))
    if ordered_ids is None or base_order_ids is None:
        return _json_error("Порядок строк содержит некорректные идентификаторы.")
    if not ordered_ids:
        return _json_error("Порядок строк пуст.")
    if len(ordered_ids) != len(set(ordered_ids)):
        return _json_error("Порядок строк содержит дубли.")
    if base_order_ids and set(base_order_ids) != set(ordered_ids):
        return _json_error("Исходный и новый порядок строк не совпадают по составу.")

    with transaction.atomic():
        result, error = apply_row_order(request, spec, ordered_ids, base_order_ids)
        if error is not None:
            # A later scope may fail after an earlier one was written: undo everything.
            transaction.set_rollback(True)
            return error
        events = _resolve_events(spec, request, result)

    response = {
        "ok": True,
        "order_ids": result.ordered_ids,
        "moved_ids": result.moved_ids,
    }
    if events:
        response["events"] = events
    return JsonResponse(response)
