# Lifecycle and Division operations

## Readiness and deployment

```python
division = client.divisions.get(division_id)
graph = client.divisions.map(division_id)
profile = client.divisions.profile(division_id)
summary = client.divisions.summary(division_id)
requirements = client.divisions.session_parameters(division_id)
readiness = client.divisions.deployability(division_id)
preview = client.divisions.deployability_preview(division_name="Draft", division_type="automation")
deployment = client.divisions.deploy(division_id)
if "operation" in deployment:
    receipt = deployment["operation"]
    if receipt["phase"] in {"prepared", "submitting", "pending", "running", "uncertain"}:
        receipt = client.reconcile_operation(receipt["operation_id"])
```

Reads and readiness previews require `agents:read`; deploy/undeploy require
`agents:write`. Deployability blockers are reported with HTTP 422. The dashboard
coordinates runtime and messaging lifecycle. API-key deployment uses a fresh
server-only 60-second JWT per downstream request; the SDK never receives it.

### Managed writes and recovery

Both clients send a fresh `X-Operation-ID` UUID with each dashboard write.
To track a write across a process restart, persist a UUID first and pass it as
`operation_id=` to the mutation. Graph commits reuse the builder's request UUID
by default. The SDK preserves a text graph request ID and derives a stable
operation UUID for it within the organization.

When the dashboard fences a write, the response can contain only an `operation`
receipt. Check its `phase` before starting dependent work. A terminal receipt
reports `succeeded`, `failed`, or `not_started`. For failures inspect
`error_code`. HTTP 202 means the operation still needs a later status check.
Use `client.get_operation(operation_id)` to read the receipt with the relevant
resource read grant. For a pending division deployment or undeployment, use
`reconcile_operation()` with `agents:write` to refresh downstream status.
Both methods are awaitable on `AsyncCoform`.

Timeouts, connection failures, and HTTP errors on dashboard writes expose the
sent UUID as `exc.operation_id`. If the outcome is unclear, look up that UUID
before submitting more work. Each call sends the mutation once. Endpoints that
do not use the managed-write protocol may have no receipt.

## Schedules and scheduled inputs

For an individual trigger, pass its division to `schedules.create`. Use the
returned `trigger_id` to read, change, or delete that trigger.

```python
trigger = client.schedules.create(division_id=division_id, name="Review", trigger_type="manual")
client.schedules.update(trigger["trigger_id"], enabled=False)
```

Patch Division scheduling fields through the graph or `divisions.update()`.
The graph supports `schedule_enabled`, `schedule_start_from`,
`schedule_frequency`, `schedule_session_parameters`, `schedule_session_id_mode`,
`schedule_persistent_session_id`, and `schedule_manual_input_text`.
The direct `client.schedules` CRUD API exposes advanced trigger definitions.

```python
definition = {
    "timezone": "Europe/Istanbul",
    "date_rule": {"type": "weekly", "weekdays": ["MO", "TU", "WE", "TH", "FR"]},
    "time_rule": {"type": "interval_window", "start": "08:30", "end": "16:15",
                  "every": {"amount": 15, "unit": "minutes"}, "include_end": True},
}
preview = client.divisions.schedule_preview(division_id, schedule_definition=definition)
client.divisions.update(division_id, schedule_enabled=True,
    schedule_definition=definition)
uploaded = client.uploads.scheduled_input(division_id, "report.pdf")
status = client.divisions.scheduled_input_status(division_id)
client.uploads.clear_scheduled_inputs(division_id)
```

Interval schedules use `schedule_frequency={"amount": 1, "unit": "hours"}`.
Units are seconds, minutes, hours, days, or weeks. Use an automation Division;
an enabled schedule alone does not make an incomplete draft deployable.

Schedule preview requires read. Schedule management and extraction status require
`agents:write`. Upload **replaces the entire existing file collection** with the
submitted file. An empty POST clears it. Extraction is asynchronous: read status
to observe completion/failure. Automation Divisions require an enabled scheduled
trigger before uploading. Use raw multipart HTTPX requests if you need to replace
with several files in one request; the convenience method uploads one file.

## Needings and monitoring

```python
from time import time

needing_payloads = [{"id": "connect-accounts", "type": "integration",
                    "title": "Connect accounts", "description": "Provide an account integration."}]
needings = client.needings.list(division_id)
client.needings.sync(division_id, {"source": "octopus", "needings": needing_payloads})
client.needings.discard(division_id, needing_id)
client.needings.satisfy(division_id, needing_id)
client.needings.reopen(division_id, needing_id)

schedules = client.monitoring.schedules(limit=20)
runs = client.monitoring.background_runs(division_id=division_id)
end = int(time())
work = client.monitoring.work_items(from_ts=end - 3600, to_ts=end)
source_health = client.monitoring.sources()
messages = client.monitoring.messages()
```

Needings are readiness work items: list requires agents read, lifecycle changes
agents write. Monitoring requires `monitoring:read`, independently of agents
read. Monitoring routes return dashboard response envelopes; their `cursor`
pagination is separate from CRUD's `iter_all()` DRF pagination. Use
`client.request()` for a background run's by-message route or a specific
operations-source route listed in the coverage matrix. Alternatively, use
`client.monitoring.background_run_by_message(message_id)` and
`client.operations_sources(division_id)` directly. Source health reads also require
`integrations:read` because the existing handler checks integration access.
The existing needing-sync schema requires `source="octopus"`; this is the
backend's source identifier, and calling sync does not generate an Octopus UI.

## Share and embed settings

```python
share = client.share.get(division_id)
client.share.update(division_id, enabled=True)
client.share.regenerate(division_id)
client.share.revoke(division_id)

embed = client.embed.get(division_id)
client.embed.update(division_id, allowed_origins=["https://your-site.example"])
client.embed.rotate_token(division_id)
client.embed.disable(division_id)
client.embed.enable(division_id)
```

Settings reads and writes require `agents:write` under the current management
policy. Share supports regenerate/revoke; embed supports rotate-token and
enable/disable. Create settings with `create()` if absent. Shared runtime/public
endpoints are separate from these SDK management operations.

## Export, import, and transfer resolution

```python
package = client.divisions.transfer_export(division_id)
preview = client.divisions.import_preview(package=package, mode="create")
result = client.divisions.import_apply(package=package, mode="create",
    expected_digest=preview["digest"])
requirements = client.divisions.transfer_status(result["division_id"])
backup = client.divisions.transfer_backup(result["division_id"])
client.divisions.transfer_resolve(result["division_id"],
    source_mappings=source_mappings, acknowledged=acknowledged)
```

Packages are credential-free graph exports. Server export response envelopes
should be inspected: use the package object returned by your dashboard version.
Imports require write for every resource family actually created or updated.
Preview checks those grants too. Update/replace requires `target_division_id`,
`expected_target_revision`, and the preview digest; update also requires
`expected_target_digest`. Removed/replaced rows require their delete grants.
API credentials, files, and unresolved external Knowledge Sources are not copied;
resolve those explicitly. Deployed targets cannot be replaced.

Duplicate is available for Divisions, agents, functions, and integrations. It
requires read of copied/reused resources and write for clones. Function
duplication may clone an integration and therefore requires integrations write.
Division composition creates agents and function wrappers from endpoint IDs;
actions in composition require functions write and integration read. No
unauthorized batch persists a partial graph.
