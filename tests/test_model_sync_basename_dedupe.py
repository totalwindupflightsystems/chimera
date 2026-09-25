"""Core-scan basename dedupe regression tests — DF-CHIMERA-V2-50.

The core path in ``scan_models_dev()`` skipped a candidate only when its
RESOLVED Chimera id matched a catalog key exactly, while the reseller watch
compares BASENAMES (a namespaced reseller id never equals its resolved
Chimera id). Consequence measured 2026-09-24: a model admitted to the
catalog under a namespaced prefix (``openrouter/minimax/minimax-m3`` and
``router9/mmx/MiniMax-M3``) re-reported as a NEW core find from the bare
``minimax`` row (``minimax/minimax-m3``) — inflating the headline diff.

These tests pin the fixed contract, entirely offline (fixture cache, no
network, no API key, no live ``.seen_models.json``):

* a core candidate whose basename already exists in the catalog (under any
  prefix) is SKIPPED — not reported, not counted in the headline;
* the skip is recorded in ``.seen_models.json`` with the basename-match
  marker, in a format old files (plain id lists) still load;
* the report carries an explicit SKIP line naming the catalog entry that
  matched, so the headline stays honest;
* the dedupe fires ONLY when the catalog already holds the basename: a
  genuinely-new model with a unique basename stays a candidate, and the
  exact-id match remains the primary;
* the reseller watch consumes the same basename helper (no second
  definition — one helper, two callers).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from chimera.provider_discovery import RegistrySnapshot

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


model_sync = _load_module("model_sync_basename_dedupe", SYNC_PATH)


# --- helpers ---------------------------------------------------------------- #


def _cache() -> dict[str, Any]:
    """Fixture cache: the real 2026-09-24 shape — the bare ``minimax`` row
    carries ``minimax-m3``, which the catalog already holds under a namespaced
    prefix; ``google`` carries the genuinely-new ``foo-v3``."""
    return {
        "minimax": {
            "models": {
                "minimax-m3": {
                    "id": "minimax-m3",
                    "family": "minimax",
                    "release_date": "2026-09-20",
                    "cost": {"input": 0.3, "output": 1.2},
                },
            },
        },
        "google": {
            "models": {
                # A genuinely-new model: no catalog entry shares its basename.
                "foo-v3": {
                    "id": "foo-v3",
                    "family": "google",
                    "release_date": "2026-09-21",
                    "cost": {"input": 0.5, "output": 2.0},
                },
            },
        },
    }


def _core_candidate(chimera_id: str, provider: str = "minimax") -> dict[str, Any]:
    """A core candidate dict in the exact shape scan_models_dev() produces."""
    return {
        "model_id": chimera_id.split("/")[-1],
        "chimera_id": chimera_id,
        "family": "minimax",
        "description": "",
        "input_cost_mtok": 0.3,
        "output_cost_mtok": 1.2,
        "input_per_1k": 0.0003,
        "output_per_1k": 0.0012,
        "recency_score": 100.0,
        "recency_ts": None,
        "provider": provider,
    }


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline fixture harness: fixture cache, scratch seen-file.

    ``_load_chimera_models`` is intentionally NOT stubbed here — each test
    pins the catalog it needs (the default-argument catalog freeze in
    ``_basename_match`` must never leak a non-empty test catalog).
    """
    cache = _cache()
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: cache)
    monkeypatch.setattr(
        model_sync,
        "load_preferred_registry",
        lambda **_kwargs: RegistrySnapshot(data=cache, source="models.dev"),
    )
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return {"cache": cache, "seen_path": seen_path}


# --- basename helpers: one definition, two callers -------------------------- #


def test_basename_match_is_case_insensitive_on_the_suffix() -> None:
    """Catalog casing (router9/mmx/MiniMax-M3) matches a lowercase basename."""
    assert model_sync._basename_match("MiniMax-M3", {"router9/mmx/MiniMax-M3"}) == "router9/mmx/MiniMax-M3"


def test_basename_match_returns_none_when_absent() -> None:
    """No catalog basename match → None (the candidate stays a candidate)."""
    assert model_sync._basename_match("google/foo-v3", {"google/foo-v2"}) is None


def test_basename_match_default_snapshot_does_not_leak_between_tests() -> None:
    """The frozen default catalog is the EMPTY set, never a populated one.

    ``_basename_match``'s default argument is frozen at import time (that is
    how Python defaults work) — it must be the empty set so a bare
    ``_basename_match(model_id)`` call can never dedupe against a stale
    catalog from some other module import. The reseller path always passes
    the catalog explicitly.
    """
    assert model_sync._basename_match("minimax-m3") is None


def test_single_basename_helper_shared_by_both_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reseller watch and the core scan use the SAME basename helper."""
    calls: list[str] = []
    original = model_sync._basename

    def spy(model_id: str) -> str:
        calls.append(model_id)
        return original(model_id)

    monkeypatch.setattr(model_sync, "_basename", spy)
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})

    # The reseller path (basename-level dedupe, DF-CHIMERA-V2-26)...
    watch, blind = model_sync.scan_reseller_watch(
        _cache(), set(), chimera_models={"openrouter/minimax/minimax-m3"}
    )
    assert watch == [] and blind == []
    # ...and the core scan (the fix) both go through _basename().
    model_sync.scan_models_dev(_cache())
    assert "minimax-m3" in calls


def test_reseller_watch_still_dedupes_by_catalog_basename(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared refactor keeps the reseller watch's catalog-basename dedupe.

    A reseller row carrying ``minimax/minimax-m3`` with the catalog holding
    ``openrouter/minimax/minimax-m3``: the basename ``minimax-m3`` matches, so
    the id is not reported. If the helper broke (e.g. stopped splitting on
    ``/``), the catalog basename set would hold the whole namespaced string
    and the reseller id would surface in ``watch`` — this test fails.
    """
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    cache = {
        "openrouter": {
            "models": {
                "minimax/minimax-m3": {
                    "id": "minimax/minimax-m3",
                    "family": "minimax",
                    "release_date": "2026-09-20",
                    "cost": {"input": 0.3, "output": 1.2},
                },
            },
        },
    }
    watch, blind = model_sync.scan_reseller_watch(cache, set())
    assert watch == [] and blind == []


# --- scan_models_dev: the core path dedupes by basename --------------------- #


def test_admitted_under_prefix_basename_skipped(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """minimax/minimax-m3 is already admitted as openrouter/minimax/minimax-m3.

    The google/foo-v3 row of the fixture cache (genuinely new) still flows
    through — only the basename-matching minimax row drops out.
    """
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    candidates = model_sync.scan_models_dev(isolated["cache"])
    assert "minimax" not in candidates  # the basename-matched row is skipped
    assert "google" in candidates  # the genuinely-new row survives
    assert [m["chimera_id"] for m in candidates["google"]] == ["google/foo-v3"]
    assert model_sync.LAST_BASENAME_SKIPS == [
        {
            "model_id": "minimax-m3",
            "chimera_id": "minimax/minimax-m3",
            "provider": "minimax",
            "catalog_id": "openrouter/minimax/minimax-m3",
        }
    ]


def test_no_basename_match_stays_a_candidate(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model whose basename matches nothing in the catalog is still new."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
    candidates = model_sync.scan_models_dev(isolated["cache"])
    ids = [m["chimera_id"] for models in candidates.values() for m in models]
    # Providers are visited in sorted order (google before minimax).
    assert ids == ["google/foo-v3", "minimax/minimax-m3"]
    assert model_sync.LAST_BASENAME_SKIPS == []


def test_same_basename_sibling_with_unique_catalog_basename_stays_a_candidate(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """google/foo-v3 remains a candidate when the catalog holds ONLY foo-v2.

    The basename check must never shadow a genuinely-new distinct model: the
    catalog does not contain the basename ``foo-v3`` (foo-v2 is a different
    basename), so google/foo-v3 is reported even though its basename shares a
    family prefix with an admitted model.
    """
    monkeypatch.setattr(
        model_sync,
        "_load_chimera_models",
        lambda: {"google/foo-v2", "openrouter/minimax/minimax-m3"},
    )
    candidates = model_sync.scan_models_dev(isolated["cache"])
    ids = [m["chimera_id"] for models in candidates.values() for m in models]
    assert "google/foo-v3" in ids
    assert "minimax/minimax-m3" not in ids  # admitted under openrouter/ prefix


def test_exact_id_match_remains_primary(isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """A resolved id in the catalog is skipped exactly as before the change —
    silently (no SKIP trail), because that path never re-reported anyway."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"minimax/minimax-m3", "google/foo-v3"})
    assert model_sync.scan_models_dev(isolated["cache"]) == {}
    assert model_sync.LAST_BASENAME_SKIPS == []


def test_scan_candidate_keeps_its_shape(isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Surviving candidates carry the exact pre-fix key set (additive only)."""
    monkeypatch.setattr(
        model_sync,
        "_load_chimera_models",
        lambda: {"google/foo-v2", "openrouter/minimax/minimax-m3"},
    )
    candidates = model_sync.scan_models_dev(isolated["cache"])
    rows = [m for models in candidates.values() for m in models]
    assert rows
    for m in rows:
        assert set(m) == {
            "model_id",
            "chimera_id",
            "family",
            "description",
            "input_cost_mtok",
            "output_cost_mtok",
            "input_per_1k",
            "output_per_1k",
            "recency_score",
            "recency_ts",
            "provider",
        }


# --- seen-file discipline --------------------------------------------------- #


def test_basename_skip_recorded_seen_with_match_note(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A basename-skipped candidate is recorded seen, with the match noted."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    report = model_sync.format_report(model_sync.scan_models_dev(isolated["cache"]))

    # The headline counts only genuinely-new finds (google/foo-v3), not the
    # basename-skipped minimax row.
    assert "Candidates: 1 new models across 1 providers" in report
    assert "minimax/minimax-m3" not in report.split("## Basename Skips")[0].split("## google")[-1]

    seen = json.loads(isolated["seen_path"].read_text())
    assert isinstance(seen, list)
    # Backward-compatible container: still a flat string list at the top level
    # (old readers must keep working), with the basename match encoded in the
    # recorded entry itself.
    assert any("minimax-m3" in entry and "openrouter/minimax/minimax-m3" in entry for entry in seen)


def test_old_seen_file_still_loads(isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-change .seen_models.json (plain id strings) loads unchanged."""
    isolated["seen_path"].write_text(json.dumps(["openrouter/old-model"]))
    assert model_sync._load_seen() == {"openrouter/old-model"}


def test_old_seen_file_entry_with_marker_still_loads(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An old file that already carries a basename-marker entry loads it."""
    isolated["seen_path"].write_text(
        json.dumps(
            [
                "plain/id-one",
                "minimax/minimax-m3 [basename=openrouter/minimax/minimax-m3]",
            ]
        )
    )
    seen = model_sync._load_seen()
    assert "plain/id-one" in seen
    assert "minimax/minimax-m3 [basename=openrouter/minimax/minimax-m3]" in seen


def test_marked_entry_filters_the_diff_again(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tomorrow's run: a seen basename-marked entry filters the diff again.

    The seen-file marker is not decoration — the ``--diff`` filter consumes it
    (prefix match on the candidate's resolved id) so a marked model never
    re-reports as a headline find, even when it reaches format_report() as a
    hand-built candidate row.
    """
    isolated["seen_path"].write_text(
        json.dumps(["minimax/minimax-m3 [basename=openrouter/minimax/minimax-m3]"])
    )
    candidates = {"minimax": [_core_candidate("minimax/minimax-m3")]}
    report = model_sync.format_report(candidates, diff_only=True)
    assert "Candidates: 0 new models" in report
    assert "| `minimax/minimax-m3` |" not in report
    assert "  minimax/minimax-m3" not in report


def test_plain_seen_entry_still_filters_the_diff(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-marker exact-id diff filter is unchanged."""
    isolated["seen_path"].write_text(json.dumps(["minimax/minimax-m3"]))
    candidates = {"minimax": [_core_candidate("minimax/minimax-m3")]}
    report = model_sync.format_report(candidates, diff_only=True)
    assert "Candidates: 0 new models" in report
    assert "  minimax/minimax-m3" not in report


# --- report honesty --------------------------------------------------------- #


def test_report_names_basename_skip_instead_of_silently_dropping(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SKIP goes on the report, naming the catalog entry that matched."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    report = model_sync.format_report(model_sync.scan_models_dev(isolated["cache"]))

    assert "SKIP" in report
    assert "minimax/minimax-m3" in report
    assert "openrouter/minimax/minimax-m3" in report
    assert "basename" in report
    assert "Candidates: 1 new models across 1 providers" in report


def test_report_skip_line_supports_markdown(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SKIP line renders in the markdown report path too (--output)."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    report = model_sync.format_report(model_sync.scan_models_dev(isolated["cache"]), markdown=True)
    assert "SKIP" in report
    assert "openrouter/minimax/minimax-m3" in report
    assert "**Candidates:** 1 new models across 1 providers" in report


def test_scan_all_applies_basename_dedupe(isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: scan_all() dedupes by basename through the same helper."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"openrouter/minimax/minimax-m3"})
    candidates, _watch, _blind, scope = model_sync.scan_all()
    assert "minimax" not in candidates  # basename-matched row skipped
    assert "google" in candidates  # genuinely-new row survives
    assert scope["core"] == sorted(model_sync._measured_core_labs(isolated["cache"]))
    assert isinstance(scope["out_of_scope"], int)
    assert scope["out_of_scope"] >= 0


# --- pre-existing contract: exact candidates still flow --------------------- #


def test_report_without_catalog_still_counts_candidates(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No catalog match anywhere → the full pre-fix report behaviour."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
    candidates = {"minimax": [_core_candidate("minimax/brand-new-model")]}
    report = model_sync.format_report(candidates)
    assert "Candidates: 1 new models" in report
    seen = json.loads(isolated["seen_path"].read_text())
    assert "minimax/brand-new-model" in seen
