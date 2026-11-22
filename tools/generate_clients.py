"""Generate matching transport clients. Run after generate_resources.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def generate(async_mode: bool) -> str:
    name = "AsyncCoform" if async_mode else "Coform"
    resource_module = "async_resources" if async_mode else "resources"
    prefix = "Async" if async_mode else ""
    keyword = "async def" if async_mode else "def"
    wait = "await " if async_mode else ""
    code = f'''class {name}:
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
    def __init__(self, *, api_key: str | None = None, organization_id: str | None = None,
                 dashboard_url: str | None = None, core_url: str | None = None,
                 timeout: float = 60.0,
                 transport: httpx.{"AsyncBaseTransport" if async_mode else "BaseTransport"} | None = None) -> None:
        """Resolve configuration and create a transport; no requests occur here."""
        from . import {resource_module} as r
        self.configuration = Configuration.resolve(api_key=api_key, organization_id=organization_id,
            dashboard_base_url=dashboard_url, core_base_url=core_url, timeout=timeout)
        self._http = httpx.{"AsyncClient" if async_mode else "Client"}(headers={{
            "Authorization": "Bearer " + self.configuration.api_key,
            "User-Agent": "coformai-python/0.1.0", "Accept": "application/json"}},
            timeout=timeout, transport=transport, follow_redirects=False)
        self._org = "clients/" + quote(self.configuration.organization_id, safe="") + "/"
'''
    resources = {"divisions": ("DivisionResource", "divisions"), "swift_agents": ("EntityResource", "swift-agents"), "flow_agents": ("EntityResource", "flow-agents"), "swift_chains": ("EntityResource", "swift-chains"), "flow_chains": ("EntityResource", "flow-chains"), "agentic_functions": ("EntityResource", "agentic-functions"), "sources": ("CRUDResource", "sources"), "model_connections": ("CRUDResource", "models-connection"), "schedules": ("CRUDResource", "division-triggers"), "swift_chain_steps": ("CRUDResource", "swift-chain-steps"), "flow_chain_steps": ("CRUDResource", "flow-chain-steps"), "dependencies": ("CRUDResource", "swift-chain-dependencies"), "integrations": ("IntegrationResource", "api-integrations"), "graph": ("GraphResource", "graph-mutations"), "uploads": ("UploadResource", ""), "catalogs": ("CatalogResource", ""), "monitoring": ("MonitoringResource", "")}
    for attr, cls in {"swift_agents": "AgentResource", "flow_agents": "AgentResource", "swift_chains": "SwiftChainResource", "flow_chains": "FlowChainResource", "agentic_functions": "FunctionResource", "dependencies": "DependencyResource"}.items():
        resources[attr] = (cls, resources[attr][1])
    resources["sources"] = ("SourceResource", "sources")
    for attr, (cls, path) in resources.items():
        code += f'        self.{attr} = r.{prefix}{cls}(self, self._org + "{path}")\n'
    for attr, path in {"actions": "actions", "static_augmentations": "static-augmentations", "dynamic_augmentations": "dynamic-augmentations"}.items():
        code += f'        self.{attr} = r.{prefix}CRUDResource(self, "{path}")\n'
    for attr, cls in {"sessions": "SessionResource", "invocations": "InvocationResource", "needings": "NeedingsResource"}.items():
        code += f'        self.{attr} = r.{prefix}{cls}(self, "")\n'
    for attr in ["share", "embed"]:
        code += f'        self.{attr} = r.{prefix}{attr.title()}Resource(self, self._org + "divisions/{{division_id}}/{attr}/")\n'
    for method, route in {"integration_functions": "api-integrations/{integration_id}/api-integration-functions", "integration_parameters": "api-integrations/{integration_id}/api-integration-functions/{function_id}/api-function-parameters", "function_parameters": "agentic-functions/{function_id}/agentic-function-parameters", "operations_sources": "divisions/{division_id}/operations-sources"}.items():
        args = ("integration_id: str, " if "integration_id" in route else "") + ("function_id: str" if "function_id" in route else "")
        args = args.rstrip(", ")
        if method == "operations_sources":
            args = "division_id: str"
        safe_route = route.replace("{integration_id}", '{quote(integration_id, safe="")}').replace("{function_id}", '{quote(function_id, safe="")}').replace("{division_id}", '{quote(division_id, safe="")}')
        cls = "OperationsSourceResource" if method == "operations_sources" else "CRUDResource"
        code += f'''\n    def {method}(self, {args}) -> {resource_module}.{prefix}{cls}:
        """Bind a nested parameter/endpoint resource without issuing requests.

        Args:
            {"division_id: Persisted Division UUID." if method == "operations_sources" else "integration_id: Persisted integration UUID." if "integration_id" in route else "function_id: Persisted function UUID."}
            {"function_id: Persisted endpoint UUID." if method == "integration_parameters" else ""}

        Returns:
            {"Operations-source resource with monitoring read and agent/integration mutation grants." if cls == "OperationsSourceResource" else "CRUD resource requiring its integrations or functions permission family."}
        """
        from .{resource_module} import {prefix}{cls}
        return {prefix}{cls}(self, self._org + f'{safe_route}')
'''
    code += f'''
    {keyword} request(self, method: str, path: str, *, service: str = "dashboard",
                      json: Any = None, params: Mapping[str, Any] | None = None,
                      operation_id: str | UUID | None = None) -> Any:
        """Make an explicit request for a server route not covered by a convenience method.

        Args:
            method: HTTP verb.
            path: Relative path or absolute URL inside the configured API root.
            service: dashboard (default) or core.
            json: JSON payload; defaults to None.
            params: Query parameters; defaults to None.
            operation_id: Optional UUID identifying one dashboard write.

        Returns:
            Parsed JSON, text for non-JSON responses, or None for HTTP 204.

        Raises:
            APIStatusError: Server rejection, including missing selected permissions.
            APIConnectionError: Transport failure. No request is retried.
            ValueError: A URL escapes the configured service root.
        """
        return {wait}self._request(method, path, service=service, json=json, params=params, operation_id=operation_id)

    {keyword} get_operation(self, operation_id: str | UUID) -> Any:
        """Read the dashboard receipt for an operation in this organization.

        Args:
            operation_id: UUID from a managed write or an interrupted request.

        Returns:
            The current receipt, including phase, resource_id and error_code.
        """
        return {wait}self._request("GET", self._org + f"operations/{{UUID(str(operation_id))}}/")

    {keyword} reconcile_operation(self, operation_id: str | UUID) -> Any:
        """Ask the dashboard to reconcile a deployment or continue a supported source batch.

        Args:
            operation_id: UUID from the original receipt. The server checks the caller's grants.

        Returns:
            The updated receipt. A pending phase may need another status check.
        """
        identifier = UUID(str(operation_id))
        return {wait}self._request("POST", self._org + f"operations/{{identifier}}/", operation_id=identifier)

    {keyword} _request(self, method: str, path: str, *, service: str = "dashboard",
                       operation_id: str | UUID | None = None, **kwargs: Any) -> Any:
        url = self.configuration.url(service, path)
        identifier = _operation_id(service, method, url, kwargs.get("json"), operation_id, self.configuration.organization_id)
        if identifier is not None:
            kwargs["headers"] = {{**kwargs.get("headers", {{}}), "X-Operation-ID": identifier}}
        try:
            response = {wait}self._http.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise APITimeoutError("Request timed out; reconcile state before retrying", operation_id=identifier) from exc
        except httpx.RequestError as exc:
            raise APIConnectionError("Request failed; reconcile state before retrying", operation_id=identifier) from exc
        check_status(response, operation_id=identifier)
        if response.status_code == 204 or not response.content:
            return None
        if "json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def _stream(self, path: str, payload: dict[str, Any], mode: StreamMode) -> {prefix}InvocationStream:
        return {prefix}InvocationStream(self._http, self.configuration.url("core", path), payload,
            mode, httpx.Timeout(self.configuration.timeout, read=None))

    {keyword} {"aclose" if async_mode else "close"}(self) -> None:
        """Close the owned HTTP transport and idle connections."""
        {wait}self._http.{"aclose" if async_mode else "close"}()

    {keyword} {"__aenter__" if async_mode else "__enter__"}(self) -> {name}:
        """Enter the client context and return this client."""
        return self

    {keyword} {"__aexit__" if async_mode else "__exit__"}(self, *exc: Any) -> None:
        """Close transport when leaving the context, including on exceptions."""
        {wait}self.{"aclose" if async_mode else "close"}()
'''
    return code

if __name__ == "__main__":
    header = '''"""HTTPX clients for dashboard management and mounted core execution routes."""
from __future__ import annotations
from typing import Any, Mapping
from urllib.parse import quote, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
import httpx
from . import resources, async_resources
from .config import Configuration
from .errors import APIConnectionError, APITimeoutError, check_status
from .models import StreamMode
from .streaming import InvocationStream, AsyncInvocationStream


def _operation_id(service: str, method: str, url: str, payload: Any,
                  explicit: str | UUID | None, organization_id: str) -> str | None:
    if service != "dashboard" or method.upper() not in {"POST", "PATCH", "PUT", "DELETE"}:
        if explicit is not None:
            raise ValueError("operation_id applies only to dashboard writes")
        return None
    if explicit is not None:
        return str(UUID(str(explicit)))
    if urlsplit(url).path.rstrip("/").endswith("/graph-mutations/commit") and isinstance(payload, Mapping):
        correlation = payload.get("request_id")
        if isinstance(correlation, str) and correlation:
            try:
                return str(UUID(correlation))
            except ValueError:
                # Older graph clients also use text correlation IDs.
                return str(uuid5(NAMESPACE_URL, f"coformai/{organization_id}/graph/{correlation}"))
    return str(uuid4())

'''
    (ROOT / "src/coformai/client.py").write_text(header + generate(False) + "\n" + generate(True), encoding="utf-8")
