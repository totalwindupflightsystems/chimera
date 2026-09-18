"""INT-PKG-001 — a bare install must get the pip remedy, not a traceback.

``fastapi``/``uvicorn`` live in the optional ``[server]``/``[full]`` extras
(``pyproject.toml``), so ``pip install chimera-deliberation`` (base) has
neither and the ``chimera serve`` path died with a raw ``ModuleNotFoundError``
traceback from ``chimera.api.server``'s fastapi import. A user following the
documented install command must instead get ONE actionable line naming the
exact pip remedy and a nonzero exit.

Hermetic: no network, no provider key, no deliberation, no server started, and
no package is uninstalled. The remedy is driven through the
``chimera.cli.main._import_run_api`` seam (the one-line function the serve path
imports through) — a bare install cannot be reproduced in a venv that has
fastapi installed. The final case is the honest equivalence proof: a REAL CLI
subprocess with fastapi + uvicorn blocked at ``sys.meta_path`` by a
``sitecustomize`` shim.

The narrowness half matters as much as the remedy: an unrelated missing module
(a real packaging bug) must keep its traceback instead of being relabelled as a
missing extra, so the boundary is pinned on the predicate, on the re-raise
path, and through the CLI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from chimera.cli import main as cli_main
from chimera.cli.main import _missing_server_extra, main
from tests.conftest import CONFIG_DICT  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

#: The remedy strings the acceptance criteria require. They are compared as
#: plain substrings because rich markup would otherwise hide ``[server]`` —
#: the escalation this fix exists to prevent (``escape()`` in the handler keeps
#: the literal text on the wire).
REMEDY_SERVER = "pip install chimera-deliberation[server]"
REMEDY_FULL = "pip install chimera-deliberation[full]"

#: Every message must name the missing distribution AND the remedy.
_MISSING_NAMES = ("fastapi", "uvicorn", "uvicorn.loops")


@pytest.fixture
def serve_config(tmp_path) -> Path:  # type: ignore[no-untyped-def]
    """A valid chimera.yaml with provider discovery OFF.

    Discovery would fetch models.dev on every load; the serve path does not
    need it and a remedy test must not depend on the network (or on whatever
    the host's provider cache happens to hold).
    """
    cfg = dict(CONFIG_DICT)
    cfg["provider_discovery"] = False
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _raise_missing(name: str | None) -> Callable[[], Any]:
    """Return an ``_import_run_api`` stand-in that raises a missing module."""

    def _seam() -> Any:
        if name is None:
            raise ModuleNotFoundError("No module named")
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    return _seam


def _invoke(serve_config: Path, **kwargs: Any) -> Any:
    from click.testing import CliRunner

    return CliRunner(**kwargs).invoke(main, ["-c", str(serve_config), "serve"])


# ---------------------------------------------------------------------------
# The remedy: nonzero exit, no traceback, wording that names the extras
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", _MISSING_NAMES)
def test_serve_missing_server_extra_names_the_remedy(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """A missing [server] extra → one actionable line naming [server] and [full]."""
    monkeypatch.setattr(cli_main, "_import_run_api", _raise_missing(missing))

    result = _invoke(serve_config)

    assert result.exit_code == 2, result.output
    assert REMEDY_SERVER in result.stderr, result.stderr
    assert REMEDY_FULL in result.stderr, result.stderr
    assert f"{missing!r}" in result.stderr, result.stderr
    assert "error:" in result.stderr
    assert "Traceback" not in result.output
    # Diagnostics stay off stdout (DF-CHIMERA-V2-3 house rule).
    assert result.stdout == ""


def test_serve_missing_extra_remedy_is_one_line_at_80_columns(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remedy survives a narrow terminal as ONE logical line.

    Mirrors the CH-GAP-050/DF-CHIMERA-V2-8 contract: the message names two
    install commands, so rich's default hard-wrap would split the remedy across
    lines — and can break inside the ``pip install`` string itself. ``soft_wrap``
    keeps the byte stream one line at any width.
    """
    monkeypatch.setattr(cli_main, "_import_run_api", _raise_missing("fastapi"))

    result = _invoke(serve_config, env={"COLUMNS": "80"})

    assert result.exit_code == 2, result.output
    assert result.stderr.count("\n") == 1, repr(result.stderr)
    assert REMEDY_SERVER in result.stderr
    assert REMEDY_FULL in result.stderr


def test_serve_missing_extra_remedy_names_the_pip_command_not_just_the_extra(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message must be runnable: ``pip install <dist>[server]``, not a bare extra name."""
    monkeypatch.setattr(cli_main, "_import_run_api", _raise_missing("fastapi"))

    result = _invoke(serve_config)

    assert "pip install" in result.stderr
    assert "chimera-deliberation" in result.stderr
    # Both extras are named, so a user who wants the web UI is not sent hunting.
    assert "[server]" in result.stderr and "[full]" in result.stderr


# ---------------------------------------------------------------------------
# Narrowness: unrelated import failures keep their traceback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["fastapi_utils", "uvicornw", "starlette", "chimera.api.server", None],
)
def test_serve_unrelated_missing_module_is_not_remedied(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch, name: str | None
) -> None:
    """Only a [server] extra module gets the remedy — everything else re-raises.

    ``fastapi_utils``/``uvicornw`` are the prefix-match trap (a naive
    ``startswith`` would report them as the extra);
    ``chimera.api.server`` is a missing package module (a broken install, not a
    missing extra); ``None`` is a ModuleNotFoundError with no ``name``.
    """
    monkeypatch.setattr(cli_main, "_import_run_api", _raise_missing(name))

    result = _invoke(serve_config)

    assert isinstance(result.exception, ModuleNotFoundError), result.output
    assert result.exit_code != 0
    assert REMEDY_SERVER not in result.output
    assert REMEDY_FULL not in result.output


def test_serve_unrelated_missing_module_propagates_uncaught(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With catch_exceptions off the ORIGINAL error surfaces (no SystemExit(2) swallow)."""
    monkeypatch.setattr(cli_main, "_import_run_api", _raise_missing("fastapi_utils"))

    with pytest.raises(ModuleNotFoundError) as excinfo:
        _invoke(serve_config, catch_exceptions=False)

    assert "fastapi_utils" in str(excinfo.value)


def test_missing_server_extra_predicate_boundary() -> None:
    """``_missing_server_extra`` matches the extra's top-level names exactly."""
    for name in ("fastapi", "uvicorn", "fastapi.applications", "uvicorn.loops"):
        assert _missing_server_extra(ModuleNotFoundError("x", name=name)) is True, name

    for name in ("fastapi_utils", "uvicornw", "starlette", "chimera", "chimera.api.server", "", None):
        assert _missing_server_extra(ModuleNotFoundError("x", name=name)) is False, name

    # Not a ModuleNotFoundError at all: an installed-but-too-old fastapi
    # missing a symbol, and a non-import error.
    assert _missing_server_extra(ImportError("cannot import name 'X' from 'fastapi'")) is False
    assert _missing_server_extra(ValueError("nope")) is False


# ---------------------------------------------------------------------------
# The untouched half: normal serve + help
# ---------------------------------------------------------------------------


def test_serve_normal_path_still_forwards_host_and_port(
    serve_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the extra present, serve runs the server with config host/port."""
    captured: dict[str, Any] = {}

    def _seam() -> Any:
        return lambda host, port: captured.update({"host": host, "port": port})

    monkeypatch.setattr(cli_main, "_import_run_api", _seam)

    result = _invoke(serve_config)

    assert result.exit_code == 0, result.output
    # CONFIG_DICT ships server.host=127.0.0.1, server.port=8000.
    assert captured == {"host": "127.0.0.1", "port": 8000}


def test_serve_help_lists_host_and_port() -> None:
    """``serve --help`` is unchanged (and needs no [server] extra to answer)."""
    from click.testing import CliRunner

    result = CliRunner().invoke(main, ["serve", "--help"])

    assert result.exit_code == 0, result.output
    assert "--host" in result.output
    assert "--port" in result.output


# ---------------------------------------------------------------------------
# Bare-install equivalence: a real CLI subprocess with the extra blocked
# ---------------------------------------------------------------------------

#: Blocks the [server] extra at import time, exactly as a bare install lacks
#: it. Loaded via PYTHONPATH/sitecustomize so the CLI child needs no flags.
_SITECUSTOMIZE = """\
import sys

_BLOCKED = {'fastapi', 'uvicorn'}


class _BlockedServerExtra:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition('.')[0] in _BLOCKED:
            raise ModuleNotFoundError(f'No module named {fullname!r}', name=fullname)
        return None


sys.meta_path.insert(0, _BlockedServerExtra())
"""


def _bare_install_env(tmp_path: Path, serve_config: Path) -> dict[str, str]:
    """Env for a `python -m chimera` child that has no [server] extra installed."""
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir(exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["HOME"] = str(home)  # keep ~/.chimera state out of the real home
    env["CHIMERA_CONFIG"] = str(serve_config)
    env["PYTHONPATH"] = os.pathsep.join([str(shim_dir), str(REPO / "src")])
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_cli(args: list[str], env: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "chimera", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=120,
        check=False,
    )


def test_real_bare_install_serve_prints_the_remedy(tmp_path: Path, serve_config: Path) -> None:
    """The acceptance criterion, end to end: no fastapi → remedy, rc != 0, no traceback."""
    env = _bare_install_env(tmp_path, serve_config)

    proc = _run_cli(["serve"], env, tmp_path)

    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert proc.returncode == 2, combined
    assert REMEDY_SERVER in proc.stderr, (proc.stdout, proc.stderr)
    assert REMEDY_FULL in proc.stderr, (proc.stdout, proc.stderr)
    assert "fastapi" in proc.stderr, proc.stderr
    assert "Traceback" not in combined, combined
    assert proc.stdout == "", proc.stdout


def test_real_bare_install_serve_help_still_works(tmp_path: Path, serve_config: Path) -> None:
    """Help must not need the [server] extra — the bare install is still usable."""
    env = _bare_install_env(tmp_path, serve_config)

    proc = _run_cli(["serve", "--help"], env, tmp_path)

    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "--host" in proc.stdout
    assert "--port" in proc.stdout
