# Documentation contributions

Install the local development extras with `python -m pip install -e ".[dev,docs]"`.
Run `python -m mkdocs serve` for preview and `python -m mkdocs build --strict`
for validation. The latter writes the complete static site to `site/`.

API reference pages are generated from package docstrings via mkdocstrings.
Update source docstrings when changing interfaces; use Google-style Args,
Returns/Yields, Raises, required permissions, defaults, and side-effect notes.
Authored guides live beside this page and explain complete workflows. Coverage
and reference page sources regenerate with `python tools/generate_docs.py`.

Run the examples through their mock verification tests. Keep credentials in
environment variables and make prerequisites/expected outcomes explicit. Do not
invent endpoints or promise replay deduplication that the backend does not
implement. Add every documentation page to `mkdocs.yml`; strict builds reject
missing links and unresolved API references. No docs hosting is configured.
