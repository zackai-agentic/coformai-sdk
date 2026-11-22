# REST and MCP integration uploads

Integration management requires `integrations:write`. Reading specifications,
endpoints, tools, and catalogs requires `integrations:read`; deletion requires
`integrations:delete`. Creating an Agentic Function wrapper around a tool also
requires `functions:write` and integration read.

## Upload an OpenAPI specification

```python
from coformai import Coform

with Coform() as client:
    integration = client.uploads.rest("service.openapi.yaml", name="Accounts",
        base_url="https://accounts.example", trust_url=False)
    print(integration)
```

`rest()` opens the file, posts multipart form data with `file`, `name`, `client`,
`base_url`, and `trust_url`, then closes the handle. The dashboard parses
OpenAPI/Swagger JSON or YAML and creates endpoint definitions. Backend validation
determines supported formats; UI file-extension filters are not a parser guarantee.

When a name already exists, `update=True` replaces its definitions and
`update=False` creates another integration. The default None leaves the dashboard's
name-conflict response intact. The upload response describes the specification
record; read `client.catalogs.integrations()` to find the integration and its
endpoint IDs after upload.

For an in-memory specification:

```python
with Coform() as client:
    integration = client.uploads.openapi_string(openapi_document)
```

The string endpoint expects `{"openapi_string": "..."}` and returns the catalog
representation. Preserve server field names, including `api_integration_id`
where that endpoint uses it.

## MCP configuration and raw JSON

```python
config = {"servers": {"search": {
    "url": "https://tools.example/mcp", "type": "apiKey",
    "headers": {"X-API-Key": provider_key},
}}}
with Coform() as client:
    result = client.uploads.mcp("Search", "Search tools", config)
    print(result)
```

Pass a JSON string instead of a mapping for the dashboard's raw-JSON workflow.
The SDK parses it locally, then sends `name`, `description`, and
`json_configuration` to `/clients/{org}/mcp/`. Configuration uses `servers` and
the server's supported auth types: `none`, `http`, `apiKey`, `oauth2`, or `s2s-jwt`.
Optional `mcp_oauth` values support provider OAuth configuration. Headers and
provider credentials are transmitted to the dashboard; supply them through
environment variables in runnable scripts.

The dashboard contacts configured MCP servers to discover tools. OAuth providers
may return start/authorization links and pending status until a user completes
provider interaction. The SDK returns those response fields unchanged. Open the
returned provider link in a browser; the SDK does not automate consent.

## Inspect, edit, and refresh

```python
tools = client.integration_functions(integration_id).list()
parameters = client.integration_parameters(integration_id, endpoint_id).list()
client.integrations.update(integration_id, description="Updated description")
client.integrations.refresh_tools(integration_id)
oauth = client.request("POST",
    f"clients/{client.configuration.organization_id}/api-integrations/{integration_id}/oauth/start/",
    json={})
```

Use nested factories for endpoint/tool and parameter CRUD. Refresh/discovery
contacts an external service. Provider errors and pending authorization remain
server responses; no request is automatically repeated. Integration duplicate
copies definitions under the same organization. Managed integrations preserve
their dashboard restrictions. Model and source catalogs are available through
`client.catalogs`.

```python
hosted = client.catalogs.hosted_models()
connected = client.catalogs.connected_models()
capabilities = client.catalogs.model_capabilities()
sources = client.catalogs.sources()
source_previews = client.catalogs.source_content(n=200)
```

Content preview requires `n`, the maximum number of content characters to return
per source. Model reads require `agents:read`; source reads require `knowledge:read`.

## Upload a Knowledge Base source

```python
source = client.sources.upload(
    "billing-policy.txt",
    name="Billing Policy",
    description="Approved demonstration billing rules",
    enable_semantic_retrieval=True,
    embedding_model_connection_id=embedding_connection_id,
    max_tokens_in_chunk=512,
)
status = client.sources.get(source["source_id"])
```

The upload uses multipart `file`, `name`, organization `client`, and source metadata on the organization's
`sources/` route. It requires `knowledge:write`. Extraction and indexing are
asynchronous: poll the returned source ID for `status="completed"` or `"failed"`
before attaching it to a Division. The SDK never sets a successful processing
status, retries a POST, or polls automatically. Disable semantic retrieval for
compact static context; embedding and chunk fields are then omitted. The server
determines supported file types and embedding-model availability. AsyncCoform
provides the same method with local file reading off the event loop.

Pass `source_id=existing_source_id` to replace an existing source's file with a
multipart PATCH while preserving graph references. The same `name` and semantic
retrieval options apply; omitted metadata fields remain under server control.
The current ingestion backend also requires an active embedding model configured
for the organization before processing semantic sources. Per-source metadata does
not configure that organization setting. Configure it in Knowledge Base first.

REST specification replacement can remove endpoint/parameter definitions and
therefore requires `integrations:delete` for those removals. Existing wrappers
or agents whose endpoint references are cleared also require their write grants.
