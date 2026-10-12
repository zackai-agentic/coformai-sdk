# Dashboard authentication implementation and rollout

Deploy the dashboard patch with this SDK before enabling key-authenticated
management. The core service, deployment service, and existing documentation
site stay unchanged. There are no new permission IDs or key-creation semantics.

`api.authentication.APIKeyAuthentication` authenticates `Bearer ak_...` through
the existing middleware validator. It reuses active status, expiry, IP validation,
usage accounting, and existing throttles. Failed API-key credentials produce 401
without JWT fallback. The shared `APIKeySupportMixin` enables key/JWT
authentication only for SDK-facing view families. User JWTs keep their existing
blacklist and membership checks.

`api.api_key_support` maps model/action and endpoint policies to selected grants.
Ordinary keys are scoped to the stored organization and permissions; they never
use the creator's membership, admin role, or superuser flag. Write/read/delete
are independent. Unknown endpoint/model operations fail closed. The existing
system-client organization exception is preserved.

Graph requests are checked at the service entry point before mutation. The root,
each resource edit/delete, parent relationship changes, existing child reads,
and raw nested IDs are authorized together. Unauthorized mixed batches return
403 and persist nothing. Serializer-resolved related objects and raw nested
references are checked for direct CRUD too. Imports authorize their validated
record inventory and removals; composition and duplication authorize nested
created and reused resources.

For deploy/undeploy, the dashboard validates the key and `agents:write`, then
signs a server-only JWT with the existing shared HS256 signing configuration.
Claims include only the target `client_ids`, API-key principal identity, `iat`,
`exp=iat+60`, and a fresh `jti`. A new token is issued for each downstream call,
including rollback requests after lifecycle waits. The key's active state and
expiry are checked again at issuance. The token is never sent to SDK callers.
Do not change the downstream signing configuration independently.

API-key usage identifies the key. Needing events use `actor_type="api_key"`
and the key UUID. Existing audit User FKs on share/embed/transfer records use
the key creator solely as attribution; authorization retains the key principal.

## Verify before rollout

The dashboard includes isolated SQLite settings and production view mounts:

```sh
python -m django test api.tests.test_sdk_api_keys --settings=api.tests.sdk_settings --noinput
```

Run existing dashboard regression suites as well, using your standard test
dependencies. Isolated settings load no production `.env`; external providers,
deployment, messaging, and Mongo are mocked where tested. Production operations
still require the dashboard's normal database/services/middleware configuration.
These tests are not a claim of a live production deployment.

See the dashboard's `docs/sdk-api-key-authentication.md` for maintenance notes and
the [permission matrix](coverage.md) for each method.
