"""Tests for FormationPreset key validation and the auto-preset error (DF-CHIMERA-V2-59).

A typo'd preset key (``stages: 2`` instead of ``workers: 2``) used to be
silently dropped by pydantic's default ``extra="ignore"``, leaving the preset
all-``None``; the user then only saw the misleading "Cannot build a structural
DAG from an auto preset" error at deliberation time. Now:

* unknown keys raise a ``ValidationError`` at config load, naming the key;
* valid presets load and build the same structural DAG as before;
* the dispatcher's auto-preset ``ValueError`` names the ``workers`` field to set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from chimera.config import FormationPreset, load_config
from chimera.dispatcher import build_preset_dag

REPO_ROOT = Path(__file__).resolve().parent.parent


def _minimal_config_yaml(formations: dict) -> str:
    """A smallest viable chimera.yaml body with the given formations block."""
    doc = {
        "defaults": {
            "dispatcher": "zai-coding-plan/glm-5.2",
            "default_worker": "deepseek/deepseek-chat",
            "default_aggregator": "zai-coding-plan/glm-5.2",
        },
        "provider_discovery": False,
        "formations": formations,
    }
    return yaml.safe_dump(doc)


# --------------------------------------------------------------------------- #
# (a) unknown keys are rejected at config load, naming the key
# --------------------------------------------------------------------------- #


def test_load_config_rejects_unknown_formation_key(tmp_path: Path) -> None:
    """`formations.simple.stages: 2` fails AT LOAD, naming `stages`."""
    path = tmp_path / "chimera.yaml"
    path.write_text(
        _minimal_config_yaml({"simple": {"stages": 2, "aggregator": "default"}}),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="stages") as excinfo:  # noqa: PT011 - any load-time validation error is fine, the message is what matters
        load_config(path)
    # The pydantic report names the offending key and its full location.
    text = str(excinfo.value)
    assert "stages" in text
    assert "simple" in text


def test_formation_preset_rejects_unknown_key_directly() -> None:
    """The model itself (not only the YAML path) forbids extra keys."""
    with pytest.raises(Exception, match="stages"):  # noqa: PT011
        FormationPreset(stages=2, aggregator="default")


def test_shipped_example_formation_blocks_have_no_unknown_keys() -> None:
    """The tracked templates must stay valid under extra="forbid" (drift guard).

    If a shipped template grows a key FormationPreset does not declare, config
    load now fails for every fresh install — catch it here instead.
    """
    for name in ("chimera.yaml.example", "chimera.yaml.docker"):
        raw = yaml.safe_load((REPO_ROOT / name).read_text(encoding="utf-8"))
        for _fname, block in (raw.get("formations") or {}).items():
            FormationPreset.model_validate(block)  # raises on an unknown key
            assert isinstance(block, dict)


# --------------------------------------------------------------------------- #
# (b) a correct workers preset is unchanged
# --------------------------------------------------------------------------- #


def test_valid_workers_preset_loads_and_builds_same_dag(config) -> None:  # type: ignore[no-untyped-def]
    """`workers: 2` still builds the identical structural DAG (no behavior change)."""
    preset_from_config = config.formations["simple"]
    assert preset_from_config.workers == 2
    dag_config = build_preset_dag(preset_from_config, config)
    dag_programmatic = build_preset_dag(FormationPreset(workers=2, aggregator="default"), config)
    # Identical to the preset built by hand — the validation layer changed
    # nothing about construction of valid presets.
    assert dag_config == dag_programmatic
    kinds = sorted(s.kind for s in dag_config.stages)
    assert kinds == ["aggregator", "worker", "worker"]
    aggregator = dag_config.stage("aggregator")
    assert set(aggregator.depends_on) == {"worker_1", "worker_2"}


def test_valid_preset_round_trips_through_load_config(tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """A yaml formation with only known keys loads unchanged."""
    path = tmp_path / "chimera.yaml"
    path.write_text(
        _minimal_config_yaml({"simple": {"workers": 2, "aggregator": "default"}}),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.formations["simple"].workers == 2
    assert cfg.formations["simple"].aggregator == "default"
    assert cfg.formations["simple"].is_auto is False


# --------------------------------------------------------------------------- #
# (c) the auto-preset error is actionable
# --------------------------------------------------------------------------- #


def test_auto_preset_error_mentions_workers(config) -> None:  # type: ignore[no-untyped-def]
    """The auto-preset ValueError tells the user to set `workers: <N>`."""
    with pytest.raises(ValueError, match="workers"):
        build_preset_dag(config.formations["auto"], config)


def test_empty_preset_error_mentions_workers(config) -> None:  # type: ignore[no-untyped-def]
    """An all-None preset (the old silent-typo end state) gets the same advice."""
    with pytest.raises(ValueError, match="workers"):
        build_preset_dag(FormationPreset(), config)
