# Verification record

Verified locally on 2026-10-05 using Python 3.12.13, HTTPX 0.28.1, Pydantic 2.13.5,
Django 5.2, and the dashboard based on commit `9189ee4` plus the accompanying
authentication changes. The SDK requires Python 3.10+; strict typing and lint
target Python 3.10. Runtime verification used Python 3.12.

| Check | Result |
|---|---|
| SDK tests | 53 passed |
| Dashboard bearer, graph, transfer, JWT, and system-client tests | 156 passed |
| Strict mypy | Passed for all nine SDK source modules |
| Ruff lint and formatting | Passed |
| Strict MkDocs build | Passed with generated API references and page links |
| Isolated wheel build | `dist/coformai_sdk-0.1.0-py3-none-any.whl` |
| Separate wheel installation | Passed with runtime dependencies only |
| Installed wheel smoke checks | Version, `py.typed`, sync prefix preservation, async stream |
| Runnable examples | All four scripts verified through mock HTTPX transports |

The dashboard suite uses the production URL configuration and real bearer
headers with isolated SQLite settings. It covers valid/invalid/expired/revoked
and IP-restricted keys, exact selected grants, tenant boundaries, mixed graph
atomicity, nested references and samples, parameter upserts, imports, duplication,
REST/MCP handler access, specification-removal grants, deployment JWTs, key
throttling/usage identity, JWT regressions, and the system-client exception.
External provider calls, deployment calls, and file storage are mocked.
The documented minimal automation draft also validates and commits through the
real dashboard views with a write-only key. Nested multimodal processor/model
references participate in the same tenant and read-permission checks.

The SDK suite covers sync/async parity, request contracts, uploads, references,
typed mutation snapshots, status/transport errors without replay, one-byte UTF-8
stream fragments, malformed events, early closure, approvals, every terminal
outcome, and missing terminal events. Public annotations/docstrings and examples
are checked automatically.

## Reproduce SDK checks

```sh
python -m pip install -e ".[dev,docs]"
python -m pytest
python -m ruff check src tests
python -m ruff format src tests --check
python -m mypy src
python tools/generate_docs.py
python -m mkdocs build --strict
python tools/check_built_docs.py
python -m build --wheel
python -m venv .wheel-env
.wheel-env/Scripts/python -m pip install dist/coformai_sdk-0.1.0-py3-none-any.whl
```

On macOS/Linux, use `.wheel-env/bin/python` for the final command. This workstation
used `uv build --wheel --offline` for the isolated build and `uv pip install` into
the separate environment, with cached dependencies.

## Reproduce dashboard checks

Run from `agentic-dashboard`, using an environment with its test dependencies:

```sh
python -m django test api.tests.test_sdk_api_keys api.tests.test_division_map_api_key_access api.tests.test_graph_mutations api.tests.test_division_transfer --settings=api.tests.sdk_settings --noinput
```

The test configuration suppresses external service initialization. Four existing
Django warnings report `null` on ManyToMany fields; these do not affect the test
result. Production services and credentials were not used for verification.

## Delivery and rollout

Only the SDK and dashboard contain task changes. The core service and existing
documentation/deployment services remain unchanged. Built documentation is in
`site/`; the wheel is in `dist/`. These generated directories are ignored by Git
and can be rebuilt from source. No remote, publishing, or deployment was performed.
Deploy dashboard authentication changes before using SDK management methods.
