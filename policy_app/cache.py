import logging
import uuid

from django.core.cache import caches
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.dummy import DummyCache
from django.db import transaction
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

POLICY_CACHE_ALIAS = "policy"
POLICY_CACHE_HIT = "HIT"
POLICY_CACHE_MISS = "MISS"
POLICY_CACHE_BYPASS = "BYPASS"
POLICY_CACHE_ERROR = "ERROR"
POLICY_GENERATION_KEY = "generation:v1"
POLICY_CATALOG_SCHEMA_VERSION = "v1"

_CACHE_MISS = object()
_REQUEST_FAILURE_ATTRIBUTE = "_policy_cache_failure"
_CONNECTION_CALLBACK_ATTRIBUTE = "_policy_cache_invalidation_callback"


def normalized_policy_catalog_key(generation):
    return f"filter-catalog:{POLICY_CATALOG_SCHEMA_VERSION}:{generation}"


def _request_failure(request):
    return getattr(request, _REQUEST_FAILURE_ATTRIBUTE, "")


def _mark_request_failure(request, operation, exc):
    if request is not None and not _request_failure(request):
        setattr(request, _REQUEST_FAILURE_ATTRIBUTE, POLICY_CACHE_ERROR)
        logger.warning(
            "Policy cache %s failed open (%s).",
            operation,
            type(exc).__name__,
        )


def _policy_cache():
    return caches[POLICY_CACHE_ALIAS]


def _cache_is_disabled(cache_backend):
    return isinstance(cache_backend, DummyCache)


def _safe_get(cache_backend, key, request):
    if _request_failure(request):
        return _CACHE_MISS, False
    try:
        return cache_backend.get(key, _CACHE_MISS), True
    except (RedisError, OSError) as exc:
        _mark_request_failure(request, "get", exc)
        return _CACHE_MISS, False


def _safe_add(cache_backend, key, value, request):
    if _request_failure(request):
        return False, False
    try:
        return cache_backend.add(key, value, timeout=None), True
    except (RedisError, OSError) as exc:
        _mark_request_failure(request, "add", exc)
        return False, False


def _safe_set(
    cache_backend,
    key,
    value,
    request=None,
    *,
    timeout=DEFAULT_TIMEOUT,
):
    if _request_failure(request):
        return False
    try:
        cache_backend.set(key, value, timeout=timeout)
        return True
    except (RedisError, OSError) as exc:
        _mark_request_failure(request, "set", exc)
        if request is None:
            logger.warning(
                "Policy cache invalidation failed open (%s).",
                type(exc).__name__,
            )
        return False


def _policy_generation(cache_backend, request):
    generation, available = _safe_get(
        cache_backend,
        POLICY_GENERATION_KEY,
        request,
    )
    if not available:
        return None, POLICY_CACHE_ERROR
    if generation is not _CACHE_MISS:
        return str(generation), ""

    candidate = uuid.uuid4().hex
    added, available = _safe_add(
        cache_backend,
        POLICY_GENERATION_KEY,
        candidate,
        request,
    )
    if not available:
        return None, POLICY_CACHE_ERROR
    if added:
        return candidate, ""

    generation, available = _safe_get(
        cache_backend,
        POLICY_GENERATION_KEY,
        request,
    )
    if not available or generation is _CACHE_MISS:
        return None, POLICY_CACHE_ERROR
    return str(generation), ""


def get_or_build_policy_catalog(request, builder):
    cache_backend = _policy_cache()
    if _cache_is_disabled(cache_backend):
        return builder(), POLICY_CACHE_BYPASS

    generation, status = _policy_generation(cache_backend, request)
    if status:
        return builder(), status

    key = normalized_policy_catalog_key(generation)
    payload, available = _safe_get(cache_backend, key, request)
    if not available:
        return builder(), POLICY_CACHE_ERROR
    if payload is not _CACHE_MISS:
        return payload, POLICY_CACHE_HIT

    # Keep renderer/data exceptions visible: only cache I/O is fail-open.
    payload = builder()
    if not _safe_set(cache_backend, key, payload, request):
        return payload, POLICY_CACHE_ERROR
    return payload, POLICY_CACHE_MISS


def invalidate_policy_generation():
    cache_backend = _policy_cache()
    if _cache_is_disabled(cache_backend):
        return False
    return _safe_set(
        cache_backend,
        POLICY_GENERATION_KEY,
        uuid.uuid4().hex,
        timeout=None,
    )


def schedule_policy_cache_invalidation(using="default"):
    connection = transaction.get_connection(using)
    existing = getattr(connection, _CONNECTION_CALLBACK_ATTRIBUTE, None)
    if existing is not None and any(
        entry[1] is existing for entry in connection.run_on_commit
    ):
        return

    def invalidate_after_commit():
        setattr(connection, _CONNECTION_CALLBACK_ATTRIBUTE, None)
        invalidate_policy_generation()

    setattr(
        connection,
        _CONNECTION_CALLBACK_ATTRIBUTE,
        invalidate_after_commit,
    )
    transaction.on_commit(invalidate_after_commit, using=using)
