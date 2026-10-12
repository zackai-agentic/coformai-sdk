"""HTTPX clients for dashboard management and mounted core execution routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from . import async_resources, resources
from .config import Configuration
from .errors import APIConnectionError, APITimeoutError, check_status
from .models import StreamMode
from .streaming import AsyncInvocationStream, InvocationStream


class Coform:
    """Authenticated SDK client with organization-scoped dashboard resources.

    Args:
        api_key: Dashboard key; defaults to COFORM_API_KEY.
        organization_id: Organization UUID; defaults to COFORM_ORGANIZATION_ID.
        dashboard_url: API root including /api/; defaults to COFORM_DASHBOARD_URL.
        core_url: Mounted core API root; defaults to COFORM_CORE_URL.
        timeout: Request timeout seconds, default 60. Streaming reads have no timeout.
        transport: Optional HTTPX transport, useful for isolated contract tests.

    Raises:
        ValueError: Missing configuration or an unsafe API root.

    Example:
        Use a context manager: ``with Coform() as client: client.divisions.list()``.
        For AsyncCoform use ``async with`` and await resource methods.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        organization_id: str | None = None,
        dashboard_url: str | None = None,
        core_url: str | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Resolve configuration and create a transport; no requests occur here."""
        from . import resources as r

        self.configuration = Configuration.resolve(
            api_key=api_key,
            organization_id=organization_id,
            dashboard_base_url=dashboard_url,
            core_base_url=core_url,
            timeout=timeout,
        )
        self._http = httpx.Client(
            headers={
                "Authorization": "Bearer " + self.configuration.api_key,
                "User-Agent": "coformai-python/0.1.0",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._org = "clients/" + quote(self.configuration.organization_id, safe="") + "/"
        self.divisions = r.DivisionResource(self, self._org + "divisions")
        self.swift_agents = r.AgentResource(self, self._org + "swift-agents")
        self.flow_agents = r.AgentResource(self, self._org + "flow-agents")
        self.swift_chains = r.SwiftChainResource(self, self._org + "swift-chains")
        self.flow_chains = r.FlowChainResource(self, self._org + "flow-chains")
        self.agentic_functions = r.FunctionResource(self, self._org + "agentic-functions")
        self.sources = r.CRUDResource(self, self._org + "sources")
        self.model_connections = r.CRUDResource(self, self._org + "models-connection")
        self.schedules = r.CRUDResource(self, self._org + "division-triggers")
        self.swift_chain_steps = r.CRUDResource(self, self._org + "swift-chain-steps")
        self.flow_chain_steps = r.CRUDResource(self, self._org + "flow-chain-steps")
        self.dependencies = r.DependencyResource(self, self._org + "swift-chain-dependencies")
        self.integrations = r.IntegrationResource(self, self._org + "api-integrations")
        self.graph = r.GraphResource(self, self._org + "graph-mutations")
        self.uploads = r.UploadResource(self, self._org + "")
        self.catalogs = r.CatalogResource(self, self._org + "")
        self.monitoring = r.MonitoringResource(self, self._org + "")
        self.actions = r.CRUDResource(self, "actions")
        self.static_augmentations = r.CRUDResource(self, "static-augmentations")
        self.dynamic_augmentations = r.CRUDResource(self, "dynamic-augmentations")
        self.sessions = r.SessionResource(self, "")
        self.invocations = r.InvocationResource(self, "")
        self.needings = r.NeedingsResource(self, "")
        self.share = r.ShareResource(self, self._org + "divisions/{division_id}/share/")
        self.embed = r.EmbedResource(self, self._org + "divisions/{division_id}/embed/")

    def integration_functions(self, integration_id: str) -> resources.CRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            integration_id: Persisted integration UUID.


        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .resources import CRUDResource

        return CRUDResource(
            self,
            self._org
            + f"api-integrations/{quote(integration_id, safe='')}/api-integration-functions",
        )

    def integration_parameters(
        self, integration_id: str, function_id: str
    ) -> resources.CRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            integration_id: Persisted integration UUID.
            function_id: Persisted endpoint UUID.

        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .resources import CRUDResource

        return CRUDResource(
            self,
            self._org
            + f"api-integrations/{quote(integration_id, safe='')}/api-integration-functions/{quote(function_id, safe='')}/api-function-parameters",
        )

    def function_parameters(self, function_id: str) -> resources.CRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            function_id: Persisted function UUID.


        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .resources import CRUDResource

        return CRUDResource(
            self,
            self._org
            + f"agentic-functions/{quote(function_id, safe='')}/agentic-function-parameters",
        )

    def operations_sources(self, division_id: str) -> resources.OperationsSourceResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            division_id: Persisted Division UUID.


        Returns:
            Operations-source resource with monitoring read and agent/integration mutation grants.
        """
        from .resources import OperationsSourceResource

        return OperationsSourceResource(
            self, self._org + f"divisions/{quote(division_id, safe='')}/operations-sources"
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        service: str = "dashboard",
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Make an explicit request for a server route not covered by a convenience method.

        Args:
            method: HTTP verb.
            path: Relative path or absolute URL inside the configured API root.
            service: dashboard (default) or core.
            json: JSON payload; defaults to None.
            params: Query parameters; defaults to None.

        Returns:
            Parsed JSON, text for non-JSON responses, or None for HTTP 204.

        Raises:
            APIStatusError: Server rejection, including missing selected permissions.
            APIConnectionError: Transport failure. No request is retried.
            ValueError: A URL escapes the configured service root.
        """
        return self._request(method, path, service=service, json=json, params=params)

    def _request(self, method: str, path: str, *, service: str = "dashboard", **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, self.configuration.url(service, path), **kwargs)
        except httpx.TimeoutException as exc:
            raise APITimeoutError("Request timed out; reconcile state before retrying") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError("Request failed; reconcile state before retrying") from exc
        check_status(response)
        if response.status_code == 204 or not response.content:
            return None
        if "json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def _stream(self, path: str, payload: dict[str, Any], mode: StreamMode) -> InvocationStream:
        return InvocationStream(
            self._http,
            self.configuration.url("core", path),
            payload,
            mode,
            httpx.Timeout(self.configuration.timeout, read=None),
        )

    def close(self) -> None:
        """Close the owned HTTP transport and idle connections."""
        self._http.close()

    def __enter__(self) -> Coform:
        """Enter the client context and return this client."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Close transport when leaving the context, including on exceptions."""
        self.close()


class AsyncCoform:
    """Authenticated SDK client with organization-scoped dashboard resources.

    Args:
        api_key: Dashboard key; defaults to COFORM_API_KEY.
        organization_id: Organization UUID; defaults to COFORM_ORGANIZATION_ID.
        dashboard_url: API root including /api/; defaults to COFORM_DASHBOARD_URL.
        core_url: Mounted core API root; defaults to COFORM_CORE_URL.
        timeout: Request timeout seconds, default 60. Streaming reads have no timeout.
        transport: Optional HTTPX transport, useful for isolated contract tests.

    Raises:
        ValueError: Missing configuration or an unsafe API root.

    Example:
        Use a context manager: ``with Coform() as client: client.divisions.list()``.
        For AsyncCoform use ``async with`` and await resource methods.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        organization_id: str | None = None,
        dashboard_url: str | None = None,
        core_url: str | None = None,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Resolve configuration and create a transport; no requests occur here."""
        from . import async_resources as r

        self.configuration = Configuration.resolve(
            api_key=api_key,
            organization_id=organization_id,
            dashboard_base_url=dashboard_url,
            core_base_url=core_url,
            timeout=timeout,
        )
        self._http = httpx.AsyncClient(
            headers={
                "Authorization": "Bearer " + self.configuration.api_key,
                "User-Agent": "coformai-python/0.1.0",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._org = "clients/" + quote(self.configuration.organization_id, safe="") + "/"
        self.divisions = r.AsyncDivisionResource(self, self._org + "divisions")
        self.swift_agents = r.AsyncAgentResource(self, self._org + "swift-agents")
        self.flow_agents = r.AsyncAgentResource(self, self._org + "flow-agents")
        self.swift_chains = r.AsyncSwiftChainResource(self, self._org + "swift-chains")
        self.flow_chains = r.AsyncFlowChainResource(self, self._org + "flow-chains")
        self.agentic_functions = r.AsyncFunctionResource(self, self._org + "agentic-functions")
        self.sources = r.AsyncCRUDResource(self, self._org + "sources")
        self.model_connections = r.AsyncCRUDResource(self, self._org + "models-connection")
        self.schedules = r.AsyncCRUDResource(self, self._org + "division-triggers")
        self.swift_chain_steps = r.AsyncCRUDResource(self, self._org + "swift-chain-steps")
        self.flow_chain_steps = r.AsyncCRUDResource(self, self._org + "flow-chain-steps")
        self.dependencies = r.AsyncDependencyResource(self, self._org + "swift-chain-dependencies")
        self.integrations = r.AsyncIntegrationResource(self, self._org + "api-integrations")
        self.graph = r.AsyncGraphResource(self, self._org + "graph-mutations")
        self.uploads = r.AsyncUploadResource(self, self._org + "")
        self.catalogs = r.AsyncCatalogResource(self, self._org + "")
        self.monitoring = r.AsyncMonitoringResource(self, self._org + "")
        self.actions = r.AsyncCRUDResource(self, "actions")
        self.static_augmentations = r.AsyncCRUDResource(self, "static-augmentations")
        self.dynamic_augmentations = r.AsyncCRUDResource(self, "dynamic-augmentations")
        self.sessions = r.AsyncSessionResource(self, "")
        self.invocations = r.AsyncInvocationResource(self, "")
        self.needings = r.AsyncNeedingsResource(self, "")
        self.share = r.AsyncShareResource(self, self._org + "divisions/{division_id}/share/")
        self.embed = r.AsyncEmbedResource(self, self._org + "divisions/{division_id}/embed/")

    def integration_functions(self, integration_id: str) -> async_resources.AsyncCRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            integration_id: Persisted integration UUID.


        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .async_resources import AsyncCRUDResource

        return AsyncCRUDResource(
            self,
            self._org
            + f"api-integrations/{quote(integration_id, safe='')}/api-integration-functions",
        )

    def integration_parameters(
        self, integration_id: str, function_id: str
    ) -> async_resources.AsyncCRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            integration_id: Persisted integration UUID.
            function_id: Persisted endpoint UUID.

        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .async_resources import AsyncCRUDResource

        return AsyncCRUDResource(
            self,
            self._org
            + f"api-integrations/{quote(integration_id, safe='')}/api-integration-functions/{quote(function_id, safe='')}/api-function-parameters",
        )

    def function_parameters(self, function_id: str) -> async_resources.AsyncCRUDResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            function_id: Persisted function UUID.


        Returns:
            CRUD resource requiring its integrations or functions permission family.
        """
        from .async_resources import AsyncCRUDResource

        return AsyncCRUDResource(
            self,
            self._org
            + f"agentic-functions/{quote(function_id, safe='')}/agentic-function-parameters",
        )

    def operations_sources(self, division_id: str) -> async_resources.AsyncOperationsSourceResource:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            division_id: Persisted Division UUID.


        Returns:
            Operations-source resource with monitoring read and agent/integration mutation grants.
        """
        from .async_resources import AsyncOperationsSourceResource

        return AsyncOperationsSourceResource(
            self, self._org + f"divisions/{quote(division_id, safe='')}/operations-sources"
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        service: str = "dashboard",
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Make an explicit request for a server route not covered by a convenience method.

        Args:
            method: HTTP verb.
            path: Relative path or absolute URL inside the configured API root.
            service: dashboard (default) or core.
            json: JSON payload; defaults to None.
            params: Query parameters; defaults to None.

        Returns:
            Parsed JSON, text for non-JSON responses, or None for HTTP 204.

        Raises:
            APIStatusError: Server rejection, including missing selected permissions.
            APIConnectionError: Transport failure. No request is retried.
            ValueError: A URL escapes the configured service root.
        """
        return await self._request(method, path, service=service, json=json, params=params)

    async def _request(
        self, method: str, path: str, *, service: str = "dashboard", **kwargs: Any
    ) -> Any:
        try:
            response = await self._http.request(
                method, self.configuration.url(service, path), **kwargs
            )
        except httpx.TimeoutException as exc:
            raise APITimeoutError("Request timed out; reconcile state before retrying") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError("Request failed; reconcile state before retrying") from exc
        check_status(response)
        if response.status_code == 204 or not response.content:
            return None
        if "json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def _stream(
        self, path: str, payload: dict[str, Any], mode: StreamMode
    ) -> AsyncInvocationStream:
        return AsyncInvocationStream(
            self._http,
            self.configuration.url("core", path),
            payload,
            mode,
            httpx.Timeout(self.configuration.timeout, read=None),
        )

    async def aclose(self) -> None:
        """Close the owned HTTP transport and idle connections."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncCoform:
        """Enter the client context and return this client."""
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Close transport when leaving the context, including on exceptions."""
        await self.aclose()
