# Installation, configuration, and keys

## Compatibility

Python 3.10 or newer, HTTPX 0.28+, and Pydantic 2.10+ are required. This version
targets dashboard commit `9189ee4` with the accompanying API-key authentication
patch and the checked-out core service's six mounted session/execution endpoints.
Deployment goes through the dashboard lifecycle API. Core deployment routes that
are not mounted are excluded.

Install from this repository:

```sh
python -m pip install .
```

## Create a key in the dashboard

Open your organization settings and the API Keys screen. Create a key with a
descriptive name, select the operations it should perform, and configure expiry
and IP restrictions as appropriate for your application. Copy the generated
key and your organization ID into environment variables. Key creation and the
existing selectable permission names are unchanged.

```powershell
$env:COFORM_API_KEY = "<dashboard-generated-key>"
$env:COFORM_ORGANIZATION_ID = "<organization-uuid>"
$env:COFORM_DASHBOARD_URL = "https://your-dashboard.example/api/"
$env:COFORM_CORE_URL = "https://your-core.example/"
```

Constructor values take precedence over environment variables. All four values
are required. The dashboard root must include `/api/`; both roots may include
reverse-proxy prefixes. Roots must be HTTP(S) without embedded credentials,
query strings, or fragments. Request timeout defaults to 60 seconds. Invocation
streams have no read timeout; use session status to reconcile disconnects.

```python
from coformai import Coform

with Coform(timeout=30) as client:
    for division in client.divisions.iter_all():
        print(division["division_id"])
```

```python
import asyncio
from coformai import AsyncCoform

async def main():
    async with AsyncCoform() as client:
        divisions = await client.divisions.list()
        print(divisions)

asyncio.run(main())
```

Resource methods match across clients. Await asynchronous HTTP methods. Resource
factories such as `client.function_parameters(id)` and invocation stream
factories perform no I/O and do not require `await`.

## Select grants explicitly

| Family | Typical use |
|---|---|
| `agents:read/write/delete` | Divisions, agents, actions, context links, samples, schedules, sharing |
| `chains:read/write/delete` | Chains, steps, dependencies |
| `functions:read/write/delete` | Agentic Function wrappers and parameters |
| `integrations:read/write/delete` | REST/MCP integrations, specs, endpoints, tools |
| `knowledge:read/write/delete` | Knowledge Sources |
| `monitoring:read` | Dashboard monitoring |
| `inference:execute` | Core session/invocation operations and Division verification |

Each grant is independent. Write does not imply read or delete. Graph saves
require write on the root and each edited resource; attaching an existing child
requires its family's read grant. A key belongs to one organization and never
inherits its creator's privileges. See [the full matrix](coverage.md).

## Response conventions

Management methods return parsed serializer dictionaries or lists; fields are
preserved. CRUD `list()` may return a DRF pagination envelope; `iter_all()` handles
plain lists and `results`/`next` envelopes. Pagination cannot send credentials
outside the configured API root. Successful empty responses return `None`.
Typed inputs, graph requests, and events retain future server fields.
