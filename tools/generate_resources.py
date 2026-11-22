"""Generate documented sync/async endpoint wrappers from one contract inventory.

Run from the repository root: python tools/generate_resources.py. The generated
files are checked in, editable, and used by mkdocstrings; no runtime code generation
or dependency on dashboard source is required.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
COMMON = '''"""{mode} dashboard resource methods, generated from tools/generate_resources.py.

Resource payloads preserve dashboard serializer fields without renaming them.
Refer to the operation matrix for exact endpoints and required permissions.
Every method raises the documented SDK HTTP/transport errors. No request is
automatically retried. Async methods are awaited; local resource factories and
invocation streams remain synchronous factories.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Iterator, AsyncIterator, Mapping
from pathlib import Path
import json
from uuid import UUID
from pydantic import BaseModel
from .graph import GraphMutationBuilder, GraphMutationRequest
from .models import HistoryPair, InputItem, StreamMode
from .streaming import {stream}
if TYPE_CHECKING:
    from .client import {client}

def _payload(data: Mapping[str, Any] | None, fields: dict[str, Any]) -> dict[str, Any]:
    overlap = set(data or {{}}) & set(fields)
    if overlap:
        raise ValueError("Duplicate payload fields: " + ", ".join(sorted(overlap)))
    return {{**(data or {{}}), **fields}}

def _wire(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {{key: _wire(item) for key, item in value.items()}}
    return value

class {prefix}Resource:
    """Organization-scoped resource base initialized by a client.

    Args:
        client: Owning Coform transport.
        path: Dashboard-relative resource path; includes the organization when required.
    """
    def __init__(self, client: {client}, path: str) -> None:
        """Bind an existing client and endpoint without making a request."""
        self._client, self._path = client, path.rstrip("/") + "/"

    def _detail(self, resource_id: str, suffix: str = "") -> str:
        from urllib.parse import quote
        return self._path + quote(str(resource_id), safe="") + "/" + suffix

class {prefix}CRUDResource({prefix}Resource):
    """Reusable CRUD methods using each resource's read/write/delete permission family."""
'''

METHODS = {
    "list": ("self, **query: Any", "Any", 'self._client._request("GET", self._path, params=query)',
             "List resources. Query parameters are forwarded, including pagination/filter fields. Requires read.", ""),
    "get": ("self, resource_id: str", "Any", 'self._client._request("GET", self._detail(resource_id))',
            "Retrieve a resource by its server ID. Requires read; inaccessible IDs return 404.", ""),
    "create": ("self, data: Mapping[str, Any] | None = None, **fields: Any", "Any",
               'self._client._request("POST", self._path, json=_payload(data, fields))',
               "Create a resource from serializer fields. Requires write; returns the server object.", ""),
    "update": ("self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any", "Any",
               'self._client._request("PATCH", self._detail(resource_id), json=_payload(data, fields))',
               "Partially update a resource. Omitted fields remain unchanged; explicit nulls are preserved. Requires write.", ""),
    "replace": ("self, resource_id: str, data: Mapping[str, Any] | None = None, **fields: Any", "Any",
                'self._client._request("PUT", self._detail(resource_id), json=_payload(data, fields))',
                "Replace a resource using its full serializer payload. Requires write.", ""),
    "delete": ("self, resource_id: str", "Any", 'self._client._request("DELETE", self._detail(resource_id))',
               "Permanently delete a resource. Requires delete; a 204 response returns None. Use graph detach for map removal.", ""),
}

CLASSES = {
    "DivisionResource": ("CRUDResource", {
        "map": ("GET", "map/", "agents:read", "Read the full saved Division graph, including its revision."),
        "profile": ("GET", "profile/", "agents:read", "Read the Division profile and type-specific settings."),
        "summary": ("GET", "summary/", "agents:read", "Read the graph summary."),
        "session_parameters": ("GET", "session-parameters/", "agents:read", "Read required and optional session parameter definitions."),
        "deployability": ("GET", "deployability/", "agents:read", "Read saved deployment blockers."),
        "deploy": ("POST", "deploy/", "agents:write", "Deploy after the dashboard readiness check; downstream failures are reported."),
        "undeploy": ("POST", "undeploy/", "agents:write", "Undeploy and stop runtime availability."),
        "duplicate": ("POST", "duplicate/", "agents:write", "Duplicate a Division; additional grants apply to cloned/reused resources."),
        "schedule_preview": ("POST", "schedule-preview/", "agents:read", "Preview schedule occurrences without saving schedule settings."),
        "trigger": ("POST", "trigger/", "inference:execute", "Trigger dashboard automation. Prefer core invocations for event streaming."),
        "scheduled_input_status": ("GET", "scheduled-input-files/status/", "agents:write", "Read scheduled-file extraction status under schedule-management permission."),
        "transfer_export": ("GET", "transfer-export/", "agents:read", "Export a credential-free Division package."),
        "transfer_status": ("GET", "transfer-status/", "agents:read", "Read imported credentials and external dependency requirements."),
        "transfer_backup": ("GET", "transfer-backup/", "agents:read", "Retrieve the server-held transfer backup."),
        "transfer_resolve": ("POST", "transfer-resolve/", "agents:write", "Resolve imported source mappings and acknowledged dependencies."),
        "deployability_preview": ("POST", "deployability-preview/", "agents:read", "Validate an unsaved Division readiness payload.", False),
        "compose": ("POST", "compose/", "agents:write", "Compose a Division and nested entities; each created resource requires its own write grant.", False),
        "import_preview": ("POST", "import-preview/", "agents:write", "Preview an import before apply; preserve digest/revision values for apply.", False),
        "import_apply": ("POST", "import-apply/", "agents:write", "Apply an import with matching preview digests/revisions; additional resource grants apply.", False),
    }),
    "EntityResource": ("CRUDResource", {
        "map": ("GET", "map/", "resource read", "Read an agent or chain graph; supported routes vary by entity type."),
        "profile": ("GET", "profile/", "resource read", "Read an entity profile where the dashboard exposes this route."),
        "summary": ("GET", "summary/", "resource read", "Read an entity summary where this route is supported."),
        "duplicate": ("POST", "duplicate/", "resource write", "Duplicate an agent/function where supported; nested resources require corresponding grants."),
        "steps": ("GET", "steps/", "chains:read", "Retrieve the dedicated Swift Chain step view."),
    }),
    "IntegrationResource": ("CRUDResource", {
        "duplicate": ("POST", "duplicate/", "integrations:write", "Duplicate an integration and its endpoint definitions."),
        "refresh_tools": ("POST", "refresh-tools/", "integrations:write", "Refresh remote MCP tools; this contacts the configured server."),
        "oauth_start": ("POST", "oauth/start/", "integrations:write", "Return an OAuth provider link for browser interaction."),
        "oauth_initiate": ("POST", "oauth/initiate/", "integrations:write", "Initiate the provider authorization flow."),
        "discover_tools": ("POST", "discover-tools/", "integrations:write", "Discover MCP tools after authorization."),
    }),
    "DependencyResource": ("CRUDResource", {
        "manage_dependencies": ("POST", "manage_dependencies/", "chains:write", "Replace specified consumers' dependency on a provider step.", False),
        "remove_dependencies": ("DELETE", "remove_dependencies/", "chains:delete", "Remove specified consumer/provider dependency links.", False),
        "chain_dependencies": ("GET", "chain_dependencies/", "chains:read", "Read step dependency links using chain_id query parameter.", False),
    }),
}

# Type-specific wrappers expose only routes actually mounted by the dashboard.
entity_methods = CLASSES.pop("EntityResource")[1]
CLASSES["AgentResource"] = ("CRUDResource", {k: v for k, v in entity_methods.items() if k != "steps"})
CLASSES["SwiftChainResource"] = ("CRUDResource", {k: v for k, v in entity_methods.items() if k != "duplicate"})
CLASSES["FlowChainResource"] = ("CRUDResource", {"map": entity_methods["map"]})
CLASSES["FunctionResource"] = ("CRUDResource", {"duplicate": entity_methods["duplicate"]})

def method(name, signature, result, expression, summary, before="", asynchronous=False):
    keyword = "async def" if asynchronous else "def"
    prefix = "await " if asynchronous else ""
    write_calls = tuple(f'self._client._request("{verb}"' for verb in ("POST", "PUT", "PATCH", "DELETE"))
    dashboard_write = expression.startswith(write_calls) and 'service="core"' not in expression
    if dashboard_write:
        # A keyword-only transport option must stay outside serializer fields and multipart data.
        args, separator, extra = signature.partition(", **")
        args += ", " if ", *, " in args else ", *, "
        signature = args + "operation_id: str | UUID | None = None" + separator + extra
        expression = expression.removesuffix(")") + ", operation_id=operation_id)"
    doc = summary + "\n\n        Args:\n            "
    parameters = []
    if dashboard_write:
        parameters.append("operation_id: UUID identifying this dashboard write. The client supplies one by default.")
    # Full signatures appear in the generated reference; descriptions cover shared contracts.
    if "resource_id" in signature:
        parameters.append("resource_id: Persisted UUID/ID from a server response.")
    if "data:" in signature:
        parameters.append("data: Optional mapping of writable server fields.")
    if "**fields" in signature:
        parameters.append("fields: Additional fields; duplicate mapping keys are rejected.")
    if "**query" in signature:
        parameters.append("query: Server query parameters; forwarded without renaming.")
    parsed = ast.parse("def f(" + signature + "): pass").body[0].args
    described = {p.split(":")[0] for p in parameters}
    descriptions = {"payload": "Builder, typed request, or raw server payload.", "division_id": "Persisted Division UUID.", "session_id": "Session identifier; None requests a generated session where supported.", "inputs": "Typed multimodal items or corresponding wire mappings.", "entity_response_stream_option": "Response framing mode; defaults to cumulative_stream.", "approved": "Explicit approval decision.", "approval_id": "Approval identifier from the awaiting_approval event.", "session_params": "Session parameter values; defaults to an empty mapping.", "input_inquiry": "Optional text inquiry.", "include_entity_inputs_in_response": "Include entity inputs in events; defaults to False.", "pairs": "History pairs to append.", "agent_id": "Persisted agent UUID.", "needing_id": "Persisted needing UUID."}
    descriptions.update({"path": "Local file to read and transmit; the handle closes after the request.", "name": "Required integration name shown in the dashboard.", "description": "Required integration description shown in the dashboard.", "base_url": "Optional REST base URL override; defaults to None.", "trust_url": "Dashboard URL validation choice; defaults to False.", "update": "Existing-name policy: True replaces, False creates a copy, None retains the dashboard conflict response.", "openapi_string": "Complete OpenAPI/Swagger specification as a JSON or YAML string.", "configuration": "MCP servers mapping or raw JSON string; parsed locally before transmission.", "message_id": "Persisted message UUID associated with a background run."})
    descriptions.update({"source_id": "Existing source UUID to replace its file in place; None creates a source.", "enable_semantic_retrieval": "Enable semantic indexing; defaults to False.", "embedding_model_connection_id": "Organization embedding-model connection UUID; None leaves selection to the server.", "max_tokens_in_chunk": "Positive semantic chunk size; defaults to 1024 and is omitted for nonsemantic sources."})
    for arg in parsed.args + parsed.kwonlyargs:
        if arg.arg != "self" and arg.arg not in described:
            parameters.append(arg.arg + ": " + descriptions.get(arg.arg, "Server field; see the endpoint guide for its contract."))
    doc += "\n            ".join(parameters)
    doc += "\n\n        Returns:\n            " + ("A lazy, single-use invocation stream. Collect for explicit terminal outcomes." if "InvocationStream" in result else "Parsed server response with field names preserved.")
    doc += "\n\n        Raises:\n            APIStatusError: Server rejected authentication, permissions, or input.\n            APIConnectionError: Network failure; no automatic retry occurs."
    if "data:" in signature or "configuration:" in signature:
        doc += "\n            ValueError: Duplicate payload fields or invalid local JSON configuration."
    if "path:" in signature:
        doc += "\n            OSError: The local file could not be read."
    if "InvocationStream" in result:
        doc += "\n            StreamProtocolError: On iteration, the server sends a malformed event."
    return f'    {keyword} {name}({signature}) -> {result}:\n        """{doc}\n        """\n{before}        return {prefix}{expression}\n\n'

def generate(asynchronous=False):
    prefix = "Async" if asynchronous else ""
    client = "AsyncCoform" if asynchronous else "Coform"
    stream = "AsyncInvocationStream" if asynchronous else "InvocationStream"
    code = COMMON.format(mode="Async" if asynchronous else "Sync", prefix=prefix,
                         client=client, stream=stream)
    for name, spec in METHODS.items():
        code += method(name, *spec, asynchronous=asynchronous)
    iterator = "AsyncIterator" if asynchronous else "Iterator"
    awaiter = "await " if asynchronous else ""
    code += f'''    {"async def" if asynchronous else "def"} iter_all(self, **query: Any) -> {iterator}[dict[str, Any]]:
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
            page = {awaiter}self._client._request("GET", path, params=params)
            rows = page.get("results", []) if isinstance(page, dict) else page
            if not isinstance(rows, list):
                raise ValueError("Expected a list or DRF pagination envelope")
            for row in rows:
                yield row
            path = page.get("next") if isinstance(page, dict) else None
            params = {{}}

'''
    code += f'class {prefix}SourceResource({prefix}CRUDResource):\n    """Knowledge Base source CRUD and multipart file ingestion."""\n\n'
    source_before = '''        if not name.strip():
            raise ValueError("Source name must not be blank")
        if enable_semantic_retrieval and max_tokens_in_chunk <= 0:
            raise ValueError("max_tokens_in_chunk must be positive")
        metadata = {"name": name, "enable_semantic_retrieval": str(enable_semantic_retrieval).lower()}
        if description is not None:
            metadata["description"] = description
        if enable_semantic_retrieval:
            metadata["max_tokens_in_chunk"] = str(max_tokens_in_chunk)
            if embedding_model_connection_id is not None:
                metadata["embedding_model_connection"] = embedding_model_connection_id
        file_path = Path(path)
        with file_path.open("rb") as handle:
'''
    source_upload = method("upload", 'self, path: str | Path, *, name: str, source_id: str | None = None, description: str | None = None, enable_semantic_retrieval: bool = False, embedding_model_connection_id: str | None = None, max_tokens_in_chunk: int = 1024', "Any", 'self._client._request("PATCH" if source_id is not None else "POST", self._detail(source_id) if source_id is not None else self._path, data=metadata, files={"file": (file_path.name, handle, "application/octet-stream")})', 'Create a Knowledge Base source or replace an existing source file in place. Requires knowledge:write. Upload starts asynchronous extraction/indexing; poll sources.get(source_id) for completed or failed status. No automatic retry or polling occurs. Embedding and chunk settings are sent only when semantic retrieval is enabled.', asynchronous=asynchronous)
    source_upload = source_upload.replace('        return ', source_before + '            return ')
    source_upload = source_upload.replace('name: Required integration name shown in the dashboard.', 'name: Required Knowledge Base source name shown in the dashboard.')
    source_upload = source_upload.replace('description: Required integration description shown in the dashboard.', 'description: Optional source description; None omits the field.')
    source_upload = source_upload.replace('            OSError:', '            ValueError: Source name is blank or semantic chunk size is not positive.\n            OSError:')
    code += source_upload
    code += f'class {prefix}OperationsSourceResource({prefix}Resource):\n    """Operations sources: list/create collection, patch/delete detail only."""\n\n'
    for name in ["list", "create", "update", "delete"]:
        spec = list(METHODS[name])
        spec[3] += " Monitoring read applies to list; agent write/delete and affected integration grants apply to mutations."
        code += method(name, *spec, asynchronous=asynchronous)
    for cls, (parent, endpoints) in CLASSES.items():
        code += f'class {prefix}{cls}({prefix}{parent}):\n    """{cls.replace("Resource", "")} resource operations. See the operation matrix for supported routes."""\n\n'
        for name, endpoint in endpoints.items():
            verb, route, permission, description = endpoint[:4]
            detail = len(endpoint) < 5 or endpoint[4]
            signature = "self" + (", resource_id: str" if detail else "")
            if verb == "GET":
                signature += ", **query: Any"
                argument = ", params=query"
            else:
                signature += ", data: Mapping[str, Any] | None = None, **fields: Any"
                argument = ", json=_payload(data, fields)"
            path = f'self._detail(resource_id, "{route}")' if detail else f'self._path + "{route}"'
            expression = f'self._client._request("{verb}", {path}{argument})'
            code += method(name, signature, "Any", expression,
                           description + " Requires " + permission + ".", asynchronous=asynchronous)
    # Explicit local/non-resource endpoints use the same request transport.
    code += f'class {prefix}GraphResource({prefix}Resource):\n    """Atomic graph validation/commit endpoints; every affected resource is authorized."""\n\n'
    for name in ["validate", "commit"]:
        before = '        if isinstance(payload, GraphMutationBuilder):\n            payload = payload.build()\n        data = _wire(payload)\n        key = data.get("request_id")\n'
        code += method(name, "self, payload: GraphMutationBuilder | GraphMutationRequest | Mapping[str, Any]", "Any",
                       f'self._client._request("POST", self._path + "{name}/", json=data, headers={{"Idempotency-Key": key}} if key else {{}})',
                       f'{name.title()} a graph request. IDs/revisions are correlation fields, not automatic retry guarantees.',
                       before, asynchronous)
    code += f'class {prefix}SettingsResource({prefix}Resource):\n    """Division share/embed settings; GET and mutations require agents:write."""\n\n'
    settings_methods = {"get": "GET", "create": "POST", "update": "PATCH"}
    for name, verb in settings_methods.items():
        signature = "self, division_id: str, **fields: Any"
        expression = f'self._client._request("{verb}", self._detail(division_id), ' + ("params=fields)" if verb == "GET" else "json=fields)")
        # Settings paths use a template rather than the CRUD path's ID suffix.
        expression = expression.replace("self._detail(division_id)", "self._path.format(division_id=division_id)")
        code += method(name, signature, "Any", expression, f'{name.title()} share/embed configuration. Requires agents:write.', asynchronous=asynchronous)
    for settings, actions in {"Embed": {"rotate_token": "rotate-token/", "enable": "enable/", "disable": "disable/"}, "Share": {"regenerate": "regenerate/", "revoke": "revoke/"}}.items():
        code += f'class {prefix}{settings}Resource({prefix}SettingsResource):\n    """Division {settings.lower()} management, requiring agents:write."""\n\n'
        for name, route in actions.items():
            code += method(name, "self, division_id: str", "Any", f'self._client._request("POST", self._path.format(division_id=division_id) + "{route}", json={{}})',
                           f'{name.replace("_", " ").title()} the {settings.lower()} token/state. Requires agents:write.', asynchronous=asynchronous)
    code += f'class {prefix}NeedingsResource({prefix}Resource):\n    """Division readiness needings and their lifecycle."""\n\n'
    code += method("list", "self, division_id: str", "Any", 'self._client._request("GET", f"divisions/{division_id}/needings")', "List Division needings. Requires agents:read.", asynchronous=asynchronous)
    code += method("sync", "self, division_id: str, data: Mapping[str, Any]", "Any", 'self._client._request("POST", f"divisions/{division_id}/needings/sync", json=dict(data))', "Sync needings. Requires agents:write.", asynchronous=asynchronous)
    for name in ["discard", "satisfy", "reopen"]:
        code += method(name, "self, division_id: str, needing_id: str", "Any", f'self._client._request("PATCH", f"divisions/{{division_id}}/needings/{{needing_id}}/{name}", json={{}})', f'{name.title()} a needing. Requires agents:write.', asynchronous=asynchronous)
    code += f'class {prefix}SessionResource({prefix}Resource):\n    """Core session operations, all requiring inference:execute."""\n\n'
    code += method("create", 'self, division_id: str, *, session_id: str | None = None, session_params: Mapping[str, Any] | None = None', "Any", 'self._client._request("POST", "create_session", service="core", json={"division_id": division_id, "session_id": session_id, "session_params": dict(session_params or {})})', "Create a session bound to a Division. Always send all three required fields; null requests a generated ID.", asynchronous=asynchronous)
    code += method("status", "self, session_id: str, division_id: str", "Any", 'self._client._request("GET", "session_status", service="core", params={"session_id": session_id, "division_id": division_id})', "Read bound session status; reconcile interrupted streams before replaying.", asynchronous=asynchronous)
    code += method("add_agent_history", "self, session_id: str, division_id: str, agent_id: str, pairs: list[HistoryPair | Mapping[str, Any]]", "Any", 'self._client._request("POST", "add_agent_history", service="core", json=_wire({"session_id": session_id, "division_id": division_id, "agent_id": agent_id, "pairs": pairs}))', "Append input/output history pairs to an existing bound agent session.", asynchronous=asynchronous)
    code += f'class {prefix}InvocationResource({prefix}Resource):\n    """Core execution streams, requiring inference:execute and Division access."""\n\n'
    for name in ["process_inquiry", "trigger_automation", "continue_agent_loop"]:
        if name == "continue_agent_loop":
            signature = 'self, session_id: str, division_id: str, approval_id: str, approved: bool, *, session_params: Mapping[str, Any] | None = None, entity_response_stream_option: StreamMode = "cumulative_stream", include_entity_inputs_in_response: bool = False'
            fields = '"session_id": session_id, "approval_id": approval_id, "approved": approved, '
        else:
            signature = 'self, division_id: str, *, session_id: str' + (' | None = None' if name == "trigger_automation" else '') + ', input_inquiry: str | None = None, inputs: list[InputItem | Mapping[str, Any]] | None = None, session_params: Mapping[str, Any] | None = None, entity_response_stream_option: StreamMode = "cumulative_stream", include_entity_inputs_in_response: bool = False'
            fields = '"session_id": session_id, "input_inquiry": input_inquiry, "inputs": inputs, '
        body = '{' + fields + '"division_id": division_id, "session_params": dict(session_params or {}), "entity_response_stream_option": entity_response_stream_option, "include_entity_inputs_in_response": include_entity_inputs_in_response}'
        # Stream factories are deliberately synchronous on both clients.
        code += method(name, signature, stream, f'self._client._stream("{name}", _wire({body}), entity_response_stream_option)', f'Start {name.replace("_", " ")} on iteration/context entry. All modes return NDJSON. Use with/async with for early closure; collect returns explicit outcomes.', asynchronous=False)
    code += f'class {prefix}UploadResource({prefix}Resource):\n    """Integration and scheduled-input uploads. File handles close after each request."""\n\n'
    before = '        file_path = Path(path)\n        with file_path.open("rb") as handle:\n'
    upload = method("rest", 'self, path: str | Path, *, name: str, base_url: str | None = None, trust_url: bool = False, update: bool | None = None', "Any", 'self._client._request("POST", self._path + "unstructured-data/", data={"name": name, "client": self._client.configuration.organization_id, "base_url": base_url or "", "trust_url": str(trust_url).lower(), **({"update": str(update).lower()} if update is not None else {})}, files={"file": (file_path.name, handle, "application/octet-stream")})', 'Upload an OpenAPI/Swagger specification as multipart. Requires integrations:write and delete for removed definitions. Server validation controls supported formats.', asynchronous=asynchronous)
    code += upload.replace('        return ', before + '            return ')
    code += method("openapi_string", 'self, openapi_string: str', "Any", 'self._client._request("POST", self._path + "integrations/openapi-string/", json={"openapi_string": openapi_string})', 'Import an OpenAPI string. Requires integrations:write.', asynchronous=asynchronous)
    code += method("mcp", 'self, name: str, description: str, configuration: Mapping[str, Any] | str', "Any", 'self._client._request("POST", self._path + "mcp/", json={"name": name, "description": description, "json_configuration": config})', 'Upload MCP servers configuration or raw JSON. Requires integrations:write. OAuth start links are returned for user interaction.', '        config = json.loads(configuration) if isinstance(configuration, str) else dict(configuration)\n', asynchronous)
    upload = method("scheduled_input", 'self, division_id: str, path: str | Path, **fields: Any', "Any", 'self._client._request("POST", self._path + f"divisions/{division_id}/scheduled-input-files/", data=fields, files={"file": (file_path.name, handle, "application/octet-stream")})', 'Upload a scheduled input file for extraction. Requires agents:write.', asynchronous=asynchronous)
    code += upload.replace('        return ', before + '            return ')
    code += method("clear_scheduled_inputs", 'self, division_id: str', "Any", 'self._client._request("POST", self._path + f"divisions/{division_id}/scheduled-input-files/", json={})', 'Clear the entire scheduled input file collection. Requires agents:write.', asynchronous=asynchronous)
    for cls, entries in {"CatalogResource": {"sources": ("sources/catalog/", "knowledge:read"), "source_content": ("sources/catalog/content-preview/", "knowledge:read"), "integrations": ("integrations/catalog/", "integrations:read"), "integration_overview": ("integrations/overview/", "integrations:read"), "connected_models": ("connected-models/", "agents:read"), "model_capabilities": ("model-capabilities/catalog/", "agents:read")}, "MonitoringResource": {"messages": ("monitoring/", "monitoring:read"), "schedules": ("monitoring/division-operations/schedules/", "monitoring:read"), "background_runs": ("monitoring/division-operations/background-runs/", "monitoring:read"), "work_items": ("monitoring/division-operations/work-items/", "monitoring:read"), "sources": ("monitoring/division-operations/sources/", "monitoring:read")}}.items():
        code += f'class {prefix}{cls}({prefix}Resource):\n    """Read organization catalogs or dashboard monitoring."""\n\n'
        for name, (route, permission) in entries.items():
            code += method(name, "self, **query: Any", "Any", f'self._client._request("GET", self._path + "{route}", params=query)', f'Retrieve {name.replace("_", " ")}. Requires {permission}.', asynchronous=asynchronous)
    code = code.replace('self._path + "monitoring/"', 'self._path.replace("clients/", "client/", 1) + "monitoring/"')
    # Hosted model definitions are global; connected-model catalogs remain scoped.
    catalog_marker = f'class {prefix}MonitoringResource'
    hosted = method("hosted_models", "self, **query: Any", "Any", 'self._client._request("GET", "hosted-models/catalog/", params=query)', 'Read available hosted models and their capabilities. Requires agents:read.', asynchronous=asynchronous)
    code = code.replace(catalog_marker, hosted + catalog_marker)
    # Work item queries and source health refresh use POST with monitoring read,
    # despite POST usually representing mutation elsewhere in the dashboard.
    code = code.replace('"GET", self._path + "monitoring/division-operations/work-items/", params=query', '"POST", self._path + "monitoring/division-operations/work-items/", json=query')
    code += method("refresh_sources", "self, **fields: Any", "Any", 'self._client._request("POST", self._path + "monitoring/division-operations/sources/", json=fields)', 'Query source health with an explicit refresh. Requires monitoring:read.', asynchronous=asynchronous)
    code += method("background_run_by_message", "self, message_id: str", "Any", 'self._client._request("GET", self._path + f"monitoring/division-operations/background-runs/by-message/{message_id}/")', 'Read a background run linked to a message. Requires monitoring:read.', asynchronous=asynchronous)
    if asynchronous:
        code = code.replace("import json\n", "import json\nimport asyncio\n")
        code = code.replace('        with file_path.open("rb") as handle:\n            return await ', '        # Read disk off the event loop; HTTPX multipart accepts the resulting bytes.\n        handle = await asyncio.to_thread(file_path.read_bytes)\n        return await ')
    return code

if __name__ == "__main__":
    for asynchronous, name in [(False, "resources.py"), (True, "async_resources.py")]:
        (ROOT / "src" / "coformai" / name).write_text(generate(asynchronous), encoding="utf-8")
