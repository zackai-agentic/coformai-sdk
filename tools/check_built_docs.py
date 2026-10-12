"""Verify local HTML links, fragments, and exported class reference anchors.

Run after ``python -m mkdocs build --strict``. External links are deliberately
excluded: this check verifies the locally built artifact without network access.
"""

from __future__ import annotations

import inspect
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import coformai


class Page(HTMLParser):
    """Collect link targets and fragment IDs from one generated HTML page."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.anchors.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))


def main() -> None:
    """Check the local site and raise AssertionError for broken references."""
    site = Path(__file__).resolve().parents[1] / "site"
    pages = {path.resolve(): Page(path) for path in site.rglob("*.html")}
    assert pages, "Build the documentation first"
    count = 0
    for path, page in pages.items():
        for href in page.links:
            link = urlsplit(href)
            if link.scheme or link.netloc:
                continue
            if link.path.startswith("/"):
                target = (site / unquote(link.path).lstrip("/")).resolve()
            else:
                target = (path.parent / unquote(link.path)).resolve() if link.path else path
            if target.is_dir():
                target /= "index.html"
            assert target.is_file(), (path.relative_to(site), href)
            if link.fragment and target in pages:
                assert unquote(link.fragment) in pages[target].anchors, (path.relative_to(site), href)
            count += 1
    overview = (site / "reference/index.html").read_text(encoding="utf-8")
    for name in coformai.__all__:
        assert name in overview, f"Missing public export: {name}"
        obj = getattr(coformai, name)
        if inspect.isclass(obj):
            module = obj.__module__.split(".")[-1]
            anchor = obj.__module__ + "." + obj.__name__
            assert anchor in pages[(site / "reference" / module / "index.html").resolve()].anchors, anchor
    print(f"Verified {count} local HTML links/fragments and {len(coformai.__all__)} public exports")


if __name__ == "__main__":
    main()
