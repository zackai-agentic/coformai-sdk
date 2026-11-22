"""Generate coverage and public API reference pages from the SDK inventory."""
from pathlib import Path
from generate_resources import CLASSES

ROOT = Path(__file__).resolve().parents[1]
rows = []

def row(operation, method, endpoint, grant):
    rows.append(f"| {operation} | `{method}` | `{endpoint}` | `{grant}` |")

resources = {
    "divisions": ("divisions", "agents"), "swift_agents": ("swift-agents", "agents"),
    "flow_agents": ("flow-agents", "agents"), "swift_chains": ("swift-chains", "chains"),
    "flow_chains": ("flow-chains", "chains"), "agentic_functions": ("agentic-functions", "functions"),
    "sources": ("sources", "knowledge"), "model_connections": ("models-connection", "agents"),
    "schedules": ("division-triggers", "agents"), "swift_chain_steps": ("swift-chain-steps", "chains"),
    "flow_chain_steps": ("flow-chain-steps", "chains"), "dependencies": ("swift-chain-dependencies", "chains"),
    "integrations": ("api-integrations", "integrations"),
    "actions": ("actions", "agents"), "static_augmentations": ("static-augmentations", "agents"),
    "dynamic_augmentations": ("dynamic-augmentations", "agents"),
    "integration_functions(id)": ("api-integrations/{integration_id}/api-integration-functions", "integrations"),
    "integration_parameters(id, endpoint)": ("api-integrations/{integration_id}/api-integration-functions/{endpoint_id}/api-function-parameters", "integrations"),
    "function_parameters(id)": ("agentic-functions/{function_id}/agentic-function-parameters", "functions"),
}
for attr, (path, family) in resources.items():
    base = path if attr in {"actions", "static_augmentations", "dynamic_augmentations"} else "clients/{org}/" + path
    for method, verb, permission, detail in [("list", "GET", "read", False), ("get", "GET", "read", True), ("create", "POST", "write", False), ("update", "PATCH", "write", True), ("replace", "PUT", "write", True), ("delete", "DELETE", "delete", True)]:
        row(f"{attr} {method}", attr + "." + method, verb + " /" + base + ("/{id}/" if detail else "/"), family + ":" + permission)
    row(f"Paginate {attr}", attr + ".iter_all", "GET /" + base + "/", family + ":read")

class_resources = {"DivisionResource": ["divisions"], "AgentResource": ["swift_agents", "flow_agents"], "SwiftChainResource": ["swift_chains"], "FlowChainResource": ["flow_chains"], "FunctionResource": ["agentic_functions"], "IntegrationResource": ["integrations"], "DependencyResource": ["dependencies"]}
for cls, attrs in class_resources.items():
    for attr in attrs:
        path = resources[attr][0]
        for method, contract in CLASSES[cls][1].items():
            verb, suffix, permission, summary = contract[:4]
            detail = len(contract) < 5 or contract[4]
            row(summary.split(";")[0], attr + "." + method,
                verb + " /clients/{org}/" + path + ("/{id}/" if detail else "/") + suffix,
                permission.replace("resource read", resources[attr][1] + ":read").replace("resource write", resources[attr][1] + ":write"))
for method in ["validate", "commit"]:
    row("Atomic graph " + method, "graph." + method, "POST /clients/{org}/graph-mutations/" + method + "/", "root write + each operation's grants")
for method, route, verb, grant in [
    ("sources.upload", "clients/{org}/sources/", "POST multipart", "knowledge:write"),
    ("sources.upload(source_id=...)", "clients/{org}/sources/{id}/", "PATCH multipart", "knowledge:write"),
    ("uploads.rest", "clients/{org}/unstructured-data/", "POST multipart", "integrations:write"),
    ("uploads.openapi_string", "clients/{org}/integrations/openapi-string/", "POST", "integrations:write"),
    ("uploads.mcp", "clients/{org}/mcp/", "POST", "integrations:write"),
    ("uploads.scheduled_input", "clients/{org}/divisions/{id}/scheduled-input-files/", "POST multipart", "agents:write"),
    ("uploads.clear_scheduled_inputs", "clients/{org}/divisions/{id}/scheduled-input-files/", "POST empty", "agents:write"),
    ("catalogs.sources", "clients/{org}/sources/catalog/", "GET", "knowledge:read"),
    ("catalogs.source_content", "clients/{org}/sources/catalog/content-preview/", "GET", "knowledge:read"),
    ("catalogs.integrations", "clients/{org}/integrations/catalog/", "GET", "integrations:read"),
    ("catalogs.integration_overview", "clients/{org}/integrations/overview/", "GET", "integrations:read"),
    ("catalogs.connected_models", "clients/{org}/connected-models/", "GET", "agents:read"),
    ("catalogs.model_capabilities", "clients/{org}/model-capabilities/catalog/", "GET", "agents:read"),
    ("catalogs.hosted_models", "hosted-models/catalog/", "GET", "agents:read"),
    ("monitoring.messages", "client/{org}/monitoring/", "GET", "monitoring:read"),
    ("monitoring.schedules", "clients/{org}/monitoring/division-operations/schedules/", "GET", "monitoring:read"),
    ("monitoring.background_runs", "clients/{org}/monitoring/division-operations/background-runs/", "GET", "monitoring:read"),
    ("monitoring.background_run_by_message", "clients/{org}/monitoring/division-operations/background-runs/by-message/{message_id}/", "GET", "monitoring:read"),
    ("monitoring.work_items", "clients/{org}/monitoring/division-operations/work-items/", "POST query", "monitoring:read"),
    ("monitoring.sources", "clients/{org}/monitoring/division-operations/sources/", "GET", "monitoring:read + integrations:read"),
    ("monitoring.refresh_sources", "clients/{org}/monitoring/division-operations/sources/", "POST query", "monitoring:read"),
    ("operations_sources(id).list", "clients/{org}/divisions/{id}/operations-sources/", "GET", "monitoring:read"),
    ("operations_sources(id).create/update/delete", "clients/{org}/divisions/{id}/operations-sources/{source_id}/", "POST collection / PATCH or DELETE detail", "agents:write/delete + integrations grant for affected connection"),
    ("needings.list", "divisions/{id}/needings", "GET", "agents:read"),
    ("needings.sync", "divisions/{id}/needings/sync", "POST", "agents:write"),
    ("needings.discard/satisfy/reopen", "divisions/{id}/needings/{needing_id}/{operation}", "PATCH", "agents:write"),
]:
    row(method.replace("_", " "), method, verb + " /" + route, grant)
for settings, actions in {"share": ["regenerate", "revoke"], "embed": ["rotate-token", "enable", "disable"]}.items():
    row(settings + " settings", settings + ".get/create/update", "GET/POST/PATCH /clients/{org}/divisions/{id}/" + settings + "/", "agents:write")
    for action in actions:
        row(action, settings + "." + action.replace("-", "_"), "POST /clients/{org}/divisions/{id}/" + settings + "/" + action + "/", "agents:write")
for method, route, verb in [("sessions.create", "create_session", "POST"), ("sessions.status", "session_status", "GET"), ("sessions.add_agent_history", "add_agent_history", "POST"), ("invocations.process_inquiry", "process_inquiry", "POST NDJSON"), ("invocations.trigger_automation", "trigger_automation", "POST NDJSON"), ("invocations.continue_agent_loop", "continue_agent_loop", "POST NDJSON")]:
    row(method, method, verb + " /" + route, "inference:execute")

header = '''# Operation coverage matrix

Generated by `python tools/generate_docs.py`. Methods are shown relative to
`client`; AsyncCoform exposes matching methods (await HTTP methods, use async
stream iteration). Dashboard routes below are relative to the configured API
root, normally `/api/`. Core routes use the configured core root.

| Operation | Method | Endpoint | Selected grant |
|---|---|---|---|
'''
notes = '''

## Graph operation policies

| Mutation | Builder method | Additional authorization |
|---|---|---|
| Create | `create_entity` | Resource write; nested existing references read |
| Patch | `patch_entity` | Resource write; nested changes and references checked |
| Permanent delete | `delete_entity` | Resource delete, independent of root write |
| Attach | `attach_relation` | Parent write, existing child read |
| Detach occurrence | `detach_relation` | Parent write, existing child read |
| Replace ordered steps | `replace_collection` | Chain write, existing targets/forward functions read |

All graph requests require root write. Preview uses the grants required by the
operation it represents. Import/compose/duplicate need every affected family;
the matrix's primary grant is not a waiver for nested resources. Temporary
children created in the same request require write rather than persisted-child
read. Unmapped operations are denied to ordinary keys. User JWT behavior and the
established system-client exception are retained.

Operations-source collections support list/create; their detail route supports
patch/delete only. Telegram pairing, Octopus generation, public runtime routes,
and unmounted core deployment are excluded. `request()` exposes a scoped escape
hatch for backend routes and does not bypass authorization.

Dependency management requires chain write and referenced-step read. Removing
dependencies additionally requires chain delete. Function parameter patches
upsert rows; delete parameters through their direct resource API. Removing saved
samples through collection replacement requires agents delete.
'''
(ROOT / "docs/coverage.md").write_text(header + "\n".join(rows) + notes, encoding="utf-8")
modules = {"client": "Clients", "config": "Configuration", "graph": "Division graph mutations", "models": "Inputs and invocation models", "streaming": "Closable invocation streams", "errors": "Exceptions", "resources": "Synchronous resources", "async_resources": "Asynchronous resources"}
reference_dir = ROOT / "docs/reference"
reference_dir.mkdir(exist_ok=True)
for name, title in modules.items():
    (reference_dir / (name + ".md")).write_text(f"# {title}\n\n::: coformai.{name}\n", encoding="utf-8")
import coformai
overview = "# Public API reference\n\nThe following exports are available directly from `coformai`. Resource classes\nare initialized by the clients and are documented on their own reference pages.\n\n| Public export | Reference |\n|---|---|\n"
aliases = {"Mutation": "graph", "Outcome": "models", "StreamMode": "models"}
for name in coformai.__all__:
    module = aliases.get(name) or getattr(coformai, name).__module__.split(".")[-1]
    overview += f"| `{name}` | [{modules[module]}](reference/{module}.md) |\n"
overview += "\n" + "\n".join(f"- [{title}](reference/{name}.md)" for name, title in modules.items()) + "\n"
(ROOT / "docs/reference.md").write_text(overview, encoding="utf-8")
