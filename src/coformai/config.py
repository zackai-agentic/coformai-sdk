"""Explicit deployment configuration and safe URL joining."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, Field, field_validator


class Configuration(BaseModel):
    """Resolved client configuration; API keys are excluded from repr.

    Attributes:
        api_key: Dashboard-generated key; falls back to COFORM_API_KEY.
        organization_id: Organization UUID, from COFORM_ORGANIZATION_ID if omitted.
        dashboard_base_url: API root including /api and any proxy prefix.
        core_base_url: Core service root, including any proxy prefix.
        timeout: Nonstreaming request timeout in seconds, default 60.

    URLs have no hosted defaults: use the roots for your own deployment.
    """

    api_key: str = Field(repr=False, min_length=1)
    organization_id: str = Field(min_length=1)
    dashboard_base_url: str
    core_base_url: str
    timeout: float = Field(default=60, gt=0)

    @field_validator("api_key", "organization_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        """Reject blank credentials and identifiers before making requests."""
        if not value.strip():
            raise ValueError("Configuration values must not be blank")
        return value.strip()

    @field_validator("dashboard_base_url", "core_base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Require HTTP(S) roots without query, fragment, or embedded credentials."""
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Use an HTTP(S) API root without credentials, query, or fragment")
        return value.rstrip("/") + "/"

    @classmethod
    def resolve(
        cls,
        api_key: str | None,
        organization_id: str | None,
        dashboard_base_url: str | None,
        core_base_url: str | None,
        timeout: float,
    ) -> Configuration:
        """Resolve constructor values before matching environment variables.

        Args:
            api_key: Dashboard credential; None reads COFORM_API_KEY.
            organization_id: Tenant UUID; None reads COFORM_ORGANIZATION_ID.
            dashboard_base_url: API root; None reads COFORM_DASHBOARD_URL.
            core_base_url: Core root; None reads COFORM_CORE_URL.
            timeout: Positive timeout for nonstreaming requests, in seconds.

        Returns:
            Validated configuration. No network request occurs.

        Raises:
            ValueError: A required value is missing or a value is invalid.
        """
        values = dict(
            api_key=api_key,
            organization_id=organization_id,
            dashboard_base_url=dashboard_base_url,
            core_base_url=core_base_url,
        )
        envs = {
            "api_key": "COFORM_API_KEY",
            "organization_id": "COFORM_ORGANIZATION_ID",
            "dashboard_base_url": "COFORM_DASHBOARD_URL",
            "core_base_url": "COFORM_CORE_URL",
        }
        for name, env in envs.items():
            if values[name] is None:
                values[name] = os.getenv(env)
        missing = [envs[name] for name, value in values.items() if not value]
        if missing:
            raise ValueError("Missing Coform configuration: " + ", ".join(missing))
        return cls.model_validate({**values, "timeout": timeout})

    def url(self, service: str, path: str) -> str:
        """Join a relative path or validate a same-root pagination URL.

        Absolute pagination URLs cannot change the origin or escape the configured
        root; this prevents transmitting the API key to an unrelated host.

        Args:
            service: dashboard or core.
            path: Relative API path or a pagination URL inside that service root.

        Returns:
            Complete URL retaining the configured reverse-proxy prefix.

        Raises:
            ValueError: Service is unknown or the path escapes the API root.
        """
        if service not in {"dashboard", "core"}:
            raise ValueError("Service must be dashboard or core")
        root = self.dashboard_base_url if service == "dashboard" else self.core_base_url
        parts = urlsplit(path)
        if ".." in unquote(parts.path).split("/") or "\\" in path or parts.fragment:
            raise ValueError("API paths must remain inside the configured root")
        if parts.scheme or parts.netloc:
            expected = urlsplit(root)
            if (
                parts.scheme != expected.scheme
                or parts.netloc != expected.netloc
                or not parts.path.startswith(expected.path)
                or parts.fragment
                or parts.username
                or parts.password
            ):
                raise ValueError("Pagination URL must remain inside the configured API root")
            return path
        if ".." in parts.path.split("/") or path.startswith("//"):
            raise ValueError("API paths must remain inside the configured root")
        return root + path.lstrip("/")
