"""Sync dashboard resource methods, generated from tools/generate_resources.py.

Resource payloads preserve dashboard serializer fields without renaming them.
Refer to the operation matrix for exact endpoints and required permissions.
Every method raises the documented SDK HTTP/transport errors. No request is
automatically retried. Async methods are awaited; local resource factories and
invocation streams remain synchronous factories.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

from .graph import GraphMutationBuilder, GraphMutationRequest
from .models import HistoryPair, InputItem, StreamMode
from .streaming import InvocationStream

if TYPE_CHECKING:
    from .client import Coform


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


class Resource:
    """Organization-scoped resource base initialized by a client.

    Args:
        client: Owning Coform transport.
        path: Dashboard-relative resource path; includes the organization when required.
    """

    def __init__(self, client: Coform, path: str) -> None:
        """Bind an existing client and endpoint without making a request."""
        self._client, self._path = client, path.rstrip("/") + "/"

    def _detail(self, resource_id: str, suffix: str = "") -> str:
        from urllib.parse import quote

        return self._path + quote(str(resource_id), safe="") + "/" + suffix


class CRUDResource(Resource):
    """Reusable CRUD methods using each resource's read/write/delete permission family."""

    def list(self, **query: Any) -> Any:
        """List resources. Query parameters are forwarded, including pagination/filter fields. Requires read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path, params=query)

    def get(self, resource_id: str) -> Any:
        """Retrieve a resource by its server ID. Requires read; inaccessible IDs return 404.

        Args:
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._detail(resource_id))

    def create(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Create a resource from serializer fields. Requires write; returns the server object.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST", self._path, json=_payload(data, fields), operation_id=operation_id
        )

    def update(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Partially update a resource. Omitted fields remain unchanged; explicit nulls are preserved. Requires write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "PATCH",
            self._detail(resource_id),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def replace(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Replace a resource using its full serializer payload. Requires write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "PUT", self._detail(resource_id), json=_payload(data, fields), operation_id=operation_id
        )

    def delete(self, resource_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Permanently delete a resource. Requires delete; a 204 response returns None. Use graph detach for map removal.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("DELETE", self._detail(resource_id), operation_id=operation_id)

    def iter_all(self, **query: Any) -> Iterator[dict[str, Any]]:
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
            page = self._client._request("GET", path, params=params)
            rows = page.get("results", []) if isinstance(page, dict) else page
            if not isinstance(rows, list):
                raise ValueError("Expected a list or DRF pagination envelope")
            for row in rows:
                yield row
            path = page.get("next") if isinstance(page, dict) else None
            params = {}


class SourceResource(CRUDResource):
    """Knowledge Base source CRUD and multipart file ingestion."""

    def upload(
        self,
        path: str | Path,
        *,
        name: str,
        source_id: str | None = None,
        description: str | None = None,
        enable_semantic_retrieval: bool = False,
        embedding_model_connection_id: str | None = None,
        max_tokens_in_chunk: int = 1024,
        operation_id: str | UUID | None = None,
    ) -> Any:
        """Create a Knowledge Base source or replace an existing source file in place. Requires knowledge:write. Upload starts asynchronous extraction/indexing; poll sources.get(source_id) for completed or failed status. No automatic retry or polling occurs. Embedding and chunk settings are sent only when semantic retrieval is enabled.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            path: Local file to read and transmit; the handle closes after the request.
            name: Required Knowledge Base source name shown in the dashboard.
            source_id: Existing source UUID to replace its file in place; None creates a source.
            description: Optional source description; None omits the field.
            enable_semantic_retrieval: Enable semantic indexing; defaults to False.
            embedding_model_connection_id: Organization embedding-model connection UUID; None leaves selection to the server.
            max_tokens_in_chunk: Positive semantic chunk size; defaults to 1024 and is omitted for nonsemantic sources.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Source name is blank or semantic chunk size is not positive.
            OSError: The local file could not be read.
        """
        if not name.strip():
            raise ValueError("Source name must not be blank")
        if enable_semantic_retrieval and max_tokens_in_chunk <= 0:
            raise ValueError("max_tokens_in_chunk must be positive")
        metadata = {
            "name": name,
            "enable_semantic_retrieval": str(enable_semantic_retrieval).lower(),
        }
        if description is not None:
            metadata["description"] = description
        if enable_semantic_retrieval:
            metadata["max_tokens_in_chunk"] = str(max_tokens_in_chunk)
            if embedding_model_connection_id is not None:
                metadata["embedding_model_connection"] = embedding_model_connection_id
        file_path = Path(path)
        with file_path.open("rb") as handle:
            return self._client._request(
                "PATCH" if source_id is not None else "POST",
                self._detail(source_id) if source_id is not None else self._path,
                data=metadata,
                files={"file": (file_path.name, handle, "application/octet-stream")},
                operation_id=operation_id,
            )


class OperationsSourceResource(Resource):
    """Operations sources: list/create collection, patch/delete detail only."""

    def list(self, **query: Any) -> Any:
        """List resources. Query parameters are forwarded, including pagination/filter fields. Requires read. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path, params=query)

    def create(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Create a resource from serializer fields. Requires write; returns the server object. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST", self._path, json=_payload(data, fields), operation_id=operation_id
        )

    def update(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Partially update a resource. Omitted fields remain unchanged; explicit nulls are preserved. Requires write. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "PATCH",
            self._detail(resource_id),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def delete(self, resource_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Permanently delete a resource. Requires delete; a 204 response returns None. Use graph detach for map removal. Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            resource_id: Persisted UUID/ID from a server response.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("DELETE", self._detail(resource_id), operation_id=operation_id)


class DivisionResource(CRUDResource):
    """Division resource operations. See the operation matrix for supported routes."""

    def map(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    def profile(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "profile/"), params=query)

    def summary(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "summary/"), params=query)

    def session_parameters(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "session-parameters/"), params=query
        )

    def deployability(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "deployability/"), params=query
        )

    def deploy(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Deploy after the dashboard readiness check; downstream failures are reported. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "deploy/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def undeploy(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Undeploy and stop runtime availability. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "undeploy/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def duplicate(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Duplicate a Division; additional grants apply to cloned/reused resources. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "duplicate/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def schedule_preview(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Preview schedule occurrences without saving schedule settings. Requires agents:read.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "schedule-preview/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def trigger(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Trigger dashboard automation. Prefer core invocations for event streaming. Requires inference:execute.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "trigger/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def scheduled_input_status(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "scheduled-input-files/status/"), params=query
        )

    def transfer_export(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "transfer-export/"), params=query
        )

    def transfer_status(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "transfer-status/"), params=query
        )

    def transfer_backup(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request(
            "GET", self._detail(resource_id, "transfer-backup/"), params=query
        )

    def transfer_resolve(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Resolve imported source mappings and acknowledged dependencies. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "transfer-resolve/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def deployability_preview(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Validate an unsaved Division readiness payload. Requires agents:read.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST",
            self._path + "deployability-preview/",
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def compose(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Compose a Division and nested entities; each created resource requires its own write grant. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST", self._path + "compose/", json=_payload(data, fields), operation_id=operation_id
        )

    def import_preview(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Preview an import before apply; preserve digest/revision values for apply. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST",
            self._path + "import-preview/",
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def import_apply(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Apply an import with matching preview digests/revisions; additional resource grants apply. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST",
            self._path + "import-apply/",
            json=_payload(data, fields),
            operation_id=operation_id,
        )


class IntegrationResource(CRUDResource):
    """Integration resource operations. See the operation matrix for supported routes."""

    def duplicate(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Duplicate an integration and its endpoint definitions. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "duplicate/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def refresh_tools(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Refresh remote MCP tools; this contacts the configured server. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "refresh-tools/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def oauth_start(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Return an OAuth provider link for browser interaction. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "oauth/start/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def oauth_initiate(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Initiate the provider authorization flow. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "oauth/initiate/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def discover_tools(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Discover MCP tools after authorization. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "discover-tools/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )


class DependencyResource(CRUDResource):
    """Dependency resource operations. See the operation matrix for supported routes."""

    def manage_dependencies(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Replace specified consumers' dependency on a provider step. Requires chains:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST",
            self._path + "manage_dependencies/",
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def remove_dependencies(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Remove specified consumer/provider dependency links. Requires chains:delete.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "DELETE",
            self._path + "remove_dependencies/",
            json=_payload(data, fields),
            operation_id=operation_id,
        )

    def chain_dependencies(self, **query: Any) -> Any:
        """Read step dependency links using chain_id query parameter. Requires chains:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path + "chain_dependencies/", params=query)


class AgentResource(CRUDResource):
    """Agent resource operations. See the operation matrix for supported routes."""

    def map(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    def profile(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "profile/"), params=query)

    def summary(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "summary/"), params=query)

    def duplicate(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Duplicate an agent/function where supported; nested resources require corresponding grants. Requires resource write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "duplicate/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )


class SwiftChainResource(CRUDResource):
    """SwiftChain resource operations. See the operation matrix for supported routes."""

    def map(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "map/"), params=query)

    def profile(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "profile/"), params=query)

    def summary(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "summary/"), params=query)

    def steps(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "steps/"), params=query)


class FlowChainResource(CRUDResource):
    """FlowChain resource operations. See the operation matrix for supported routes."""

    def map(self, resource_id: str, **query: Any) -> Any:
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
        return self._client._request("GET", self._detail(resource_id, "map/"), params=query)


class FunctionResource(CRUDResource):
    """Function resource operations. See the operation matrix for supported routes."""

    def duplicate(
        self,
        resource_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Duplicate an agent/function where supported; nested resources require corresponding grants. Requires resource write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._detail(resource_id, "duplicate/"),
            json=_payload(data, fields),
            operation_id=operation_id,
        )


class GraphResource(Resource):
    """Atomic graph validation/commit endpoints; every affected resource is authorized."""

    def validate(
        self,
        payload: GraphMutationBuilder | GraphMutationRequest | Mapping[str, Any],
        *,
        operation_id: str | UUID | None = None,
    ) -> Any:
        """Validate a graph request. IDs/revisions are correlation fields, not automatic retry guarantees.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._path + "validate/",
            json=data,
            headers={"Idempotency-Key": key} if key else {},
            operation_id=operation_id,
        )

    def commit(
        self,
        payload: GraphMutationBuilder | GraphMutationRequest | Mapping[str, Any],
        *,
        operation_id: str | UUID | None = None,
    ) -> Any:
        """Commit a graph request. IDs/revisions are correlation fields, not automatic retry guarantees.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._path + "commit/",
            json=data,
            headers={"Idempotency-Key": key} if key else {},
            operation_id=operation_id,
        )


class SettingsResource(Resource):
    """Division share/embed settings; GET and mutations require agents:write."""

    def get(self, division_id: str, **fields: Any) -> Any:
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
        return self._client._request(
            "GET", self._path.format(division_id=division_id), params=fields
        )

    def create(
        self, division_id: str, *, operation_id: str | UUID | None = None, **fields: Any
    ) -> Any:
        """Create share/embed configuration. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id),
            json=fields,
            operation_id=operation_id,
        )

    def update(
        self, division_id: str, *, operation_id: str | UUID | None = None, **fields: Any
    ) -> Any:
        """Update share/embed configuration. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            fields: Additional fields; duplicate mapping keys are rejected.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "PATCH",
            self._path.format(division_id=division_id),
            json=fields,
            operation_id=operation_id,
        )


class EmbedResource(SettingsResource):
    """Division embed management, requiring agents:write."""

    def rotate_token(self, division_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Rotate Token the embed token/state. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id) + "rotate-token/",
            json={},
            operation_id=operation_id,
        )

    def enable(self, division_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Enable the embed token/state. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id) + "enable/",
            json={},
            operation_id=operation_id,
        )

    def disable(self, division_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Disable the embed token/state. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id) + "disable/",
            json={},
            operation_id=operation_id,
        )


class ShareResource(SettingsResource):
    """Division share management, requiring agents:write."""

    def regenerate(self, division_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Regenerate the share token/state. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id) + "regenerate/",
            json={},
            operation_id=operation_id,
        )

    def revoke(self, division_id: str, *, operation_id: str | UUID | None = None) -> Any:
        """Revoke the share token/state. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path.format(division_id=division_id) + "revoke/",
            json={},
            operation_id=operation_id,
        )


class NeedingsResource(Resource):
    """Division readiness needings and their lifecycle."""

    def list(self, division_id: str) -> Any:
        """List Division needings. Requires agents:read.

        Args:
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", f"divisions/{division_id}/needings")

    def sync(
        self, division_id: str, data: Mapping[str, Any], *, operation_id: str | UUID | None = None
    ) -> Any:
        """Sync needings. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            data: Optional mapping of writable server fields.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
            ValueError: Duplicate payload fields or invalid local JSON configuration.
        """
        return self._client._request(
            "POST",
            f"divisions/{division_id}/needings/sync",
            json=dict(data),
            operation_id=operation_id,
        )

    def discard(
        self, division_id: str, needing_id: str, *, operation_id: str | UUID | None = None
    ) -> Any:
        """Discard a needing. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "PATCH",
            f"divisions/{division_id}/needings/{needing_id}/discard",
            json={},
            operation_id=operation_id,
        )

    def satisfy(
        self, division_id: str, needing_id: str, *, operation_id: str | UUID | None = None
    ) -> Any:
        """Satisfy a needing. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "PATCH",
            f"divisions/{division_id}/needings/{needing_id}/satisfy",
            json={},
            operation_id=operation_id,
        )

    def reopen(
        self, division_id: str, needing_id: str, *, operation_id: str | UUID | None = None
    ) -> Any:
        """Reopen a needing. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.
            needing_id: Persisted needing UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "PATCH",
            f"divisions/{division_id}/needings/{needing_id}/reopen",
            json={},
            operation_id=operation_id,
        )


class SessionResource(Resource):
    """Core session operations, all requiring inference:execute."""

    def create(
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
        return self._client._request(
            "POST",
            "create_session",
            service="core",
            json={
                "division_id": division_id,
                "session_id": session_id,
                "session_params": dict(session_params or {}),
            },
        )

    def status(self, session_id: str, division_id: str) -> Any:
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
        return self._client._request(
            "GET",
            "session_status",
            service="core",
            params={"session_id": session_id, "division_id": division_id},
        )

    def add_agent_history(
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
        return self._client._request(
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


class InvocationResource(Resource):
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
    ) -> InvocationStream:
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
    ) -> InvocationStream:
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
    ) -> InvocationStream:
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


class UploadResource(Resource):
    """Integration and scheduled-input uploads. File handles close after each request."""

    def rest(
        self,
        path: str | Path,
        *,
        name: str,
        base_url: str | None = None,
        trust_url: bool = False,
        update: bool | None = None,
        operation_id: str | UUID | None = None,
    ) -> Any:
        """Upload an OpenAPI/Swagger specification as multipart. Requires integrations:write and delete for removed definitions. Server validation controls supported formats.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        with file_path.open("rb") as handle:
            return self._client._request(
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
                operation_id=operation_id,
            )

    def openapi_string(self, openapi_string: str, *, operation_id: str | UUID | None = None) -> Any:
        """Import an OpenAPI string. Requires integrations:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            openapi_string: Complete OpenAPI/Swagger specification as a JSON or YAML string.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path + "integrations/openapi-string/",
            json={"openapi_string": openapi_string},
            operation_id=operation_id,
        )

    def mcp(
        self,
        name: str,
        description: str,
        configuration: Mapping[str, Any] | str,
        *,
        operation_id: str | UUID | None = None,
    ) -> Any:
        """Upload MCP servers configuration or raw JSON. Requires integrations:write. OAuth start links are returned for user interaction.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        return self._client._request(
            "POST",
            self._path + "mcp/",
            json={"name": name, "description": description, "json_configuration": config},
            operation_id=operation_id,
        )

    def scheduled_input(
        self,
        division_id: str,
        path: str | Path,
        *,
        operation_id: str | UUID | None = None,
        **fields: Any,
    ) -> Any:
        """Upload a scheduled input file for extraction. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
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
        with file_path.open("rb") as handle:
            return self._client._request(
                "POST",
                self._path + f"divisions/{division_id}/scheduled-input-files/",
                data=fields,
                files={"file": (file_path.name, handle, "application/octet-stream")},
                operation_id=operation_id,
            )

    def clear_scheduled_inputs(
        self, division_id: str, *, operation_id: str | UUID | None = None
    ) -> Any:
        """Clear the entire scheduled input file collection. Requires agents:write.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            division_id: Persisted Division UUID.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path + f"divisions/{division_id}/scheduled-input-files/",
            json={},
            operation_id=operation_id,
        )


class CatalogResource(Resource):
    """Read organization catalogs or dashboard monitoring."""

    def sources(self, **query: Any) -> Any:
        """Retrieve sources. Requires knowledge:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path + "sources/catalog/", params=query)

    def source_content(self, **query: Any) -> Any:
        """Retrieve source content. Requires knowledge:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path + "sources/catalog/content-preview/", params=query
        )

    def integrations(self, **query: Any) -> Any:
        """Retrieve integrations. Requires integrations:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path + "integrations/catalog/", params=query)

    def integration_overview(self, **query: Any) -> Any:
        """Retrieve integration overview. Requires integrations:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path + "integrations/overview/", params=query)

    def connected_models(self, **query: Any) -> Any:
        """Retrieve connected models. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", self._path + "connected-models/", params=query)

    def model_capabilities(self, **query: Any) -> Any:
        """Retrieve model capabilities. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path + "model-capabilities/catalog/", params=query
        )

    def hosted_models(self, **query: Any) -> Any:
        """Read available hosted models and their capabilities. Requires agents:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request("GET", "hosted-models/catalog/", params=query)


class MonitoringResource(Resource):
    """Read organization catalogs or dashboard monitoring."""

    def messages(self, **query: Any) -> Any:
        """Retrieve messages. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path.replace("clients/", "client/", 1) + "monitoring/", params=query
        )

    def schedules(self, **query: Any) -> Any:
        """Retrieve schedules. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path + "monitoring/division-operations/schedules/", params=query
        )

    def background_runs(self, **query: Any) -> Any:
        """Retrieve background runs. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path + "monitoring/division-operations/background-runs/", params=query
        )

    def work_items(self, **query: Any) -> Any:
        """Retrieve work items. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST", self._path + "monitoring/division-operations/work-items/", json=query
        )

    def sources(self, **query: Any) -> Any:
        """Retrieve sources. Requires monitoring:read.

        Args:
            query: Server query parameters; forwarded without renaming.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET", self._path + "monitoring/division-operations/sources/", params=query
        )

    def refresh_sources(self, *, operation_id: str | UUID | None = None, **fields: Any) -> Any:
        """Query source health with an explicit refresh. Requires monitoring:read.

        Args:
            operation_id: UUID identifying this dashboard write. The client supplies one by default.
            fields: Additional fields; duplicate mapping keys are rejected.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "POST",
            self._path + "monitoring/division-operations/sources/",
            json=fields,
            operation_id=operation_id,
        )

    def background_run_by_message(self, message_id: str) -> Any:
        """Read a background run linked to a message. Requires monitoring:read.

        Args:
            message_id: Persisted message UUID associated with a background run.

        Returns:
            Parsed server response with field names preserved.

        Raises:
            APIStatusError: Server rejected authentication, permissions, or input.
            APIConnectionError: Network failure; no automatic retry occurs.
        """
        return self._client._request(
            "GET",
            self._path + f"monitoring/division-operations/background-runs/by-message/{message_id}/",
        )
