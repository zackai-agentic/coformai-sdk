"""Async dashboard resource methods, generated from tools/generate_resources.py.

Resource payloads preserve dashboard serializer fields without renaming them.
Refer to the operation matrix for exact endpoints and required permissions.
Every method raises the documented SDK HTTP/transport errors. No request is
automatically retried. Async methods are awaited; local resource factories and
invocation streams remain synchronous factories.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .graph import GraphMutationBuilder, GraphMutationRequest
from .models import HistoryPair, InputItem, StreamMode
from .streaming import AsyncInvocationStream

if TYPE_CHECKING:
    from .client import AsyncCoform


def _payload(data: Mapping[str, Any] | None, fields: dict[str, Any]) -> dict[str, Any]:
    overlap = set(data or {}) & set(fields)
    if overlap:
        raise ValueError("Duplicate payload fields: " + ", ".join(sorted(overlap)))
    return {**(data or {}), **fields}


def _wire(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    return value


class AsyncResource:
    """Organization-scoped resource base initialized by a client.

    Args:
        client: Owning Coform transport.
        path: Dashboard-relative resource path; includes the organization when required.
    """

    def __init__(self, client: AsyncCoform, path: str) -> None:
        """Bind an existing client and endpoint without making a request."""
        self._client, self._path = client, path.rstrip("/") + "/"

    def _detail(self, resource_id: str, suffix: str = "") -> str:
        from urllib.parse import quote

        return self._path + quote(str(resource_id), safe="") + "/" + suffix


class AsyncCRUDResource(AsyncResource):
    """Reusable CRUD methods using each resource's read/write/delete permission family."""

    async def list(self, **query: Any) -> Any:
        """List resources. Query parameters are forwarded, including pagination/filter fields. Requires read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._path, params=query)

    async def get(self, resource_id: str) -> Any:
        """Retrieve a resource by its server ID. Requires read; inaccessible IDs return 404.

        Args:
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id))

    async def create(self, data: Mapping[str, Any] | None = None, **fields: Any) -> Any:
        """Create a resource from serializer fields. Requires write; returns the server object.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request("POST", self._path, json=_payload(data, fields))

    async def update(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Partially update a resource. Omitted fields remain unchanged; explicit nulls are preserved. Requires write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "PATCH", self._detail(resource_id), json=_payload(data, fields)
        )

    async def replace(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Replace a resource using its full serializer payload. Requires write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "PUT", self._detail(resource_id), json=_payload(data, fields)
        )

    async def delete(self, resource_id: str) -> Any:
        """Permanently delete a resource. Requires delete; a 204 response returns None. Use graph detach for map removal.

        Args:
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("DELETE", self._detail(resource_id))

    async def iter_all(self, **query: Any) -> AsyncIterator[dict[str, Any]]:
        """Iterate plain lists or DRF paginated results, validating every next URL.

        Args:
            query: Initial filters and pagination options. Requires resource read.

        Yields:
            Resource objects across all pages.

        Raises:
            ValueError: Unexpected pagination shape or a next URL outside the API root.
            APIStatusError: A server page request failed.
        """
        path: str | None = self._path
        params = query
        while path:
            page = await self._client._request("GET", path, params=params)
            rows = page.get("results", []) if isinstance(page, dict) else page
            if not isinstance(rows, list):
                raise ValueError("Expected a list or DRF pagination envelope")
            for row in rows:
                yield row
            path = page.get("next") if isinstance(page, dict) else None
            params = {}


class AsyncOperationsSourceResource(AsyncResource):
    """Operations sources: list/create collection, patch/delete detail only."""

    async def list(self, **query: Any) -> Any:
        """List resources. Query parameters are forwarded, including pagination/filter fields. Requires read. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._path, params=query)

    async def create(self, data: Mapping[str, Any] | None = None, **fields: Any) -> Any:
        """Create a resource from serializer fields. Requires write; returns the server object. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request("POST", self._path, json=_payload(data, fields))

    async def update(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Partially update a resource. Omitted fields remain unchanged; explicit nulls are preserved. Requires write. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "PATCH", self._detail(resource_id), json=_payload(data, fields)
        )

    async def delete(self, resource_id: str) -> Any:
        """Permanently delete a resource. Requires delete; a 204 response returns None. Use graph detach for map removal. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("DELETE", self._detail(resource_id))


class AsyncDivisionResource(AsyncCRUDResource):
    """Division resource operations. See the operation matrix for supported routes."""

    async def map(self, resource_id: str, **query: Any) -> Any:
        """Read the full saved Division graph, including its revision. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    async def profile(self, resource_id: str, **query: Any) -> Any:
        """Read the Division profile and type-specific settings. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "profile/"), params=query
        )

    async def summary(self, resource_id: str, **query: Any) -> Any:
        """Read the graph summary. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "summary/"), params=query
        )

    async def session_parameters(self, resource_id: str, **query: Any) -> Any:
        """Read required and optional session parameter definitions. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "session-parameters/"), params=query
        )

    async def deployability(self, resource_id: str, **query: Any) -> Any:
        """Read saved deployment blockers. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "deployability/"), params=query
        )

    async def deploy(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Deploy after the dashboard readiness check; downstream failures are reported. Requires agents:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "deploy/"), json=_payload(data, fields)
        )

    async def undeploy(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Undeploy and stop runtime availability. Requires agents:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "undeploy/"), json=_payload(data, fields)
        )

    async def duplicate(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Duplicate a Division; additional grants apply to cloned/reused resources. Requires agents:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "duplicate/"), json=_payload(data, fields)
        )

    async def schedule_preview(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Preview schedule occurrences without saving schedule settings. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "schedule-preview/"), json=_payload(data, fields)
        )

    async def trigger(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Trigger dashboard automation. Prefer core invocations for event streaming. Requires inference:execute.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "trigger/"), json=_payload(data, fields)
        )

    async def scheduled_input_status(self, resource_id: str, **query: Any) -> Any:
        """Read scheduled-file extraction status under schedule-management permission. Requires agents:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "scheduled-input-files/status/"), params=query
        )

    async def transfer_export(self, resource_id: str, **query: Any) -> Any:
        """Export a credential-free Division package. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "transfer-export/"), params=query
        )

    async def transfer_status(self, resource_id: str, **query: Any) -> Any:
        """Read imported credentials and external dependency requirements. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "transfer-status/"), params=query
        )

    async def transfer_backup(self, resource_id: str, **query: Any) -> Any:
        """Retrieve the server-held transfer backup. Requires agents:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "transfer-backup/"), params=query
        )

    async def transfer_resolve(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Resolve imported source mappings and acknowledged dependencies. Requires agents:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "transfer-resolve/"), json=_payload(data, fields)
        )

    async def deployability_preview(
        self, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Validate an unsaved Division readiness payload. Requires agents:read.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._path + "deployability-preview/", json=_payload(data, fields)
        )

    async def compose(self, data: Mapping[str, Any] | None = None, **fields: Any) -> Any:
        """Compose a Division and nested entities; each created resource requires its own write grant. Requires agents:write.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._path + "compose/", json=_payload(data, fields)
        )

    async def import_preview(self, data: Mapping[str, Any] | None = None, **fields: Any) -> Any:
        """Preview an import before apply; preserve digest/revision values for apply. Requires agents:write.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._path + "import-preview/", json=_payload(data, fields)
        )

    async def import_apply(self, data: Mapping[str, Any] | None = None, **fields: Any) -> Any:
        """Apply an import with matching preview digests/revisions; additional resource grants apply. Requires agents:write.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._path + "import-apply/", json=_payload(data, fields)
        )


class AsyncIntegrationResource(AsyncCRUDResource):
    """Integration resource operations. See the operation matrix for supported routes."""

    async def duplicate(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Duplicate an integration and its endpoint definitions. Requires integrations:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "duplicate/"), json=_payload(data, fields)
        )

    async def refresh_tools(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Refresh remote MCP tools; this contacts the configured server. Requires integrations:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "refresh-tools/"), json=_payload(data, fields)
        )

    async def oauth_start(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Return an OAuth provider link for browser interaction. Requires integrations:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "oauth/start/"), json=_payload(data, fields)
        )

    async def oauth_initiate(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Initiate the provider authorization flow. Requires integrations:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "oauth/initiate/"), json=_payload(data, fields)
        )

    async def discover_tools(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Discover MCP tools after authorization. Requires integrations:write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "discover-tools/"), json=_payload(data, fields)
        )


class AsyncDependencyResource(AsyncCRUDResource):
    """Dependency resource operations. See the operation matrix for supported routes."""

    async def manage_dependencies(
        self, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Replace specified consumers' dependency on a provider step. Requires chains:write.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._path + "manage_dependencies/", json=_payload(data, fields)
        )

    async def remove_dependencies(
        self, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Remove specified consumer/provider dependency links. Requires chains:delete.

        Args:
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "DELETE", self._path + "remove_dependencies/", json=_payload(data, fields)
        )

    async def chain_dependencies(self, **query: Any) -> Any:
        """Read step dependency links using chain_id query parameter. Requires chains:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._path + "chain_dependencies/", params=query)


class AsyncAgentResource(AsyncCRUDResource):
    """Agent resource operations. See the operation matrix for supported routes."""

    async def map(self, resource_id: str, **query: Any) -> Any:
        """Read an agent or chain graph; supported routes vary by entity type. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    async def profile(self, resource_id: str, **query: Any) -> Any:
        """Read an entity profile where the dashboard exposes this route. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "profile/"), params=query
        )

    async def summary(self, resource_id: str, **query: Any) -> Any:
        """Read an entity summary where this route is supported. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "summary/"), params=query
        )

    async def duplicate(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Duplicate an agent/function where supported; nested resources require corresponding grants. Requires resource write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "duplicate/"), json=_payload(data, fields)
        )


class AsyncSwiftChainResource(AsyncCRUDResource):
    """SwiftChain resource operations. See the operation matrix for supported routes."""

    async def map(self, resource_id: str, **query: Any) -> Any:
        """Read an agent or chain graph; supported routes vary by entity type. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    async def profile(self, resource_id: str, **query: Any) -> Any:
        """Read an entity profile where the dashboard exposes this route. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "profile/"), params=query
        )

    async def summary(self, resource_id: str, **query: Any) -> Any:
        """Read an entity summary where this route is supported. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._detail(resource_id, "summary/"), params=query
        )

    async def steps(self, resource_id: str, **query: Any) -> Any:
        """Retrieve the dedicated Swift Chain step view. Requires chains:read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id, "steps/"), params=query)


class AsyncFlowChainResource(AsyncCRUDResource):
    """FlowChain resource operations. See the operation matrix for supported routes."""

    async def map(self, resource_id: str, **query: Any) -> Any:
        """Read an agent or chain graph; supported routes vary by entity type. Requires resource read.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._detail(resource_id, "map/"), params=query)


class AsyncFunctionResource(AsyncCRUDResource):
    """Function resource operations. See the operation matrix for supported routes."""

    async def duplicate(
        self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any
    ) -> Any:
        """Duplicate an agent/function where supported; nested resources require corresponding grants. Requires resource write.

        Args:
            resource_id: Persisted UUID/ID from a server response.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", self._detail(resource_id, "duplicate/"), json=_payload(data, fields)
        )


class AsyncGraphResource(AsyncResource):
    """Atomic graph validation/commit endpoints; every affected resource is authorized."""

    async def validate(
        self, payload: GraphMutationBuilder | GraphMutationRequest | Mapping[str, Any]
    ) -> Any:
        """Validate a graph request. IDs/revisions are correlation fields, not automatic retry guarantees.

        Args:
            payload: Builder, typed request, or raw server payload.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        if isinstance(payload, GraphMutationBuilder):
            payload = payload.build()
        data = _wire(payload)
        key = data.get("request_id")
        return await self._client._request(
            "POST",
            self._path + "validate/",
            json=data,
            headers={"Idempotency-Key": key} if key else {},
        )

    async def commit(
        self, payload: GraphMutationBuilder | GraphMutationRequest | Mapping[str, Any]
    ) -> Any:
        """Commit a graph request. IDs/revisions are correlation fields, not automatic retry guarantees.

        Args:
            payload: Builder, typed request, or raw server payload.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        if isinstance(payload, GraphMutationBuilder):
            payload = payload.build()
        data = _wire(payload)
        key = data.get("request_id")
        return await self._client._request(
            "POST",
            self._path + "commit/",
            json=data,
            headers={"Idempotency-Key": key} if key else {},
        )


class AsyncSettingsResource(AsyncResource):
    """Division share/embed settings; GET and mutations require agents:write."""

    async def get(self, division_id: str, **fields: Any) -> Any:
        """Get share/embed configuration. Requires agents:write.

        Args:
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path.format(division_id=division_id), params=fields
        )

    async def create(self, division_id: str, **fields: Any) -> Any:
        """Create share/embed configuration. Requires agents:write.

        Args:
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id), json=fields
        )

    async def update(self, division_id: str, **fields: Any) -> Any:
        """Update share/embed configuration. Requires agents:write.

        Args:
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "PATCH", self._path.format(division_id=division_id), json=fields
        )


class AsyncEmbedResource(AsyncSettingsResource):
    """Division embed management, requiring agents:write."""

    async def rotate_token(self, division_id: str) -> Any:
        """Rotate Token the embed token/state. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id) + "rotate-token/", json={}
        )

    async def enable(self, division_id: str) -> Any:
        """Enable the embed token/state. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id) + "enable/", json={}
        )

    async def disable(self, division_id: str) -> Any:
        """Disable the embed token/state. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id) + "disable/", json={}
        )


class AsyncShareResource(AsyncSettingsResource):
    """Division share management, requiring agents:write."""

    async def regenerate(self, division_id: str) -> Any:
        """Regenerate the share token/state. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id) + "regenerate/", json={}
        )

    async def revoke(self, division_id: str) -> Any:
        """Revoke the share token/state. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path.format(division_id=division_id) + "revoke/", json={}
        )


class AsyncNeedingsResource(AsyncResource):
    """Division readiness needings and their lifecycle."""

    async def list(self, division_id: str) -> Any:
        """List Division needings. Requires agents:read.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", f"divisions/{division_id}/needings")

    async def sync(self, division_id: str, data: Mapping[str, Any]) -> Any:
        """Sync needings. Requires agents:write.

        Args:
            data: Optional mapping of writable server fields.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return await self._client._request(
            "POST", f"divisions/{division_id}/needings/sync", json=dict(data)
        )

    async def discard(self, division_id: str, needing_id: str) -> Any:
        """Discard a needing. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "PATCH", f"divisions/{division_id}/needings/{needing_id}/discard", json={}
        )

    async def satisfy(self, division_id: str, needing_id: str) -> Any:
        """Satisfy a needing. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "PATCH", f"divisions/{division_id}/needings/{needing_id}/satisfy", json={}
        )

    async def reopen(self, division_id: str, needing_id: str) -> Any:
        """Reopen a needing. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "PATCH", f"divisions/{division_id}/needings/{needing_id}/reopen", json={}
        )


class AsyncSessionResource(AsyncResource):
    """Core session operations, all requiring inference:execute."""

    async def create(
        self,
        division_id: str,
        *,
        session_id: str | None = None,
        session_params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Create a session bound to a Division. Always send all three required fields; null requests a generated ID.

        Args:
            division_id: Persisted Division UUID.
            session_id: Session identifier; None requests a generated session where supported.
            session_params: Session parameter values; defaults to an empty mapping.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST",
            "create_session",
            service="core",
            json={
                "division_id": division_id,
                "session_id": session_id,
                "session_params": dict(session_params or {}),
            },
        )

    async def status(self, session_id: str, division_id: str) -> Any:
        """Read bound session status; reconcile interrupted streams before replaying.

        Args:
            session_id: Session identifier; None requests a generated session where supported.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET",
            "session_status",
            service="core",
            params={"session_id": session_id, "division_id": division_id},
        )

    async def add_agent_history(
        self,
        session_id: str,
        division_id: str,
        agent_id: str,
        pairs: list[HistoryPair | Mapping[str, Any]],
    ) -> Any:
        """Append input/output history pairs to an existing bound agent session.

        Args:
            session_id: Session identifier; None requests a generated session where supported.
            division_id: Persisted Division UUID.
            agent_id: Persisted agent UUID.
            pairs: History pairs to append.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST",
            "add_agent_history",
            service="core",
            json=_wire(
                {
                    "session_id": session_id,
                    "division_id": division_id,
                    "agent_id": agent_id,
                    "pairs": pairs,
                }
            ),
        )


class AsyncInvocationResource(AsyncResource):
    """Core execution streams, requiring inference:execute and Division access."""

    def process_inquiry(
        self,
        division_id: str,
        *,
        session_id: str,
        input_inquiry: str | None = None,
        inputs: list[InputItem | Mapping[str, Any]] | None = None,
        session_params: Mapping[str, Any] | None = None,
        entity_response_stream_option: StreamMode = "cumulative_stream",
        include_entity_inputs_in_response: bool = False,
    ) -> AsyncInvocationStream:
        """Start process inquiry on iteration/context entry. All modes return NDJSON. Use with/async with for early closure; collect returns explicit outcomes.

        Args:
            division_id: Persisted Division UUID.
            session_id: Session identifier; None requests a generated session where supported.
            input_inquiry: Optional text inquiry.
            inputs: Typed multimodal items or corresponding wire mappings.
            session_params: Session parameter values; defaults to an empty mapping.
            entity_response_stream_option: Response framing mode; defaults to cumulative_stream.
            include_entity_inputs_in_response: Include entity inputs in events; defaults to False.

        Returns:
            A lazy, single-use invocation stream. Collect for explicit terminal outcomes.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            StreamProtocolError: On iteration, the server sends a malformed event.
        """
        return self._client._stream(
            "process_inquiry",
            _wire(
                {
                    "session_id": session_id,
                    "input_inquiry": input_inquiry,
                    "inputs": inputs,
                    "division_id": division_id,
                    "session_params": dict(session_params or {}),
                    "entity_response_stream_option": entity_response_stream_option,
                    "include_entity_inputs_in_response": include_entity_inputs_in_response,
                }
            ),
            entity_response_stream_option,
        )

    def trigger_automation(
        self,
        division_id: str,
        *,
        session_id: str | None = None,
        input_inquiry: str | None = None,
        inputs: list[InputItem | Mapping[str, Any]] | None = None,
        session_params: Mapping[str, Any] | None = None,
        entity_response_stream_option: StreamMode = "cumulative_stream",
        include_entity_inputs_in_response: bool = False,
    ) -> AsyncInvocationStream:
        """Start trigger automation on iteration/context entry. All modes return NDJSON. Use with/async with for early closure; collect returns explicit outcomes.

        Args:
            division_id: Persisted Division UUID.
            session_id: Session identifier; None requests a generated session where supported.
            input_inquiry: Optional text inquiry.
            inputs: Typed multimodal items or corresponding wire mappings.
            session_params: Session parameter values; defaults to an empty mapping.
            entity_response_stream_option: Response framing mode; defaults to cumulative_stream.
            include_entity_inputs_in_response: Include entity inputs in events; defaults to False.

        Returns:
            A lazy, single-use invocation stream. Collect for explicit terminal outcomes.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            StreamProtocolError: On iteration, the server sends a malformed event.
        """
        return self._client._stream(
            "trigger_automation",
            _wire(
                {
                    "session_id": session_id,
                    "input_inquiry": input_inquiry,
                    "inputs": inputs,
                    "division_id": division_id,
                    "session_params": dict(session_params or {}),
                    "entity_response_stream_option": entity_response_stream_option,
                    "include_entity_inputs_in_response": include_entity_inputs_in_response,
                }
            ),
            entity_response_stream_option,
        )

    def continue_agent_loop(
        self,
        session_id: str,
        division_id: str,
        approval_id: str,
        approved: bool,
        *,
        session_params: Mapping[str, Any] | None = None,
        entity_response_stream_option: StreamMode = "cumulative_stream",
        include_entity_inputs_in_response: bool = False,
    ) -> AsyncInvocationStream:
        """Start continue agent loop on iteration/context entry. All modes return NDJSON. Use with/async with for early closure; collect returns explicit outcomes.

        Args:
            session_id: Session identifier; None requests a generated session where supported.
            division_id: Persisted Division UUID.
            approval_id: Approval identifier from the awaiting_approval event.
            approved: Explicit approval decision.
            session_params: Session parameter values; defaults to an empty mapping.
            entity_response_stream_option: Response framing mode; defaults to cumulative_stream.
            include_entity_inputs_in_response: Include entity inputs in events; defaults to False.

        Returns:
            A lazy, single-use invocation stream. Collect for explicit terminal outcomes.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            StreamProtocolError: On iteration, the server sends a malformed event.
        """
        return self._client._stream(
            "continue_agent_loop",
            _wire(
                {
                    "session_id": session_id,
                    "approval_id": approval_id,
                    "approved": approved,
                    "division_id": division_id,
                    "session_params": dict(session_params or {}),
                    "entity_response_stream_option": entity_response_stream_option,
                    "include_entity_inputs_in_response": include_entity_inputs_in_response,
                }
            ),
            entity_response_stream_option,
        )


class AsyncUploadResource(AsyncResource):
    """Integration and scheduled-input uploads. File handles close after each request."""

    async def rest(
        self,
        path: str | Path,
        *,
        name: str,
        base_url: str | None = None,
        trust_url: bool = False,
        update: bool | None = None,
    ) -> Any:
        """Upload an OpenAPI/Swagger specification as multipart. Requires integrations:write and delete for removed definitions. Server validation controls supported formats.

        Args:
            path: Local file to read and transmit; the handle closes after the request.
            name: Required integration name shown in the dashboard.
            base_url: Optional REST base URL override; defaults to None.
            trust_url: Dashboard URL validation choice; defaults to False.
            update: Existing-name policy: True replaces, False creates a copy, None retains the dashboard conflict response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            OSError: The local file could not be read.
        """
        file_path = Path(path)
        # Read disk off the event loop; HTTPX multipart accepts the resulting bytes.
        handle = await asyncio.to_thread(file_path.read_bytes)
        return await self._client._request(
            "POST",
            self._path + "unstructured-data/",
            data={
                "name": name,
                "client": self._client.configuration.organization_id,
                "base_url": base_url or "",
                "trust_url": str(trust_url).lower(),
                **({"update": str(update).lower()} if update is not None else {}),
            },
            files={"file": (file_path.name, handle, "application/octet-stream")},
        )

    async def openapi_string(self, openapi_string: str) -> Any:
        """Import an OpenAPI string. Requires integrations:write.

        Args:
            openapi_string: Complete OpenAPI/Swagger specification as a JSON or YAML string.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST",
            self._path + "integrations/openapi-string/",
            json={"openapi_string": openapi_string},
        )

    async def mcp(self, name: str, description: str, configuration: Mapping[str, Any] | str) -> Any:
        """Upload MCP servers configuration or raw JSON. Requires integrations:write. OAuth start links are returned for user interaction.

        Args:
            name: Required integration name shown in the dashboard.
            description: Required integration description shown in the dashboard.
            configuration: MCP servers mapping or raw JSON string; parsed locally before transmission.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        config = (
            json.loads(configuration) if isinstance(configuration, str) else dict(configuration)
        )
        return await self._client._request(
            "POST",
            self._path + "mcp/",
            json={"name": name, "description": description, "json_configuration": config},
        )

    async def scheduled_input(self, division_id: str, path: str | Path, **fields: Any) -> Any:
        """Upload a scheduled input file for extraction. Requires agents:write.

        Args:
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.
            path: Local file to read and transmit; the handle closes after the request.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            OSError: The local file could not be read.
        """
        file_path = Path(path)
        # Read disk off the event loop; HTTPX multipart accepts the resulting bytes.
        handle = await asyncio.to_thread(file_path.read_bytes)
        return await self._client._request(
            "POST",
            self._path + f"divisions/{division_id}/scheduled-input-files/",
            data=fields,
            files={"file": (file_path.name, handle, "application/octet-stream")},
        )

    async def clear_scheduled_inputs(self, division_id: str) -> Any:
        """Clear the entire scheduled input file collection. Requires agents:write.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path + f"divisions/{division_id}/scheduled-input-files/", json={}
        )


class AsyncCatalogResource(AsyncResource):
    """Read organization catalogs or dashboard monitoring."""

    async def sources(self, **query: Any) -> Any:
        """Retrieve sources. Requires knowledge:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._path + "sources/catalog/", params=query)

    async def source_content(self, **query: Any) -> Any:
        """Retrieve source content. Requires knowledge:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "sources/catalog/content-preview/", params=query
        )

    async def integrations(self, **query: Any) -> Any:
        """Retrieve integrations. Requires integrations:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "integrations/catalog/", params=query
        )

    async def integration_overview(self, **query: Any) -> Any:
        """Retrieve integration overview. Requires integrations:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "integrations/overview/", params=query
        )

    async def connected_models(self, **query: Any) -> Any:
        """Retrieve connected models. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", self._path + "connected-models/", params=query)

    async def model_capabilities(self, **query: Any) -> Any:
        """Retrieve model capabilities. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "model-capabilities/catalog/", params=query
        )

    async def hosted_models(self, **query: Any) -> Any:
        """Read available hosted models and their capabilities. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request("GET", "hosted-models/catalog/", params=query)


class AsyncMonitoringResource(AsyncResource):
    """Read organization catalogs or dashboard monitoring."""

    async def messages(self, **query: Any) -> Any:
        """Retrieve messages. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path.replace("clients/", "client/", 1) + "monitoring/", params=query
        )

    async def schedules(self, **query: Any) -> Any:
        """Retrieve schedules. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "monitoring/division-operations/schedules/", params=query
        )

    async def background_runs(self, **query: Any) -> Any:
        """Retrieve background runs. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "monitoring/division-operations/background-runs/", params=query
        )

    async def work_items(self, **query: Any) -> Any:
        """Retrieve work items. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path + "monitoring/division-operations/work-items/", json=query
        )

    async def sources(self, **query: Any) -> Any:
        """Retrieve sources. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET", self._path + "monitoring/division-operations/sources/", params=query
        )

    async def refresh_sources(self, **fields: Any) -> Any:
        """Query source health with an explicit refresh. Requires monitoring:read.

        Args:
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "POST", self._path + "monitoring/division-operations/sources/", json=fields
        )

    async def background_run_by_message(self, message_id: str) -> Any:
        """Read a background run linked to a message. Requires monitoring:read.

        Args:
            message_id: Persisted message UUID associated with a background run.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return await self._client._request(
            "GET",
            self._path + f"monitoring/division-operations/background-runs/by-message/{message_id}/",
        )
