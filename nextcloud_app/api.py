from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import requests
from django.conf import settings


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


class NextcloudApiClient:
    EDITOR_PERMISSIONS = 15
    PUBLIC_LINK_SHARE_TYPE = 3

    def __init__(self, *, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self.base_url = (getattr(settings, "NEXTCLOUD_PROVISIONING_BASE_URL", "") or "").strip().rstrip("/")
        self.username = (getattr(settings, "NEXTCLOUD_PROVISIONING_USERNAME", "") or "").strip()
        self.token = (getattr(settings, "NEXTCLOUD_PROVISIONING_TOKEN", "") or "").strip()
        self.provider_id = int(getattr(settings, "NEXTCLOUD_OIDC_PROVIDER_ID", 0) or 0)
        self.default_group = (getattr(settings, "NEXTCLOUD_DEFAULT_GROUP", "") or "").strip()
        self.default_quota = (getattr(settings, "NEXTCLOUD_DEFAULT_QUOTA", "") or "").strip()

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
                return NextcloudShare(
                    share_id=existing.share_id,
                    path=existing.path,
                    share_with=existing.share_with,
                    permissions=permissions,
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
        return NextcloudShare(
            share_id=str(data.get("id") or ""),
            path=str(data.get("path") or normalized),
            share_with=str(data.get("share_with") or share_with_user_id),
            permissions=int(data.get("permissions") or permissions),
        )

    def get_user_share(
        self,
        owner_user_id: str,
        path: str,
        share_with_user_id: str,
    ) -> NextcloudShare | None:
        normalized = self._normalize_folder_path(path)
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
            if int(item.get("share_type") or -1) != 0:
                continue
            return NextcloudShare(
                share_id=str(item.get("id") or ""),
                path=str(item.get("path") or normalized),
                share_with=str(item.get("share_with") or share_with_user_id),
                permissions=int(item.get("permissions") or self.EDITOR_PERMISSIONS),
            )
        return None

    def build_files_url(self, path: str) -> str:
        normalized = self._normalize_folder_path(path)
        return f"{self.base_url}/apps/files/files?dir={quote(normalized, safe='/')}"

    def list_resources(self, owner_user_id: str, path: str, *, limit: int = 100) -> list[dict[str, object]]:
        normalized = self._normalize_folder_path(path)
        response = self._dav_request(
            "PROPFIND",
            self._webdav_path(owner_user_id, normalized),
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=(
                '<?xml version="1.0"?>'
                '<d:propfind xmlns:d="DAV:">'
                "<d:prop><d:displayname/><d:resourcetype/><d:getcontentlength/><d:getlastmodified/></d:prop>"
                "</d:propfind>"
            ),
            allow_statuses={207, 404},
        )
        if response.status_code == 404:
            return []

        requested_path = self._normalize_folder_path(path)
        items: list[dict[str, object]] = []
        root = ET.fromstring(response.content)
        ns = {"d": "DAV:"}
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
            items.append(
                {
                    "name": name,
                    "path": item_path,
                    "type": "dir" if is_dir else "file",
                    "size": int(size_raw) if str(size_raw).isdigit() else None,
                    "modified": modified,
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

    def ensure_public_link_share(self, owner_user_id: str, path: str) -> str:
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
        )
        data = self._extract_data(response)
        return str(data.get("url") or data.get("link") or "")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if not self.is_configured:
            raise NextcloudApiError("Nextcloud provisioning is not configured.")

        headers = {"OCS-APIRequest": "true"}
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        params = dict(kwargs.pop("params", {}) or {})
        params.setdefault("format", "json")
        response = self._session.request(
            method,
            f"{self.base_url}{path}",
            auth=(self.username, self.token),
            headers=headers,
            params=params,
            timeout=20,
            **kwargs,
        )
        if response.status_code >= 400:
            raise NextcloudApiError(f"Nextcloud API error {response.status_code}: {response.text[:500]}")
        return response

    def _dav_request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not self.is_configured:
            raise NextcloudApiError("Nextcloud provisioning is not configured.")

        allow_statuses = set(kwargs.pop("allow_statuses", set()) or set())
        response = self._session.request(
            method,
            url,
            auth=(self.username, self.token),
            timeout=20,
            **kwargs,
        )
        if response.status_code >= 400 and response.status_code not in ({405} | allow_statuses):
            raise NextcloudApiError(f"Nextcloud DAV error {response.status_code}: {response.text[:500]}")
        return response

    def _webdav_path(self, owner_user_id: str, path: str) -> str:
        normalized = self._normalize_folder_path(path)
        encoded = quote(normalized.lstrip("/"), safe="/")
        return f"{self.base_url}/remote.php/dav/files/{quote(owner_user_id, safe='')}/{encoded}"

    @staticmethod
    def _normalize_folder_path(path: str) -> str:
        raw = str(path or "").strip().replace("\\", "/")
        parts = [part.strip() for part in raw.split("/") if part.strip()]
        if not parts:
            return "/"
        return "/" + "/".join(parts)

    def get_public_link_share(self, owner_user_id: str, path: str) -> NextcloudShare | None:
        normalized = self._normalize_folder_path(path)
        response = self._request(
            "GET",
            "/ocs/v2.php/apps/files_sharing/api/v1/shares",
            params={"path": normalized, "reshares": "true", "subfiles": "false"},
        )
        for item in self._extract_list_data(response):
            item_path = self._normalize_folder_path(item.get("path") or normalized)
            if item_path != normalized:
                continue
            if int(item.get("share_type") or -1) != self.PUBLIC_LINK_SHARE_TYPE:
                continue
            return NextcloudShare(
                share_id=str(item.get("id") or ""),
                path=item_path,
                share_with="",
                permissions=int(item.get("permissions") or 1),
                share_type=self.PUBLIC_LINK_SHARE_TYPE,
                url=str(item.get("url") or item.get("link") or ""),
            )
        return None

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
