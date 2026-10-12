# Contributing

Create a Python 3.10+ virtual environment and install `.[dev,docs]`. SDK changes
must preserve sync/async method parity, typed public signatures, Google-style
docstrings, and the wire contracts documented in the coverage matrix.

Resource/client endpoint inventories live in `tools/generate_resources.py` and
`tools/generate_clients.py`. Regenerate checked-in wrappers after changing them,
then format and verify. Do not put credentials in examples or fixtures.

```sh
python tools/generate_resources.py
python tools/generate_clients.py
python tools/generate_docs.py
python -m ruff check src --fix
python -m ruff format src
python -m mypy src
python -m pytest
python -m mkdocs build --strict
python tools/check_built_docs.py
python -m build
```

Document new public interfaces, defaults, return values, exceptions, permissions,
and side effects. Add runnable environment-based examples and mock contract tests
for new workflows. Keep authored guides aligned with actual backend serializers.
Use `python -m mkdocs serve` for local preview. Built docs are in `site/` and are
not published. Changes to dashboard auth should include real bearer-header
regressions; core/docs/deployment repositories are reference-only for this task.
