# Errors, recovery, and limitations

| Error | Recovery |
|---|---|
| `AuthenticationError` (401) | Check key value, expiry, revocation, and allowed IPs |
| `PermissionDeniedError` (403) | Select every required exact grant; inspect server detail |
| `NotFoundError` (404) | Verify organization and IDs; foreign tenant IDs are inaccessible |
| `ValidationError` (400/422) | Inspect `.body` field/operation errors; readiness blockers can be 422 |
| `ConflictError` (409) | Reconcile session ownership, active operation, or server state |
| `RateLimitError` (429) | Respect `.retry_after`; inspect request or token budget limits |
| `APIConnectionError` / `APITimeoutError` | Reconcile saved graph or session before repeating work |
| `StreamProtocolError` | Inspect `.partial_result` and session status; check proxy framing |

`APIStatusError` retains status, parsed body, request ID, and Retry-After; error
messages do not contain request credentials. Other non-success statuses use the
base status error. HTTP redirects are not followed automatically. SDK methods
do not retry HTTP failures, mutations, uploads, or invocations.

A response timeout can occur after the server committed a mutation. Read the
current graph before rebuilding the request. A closed stream can leave server
execution running. Read session status before restarting; an indeterminate
result is not a successful or failed workflow claim. A request ID is correlation,
not a guarantee of server-side deduplication; current graph revision behavior is
preserved without inventing conflict checks.

Management response dictionaries intentionally preserve dashboard serializers.
They may contain backend-specific enums or extra fields. Typed graph/input/event
envelopes validate stable contracts; resource CRUD fields are forwarded.

Version 0.1.0 excludes Telegram pairing, Octopus UI generation, unmounted core
deployment, package publication, documentation hosting, and automatic OAuth
consent. Sharing documentation covers settings, not the public runtime client.
The SDK does not expose a core cancel endpoint because none is mounted. Local
file-to-base64 helpers hold files in memory. Stream collection retains events in
memory; iterate instead for long-running streams.

Validate against your deployed dashboard/core versions before production use.
The repository's tests mock external providers and deployment, and do not claim
a live end-to-end production deployment. See [dashboard roll-out notes](dashboard-auth.md).
