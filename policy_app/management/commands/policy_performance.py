import gzip
import json
import math
import time
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse


DEFAULT_ENDPOINTS = (
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
)


def _percentile(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _distribution(values):
    return {
        "min": round(min(values), 2),
        "p50": round(_percentile(values, 0.50), 2),
        "p95": round(_percentile(values, 0.95), 2),
        "max": round(max(values), 2),
    }


class Command(BaseCommand):
    help = "Measure policy endpoint render time, SQL count and response size."

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument(
            "--endpoint",
            action="append",
            dest="endpoints",
            help="URL name to measure; may be repeated.",
        )
        parser.add_argument("--label", default="", help="Optional label included in the JSON output.")
        parser.add_argument("--page", type=int, help="Page number passed to table endpoints.")
        parser.add_argument("--product", action="append", type=int, default=[])
        parser.add_argument("--consulting", action="append", default=[])
        parser.add_argument("--category", action="append", default=[])
        parser.add_argument("--subtype", action="append", default=[])
        parser.add_argument(
            "--repeat",
            type=int,
            default=1,
            help="Sequential repetitions per endpoint (not a load test).",
        )

    def handle(self, *args, **options):
        if options["repeat"] < 1:
            raise CommandError("--repeat must be at least 1.")
        users = get_user_model().objects.filter(is_active=True)
        if options["username"]:
            user = users.filter(username=options["username"]).first()
        else:
            user = users.filter(is_staff=True).order_by("pk").first()
        if user is None:
            raise CommandError("No matching active user was found.")

        factory = RequestFactory()
        query_params = {
            key: options[key]
            for key in ("product", "consulting", "category", "subtype")
            if options[key]
        }
        if options["page"] is not None:
            query_params["page"] = options["page"]
        results = []
        for url_name in options["endpoints"] or DEFAULT_ENDPOINTS:
            for run in range(1, options["repeat"] + 1):
                try:
                    path = reverse(url_name)
                except Exception as exc:
                    raise CommandError(f"Cannot reverse {url_name}: {exc}") from exc
                match = resolve(path)
                request = factory.get(path, data=query_params, HTTP_HX_REQUEST="true")
                request.user = user

                started = time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    response = match.func(request, **match.kwargs)
                    if hasattr(response, "render"):
                        response.render()
                elapsed_ms = (time.perf_counter() - started) * 1000
                body = bytes(response.content)
                results.append(
                    {
                        "endpoint": url_name,
                        "run": run,
                        "status": response.status_code,
                        "cache_status": response.get("X-Policy-Cache") or None,
                        "milliseconds": round(elapsed_ms, 2),
                        "sql_time_ms": round(
                            sum(float(query.get("time") or 0) for query in queries) * 1000,
                            2,
                        ),
                        "sql_queries": len(queries),
                        "bytes": len(body),
                        "gzip_bytes": len(gzip.compress(body)),
                    }
                )

        summary = {}
        for url_name in options["endpoints"] or DEFAULT_ENDPOINTS:
            endpoint_results = [
                result for result in results if result["endpoint"] == url_name
            ]
            summary[url_name] = {
                "runs": len(endpoint_results),
                "milliseconds": _distribution(
                    [result["milliseconds"] for result in endpoint_results]
                ),
                "sql_queries": _distribution(
                    [result["sql_queries"] for result in endpoint_results]
                ),
                "bytes": _distribution(
                    [result["bytes"] for result in endpoint_results]
                ),
                "cache_statuses": dict(
                    Counter(
                        result["cache_status"] or "NONE"
                        for result in endpoint_results
                    )
                ),
            }

        self.stdout.write(
            json.dumps(
                {
                    "label": options["label"],
                    "database": connection.vendor,
                    "user_id": user.pk,
                    "repeat": options["repeat"],
                    "params": {
                        key: request.GET.getlist(key)
                        for key in ("product", "consulting", "category", "subtype", "page")
                        if request.GET.getlist(key)
                    },
                    "results": results,
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
