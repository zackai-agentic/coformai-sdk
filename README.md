# Coform Python SDK

Python 3.10+ SDK for managing Division maps through the dashboard and executing
them through the mounted agentic core API. Includes matching `Coform` and
`AsyncCoform` clients, typed graph mutations, REST/MCP uploads, and closable
invocation streams. Version **0.1.0**.

```sh
python -m pip install .
```

Set `COFORM_API_KEY`, `COFORM_ORGANIZATION_ID`, `COFORM_DASHBOARD_URL` (including
`/api/`), and `COFORM_CORE_URL`. Use your deployment's roots; proxy prefixes are
preserved. API keys come from the dashboard's key management screen.

```python
from coformai import Coform

with Coform() as client:
    divisions = client.divisions.list()
```

Start with [installation and configuration](docs/getting-started.md), then follow
[Division maps](docs/maps.md), [integrations](docs/integrations.md), and
[invocations](docs/invocations.md). [Lifecycle](docs/lifecycle.md) covers schedules,
deployment, transfers, share/embed settings, and monitoring.

- [Operation coverage matrix](docs/coverage.md): methods, endpoints, and grants
- [API reference](docs/reference.md): generated from public docstrings
- [Errors and compatibility](docs/troubleshooting.md): recovery and limitations
- [Dashboard authentication](docs/dashboard-auth.md): deployment prerequisite
- [Runnable examples](examples/README.md): credentials supplied through environment
- [Contribution instructions](CONTRIBUTING.md) and [changelog](CHANGELOG.md)
- [Verification record](docs/verification.md): tests, isolated packaging, and rollout

Deploy the accompanying dashboard authentication changes before using management
methods. The core service and documentation site require no SDK changes. Requests
are never automatically retried. Detach removes a map occurrence; delete removes
a reusable entity permanently.

```sh
python -m pip install -e ".[dev,docs]"
python -m pytest
python -m mypy src
python -m mkdocs serve
python -m mkdocs build --strict
python -m build
```

The documentation is built locally in `site/`; wheels are written to `dist/`.
Nothing is published, and this repository has no configured remote.
