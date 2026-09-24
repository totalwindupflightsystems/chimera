"""CH-GAP-053 (rework): explicit-config providers are separated from discovered.

``load_config`` auto-discovery merges models.dev providers into
``config.providers``, which made ``/v1/health``'s ``providers_configured``
count silently drift upward with whatever discovery found. The fix records
the explicitly-declared provider names at load time (an internal,
excluded-from-serialization set) and splits the health details:

* ``providers_configured`` — providers the YAML (or a programmatic fixture)
  declared, never the discovery-added ones;
* ``providers_discovered`` — sorted names present in ``cfg.providers`` but
  not in the configured set (additive field).

Programmatically built ``ChimeraConfig`` fixtures carry no load-time
metadata, so they keep the backward-compatible meaning: every current
``providers`` entry counts as configured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig, load_config  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402


def _yaml_doc() -> dict:
    """A minimal config declaring exactly one provider: ``declared``."""
    return {
        "providers": {"declared": {"base_url": "https://declared.example/v1"}},
        "models": {
            "declared/model-a": {"provider": "declared", "cost_tier": "budget"},
        },
        "defaults": {
            "dispatcher": "declared/model-a",
            "default_worker": "declared/model-a",
            "default_aggregator": "declared/model-a",
        },
    }


def _fake_discovery(extra: dict[str, str]):
    """A deterministic stand-in for ``discover_providers`` (no network)."""

    def fake(api_keys: dict | None = None):  # noqa: ARG001 - signature parity
        pricing: dict = {}
        providers = {name: {"base_url": f"https://{name}.example/v1"} for name in extra}
        return providers, pricing

    return fake


def _health_client(cfg: ChimeraConfig) -> TestClient:
    return TestClient(create_app(config=cfg, engine=Engine(cfg, FakeGateway())))


def _stub_probe(status: dict[str, dict]):
    async def probe(config: ChimeraConfig, gateway: object) -> dict[str, dict]:
        return status

    return probe


# --------------------------------------------------------------------------- #
# load_config records the declared provider names
# --------------------------------------------------------------------------- #


def test_load_config_records_declared_names_not_discovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery adds ``phantom``; the internal set still says ``declared``."""
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(_yaml_doc()), encoding="utf-8")
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        _fake_discovery({"phantom"}),
    )

    cfg = load_config(path)

    assert cfg.configured_provider_names == {"declared"}
    # Discovery still merged phantom into the live provider map.
    assert set(cfg.providers) == {"declared", "phantom"}


def test_load_config_records_declared_names_with_discovery_disabled(
    tmp_path: Path,
) -> None:
    """No discovery: the set equals the declared names verbatim."""
    doc = _yaml_doc()
    doc["provider_discovery"] = False
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    cfg = load_config(path)

    assert cfg.configured_provider_names == {"declared"}


def test_declared_names_field_is_internal_and_never_serialized() -> None:
    """The field is excluded from model dumps — no YAML round-trip surface."""
    cfg = ChimeraConfig.model_validate(_yaml_doc())

    assert "configured_provider_names" not in cfg.model_dump()
    assert "configured_provider_names" not in cfg.model_dump_json()


# --------------------------------------------------------------------------- #
# /v1/health separates configured from discovered
# --------------------------------------------------------------------------- #


def test_health_separates_declared_from_discovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: 1 configured + phantom discovered; the map shows both."""
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(_yaml_doc()), encoding="utf-8")
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        _fake_discovery({"phantom"}),
    )
    cfg = load_config(path)
    monkeypatch.setattr(
        "chimera.api.server._check_providers",
        _stub_probe(
            {
                "declared": {"healthy": True, "model_tested": "declared/model-a"},
                "phantom": {"healthy": True, "model_tested": "phantom/model-x"},
            }
        ),
    )

    data = _health_client(cfg).get("/v1/health").json()
    details = data["details"]

    assert data["status"] == "healthy"
    # The count that used to drift with discovery is now explicit-only.
    assert details["providers_configured"] == 1
    # Discovered providers are reported separately (sorted, deterministic).
    assert details["providers_discovered"] == ["phantom"]
    # The provider map still shows both — no discovery information is lost.
    assert set(details["providers"]) == {"declared", "phantom"}


def test_health_programmatic_config_counts_current_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fixture built in code has no load metadata: backward-compatible.

    Every current ``providers`` entry counts as configured and nothing is
    reported as discovered — the old ``== len(cfg.providers)`` contract.
    """
    cfg = ChimeraConfig.model_validate(_yaml_doc())
    cfg.providers["lonely"] = cfg.providers["declared"].model_copy(
        update={"base_url": "https://lonely.example/v1"},
    )
    monkeypatch.setattr(
        "chimera.api.server._check_providers",
        _stub_probe(
            {
                "declared": {"healthy": True, "model_tested": "declared/model-a"},
                "lonely": {"healthy": True, "model_tested": "declared/model-b"},
            }
        ),
    )

    data = _health_client(cfg).get("/v1/health").json()
    details = data["details"]

    assert details["providers_configured"] == len(cfg.providers) == 2
    assert details["providers_discovered"] == []


def test_health_details_shape_adds_only_the_discovered_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Additive: every pre-existing details key stays, one key is added."""
    cfg = ChimeraConfig.model_validate(_yaml_doc())
    monkeypatch.setattr(
        "chimera.api.server._check_providers",
        _stub_probe({"declared": {"healthy": True, "model_tested": "declared/model-a"}}),
    )

    details = _health_client(cfg).get("/v1/health").json()["details"]

    assert set(details) == {
        "config_loaded",
        "models_configured",
        "providers_configured",
        "providers_discovered",
        "commit",
        "version",
        "providers",
    }
