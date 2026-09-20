"""Docs model-id alignment tests (CH-GAP-054).

Every model id quoted in ``README.md`` and ``docs/*.md`` must resolve against
the shipped catalog (``chimera.yaml.example``). The docs drifted once already:
they named ``z-ai/glm-5.2``, ``openrouter/anthropic/claude-sonnet-4`` and
``openrouter/anthropic/claude-haiku-4.5`` while the shipped catalog carries
``zai-coding-plan/glm-5.2``, ``anthropic/claude-sonnet-4.6``,
``openrouter/anthropic/claude-fable-5`` and ``anthropic/claude-haiku-4.5`` — so
a reader pasting a documented override got an unknown-model rejection.

Scope discipline, deliberately not brittle:

* Only QUOTED tokens (``"..."`` or backticks) are candidates, and only when
  their first path segment is a provider namespace present in the shipped
  catalog. That filter keeps category paths (``technology_code/...``), file
  paths, endpoint paths and badge URLs out of the check.
* Ids documented as something OTHER than a chimera catalog id are excluded via
  ``KNOWN_NON_CATALOG_IDS`` — e.g. the 9router wire-mapping prose shows
  ``openrouter/x-ai/grok-4.6`` as the id AFTER the ``router9/`` prefix strip,
  and OPENAI_API.md's error example uses a deliberately bogus id. Each entry
  names its justification; a new non-catalog id fails loudly until a reviewer
  adds it there with a reason.
* ``docs/dogfood/`` is excluded — dated run logs are historical records.

Hermetic by construction: paths resolve from this file, the catalog comes from
the shipped template, and there is no network access.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPO / "chimera.yaml.example"
MODEL_CATALOG_DOC = REPO / "docs" / "model-catalog.yaml"

#: Quoted token (double quotes or backticks) without the quotes.
_QUOTED = re.compile(r'"([^"\n]+)"|`([^`\n]+)`')

#: Model-id shape: provider/model[/...] — lowercase start, allows the comma in
#: the shipped ``cliproxy/deepseek,deepseek-v4-flash`` id.
_MODEL_ID = re.compile(r"^[a-z][a-z0-9._-]*/[a-z0-9][a-z0-9.,_/-]*$")

#: Quoted ids that are NOT chimera catalog ids on purpose. Each maps to the
#: reason the docs show it; the test fails if one disappears (stale allowlist)
#: or if any OTHER non-catalog id appears.
KNOWN_NON_CATALOG_IDS: dict[str, str] = {
    # README/CONFIG wire-mapping prose: the id AFTER chimera strips the one
    # router9/ prefix — the catalog id is router9/openrouter/x-ai/grok-4.6.
    "openrouter/x-ai/grok-4.6": "9router wire form of router9/openrouter/x-ai/grok-4.6",
}

#: Stale ids this task removed — pinned so they cannot creep back.
STALE_IDS = (
    "z-ai/glm-5.2",
    "anthropic/claude-sonnet-4",
    "openrouter/anthropic/claude-sonnet-4",
    "openrouter/anthropic/claude-haiku-4.5",
)


def _catalog_keys() -> set[str]:
    with EXAMPLE_CONFIG.open(encoding="utf-8") as fh:
        return set(yaml.safe_load(fh).get("models", {}))


CATALOG_KEYS = _catalog_keys()

#: Provider namespaces = first segments of shipped catalog ids. A quoted token
#: is only a candidate when it starts with one of these.
PROVIDER_NAMESPACES = {key.split("/", 1)[0] for key in CATALOG_KEYS}


def _doc_files() -> list[Path]:
    return [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]


def _quoted_model_ids(path: Path) -> list[tuple[int, str]]:
    """(line, token) for every quoted catalog-namespace model id in ``path``."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in _QUOTED.finditer(line):
            token = match.group(1) or match.group(2)
            if not _MODEL_ID.match(token):
                continue
            if token.split("/", 1)[0] in PROVIDER_NAMESPACES:
                hits.append((lineno, token))
    return hits


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: p.name)
def test_quoted_model_ids_resolve_in_shipped_catalog(doc: Path) -> None:
    hits = _quoted_model_ids(doc)
    unknown = sorted({(token, lineno) for lineno, token in hits if token not in CATALOG_KEYS})
    unknown = [(tok, ln) for tok, ln in unknown if tok not in KNOWN_NON_CATALOG_IDS]
    assert not unknown, (
        f"{doc.relative_to(REPO)} quotes model ids missing from "
        f"chimera.yaml.example: "
        + ", ".join(f"{tok!r} (line {ln})" for tok, ln in unknown)
        + " — fix the doc, or add the id to KNOWN_NON_CATALOG_IDS with a reason"
    )


def test_extraction_actually_matches() -> None:
    """The candidate harvest must be non-trivial — an empty regex is a vacuous gate."""
    total = sum(len(_quoted_model_ids(doc)) for doc in _doc_files())
    assert total >= 10, f"only {total} candidate ids extracted — extraction is broken"


def test_known_non_catalog_ids_still_present() -> None:
    """KNOWN_NON_CATALOG_IDS entries must still be quoted in the docs (no rot)."""
    seen = {token for doc in _doc_files() for _, token in _quoted_model_ids(doc)}
    for token, reason in KNOWN_NON_CATALOG_IDS.items():
        assert token in seen, (
            f"{token!r} is allowlisted ({reason}) but no longer quoted in the "
            f"docs — remove it from KNOWN_NON_CATALOG_IDS"
        )


def test_stale_ids_do_not_return() -> None:
    for doc in _doc_files():
        seen = {token for _, token in _quoted_model_ids(doc)}
        for stale in STALE_IDS:
            assert stale not in seen, (
                f"{doc.relative_to(REPO)} quotes stale id {stale!r} — see "
                f"CH-GAP-054 for the canonical replacement"
            )


def test_model_catalog_doc_uses_shipped_glm_id() -> None:
    """docs/model-catalog.yaml must key GLM-5.2 by the shipped catalog id."""
    text = MODEL_CATALOG_DOC.read_text(encoding="utf-8")
    assert '"z-ai/glm-5.2"' not in text
    assert '"zai-coding-plan/glm-5.2"' in text
