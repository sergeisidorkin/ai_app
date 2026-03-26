from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


class MoodleApiError(RuntimeError):
    pass


@dataclass(slots=True)
class MoodleApiConfig:
    base_url: str
    token: str
    timeout: int = 20


class MoodleApiClient:
    def __init__(self, config: MoodleApiConfig | None = None):
        if config is None:
            base_url = (getattr(settings, "MOODLE_BASE_URL", "") or "").strip().rstrip("/")
            token = (getattr(settings, "MOODLE_WEB_SERVICE_TOKEN", "") or "").strip()
            timeout = int(getattr(settings, "MOODLE_WEB_SERVICE_TIMEOUT", 20) or 20)
            config = MoodleApiConfig(base_url=base_url, token=token, timeout=timeout)

        self.config = config
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.base_url and self.config.token)

    def ensure_configured(self) -> None:
        if self.is_configured:
            return
        raise MoodleApiError(
            "Moodle API is not configured. Set MOODLE_BASE_URL and MOODLE_WEB_SERVICE_TOKEN."
        )

    def _endpoint(self) -> str:
        self.ensure_configured()
        explicit = (getattr(settings, "MOODLE_WEB_SERVICE_URL", "") or "").strip()
        if explicit:
            return explicit
        return f"{self.config.base_url}/webservice/rest/server.php"

    def call(self, function_name: str, **params: Any) -> Any:
        payload = {
            "wstoken": self.config.token,
            "moodlewsrestformat": "json",
            "wsfunction": function_name,
        }
        payload.update(self._flatten(params))
        try:
            response = self.session.post(
                self._endpoint(),
                data=payload,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MoodleApiError(f"HTTP error calling Moodle function `{function_name}`: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise MoodleApiError(
                f"Moodle function `{function_name}` returned non-JSON response."
            ) from exc

        if isinstance(data, dict) and data.get("exception"):
            message = data.get("message") or data.get("errorcode") or "Unknown Moodle exception"
            raise MoodleApiError(f"Moodle function `{function_name}` failed: {message}")

        return data

    def get_users_by_email(self, email: str) -> list[dict[str, Any]]:
        return self.call("core_user_get_users_by_field", field="email", values=[email])

    def get_users_by_username(self, username: str) -> list[dict[str, Any]]:
        return self.call("core_user_get_users_by_field", field="username", values=[username])

    def get_users_by_id(self, moodle_user_id: int) -> list[dict[str, Any]]:
        return self.call("core_user_get_users_by_field", field="id", values=[moodle_user_id])

    def get_users_by_idnumber(self, idnumber: str) -> list[dict[str, Any]]:
        return self.call("core_user_get_users_by_field", field="idnumber", values=[idnumber])

    def create_users(self, users: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = self.call("core_user_create_users", users=users)
        return data if isinstance(data, list) else []

    def update_users(self, users: list[dict[str, Any]]) -> Any:
        return self.call("core_user_update_users", users=users)

    def get_user_courses(self, moodle_user_id: int) -> list[dict[str, Any]]:
        data = self.call("core_enrol_get_users_courses", userid=moodle_user_id)
        return data if isinstance(data, list) else []

    def get_course_completion_status(self, course_id: int, moodle_user_id: int) -> dict[str, Any]:
        data = self.call(
            "core_completion_get_course_completion_status",
            courseid=course_id,
            userid=moodle_user_id,
        )
        return data if isinstance(data, dict) else {}

    def get_activities_completion_status(self, course_id: int, moodle_user_id: int) -> dict[str, Any]:
        data = self.call(
            "core_completion_get_activities_completion_status",
            courseid=course_id,
            userid=moodle_user_id,
        )
        return data if isinstance(data, dict) else {}

    def get_course_details(self, course_id: int) -> dict[str, Any]:
        data = self.call("core_course_get_courses", options=[{"name": "ids", "value": str(course_id)}])
        if isinstance(data, list) and data:
            return data[0]
        return {}

    @classmethod
    def _flatten(cls, value: Any, prefix: str | None = None) -> dict[str, Any]:
        items: dict[str, Any] = {}
        if isinstance(value, dict):
            for key, nested in value.items():
                nested_prefix = f"{prefix}[{key}]" if prefix is not None else str(key)
                items.update(cls._flatten(nested, nested_prefix))
            return items

        if isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                nested_prefix = f"{prefix}[{index}]"
                items.update(cls._flatten(nested, nested_prefix))
            return items

        if prefix is None:
            raise ValueError("Prefix is required for scalar flattening.")

        items[prefix] = value
        return items
