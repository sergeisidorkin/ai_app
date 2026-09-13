import json
import logging
import time

from django.conf import settings
from django.shortcuts import redirect, resolve_url


policy_performance_logger = logging.getLogger("policy.performance")

POLICY_OBSERVABILITY_ROUTE_NAMES = frozenset(
    {
        "policy_partial",
        "policy_filter_catalog",
        "policy_expertise_directions_table",
        "policy_consulting_directions_table",
        "policy_products_table",
        "policy_service_goal_reports_table",
        "policy_typical_sections_table",
        "policy_section_structures_table",
        "policy_report_structures_table",
        "policy_typical_service_compositions_table",
        "policy_typical_service_terms_table",
        "policy_grades_table",
        "policy_expert_specialties_table",
        "policy_specialty_tariffs_table",
        "policy_tariffs_table",
        "product_workspace",
    }
)


def _policy_route_name(request):
    match = getattr(request, "resolver_match", None)
    route_name = getattr(match, "url_name", None)
    return route_name if route_name in POLICY_OBSERVABILITY_ROUTE_NAMES else ""


def _response_bytes_without_consuming(response):
    if getattr(response, "streaming", False):
        raw_length = response.get("Content-Length")
        try:
            return int(raw_length) if raw_length is not None else None
        except (TypeError, ValueError):
            return None
    return len(response.content)


class PolicyObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        route_name = _policy_route_name(request)
        if not route_name:
            return response

        duration_ms = (time.perf_counter() - started) * 1000
        response_bytes = _response_bytes_without_consuming(response)
        cache_status = response.get("X-Policy-Cache", "")

        app_timing = f"app;dur={duration_ms:.2f}"
        existing_timing = response.get("Server-Timing")
        response["Server-Timing"] = (
            f"{existing_timing}, {app_timing}"
            if existing_timing
            else app_timing
        )
        if response_bytes is not None:
            response["X-Policy-Response-Bytes"] = str(response_bytes)

        event = {
            "cache_status": cache_status or None,
            "duration_ms": round(duration_ms, 2),
            "event": "policy_response",
            "response_bytes": response_bytes,
            "route": route_name,
            "status": response.status_code,
        }
        latency_warning_ms = getattr(
            settings,
            "POLICY_OBSERVABILITY_LATENCY_WARNING_MS",
            750.0,
        )
        bytes_warning = getattr(
            settings,
            "POLICY_OBSERVABILITY_BYTES_WARNING",
            512 * 1024,
        )
        log_method = (
            policy_performance_logger.warning
            if duration_ms >= latency_warning_ms
            or (
                response_bytes is not None
                and response_bytes >= bytes_warning
            )
            else policy_performance_logger.info
        )
        log_method(json.dumps(event, separators=(",", ":"), sort_keys=True))
        return response


class EnforceLoginMiddleware:
    """
    Если пользователь не аутентифицирован — пускаем только на LOGIN_URL и статические ресурсы.
    Всё остальное (включая /admin) — редиректим на страницу входа.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Уже авторизован — пропускаем
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path or "/"
        login_url = resolve_url(getattr(settings, "LOGIN_URL", "login"))

        # Разрешённые точные пути (login, logout может быть полезен)
        allowed_exact = {
            login_url,
            "/accounts/login/",
            "/accounts/logout/",
        }

        # Разрешённые префиксы (статика, health и т.п.)
        allowed_prefixes = (
            getattr(settings, "STATIC_URL", "/static/"),
        ) + tuple(getattr(settings, "ENFORCE_LOGIN_EXEMPT", ()))

        # Разрешаем доступ, если путь подпадает под исключения
        if path in allowed_exact or any(path.startswith(pfx) for pfx in allowed_prefixes):
            return self.get_response(request)

        # Иначе — редирект на страницу логина с возвратом обратно (next)
        return redirect(f"{login_url}?next={path}")