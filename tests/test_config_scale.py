"""Category-score scale enforcement (INT-API-002).

Measured defect, frozen 2026-09-18 (HEAD f09c8cd): ``docs/CONFIG.md`` documented
``categories:`` as *0.0-1.0* scores (with a ``0.90`` sample) while the shipped
templates (``chimera.yaml.example`` / ``chimera.yaml.docker``), the live
``chimera.yaml`` and ``GET /v1/models`` all carried 0-100 values (live: 42
models / 1175 values, min 60.0, max 98.0).  ``CategorySelector.score``
multiplies the raw value with no rescale, so a model configured from the docs
landed ~100x below every peer — silently never selected, with no warning.

The contract this module pins:

* percent (0-100) is the ONE canonical scale;
* a catalog written from the docs (nothing above 1.0) is rescaled x100 on load,
  so it competes instead of starving;
* a docs-style value mixed into a percent catalog is rescaled with ONE warning
  per affected model+path — and a previously-percent value is never touched;
* out-of-range / non-numeric / NaN / infinite scores are rejected with ONE
  actionable line (no traceback, non-zero CLI exit);
* enforcement happens at ONE choke point (``load_config``), so no entry point
  can bypass it.

Warnings are asserted with ``structlog.testing.capture_logs()`` — the
codebase's logger is structlog writing to a stream via ``PrintLoggerFactory``
(the pattern ``tests/test_aggregator.py`` / ``tests/test_blocked_models.py``
already use), so ``caplog`` — which hooks stdlib ``logging`` — never sees these
records.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog.testing
import yaml

import chimera.config as config_mod
from chimera.config import load_config
from chimera.exceptions import ConfigError
from chimera.selector import CategorySelector, task_to_paths

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

#: Task that resolves to the code-generation paths the fixtures score on.
CODE_TASK = "write a python script that runs a sql query"

PY_PATH = "technology_code/code_generation/python"
SQL_PATH = "technology_code/code_generation/sql"


def _base_doc(models: dict) -> dict:
    """A minimal loadable document around *models* (one provider, no live calls)."""
    return {
        "providers": {"deepseek": {"base_url": "https://api.deepseek.com/v1"}},
        "models": models,
        "defaults": {
            "dispatcher": "deepseek/peer-a",
            "default_worker": "deepseek/peer-a",
            "default_aggregator": "deepseek/peer-a",
        },
        "formations": {"auto": {"mode": "auto"}},
    }


def _write(tmp_path: Path, models: dict, name: str = "chimera.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(_base_doc(models)), encoding="utf-8")
    return path


def _entry(categories: dict) -> dict:
    return {"categories": categories, "cost_tier": "budget", "provider": "deepseek"}


#: Two template-style (percent) peers, mirroring chimera.yaml.example weights.
PEER_PERCENT = {
    "deepseek/peer-a": _entry({PY_PATH: 88, SQL_PATH: 80}),
    "deepseek/peer-b": _entry({PY_PATH: 82, SQL_PATH: 78}),
}

#: The docs sample scale: 0.90 / 0.80 (docs/CONFIG.md, README.md, OPENAI_API.md).
DOCS_STYLE = {"deepseek/docs-style": _entry({PY_PATH: 0.90, SQL_PATH: 0.80})}


def _normalisation_records(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["event"] == "category_scale_normalized"]


# --------------------------------------------------------------------------- #
# A. mixed catalog: the docs-style entry is normalised, the peers are not
# --------------------------------------------------------------------------- #


def test_mixed_scale_catalog_normalises_docs_style_model(tmp_path: Path) -> None:
    """One docs-style model in a percent catalog → 0.90 normalised to 90.0."""
    path = _write(tmp_path, {**PEER_PERCENT, **DOCS_STYLE})

    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    assert cfg.models["deepseek/docs-style"].categories[PY_PATH] == 90.0
    assert cfg.models["deepseek/docs-style"].categories[SQL_PATH] == 80.0
    # Peers were already percent — byte-identical, untouched.
    assert cfg.models["deepseek/peer-a"].categories == {PY_PATH: 88, SQL_PATH: 80}
    assert cfg.models["deepseek/peer-b"].categories == {PY_PATH: 82, SQL_PATH: 78}

    records = _normalisation_records(logs)
    assert len(records) == 2, records
    by_path = {record["path"]: record for record in records}
    assert set(by_path) == {PY_PATH, SQL_PATH}
    assert by_path[PY_PATH]["model"] == "deepseek/docs-style"
    assert by_path[PY_PATH]["old"] == 0.9
    assert by_path[PY_PATH]["new"] == 90.0
    assert by_path[SQL_PATH]["old"] == 0.8
    assert by_path[SQL_PATH]["new"] == 80.0
    # The warning names the model and the path — not just "something moved".
    for record in records:
        assert record["model"] == "deepseek/docs-style"
        assert record["log_level"] == "warning"


# --------------------------------------------------------------------------- #
# B. the normalised model competes (score printed, pre-fix vs post-fix)
# --------------------------------------------------------------------------- #


def test_docs_style_model_competes_after_normalisation(tmp_path: Path) -> None:
    """Selector.score() for the docs-style model is in its peers' range.

    The pre-fix control is the SAME fixture handed to the selector the way
    ``load_config`` used to hand it over: raw values, no normalisation.  That is
    the measured defect (docs-scale model ~100x below every peer).
    """
    path = _write(tmp_path, {**PEER_PERCENT, **DOCS_STYLE})
    cfg = load_config(path)

    post = CategorySelector(cfg.models).score(CODE_TASK)

    from chimera.config import ModelEntry

    raw_models = {
        "deepseek/peer-a": ModelEntry(**_entry({PY_PATH: 88, SQL_PATH: 80})),
        "deepseek/peer-b": ModelEntry(**_entry({PY_PATH: 82, SQL_PATH: 78})),
        "deepseek/docs-style": ModelEntry(**_entry({PY_PATH: 0.90, SQL_PATH: 0.80})),
    }
    pre = CategorySelector(raw_models).score(CODE_TASK)

    # Pre-fix: the docs-style model is ~100x below its peers.
    assert pre["deepseek/docs-style"] < 1.0, pre
    assert pre["deepseek/docs-style"] < pre["deepseek/peer-a"] / 50, pre

    # Post-fix: same order of magnitude as both peers (0.90 * 100 == 90).
    peers = (post["deepseek/peer-a"], post["deepseek/peer-b"])
    assert post["deepseek/docs-style"] > 0, post
    assert min(peers) / 2 <= post["deepseek/docs-style"] <= max(peers) * 2, post
    # Exact number, not a hand-wave: recompute the expected weighted sum from
    # the task weights and the normalised scores independently of the selector.
    weights = task_to_paths(CODE_TASK)
    expected = sum(
        weights[path] * score
        for path, score in ((PY_PATH, 90.0), (SQL_PATH, 80.0))
    )
    assert post["deepseek/docs-style"] == pytest.approx(expected), post


# --------------------------------------------------------------------------- #
# C. pure unit-scale catalog: rescaled x100, ranking order unchanged
# --------------------------------------------------------------------------- #


def _unit_models() -> dict:
    return {
        "deepseek/unit-a": _entry({"code": 0.95, "analysis": 0.70}),
        "deepseek/unit-b": _entry({"code": 0.88, "analysis": 0.90}),
        "deepseek/unit-c": _entry({"code": 0.70, "analysis": 0.75}),
    }


def test_pure_unit_scale_catalog_is_rescaled_x100(tmp_path: Path) -> None:
    path = _write(tmp_path, _unit_models())

    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    assert cfg.models["deepseek/unit-a"].categories == {"code": 95.0, "analysis": 70.0}
    assert cfg.models["deepseek/unit-b"].categories == {"code": 88.0, "analysis": 90.0}
    assert cfg.models["deepseek/unit-c"].categories == {"code": 70.0, "analysis": 75.0}

    records = _normalisation_records(logs)
    # ONE warning for the whole catalog, naming how many models were rescaled.
    assert len(records) == 1, records
    assert records[0]["models"] == 3
    assert records[0]["categories"] == 6
    assert records[0]["factor"] == 100


def test_unit_scale_rescale_preserves_ranking_order(tmp_path: Path) -> None:
    """x100 is a uniform factor: the ranking is identical before and after."""
    path = _write(tmp_path, _unit_models())

    from chimera.config import ModelEntry

    pre_scores = CategorySelector(
        {name: ModelEntry(**body) for name, body in _unit_models().items()}
    ).score(CODE_TASK)
    cfg = load_config(path)
    post_scores = CategorySelector(cfg.models).score(CODE_TASK)

    pre_order = [name for name, _ in sorted(pre_scores.items(), key=lambda kv: -kv[1])]
    post_order = [name for name, _ in sorted(post_scores.items(), key=lambda kv: -kv[1])]
    assert pre_order == post_order == ["deepseek/unit-a", "deepseek/unit-b", "deepseek/unit-c"]
    # Same order AND exactly 100x the pre-normalisation score.
    for name, value in pre_scores.items():
        assert post_scores[name] == pytest.approx(value * 100, rel=1e-9), (name, value)


# --------------------------------------------------------------------------- #
# D. rejections: ONE actionable line, no traceback
# --------------------------------------------------------------------------- #


def _message(tmp_path: Path, models: dict) -> str:
    path = _write(tmp_path, models)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    message = str(excinfo.value)
    assert "\n" not in message, f"expected ONE line, got: {message!r}"
    return message


@pytest.mark.parametrize("value", [150, -5, 100.5])
def test_out_of_range_score_is_rejected(tmp_path: Path, value: float) -> None:
    message = _message(tmp_path, {"deepseek/bad": _entry({"code": value})})
    assert "invalid category score" in message
    assert str(tmp_path / "chimera.yaml") in message      # the file being loaded
    assert "'deepseek/bad'" in message                    # model id
    assert "'code'" in message                            # category path
    assert repr(float(value)) in message                  # offending value
    assert "0-100" in message                             # accepted range
    assert "0.0-1.0" in message and "rescaled" in message  # documented exception


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_score_is_rejected(tmp_path: Path, value: float) -> None:
    message = _message(tmp_path, {"deepseek/bad": _entry({"code": value})})
    assert "not a finite number" in message
    assert "'deepseek/bad'" in message and "'code'" in message
    assert str(tmp_path / "chimera.yaml") in message


def test_non_numeric_score_is_rejected(tmp_path: Path) -> None:
    """A string score fails in pydantic — translated to the same one-liner."""
    message = _message(tmp_path, {"deepseek/bad": _entry({"code": "high"})})
    assert "not a number" in message
    assert "'deepseek/bad'" in message and "'code'" in message
    assert "0-100" in message
    assert str(tmp_path / "chimera.yaml") in message


def test_cli_out_of_range_config_is_one_line_and_non_zero(tmp_path: Path) -> None:
    """The user-facing edge: one actionable line, exit 2, no traceback."""
    path = _write(tmp_path, {"deepseek/bad": _entry({PY_PATH: 150})})
    result = CliRunner().invoke(main, ["-c", str(path), "models"])

    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
    assert "invalid category score" in result.output
    assert "'deepseek/bad'" in result.output
    assert PY_PATH in result.output
    assert "150" in result.output
    # Exactly one non-empty line of error text.
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1, lines


def test_cli_non_numeric_config_is_one_line_and_non_zero(tmp_path: Path) -> None:
    path = _write(tmp_path, {"deepseek/bad": _entry({"code": "high"})})
    result = CliRunner().invoke(main, ["-c", str(path), "models"])

    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
    assert "not a number" in result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1, lines


# --------------------------------------------------------------------------- #
# E. no regression: shipped templates and already-percent catalogs are untouched
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("template", ["chimera.yaml.example", "chimera.yaml.docker"])
def test_shipped_template_values_are_byte_identical(template: str) -> None:
    """Percent catalogs load with EXACTLY the raw YAML values (no translation)."""
    raw = yaml.safe_load((REPO / template).read_text(encoding="utf-8"))

    with structlog.testing.capture_logs() as logs:
        cfg = load_config(REPO / template)

    checked = 0
    for model_id, entry in raw["models"].items():
        for category_path, value in (entry.get("categories") or {}).items():
            assert cfg.models[model_id].categories[category_path] == value, (
                model_id, category_path, value, cfg.models[model_id].categories[category_path]
            )
            assert isinstance(cfg.models[model_id].categories[category_path], float)
            checked += 1
    assert checked > 500, f"expected the full template catalog, checked {checked}"
    # No rescale happened, so no warning may be emitted at all.
    assert _normalisation_records(logs) == []


def test_already_percent_catalog_emits_no_warning(tmp_path: Path) -> None:
    path = _write(tmp_path, {"deepseek/pct": _entry({"code": 60, "analysis": 98})})
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    assert cfg.models["deepseek/pct"].categories == {"code": 60, "analysis": 98}
    assert _normalisation_records(logs) == []


def test_shared_suite_catalog_fixture_is_already_percent(tmp_path: Path) -> None:
    """The shared ``tests/conftest.py`` catalog must stay on the canonical scale.

    That fixture claims to mirror ``chimera.yaml.example`` (percent) and is
    loaded through ``load_config`` by most of the suite — the CLI and
    output-mode tests assert on the channels a rescale warning would land on.
    If it ever drifts back to 0.0-1.0, every one of those tests inherits a
    ``category_scale_normalized`` record. Loading it verbatim must therefore
    emit NOTHING and hand back exactly the configured values.
    """
    from tests.conftest import CONFIG_DICT

    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")

    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    for model_id, entry in CONFIG_DICT["models"].items():
        assert cfg.models[model_id].categories == entry["categories"], model_id
    assert _normalisation_records(logs) == []


def test_boundary_values_one_and_zero_are_normalised_not_rejected(tmp_path: Path) -> None:
    """1.0 is inside the rescaled interval; 0.0 is a legitimate untouched zero."""
    path = _write(tmp_path, {
        "deepseek/percent-peer": _entry({"code": 90}),
        "deepseek/edge": _entry({"code": 1.0, "analysis": 0.0}),
    })
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    assert cfg.models["deepseek/edge"].categories == {"code": 100.0, "analysis": 0.0}
    records = _normalisation_records(logs)
    # Only the 1.0 value is "affected": 0.0 * 100 == 0.0, so it is not reported.
    assert len(records) == 1, records
    assert records[0]["path"] == "code"
    assert records[0]["old"] == 1.0 and records[0]["new"] == 100.0


# --------------------------------------------------------------------------- #
# F. one choke point: load_config is the only path that normalises
# --------------------------------------------------------------------------- #


def test_load_config_is_the_single_normalisation_choke_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every entry point loads through load_config, so enforcement lives there."""
    calls: list[object] = []
    real = config_mod._normalize_category_scales

    def spy(config: object, config_path: object = None) -> None:
        calls.append(config)
        real(config, config_path)  # type: ignore[arg-type]

    monkeypatch.setattr(config_mod, "_normalize_category_scales", spy)
    path = _write(tmp_path, {**PEER_PERCENT, **DOCS_STYLE})
    cfg = load_config(path)

    assert len(calls) == 1, "load_config must call the normaliser exactly once"
    assert cfg.models["deepseek/docs-style"].categories[PY_PATH] == 90.0


# --------------------------------------------------------------------------- #
# G. the warning channel must not depend on which structlog config ran first
# --------------------------------------------------------------------------- #


def test_warning_capture_survives_a_structlog_repin(tmp_path: Path) -> None:
    """Capturing the warning must not depend on the run order of earlier tests.

    ``observability.configure_logging`` installs a FRESH processor list on every
    sink/level re-pin (every CLI / API / MCP entry point calls it), and it sets
    ``cache_logger_on_first_use=True``. A module-level ``structlog.get_logger()``
    proxy binds once — to whichever list was live at its first emission — so
    after any earlier test triggered a warning (this module's first test does)
    this capture came back EMPTY: the record was rendered by the logger's old
    pipeline instead of the capturing one. The fix resolves the logger per
    emission, so the capture below is order-independent — the FULL suite, not
    this file alone, is the proof that it holds.
    """
    from chimera.config import Observability
    from chimera.observability import configure_logging

    # Stand in for any earlier entry point (a CLI test's config load, a
    # create_app()ed server, the MCP stdio pin) re-pinning structlog.
    configure_logging(Observability(use_stdout=False, langfuse={"enabled": False}),
                      force_stderr=True)

    path = _write(tmp_path, _unit_models())
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(path)

    records = _normalisation_records(logs)
    assert len(records) == 1, records
    assert records[0]["log_level"] == "warning"
    assert records[0]["models"] == 3
    assert cfg.models["deepseek/unit-a"].categories == {"code": 95.0, "analysis": 70.0}
