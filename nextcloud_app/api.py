from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings


class NextcloudApiError(Exception):
    pass


@dataclass(frozen=True)
class NextcloudProvisionedUser:
    user_id: str
    display_name: str
    email: str


class NextcloudApiClient:
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

    @staticmethod
    def _extract_data(response: requests.Response) -> dict[str, object]:
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
                data = ocs.get("data")
                if isinstance(data, dict):
                    return data
                return {}
            if isinstance(body.get("data"), dict):
                return body["data"]
        return {}
