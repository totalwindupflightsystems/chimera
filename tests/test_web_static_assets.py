"""DF-CHIMERA-V2-21 — the web UI's mermaid renderer is vendored and fails visibly.

The SPA used to load mermaid from ``cdn.jsdelivr.net``, so the DAG panel died
on hosts without egress and under a strict CSP. This locks the replacement in
end to end:

* the vendored bundle exists in the shipped package, is a real mermaid build,
  and is served by the ``/web`` static-asset route;
* the served page references the vendored path with an ``onerror`` fallback
  and carries the hidden ``#dag-renderer-unavailable`` banner plus the
  ``window.mermaid`` init guard — and NO external script/link URL;
* the failure path is exercised behaviorally: the page's real ``onerror``
  attribute body and init-guard code are executed (Node, DOM stubbed) against
  a missing ``window.mermaid`` and must reveal the banner.

The broken-load scenario is simulated by executing the page's own ``onerror``
handler — exactly what a browser invokes when ``vendor/mermaid.min.js`` 404s —
so no second HTML copy or JS runtime dependency beyond Node (skipped honestly
when absent) is needed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "chimera" / "web" / "static"
VENDOR_JS = STATIC_DIR / "vendor" / "mermaid.min.js"
VENDOR_README = STATIC_DIR / "vendor" / "README.md"

#: mermaid version the vendored bundle must match (kept in vendor/README.md).
MERMAID_VERSION = "11.17.2"

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
ATTR_RE = {"src": re.compile(r"\bsrc\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE),
           "href": re.compile(r"\bhref\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)}


def _page(client: TestClient) -> str:
    """The SPA exactly as the real ``/web/`` route serves it."""
    resp = client.get("/web/")
    assert resp.status_code == 200
    return resp.text


def _tag_urls(html: str, tag_re: re.Pattern[str], attr: str) -> list[str]:
    urls: list[str] = []
    for tag in tag_re.findall(html):
        match = ATTR_RE[attr].search(tag)
        if match:
            urls.append(match.group(1))
    return urls


@pytest.fixture
def client(config):  # type: ignore[no-untyped-def]
    """TestClient over the real app — same shape as tests/test_web.py."""
    app = create_app(config=config, engine=Engine(config, FakeGateway()))
    return TestClient(app)


@pytest.fixture
def page(client):  # type: ignore[no-untyped-def]
    return _page(client)


# ---------------------------------------------------------------------------
# (a) the vendored bundle is real mermaid and ships with the package
# ---------------------------------------------------------------------------


def test_vendor_file_exists_is_mermaid_and_version_pinned() -> None:
    assert VENDOR_JS.is_file(), f"vendored mermaid missing: {VENDOR_JS}"
    blob = VENDOR_JS.read_bytes()
    assert len(blob) > 1_000_000, f"vendored bundle suspiciously small: {len(blob)} bytes"
    assert blob.count(b"mermaid") >= 20, "bundle does not look like mermaid"
    identifiers = [
        b"registerExternalDiagrams",
        b"mermaid.initialize",
        b'globalThis["mermaid"]',
    ]
    assert any(ident in blob for ident in identifiers), (
        "no mermaid API identifier found in the vendored bundle"
    )
    assert b'version:"%s"' % MERMAID_VERSION.encode() in blob, (
        f"vendored bundle is not mermaid {MERMAID_VERSION}"
    )
    assert VENDOR_README.is_file()
    assert MERMAID_VERSION in VENDOR_README.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (b) the SERVED page contains no external script/link URL
# ---------------------------------------------------------------------------


def test_served_page_has_no_external_script_or_link_urls(page: str) -> None:
    external = [
        url
        for url in _tag_urls(page, SCRIPT_TAG_RE, "src")
        + _tag_urls(page, LINK_TAG_RE, "href")
        if url.startswith(("http://", "https://", "//"))
    ]
    assert external == [], f"external loader URLs still referenced: {external}"
    # Non-vacuous: the page must actually carry the vendored script tag.
    assert "vendor/mermaid.min.js" in _tag_urls(page, SCRIPT_TAG_RE, "src")


# ---------------------------------------------------------------------------
# (c) the page references the vendored path and declares the fallback wiring
# ---------------------------------------------------------------------------


def test_page_references_vendored_path_with_onerror_and_fallback_element(page: str) -> None:
    assert '<script src="vendor/mermaid.min.js"' in page
    assert 'id="dag-renderer-unavailable"' in page
    assert "onerror=" in page
    assert "DAG renderer unavailable" in page
    # The banner starts hidden and is revealed via the .visible class rule.
    assert re.search(
        r"#dag-renderer-unavailable\s*\{[^}]*display:\s*none", page, re.DOTALL
    ), "fallback banner must start hidden"
    assert re.search(
        r"#dag-renderer-unavailable\.visible\s*\{\s*display:\s*block", page
    ), "fallback banner must be revealed via the .visible class"
    # The init guard: a missing window.mermaid must route to the fallback…
    assert "typeof window.mermaid === 'undefined'" in page
    assert "function showDagRendererFallback" in page
    # …not into a raw `mermaid.initialize` TypeError.
    guard_pos = page.index("typeof window.mermaid === 'undefined'")
    init_pos = page.index("mermaid.initialize({")
    assert guard_pos < init_pos, "init guard must run before mermaid.initialize"


# ---------------------------------------------------------------------------
# (d) the /web static route actually serves the vendored bundle
# ---------------------------------------------------------------------------


def test_static_route_serves_vendored_mermaid(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/web/vendor/mermaid.min.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    body = resp.content
    assert len(body) == VENDOR_JS.stat().st_size
    assert b"registerExternalDiagrams" in body or b"mermaid.initialize" in body


def test_static_route_confines_paths_and_suffixes(client) -> None:  # type: ignore[no-untyped-def]
    # Traversal out of static/ is a 404, never a leak or a 400 (raw and
    # percent-encoded forms — whichever layer rejects it, it stays a 404).
    for hostile in (
        "/web/static/../index.html",
        "/web/static/..%2findex.html",
        "/web/vendor/../../../pyproject.toml",
    ):
        resp = client.get(hostile)
        assert resp.status_code == 404, hostile
    # Only .js/.css are served — vendor docs stay private.
    assert client.get("/web/vendor/README.md").status_code == 404
    # Missing files 404 (this is what triggers the SPA's onerror fallback).
    assert client.get("/web/vendor/nope.min.js").status_code == 404


# ---------------------------------------------------------------------------
# (e) BEHAVIORAL: the failure path reveals the banner (real shipped JS, Node)
# ---------------------------------------------------------------------------


def _extract_show_fallback_source(page: str) -> str:
    match = re.search(r"function showDagRendererFallback\(\) \{.*?\n\}", page, re.DOTALL)
    assert match, "showDagRendererFallback() not found in the served page"
    return match.group(0)


def _extract_guard_if_block(page: str) -> str:
    """The shipped ``if (typeof window.mermaid === 'undefined') {...} else {`` head."""
    match = re.search(r"if \(typeof window\.mermaid === 'undefined'\) \{[^}]*\} else \{", page)
    assert match, "window.mermaid init guard not found in the served page"
    return match.group(0)


def _extract_onerror_body(page: str) -> str:
    match = re.search(r"<script src=\"vendor/mermaid\.min\.js\" onerror=\"([^\"]+)\">", page)
    assert match, "onerror handler missing from the vendored script tag"
    return match.group(1)


def test_fallback_revealed_when_mermaid_absent(page: str) -> None:
    """Execute the page's real guard + onerror JS with ``window.mermaid`` absent.

    This is the broken-load scenario: the browser fires the ``onerror``
    attribute when ``vendor/mermaid.min.js`` fails to load, and the inline
    init guard catches a bundle that loaded but left no global. Both paths
    must add the ``visible`` class to the banner element.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH — static wiring assertions in this module cover the rest")
    show_fn = _extract_show_fallback_source(page)
    guard_if = _extract_guard_if_block(page)
    onerror_body = _extract_onerror_body(page)

    driver = (
        "const classes = [];\n"
        "const el = { classList: { add(c) { classes.push(c); } } };\n"
        "const document = { getElementById(id) {"
        " return id === 'dag-renderer-unavailable' ? el : null; } };\n"
        "const window = {};  // vendored bundle absent — the failure under test\n"
        + show_fn + "\n"  # verbatim from the page
        + guard_if + "\n"  # the guard's if/else head, verbatim from the page
        "}\n"  # close the else branch
        "const guardFired = classes.includes('visible');\n"
        "classes.length = 0;\n"
        + onerror_body + "\n"  # verbatim from the page
        "const onerrorFired = classes.includes('visible');\n"
        "console.log(JSON.stringify({ guardFired, onerrorFired }));\n"
    )
    proc = subprocess.run(
        [node, "-e", driver], capture_output=True, text=True, timeout=30, check=False
    )
    assert proc.returncode == 0, f"fallback JS failed under node: {proc.stderr}"
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["guardFired"], "missing window.mermaid did not reveal the fallback banner"
    assert result["onerrorFired"], "script onerror did not reveal the fallback banner"
