from __future__ import annotations

import logging
from dataclasses import dataclass
import threading
import time
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class NextcloudApiError(Exception):
    pass


@dataclass(frozen=True)
class NextcloudProvisionedUser:
    user_id: str
    display_name: str
    email: str


@dataclass(frozen=True)
class NextcloudShare:
    share_id: str
    path: str
    share_with: str
    permissions: int
    share_type: int = 0
    url: str = ""
    target_path: str = ""


class NextcloudApiClient:
    EDITOR_PERMISSIONS = 15
    PUBLIC_LINK_SHARE_TYPE = 3
    RETRYABLE_STATUS_CODES = {429, 503}
    DAV_RETRYABLE_STATUSES = {429, 503}
    SHARE_CREATE_INTERVAL_SECONDS = 1.0
    MAX_OCS_ATTEMPTS = 2
    MAX_DAV_ATTEMPTS = 2
    MAX_RETRY_SLEEP_SECONDS = 2.0
    SAFE_RETRY_METHODS = {"GET", "HEAD", "OPTIONS", "PROPFIND", "REPORT"}
    IDEMPOTENT_DAV_RETRY_METHODS = SAFE_RETRY_METHODS | {"PUT", "DELETE", "MKCOL"}

    _request_semaphore = None
    _request_semaphore_size = None
    _request_semaphore_lock = threading.Lock()
    _share_cache_condition = threading.Condition()
    _share_cache: dict[tuple[str, str, str], tuple[float, dict[str, NextcloudShare]]] = {}
    _share_cache_loading: set[tuple[str, str, str]] = set()

    def __init__(self, *, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self.base_url = (
            (getattr(settings, "NEXTCLOUD_PROVISIONING_BASE_URL", "") or "").strip()
            or (getattr(settings, "NEXTCLOUD_BASE_URL", "") or "").strip()
        ).rstrip("/")
        self.transport_base_url = (
            (getattr(settings, "NEXTCLOUD_INTERNAL_BASE_URL", "") or "").strip()
            or self.base_url
        ).rstrip("/")
        self.username = (getattr(settings, "NEXTCLOUD_PROVISIONING_USERNAME", "") or "").strip()
        self.token = (getattr(settings, "NEXTCLOUD_PROVISIONING_TOKEN", "") or "").strip()
        self.provider_id = int(getattr(settings, "NEXTCLOUD_OIDC_PROVIDER_ID", 0) or 0)
        self.default_group = (getattr(settings, "NEXTCLOUD_DEFAULT_GROUP", "") or "").strip()
        self.default_quota = (getattr(settings, "NEXTCLOUD_DEFAULT_QUOTA", "") or "").strip()
        self.connect_timeout = float(getattr(settings, "NEXTCLOUD_CONNECT_TIMEOUT", 3) or 3)
        self.read_timeout = float(getattr(settings, "NEXTCLOUD_READ_TIMEOUT", 60) or 60)
        self.ocs_read_attempts = max(int(getattr(settings, "NEXTCLOUD_OCS_READ_ATTEMPTS", 2) or 2), 1)
        self.dav_read_attempts = max(int(getattr(settings, "NEXTCLOUD_DAV_READ_ATTEMPTS", 2) or 2), 1)
        self.share_cache_ttl = max(float(getattr(settings, "NEXTCLOUD_SHARE_MAP_CACHE_TTL", 15) or 0), 0)
        self._public_share_cache_loaded = False
        self._public_share_cache: dict[str, NextcloudShare] = {}
        self._user_share_cache: dict[tuple[str, str], dict[str, NextcloudShare]] = {}
        self._next_share_create_at = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.username and self.token and self.provider_id > 0)

    def provision_user(self, *, user_id: str, display_name: str, email: str) -> NextcloudProvisionedUser:
        payload: dict[str, object] = {
            "providerId": self.provider_id,
            "userId": user_id,
            "displayName": display_name,
            "email": email,
        }
        if self.default_quota:
            payload["quota"] = self.default_quota

        response = self._request(
            "POST",
            "/ocs/v2.php/apps/user_oidc/api/v1/user",
            json=payload,
        )
        data = self._extract_data(response)

        if self.default_group:
            self.add_user_to_group(user_id, self.default_group)

        resolved_email = str(data.get("email") or email)
        resolved_display_name = str(data.get("displayName") or data.get("display-name") or display_name)
        resolved_user_id = str(data.get("id") or data.get("userId") or user_id)
        return NextcloudProvisionedUser(
            user_id=resolved_user_id,
            display_name=resolved_display_name,
            email=resolved_email,
        )

    def get_user(self, user_id: str) -> dict[str, object]:
        response = self._request("GET", f"/ocs/v1.php/cloud/users/{user_id}")
        return self._extract_data(response)

    def set_user_email(self, user_id: str, email: str) -> None:
        self._request(
            "PUT",
            f"/ocs/v1.php/cloud/users/{user_id}",
            data={"key": "email", "value": email},
        )

    def set_user_display_name(self, user_id: str, display_name: str) -> None:
        self._request(
            "PUT",
            f"/ocs/v1.php/cloud/users/{user_id}",
            data={"key": "displayname", "value": display_name},
        )

    def enable_user(self, user_id: str) -> None:
        self._request("PUT", f"/ocs/v1.php/cloud/users/{user_id}/enable")

    def disable_user(self, user_id: str) -> None:
        self._request("PUT", f"/ocs/v1.php/cloud/users/{user_id}/disable")

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        self._request(
            "POST",
            f"/ocs/v1.php/cloud/users/{user_id}/groups",
            data={"groupid": group_id},
        )

    def ensure_folder(self, owner_user_id: str, path: str) -> str:
        normalized = self._normalize_folder_path(path)
        if normalized == "/":
            return normalized

        current = ""
        for part in normalized.strip("/").split("/"):
            current = f"{current}/{part}" if current else f"/{part}"
            response = self._dav_request("MKCOL", self._webdav_path(owner_user_id, current))
            if response.status_code not in (201, 405):
                raise NextcloudApiError(
                    f"Nextcloud DAV error {response.status_code}: "
                    f"не удалось создать папку `{current}`."
                )
        return normalized

    def move_resource(
        self,
        owner_user_id: str,
        source_path: str,
        target_path: str,
        *,
        overwrite: bool = False,
    ) -> str:
        source = self._normalize_folder_path(source_path)
        target = self._normalize_folder_path(target_path)
        if source == "/" or target == "/":
            raise NextcloudApiError("Nextcloud root folder cannot be moved.")
        if source == target:
            return target

        parent = "/" + "/".join(target.strip("/").split("/")[:-1])
        if parent and parent != "/":
            self.ensure_folder(owner_user_id, parent)

        response = self._dav_request(
            "MOVE",
            self._webdav_path(owner_user_id, source),
            headers={
                "Destination": self._webdav_path(owner_user_id, target),
                "Overwrite": "T" if overwrite else "F",
            },
            allow_statuses={201, 204, 404, 412},
        )
        if response.status_code in (201, 204):
            return target
        if response.status_code == 404:
            raise NextcloudApiError(f"Nextcloud DAV error 404: исходная папка не найдена `{source}`.")
        if response.status_code == 412:
            raise NextcloudApiError(f"Nextcloud DAV error 412: целевая папка уже существует `{target}`.")
        raise NextcloudApiError(f"Nextcloud DAV error {response.status_code}: не удалось переместить `{source}`.")

    def ensure_user_share(
        self,
        owner_user_id: str,
        path: str,
        share_with_user_id: str,
        *,
        permissions: int = EDITOR_PERMISSIONS,
    ) -> NextcloudShare:
        normalized = self._normalize_folder_path(path)
        existing = self.get_user_share(owner_user_id, normalized, share_with_user_id)
        if existing is not None:
            if existing.permissions != permissions:
                self._request(
                    "PUT",
                    f"/ocs/v2.php/apps/files_sharing/api/v1/shares/{existing.share_id}",
                    data={"permissions": permissions},
                )
                self._invalidate_user_share_cache(owner_user_id, share_with_user_id)
                return NextcloudShare(
                    share_id=existing.share_id,
                    path=existing.path,
                    share_with=existing.share_with,
                    permissions=permissions,
                    target_path=existing.target_path,
                )
            return existing

        response = self._request(
            "POST",
            "/ocs/v2.php/apps/files_sharing/api/v1/shares",
            data={
                "path": normalized,
                "shareType": 0,
                "shareWith": share_with_user_id,
                "permissions": permissions,
            },
        )
        data = self._extract_data(response)
        self._invalidate_user_share_cache(owner_user_id, share_with_user_id)
        return NextcloudShare(
            share_id=str(data.get("id") or ""),
            path=str(data.get("path") or normalized),
            share_with=str(data.get("share_with") or share_with_user_id),
            permissions=int(data.get("permissions") or permissions),
            target_path=str(data.get("file_target") or data.get("fileTarget") or ""),
        )

    def revoke_user_share(
        self,
        owner_user_id: str,
        path: str,
        share_with_user_id: str,
    ) -> bool:
        existing = self.get_user_share(owner_user_id, path, share_with_user_id)
        if existing is None:
            return False
        return self.delete_share(existing.share_id)

    def delete_share(self, share_id: str) -> bool:
        clean_share_id = str(share_id or "").strip()
        if not clean_share_id:
            return False

        response = self._request(
            "DELETE",
            f"/ocs/v2.php/apps/files_sharing/api/v1/shares/{quote(clean_share_id, safe='')}",
        )
        self._extract_raw_data(response)
        self._user_share_cache.clear()
        self._invalidate_all_user_share_caches()
        self._public_share_cache = {
            path: share
            for path, share in self._public_share_cache.items()
            if share.share_id != clean_share_id
        }
        return True

    def get_user_share(
        self,
        owner_user_id: str,
        path: str,
        share_with_user_id: str,
    ) -> NextcloudShare | None:
        normalized = self._normalize_folder_path(path)
        instance_key = (str(owner_user_id), str(share_with_user_id))
        instance_cached = self._user_share_cache.get(instance_key)
        if instance_cached is not None and normalized in instance_cached:
            return instance_cached[normalized]
        cached = self._get_cached_user_shares(owner_user_id, share_with_user_id)
        if cached is not None and normalized in cached:
            self._user_share_cache.setdefault(instance_key, {})[normalized] = cached[normalized]
            return cached[normalized]
        response = self._request(
            "GET",
            "/ocs/v2.php/apps/files_sharing/api/v1/shares",
            params={"path": normalized, "reshares": "true", "subfiles": "false"},
        )
        for item in self._extract_list_data(response):
            if str(item.get("path") or normalized) != normalized:
                continue
            if str(item.get("share_with") or "") != share_with_user_id:
                continue
            if self._as_int(item.get("share_type"), default=-1) != 0:
                continue
            share = NextcloudShare(
                share_id=str(item.get("id") or ""),
                path=str(item.get("path") or normalized),
                share_with=str(item.get("share_with") or share_with_user_id),
                permissions=int(item.get("permissions") or self.EDITOR_PERMISSIONS),
                target_path=str(item.get("file_target") or item.get("fileTarget") or ""),
            )
            self._user_share_cache.setdefault(instance_key, {})[normalized] = share
            return share
        return None

    def list_user_shares(
        self,
        owner_user_id: str,
        share_with_user_id: str,
    ) -> dict[str, NextcloudShare]:
        key = self._user_share_cache_key(owner_user_id, share_with_user_id)
        with self._share_cache_condition:
            while True:
                cached = self._get_cached_user_shares_locked(key)
                if cached is not None:
                    self.prime_user_share_cache(owner_user_id, share_with_user_id, cached)
                    return cached
                if key not in self._share_cache_loading:
                    self._share_cache_loading.add(key)
                    break
                self._share_cache_condition.wait()

        try:
            response = self._request(
                "GET",
                "/ocs/v2.php/apps/files_sharing/api/v1/shares",
                params={"reshares": "true", "subfiles": "false"},
            )
            shares: dict[str, NextcloudShare] = {}
            for item in self._extract_list_data(response):
                if str(item.get("share_with") or "") != share_with_user_id:
                    continue
                if self._as_int(item.get("share_type"), default=-1) != 0:
                    continue
                normalized_path = self._normalize_folder_path(item.get("path") or "")
                if not normalized_path or normalized_path == "/":
                    continue
                shares[normalized_path] = NextcloudShare(
                    share_id=str(item.get("id") or ""),
                    path=normalized_path,
                    share_with=str(item.get("share_with") or share_with_user_id),
                    permissions=int(item.get("permissions") or self.EDITOR_PERMISSIONS),
                    target_path=str(item.get("file_target") or item.get("fileTarget") or ""),
                )
            with self._share_cache_condition:
                self._share_cache[key] = (time.monotonic() + self.share_cache_ttl, dict(shares))
            self.prime_user_share_cache(owner_user_id, share_with_user_id, shares)
            return shares
        finally:
            with self._share_cache_condition:
                self._share_cache_loading.discard(key)
                self._share_cache_condition.notify_all()

    def prime_user_share_cache(
        self,
        owner_user_id: str,
        share_with_user_id: str,
        shares: dict[str, NextcloudShare],
    ) -> None:
        """Keep one bulk result authoritative for the lifetime of this client."""
        self._user_share_cache[(str(owner_user_id), str(share_with_user_id))] = dict(shares)

    def build_files_url(self, path: str) -> str:
        normalized = self._normalize_folder_path(path)
        return f"{self.base_url}/apps/files/files?dir={quote(normalized, safe='/')}"

    def build_files_open_url(self, file_id: str | int, dir_path: str) -> str:
        normalized_dir = self._normalize_folder_path(dir_path)
        return f"{self.base_url}/apps/files/files/{file_id}?dir={quote(normalized_dir, safe='/')}&openfile=true"

    def list_resources(self, owner_user_id: str, path: str, *, limit: int = 100) -> list[dict[str, object]]:
        normalized = self._normalize_folder_path(path)
        response = self._dav_request(
            "PROPFIND",
            self._webdav_path(owner_user_id, normalized),
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=(
                '<?xml version="1.0"?>'
                '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
                "<d:prop><d:displayname/><d:resourcetype/><d:getcontentlength/><d:getlastmodified/><oc:fileid/></d:prop>"
                "</d:propfind>"
            ),
            allow_statuses={207, 404},
        )
        if response.status_code == 404:
            return []

        requested_path = self._normalize_folder_path(path)
        items: list[dict[str, object]] = []
        root = ET.fromstring(response.content)
        ns = {"d": "DAV:", "oc": "http://owncloud.org/ns"}
        for node in root.findall("d:response", ns):
            href = node.findtext("d:href", default="", namespaces=ns)
            item_path = self._extract_cloud_path(owner_user_id, href)
            if not item_path or item_path == requested_path:
                continue

            prop = node.find("d:propstat/d:prop", ns)
            if prop is None:
                continue
            is_dir = prop.find("d:resourcetype/d:collection", ns) is not None
            name = prop.findtext("d:displayname", default="", namespaces=ns) or item_path.rstrip("/").split("/")[-1]
            size_raw = prop.findtext("d:getcontentlength", default="", namespaces=ns)
            modified = prop.findtext("d:getlastmodified", default="", namespaces=ns) or None
            file_id_raw = prop.findtext("oc:fileid", default="", namespaces=ns)
            items.append(
                {
                    "name": name,
                    "path": item_path,
                    "type": "dir" if is_dir else "file",
                    "size": int(size_raw) if str(size_raw).isdigit() else None,
                    "modified": modified,
                    "file_id": str(file_id_raw).strip() or None,
                }
            )
            if len(items) >= limit:
                break
        return items

    def upload_file(self, owner_user_id: str, path: str, data: bytes, *, overwrite: bool = True) -> bool:
        normalized = self._normalize_folder_path(path)
        parent = "/" + "/".join(normalized.strip("/").split("/")[:-1]) if "/" in normalized.strip("/") else "/"
        if parent and parent != "/":
            self.ensure_folder(owner_user_id, parent)

        headers = {"Content-Type": "application/octet-stream"}
        if not overwrite:
            headers["If-None-Match"] = "*"
        response = self._dav_request(
            "PUT",
            self._webdav_path(owner_user_id, normalized),
            headers=headers,
            data=data,
            allow_statuses={201, 204, 412},
        )
        return response.status_code in (201, 204)

    def download_file(self, owner_user_id: str, path: str) -> tuple[str | None, bytes]:
        normalized = self._normalize_folder_path(path)
        response = self._dav_request(
            "GET",
            self._webdav_path(owner_user_id, normalized),
            allow_statuses={200, 404},
        )
        if response.status_code == 404:
            return (None, b"")
        content_type = str(response.headers.get("Content-Type") or "").strip() or None
        return (content_type, response.content or b"")

    def ensure_public_link_share(self, owner_user_id: str, path: str, *, _quick: bool = False) -> str:
        normalized = self._normalize_folder_path(path)
        existing = self.get_public_link_share(owner_user_id, normalized)
        if existing is not None and existing.url:
            return existing.url

        response = self._request(
            "POST",
            "/ocs/v2.php/apps/files_sharing/api/v1/shares",
            data={
                "path": normalized,
                "shareType": self.PUBLIC_LINK_SHARE_TYPE,
                "permissions": 1,
            },
            _max_attempts=1 if _quick else self.MAX_OCS_ATTEMPTS,
        )
        data = self._extract_data(response)
        share = NextcloudShare(
            share_id=str(data.get("id") or ""),
            path=str(data.get("path") or normalized),
            share_with="",
            permissions=int(data.get("permissions") or 1),
            share_type=self.PUBLIC_LINK_SHARE_TYPE,
            url=str(data.get("url") or data.get("link") or ""),
            target_path=str(data.get("file_target") or data.get("fileTarget") or ""),
        )
        self._remember_public_share(share)
        return share.url

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if not self.is_configured:
            raise NextcloudApiError("Nextcloud provisioning is not configured.")

        method_upper = method.upper()
        default_attempts = self.ocs_read_attempts if method_upper in self.SAFE_RETRY_METHODS else 1
        max_attempts = max(int(kwargs.pop("_max_attempts", None) or default_attempts), 1)
        headers = {"OCS-APIRequest": "true"}
        headers.update(self._transport_headers())
        headers.update(kwargs.pop("headers", {}) or {})
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        params = dict(kwargs.pop("params", {}) or {})
        params.setdefault("format", "json")
        is_share_create = self._is_share_create_request(method, path)
        cap = self.MAX_RETRY_SLEEP_SECONDS
        response = None
        for attempt in range(max_attempts):
            if is_share_create:
                self._wait_for_share_slot()
            try:
                with self._request_slot():
                    response = self._session.request(
                        method,
                        f"{self.transport_base_url}{path}",
                        auth=(self.username, self.token),
                        headers=headers,
                        params=params,
                        timeout=(self.connect_timeout, self.read_timeout),
                        **kwargs,
                    )
            except requests.RequestException as exc:
                retryable_exception = (
                    method_upper in self.SAFE_RETRY_METHODS
                    and not isinstance(exc, requests.ReadTimeout)
                )
                if not retryable_exception or attempt == max_attempts - 1:
                    raise NextcloudApiError(f"Nextcloud request failed: {exc}") from exc
                delay = min(2.0 * (2 ** attempt), cap)
                logger.warning(
                    "OCS %s %s network error (attempt %d/%d), retry in %.1fs: %s",
                    method, path, attempt + 1, max_attempts, delay, exc,
                )
                time.sleep(delay)
                continue
            if response.status_code not in self.RETRYABLE_STATUS_CODES:
                if is_share_create and response.status_code < 400:
                    self._next_share_create_at = time.monotonic() + self.SHARE_CREATE_INTERVAL_SECONDS
                break
            if attempt == max_attempts - 1:
                break
            default_delay = min(2.0 * (2 ** attempt), cap)
            retry_after = min(self._get_retry_after_seconds(response, default=default_delay), cap)
            logger.warning(
                "OCS %s %s returned %d (attempt %d/%d), retry in %.1fs",
                method, path, response.status_code,
                attempt + 1, max_attempts, retry_after,
            )
            if is_share_create:
                self._next_share_create_at = max(
                    self._next_share_create_at,
                    time.monotonic() + retry_after,
                )
            time.sleep(retry_after)
        if response is not None and response.status_code >= 400:
            raise NextcloudApiError(f"Nextcloud API error {response.status_code}: {response.text[:500]}")
        return response

    def _dav_request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not self.is_configured:
            raise NextcloudApiError("Nextcloud provisioning is not configured.")

        allow_statuses = set(kwargs.pop("allow_statuses", set()) or set())
        method_upper = method.upper()
        max_attempts = self.dav_read_attempts if method_upper in self.IDEMPOTENT_DAV_RETRY_METHODS else 1
        headers = self._transport_headers()
        headers.update(kwargs.pop("headers", {}) or {})
        cap = self.MAX_RETRY_SLEEP_SECONDS
        response = None
        for attempt in range(max_attempts):
            try:
                with self._request_slot():
                    response = self._session.request(
                        method,
                        self._transport_url(url),
                        auth=(self.username, self.token),
                        headers=headers,
                        timeout=(self.connect_timeout, self.read_timeout),
                        **kwargs,
                    )
            except requests.RequestException as exc:
                retryable_exception = (
                    method_upper in self.IDEMPOTENT_DAV_RETRY_METHODS
                    and not isinstance(exc, requests.ReadTimeout)
                )
                if not retryable_exception or attempt == max_attempts - 1:
                    raise NextcloudApiError(f"Nextcloud DAV request failed: {exc}") from exc
                delay = min(2.0 * (2 ** attempt), cap)
                logger.warning(
                    "DAV %s network error (attempt %d/%d), retry in %.1fs: %s",
                    method, attempt + 1, max_attempts, delay, exc,
                )
                time.sleep(delay)
                continue
            if response.status_code not in self.DAV_RETRYABLE_STATUSES:
                break
            if attempt == max_attempts - 1:
                break
            delay = min(
                self._get_retry_after_seconds(response, default=min(2.0 * (2 ** attempt), cap)),
                cap,
            )
            logger.warning(
                "DAV %s returned %d (attempt %d/%d), retry in %.1fs",
                method, response.status_code, attempt + 1, max_attempts, delay,
            )
            time.sleep(delay)
        if response is not None and response.status_code >= 400 and response.status_code not in ({405} | allow_statuses):
            raise NextcloudApiError(f"Nextcloud DAV error {response.status_code}: {response.text[:500]}")
        return response

    def _webdav_path(self, owner_user_id: str, path: str) -> str:
        normalized = self._normalize_folder_path(path)
        encoded = quote(normalized.lstrip("/"), safe="/")
        return f"{self.base_url}/remote.php/dav/files/{quote(owner_user_id, safe='')}/{encoded}"

    def _transport_url(self, url: str) -> str:
        if self.transport_base_url == self.base_url or not url.startswith(self.base_url):
            return url
        return f"{self.transport_base_url}{url[len(self.base_url):]}"

    def _transport_headers(self) -> dict[str, str]:
        if self.transport_base_url == self.base_url:
            return {}
        public_host = urlparse(self.base_url).netloc
        return {"Host": public_host} if public_host else {}

    @classmethod
    def _get_request_semaphore(cls):
        size = max(int(getattr(settings, "NEXTCLOUD_MAX_CONCURRENT_REQUESTS_PER_PROCESS", 2) or 2), 1)
        with cls._request_semaphore_lock:
            if cls._request_semaphore is None or cls._request_semaphore_size != size:
                cls._request_semaphore = threading.BoundedSemaphore(size)
                cls._request_semaphore_size = size
            return cls._request_semaphore

    @classmethod
    def _request_slot(cls):
        return cls._get_request_semaphore()

    def _user_share_cache_key(self, owner_user_id: str, share_with_user_id: str):
        return (self.base_url, str(owner_user_id), str(share_with_user_id))

    def _get_cached_user_shares_locked(self, key):
        cached = self._share_cache.get(key)
        if cached is None:
            return None
        expires_at, shares = cached
        if expires_at <= time.monotonic():
            self._share_cache.pop(key, None)
            return None
        return dict(shares)

    def _get_cached_user_shares(self, owner_user_id: str, share_with_user_id: str):
        key = self._user_share_cache_key(owner_user_id, share_with_user_id)
        with self._share_cache_condition:
            return self._get_cached_user_shares_locked(key)

    def _invalidate_user_share_cache(self, owner_user_id: str, share_with_user_id: str) -> None:
        key = self._user_share_cache_key(owner_user_id, share_with_user_id)
        self._user_share_cache.pop((str(owner_user_id), str(share_with_user_id)), None)
        with self._share_cache_condition:
            self._share_cache.pop(key, None)

    @classmethod
    def _invalidate_all_user_share_caches(cls) -> None:
        with cls._share_cache_condition:
            cls._share_cache.clear()

    @staticmethod
    def _normalize_folder_path(path: str) -> str:
        raw = str(path or "").strip().replace("\\", "/")
        parts = [part.strip() for part in raw.split("/") if part.strip()]
        if not parts:
            return "/"
        return "/" + "/".join(parts)

    def get_public_link_share(self, owner_user_id: str, path: str) -> NextcloudShare | None:
        normalized = self._normalize_folder_path(path)
        if not self._public_share_cache_loaded:
            self.list_public_link_shares(owner_user_id)
        return self._public_share_cache.get(normalized)

    def list_public_link_shares(self, owner_user_id: str) -> dict[str, NextcloudShare]:
        response = self._request(
            "GET",
            "/ocs/v2.php/apps/files_sharing/api/v1/shares",
            params={"reshares": "true", "subfiles": "false"},
        )
        shares: dict[str, NextcloudShare] = {}
        for item in self._extract_list_data(response):
            item_path = self._normalize_folder_path(item.get("path") or "")
            if not item_path or item_path == "/":
                continue
            if self._as_int(item.get("share_type"), default=-1) != self.PUBLIC_LINK_SHARE_TYPE:
                continue
            shares[item_path] = NextcloudShare(
                share_id=str(item.get("id") or ""),
                path=item_path,
                share_with="",
                permissions=int(item.get("permissions") or 1),
                share_type=self.PUBLIC_LINK_SHARE_TYPE,
                url=str(item.get("url") or item.get("link") or ""),
                target_path=str(item.get("file_target") or item.get("fileTarget") or ""),
            )
        self._public_share_cache = shares
        self._public_share_cache_loaded = True
        return shares

    def _remember_public_share(self, share: NextcloudShare) -> None:
        if share.path:
            self._public_share_cache[share.path] = share
            self._public_share_cache_loaded = True

    def _extract_cloud_path(self, owner_user_id: str, href: str) -> str:
        base_prefix = f"/remote.php/dav/files/{quote(owner_user_id, safe='')}/"
        decoded = unquote(str(href or ""))
        if "/remote.php/dav/files/" in decoded:
            decoded = decoded.split("/remote.php/dav/files/", 1)[1]
            decoded = decoded.split("/", 1)[1] if "/" in decoded else ""
            return self._normalize_folder_path(decoded)
        if decoded.startswith(base_prefix):
            return self._normalize_folder_path(decoded[len(base_prefix):])
        return ""

    @staticmethod
    def _get_retry_after_seconds(response: requests.Response, *, default: float) -> float:
        raw = str(response.headers.get("Retry-After") or "").strip()
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return max(default, 0.0)
        return max(seconds, 0.0)

    def _wait_for_share_slot(self) -> None:
        now = time.monotonic()
        if self._next_share_create_at > now:
            time.sleep(min(self._next_share_create_at - now, self.MAX_RETRY_SLEEP_SECONDS))

    @staticmethod
    def _is_share_create_request(method: str, path: str) -> bool:
        return (
            method.upper() == "POST"
            and path == "/ocs/v2.php/apps/files_sharing/api/v1/shares"
        )

    @staticmethod
    def _as_int(value, *, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_data(response: requests.Response) -> dict[str, object]:
        data = NextcloudApiClient._extract_raw_data(response)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _extract_list_data(response: requests.Response) -> list[dict[str, object]]:
        data = NextcloudApiClient._extract_raw_data(response)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    @staticmethod
    def _extract_raw_data(response: requests.Response):
        if not response.content:
            return {}

        body = response.json()
        if isinstance(body, dict):
            ocs = body.get("ocs")
            if isinstance(ocs, dict):
                meta = ocs.get("meta") or {}
                statuscode = int(meta.get("statuscode") or 100)
                if statuscode >= 400:
                    raise NextcloudApiError(str(meta.get("message") or "Unexpected Nextcloud OCS error."))
                return ocs.get("data") or {}
            if isinstance(body.get("data"), dict):
                return body["data"]
        return {}
