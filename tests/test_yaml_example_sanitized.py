"""REV-CHIMERA-V2-20261005-3: the public example must not leak internal topology.

``chimera.yaml.example`` is tracked AND shipped in the wheel (force-include,
``pyproject.toml``), so it publishes to PyPI and the public GitHub mirror. The
1671-line operator config it used to carry named internal infrastructure:
the tailnet hostname ``master001``, a "Vegas hosts" comment, and internal
gateway ports ``8642`` / ``20128`` / ``3456`` — all resolved from a public
artifact. The split:

* ``chimera.yaml.example`` — minimal, public-safe starter (<=120 lines) that
  still boots chimera (``chimera config init`` copies it);
* ``chimera.yaml.fleet`` — the full operator reference, tracked in the
  checkout only and deliberately NOT force-included into the wheel, so the
  internal topology stops travelling with the published artifact. Its
  sensitive values are the same class the live ``chimera.yaml`` already keeps
  local-only (DF-CHIMERA-0916B-4); env-indirect credentials
  (``${ENV_VAR}``) are the one credential shape allowed in either file.

This module pins the public surface. The fleet file is only checked for
existence + YAML parseability here — its internal content is the operator's
business, not the public mirror's.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "chimera.yaml.example"
FLEET = REPO_ROOT / "chimera.yaml.fleet"

#: Internal-topology tokens that must never appear in the published artifact.
LEAK_TOKENS = ("master001", "8642", "20128", "3456")

#: The example is a MINIMAL starter — a silent regrowth of the old 1671-line
#: operator config would re-open the leak surface this task closed.
MAX_EXAMPLE_LINES = 120


def test_example_contains_no_internal_topology() -> None:
    """No tailnet hostname, no internal gateway port, anywhere in the example."""
    text = EXAMPLE.read_text(encoding="utf-8")
    for token in LEAK_TOKENS:
        assert token not in text, (
            f"chimera.yaml.example leaks internal topology token {token!r} — "
            f"move that entry to chimera.yaml.fleet (REV-CHIMERA-V2-20261005-3)"
        )


def test_example_stays_minimal() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) <= MAX_EXAMPLE_LINES, (
        f"chimera.yaml.example grew to {len(lines)} lines (max {MAX_EXAMPLE_LINES}) — "
        f"it is the minimal public starter; full operator config belongs in "
        f"chimera.yaml.fleet"
    )


def test_example_is_valid_yaml_and_boots() -> None:
    """The minimal example is a bootable config, not decoration.

    Same top-level structure contract as before the split: chimera
    ``config init`` copies this file and the result must load.
    """
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict) and raw, "example must be a non-empty YAML mapping"
    for section in ("api_keys", "defaults", "formations", "providers"):
        assert section in raw, f"example lost its {section!r} section"
    # Credentials stay env-indirect — never literal key material.
    for _name, value in raw["api_keys"].items():
        assert str(value).startswith("${"), (
            f"api_keys entry {_name!r} must use ${{ENV_VAR}} indirection, got {value!r}"
        )
    # No provider may inline a credential either.
    for _name, provider in raw["providers"].items():
        assert "api_key" not in provider, (
            f"provider {_name!r} must not inline api_key — use api_key_env or api_keys entries"
        )


def test_example_boots_through_load_config() -> None:
    """The shipped example round-trips through the real config loader."""
    from chimera.config import ChimeraConfig, load_config

    config = load_config(EXAMPLE)
    assert isinstance(config, ChimeraConfig)
    assert config.formations, "the example must define at least one formation"
    assert config.defaults.dispatcher, "the example must name a dispatcher model"


def test_fleet_reference_exists_and_parses() -> None:
    """The operator reference replaced the old example — present and valid YAML.

    Line-count is checked loosely: the fleet file is the >=1600-line operator
    config the example used to be. Content assertions stop here on purpose —
    it lives in the checkout, not the wheel.
    """
    assert FLEET.is_file(), "chimera.yaml.fleet missing — the operator reference must stay tracked"
    text = FLEET.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 1600, "chimera.yaml.fleet lost its fleet-scale content"
    raw = yaml.safe_load(text)
    assert isinstance(raw, dict) and raw, "fleet reference must be a non-empty YAML mapping"
    assert "formations" in raw and "providers" in raw


def test_fleet_reference_is_not_wheel_shipped() -> None:
    """The leak fix is the packaging boundary: fleet stays out of the wheel.

    ``pyproject.toml`` force-includes the example + docker templates; if the
    fleet file is ever added there, the internal topology ships to PyPI again.
    Parsed structurally (tomllib), not grepped — the sdist exclude section
    below legitimately names the file.
    """
    import tomllib

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    leaked = [src for src in force_include if "chimera.yaml.fleet" in src]
    assert not leaked, (
        f"chimera.yaml.fleet is force-included into the wheel ({leaked}) — it "
        f"carries internal topology and must stay checkout-only"
    )
    # The sdist must be fenced too: `python -m build` produces both artifacts
    # and the release workflow uploads dist/*, so wheel-only exclusion leaks.
    sdist = data["tool"]["hatch"]["build"]["targets"].get("sdist", {})
    assert "chimera.yaml.fleet" in sdist.get("exclude", []), (
        "chimera.yaml.fleet missing from the sdist exclude list — the sdist would ship it to PyPI"
    )


# DF-CHIMERA-V2-92: the checks above grade the SOURCE (pyproject mapping, repo
# files). A stale or mis-built archive can still leak the operator config, so
# this test grades the BUILT artifact bytes: it builds the real wheel + sdist
# from this checkout into a tmp dir via the PEP 517 backend and inspects the
# archive members. No network, no build isolation (hatchling is a dev dep), no
# writes outside tmp_path, no dependency on any pre-existing dist/ artifact.
_BUILD_SNIPPET = (
    "import sys, hatchling.build as backend;backend.build_wheel(sys.argv[1]);backend.build_sdist(sys.argv[2])"
)


def _build_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    """Build the wheel and sdist from this checkout; return (whl, sdist) paths."""
    import subprocess
    import sys

    wheel_dir = tmp_path / "wheel"
    sdist_dir = tmp_path / "sdist"
    wheel_dir.mkdir()
    sdist_dir.mkdir()
    proc = subprocess.run(
        [sys.executable, "-c", _BUILD_SNIPPET, str(wheel_dir), str(sdist_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"PEP 517 build failed (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    wheels = list(wheel_dir.glob("*.whl"))
    sdists = list(sdist_dir.glob("*.tar.gz"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    assert len(sdists) == 1, f"expected exactly one sdist, got {sdists}"
    return wheels[0], sdists[0]


def test_built_artifacts_exclude_fleet_config(tmp_path: Path) -> None:
    """The published artifacts themselves must not carry the fleet config.

    Asserts on the BUILT bytes, not the checkout:
    1. chimera.yaml.fleet is absent from both the wheel and the sdist;
    2. chimera/chimera.yaml.example IS in the wheel and its bytes carry no
       internal topology tokens;
    3. the sdist still ships the (sanitized) example at its root.
    """
    import tarfile
    import zipfile

    wheel, sdist = _build_artifacts(tmp_path)

    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        leaked = [n for n in names if "chimera.yaml.fleet" in n]
        assert not leaked, (
            f"wheel ships the fleet config ({leaked}) — internal topology would publish to PyPI"
        )
        assert "chimera/chimera.yaml.example" in names, (
            f"wheel lost the force-included example; members: {sorted(names)[:20]}…"
        )
        example_bytes = zf.read("chimera/chimera.yaml.example").decode("utf-8")
        for token in LEAK_TOKENS:
            assert token not in example_bytes, (
                f"built wheel's chimera/chimera.yaml.example leaks internal topology token {token!r}"
            )

    with tarfile.open(sdist) as tf:
        names = tf.getnames()
        leaked = [n for n in names if "chimera.yaml.fleet" in n]
        assert not leaked, f"sdist ships the fleet config ({leaked}) — twine uploads dist/* wholesale"
        assert any(n.endswith("/chimera.yaml.example") for n in names), (
            f"sdist lost the example; members: {sorted(names)[:20]}…"
        )
