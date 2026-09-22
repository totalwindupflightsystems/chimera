"""Subprocess stdout-purity regression tests for the Click CLI.

DF-CHIMERA-V2-3: the CLI never called ``configure_logging``, so structlog's
UNCONFIGURED default wrote to stdout. Provider auto-discovery (which runs
INSIDE ``load_config`` → ``_apply_env_overrides`` → ``provider_discovery``)
logged ``provider_cache_hit`` / ``provider_fetch_ok`` /
``provider_discovery_done`` onto stdout ahead of the rich table/panel on
every ``chimera models`` / ``formations`` / deliberation invocation.

The fix (mirroring the MCP stdio fix, DF-CHIMERA-0906-2) is a two-phase
``configure_logging(..., force_stderr=True)`` pin in ``cli.main._load_cfg``:
phase 1 BEFORE ``load_config`` (catches pre-config discovery logs), phase 2
after a successful load with the real observability settings — both forced
to stderr, so a ``chimera.yaml`` ``observability.use_stdout: true`` flip
cannot undo the purity.

These tests spawn the REAL ``python -m chimera`` entry point as a
subprocess and assert on ``stdout`` / ``stderr`` SEPARATELY (click 9.x
``CliRunner(mix_stderr=...)`` raises TypeError, so CliRunner's merged
``result.output`` cannot prove stream purity). The env fixture mirrors
``test_mcp_stdio_purity.py``: isolated HOME, fresh offline provider cache,
and ``use_stdout: true`` in the temp config — proving the fix is
STRUCTURAL, not a config flip.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from tests.conftest import CONFIG_DICT

REPO = Path(__file__).resolve().parent.parent

#: structlog signatures that must NEVER appear on CLI stdout.
LOG_SIGNATURES = (
    "provider_cache_hit",
    "provider_fetch_ok",
    "provider_discovery_done",
    "provider_fetch_failed",
    '"event"',
    '"timestamp"',
    "'event':",
)

#: Provider discovery log events that MUST appear on stderr (proving logs
#: were REDIRECTED, not silenced).
REQUIRED_STDERR_EVENTS = ("provider_cache_hit", "provider_discovery_done")


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    """Isolated HOME + tmp chimera.yaml + fresh offline provider cache.

    Mirrors ``test_mcp_stdio_purity.py::mcp_env``. ``observability.use_stdout``
    is forced to ``true`` and ``log_level`` to ``info`` so the discovery
    events pass the filter and are observable — only a structural
    force-stderr fix can keep stdout clean under this config.
    """
    home = tmp_path / "home"
    (home / ".chimera").mkdir(parents=True)
    cache = {
        "_fetched_at": time.time(),
        "deepseek": {
            "env": ["DEEPSEEK_API_KEY"],
            "models": {"deepseek-chat": {"cost": {"input": 1.0, "output": 1.0}}},
        },
    }
    (home / ".chimera" / "models-dev-cache.json").write_text(json.dumps(cache), encoding="utf-8")

    cfg_dict = copy.deepcopy(CONFIG_DICT)
    cfg_dict["observability"] = {
        "log_level": "info",  # discovery events must pass the filter
        "trace_enabled": False,
        "use_stdout": True,  # config asks for stdout — the fix must override
        "langfuse": {"enabled": False},
    }
    cfg_dict["provider_discovery"] = True
    cfg_path = tmp_path / "chimera.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CHIMERA_CONFIG"] = str(cfg_path)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_cli(args: list[str], env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run ``python -m chimera`` with split stdout/stderr capture."""
    return subprocess.run(
        [sys.executable, "-m", "chimera", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=timeout,
        check=False,
    )


def _assert_stdout_pure(proc: subprocess.CompletedProcess[str]) -> None:
    """Fail with the offending lines if any log signature reached stdout."""
    hits = [sig for sig in LOG_SIGNATURES if sig in proc.stdout]
    assert not hits, (
        f"structlog/log signatures {hits} leaked onto stdout "
        f"(DF-CHIMERA-V2-3 regression):\n"
        f"--- stdout ---\n{proc.stdout[:2000]}\n"
        f"--- stderr ---\n{proc.stderr[:2000]}"
    )


def _assert_logs_on_stderr(proc: subprocess.CompletedProcess[str]) -> None:
    """Discovery events must be present on stderr — redirected, not silenced."""
    missing = [ev for ev in REQUIRED_STDERR_EVENTS if ev not in proc.stderr]
    assert not missing, (
        f"provider-discovery events {missing} missing from stderr "
        f"(were they silenced instead of redirected?)\n"
        f"--- stderr ---\n{proc.stderr[:2000]}"
    )


@pytest.mark.parametrize("command", [["models"], ["formations"]])
def test_cli_stdout_pure_table_commands(command: list[str], cli_env: dict[str, str]) -> None:
    """`chimera models` / `formations`: stdout = table only, logs on stderr."""
    proc = _run_cli(["-c", cli_env["CHIMERA_CONFIG"], *command], cli_env)
    assert proc.returncode == 0, (
        f"CLI {command} failed rc={proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[:2000]}\n"
        f"--- stderr ---\n{proc.stderr[:2000]}"
    )
    _assert_stdout_pure(proc)
    _assert_logs_on_stderr(proc)

    # Content must still be on stdout (the table did not vanish with the logs).
    if command == ["models"]:
        assert "deepseek/deepseek-chat" in proc.stdout
        assert "Models" in proc.stdout
    else:
        assert "debate" in proc.stdout
        assert "Formations" in proc.stdout


def test_cli_stdout_pure_deliberation_error_path(
    cli_env: dict[str, str],
) -> None:
    """Deliberation-path invocation that fails pre-network stays stdout-pure.

    A missing config must print the clean one-line error (CH-GAP-050) on
    stdout — and nothing else. The phase-1 pre-config pin guarantees even
    the failed-load invocation cannot emit structlog lines on stdout.
    """
    proc = _run_cli(
        ["-c", "/nonexistent/definitely-missing/chimera.yaml", "hello world"],
        cli_env,
    )
    assert proc.returncode == 2, (
        f"expected exit 2 on missing config, got {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[:2000]}\n"
        f"--- stderr ---\n{proc.stderr[:2000]}"
    )
    _assert_stdout_pure(proc)
    # The actionable error is the ONLY stdout content.
    assert "error:" in proc.stdout
    assert "chimera.yaml" in proc.stdout
    # No help dump, no traceback fragments.
    assert "Traceback" not in proc.stdout
    assert "Usage:" not in proc.stdout


def test_cli_stdout_pure_models_with_real_repo_config() -> None:
    """Live probe against the repo's own chimera.yaml (skipped if absent).

    This is the exact invocation from the bug report: with the repo's
    provider cache present, discovery fires on load — pre-fix its
    ``provider_cache_hit`` / ``provider_discovery_done`` lines landed on
    stdout ahead of the Models table.
    """
    repo_cfg = REPO / "chimera.yaml"
    if not repo_cfg.is_file():
        pytest.skip("repo chimera.yaml not present")
    env = dict(os.environ)
    env.pop("CHIMERA_CONFIG", None)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = _run_cli(["-c", str(repo_cfg), "models"], env)
    assert proc.returncode == 0, proc.stderr[-2000:]
    _assert_stdout_pure(proc)
    assert "Models" in proc.stdout
    assert "deepseek" in proc.stdout.lower()


def test_module_logger_follows_a_stdout_to_stderr_repin() -> None:
    """A module logger bound while logging was on stdout must follow the CLI pin.

    The subprocess tests above prove stdout purity for a FRESH process. The same
    contract has an in-process hole (DF-CHIMERA-V2-34): a module-level
    ``structlog.get_logger()`` proxy (``chimera.dispatcher`` / ``.engine`` /
    ``.aggregator``) binds against whichever configuration is live at its first
    emission, and ``api.server.create_app`` calls ``configure_logging`` with the
    config default ``use_stdout: true``. With ``cache_logger_on_first_use=True``
    that binding survives every later re-pin, so a degraded deliberation run
    dispatched in-process (an embedding app, a test session) wrote its structlog
    records onto the machine-mode stdout contract — a structlog line ahead of the
    ``--json`` document, which is exactly what the documented streams table
    forbids. Resolving the logger per emission (``cache_logger_on_first_use``
    off) makes the pin authoritative.

    Captured streams make the assertion about the SINK, not about ordering: the
    logger is first bound while ``sys.stdout`` is a captured StringIO, so a
    stale binding is visible as a record landing there after the re-pin.
    """
    import contextlib
    import io

    import chimera.dispatcher as dispatcher_mod
    from chimera.config import Observability
    from chimera.observability import configure_logging

    stdout_a, stderr_a = io.StringIO(), io.StringIO()
    try:
        # An in-process caller (create_app) configures logging with the default
        # use_stdout=True, and a module logger emits through that pipeline.
        with contextlib.redirect_stdout(stdout_a), contextlib.redirect_stderr(stderr_a):
            configure_logging(Observability(use_stdout=True, langfuse={"enabled": False}))
            dispatcher_mod.log.warning("purity_probe_bound_on_stdout")
        assert "purity_probe_bound_on_stdout" in stdout_a.getvalue()

        stdout_b, stderr_b = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout_b), contextlib.redirect_stderr(stderr_b):
            # The CLI's phase-1/2 pin (cli.main._load_cfg).
            configure_logging(
                Observability(use_stdout=False, langfuse={"enabled": False}),
                force_stderr=True,
            )
            dispatcher_mod.log.warning("purity_probe_after_repin")

        assert "purity_probe_after_repin" not in (stdout_a.getvalue() + stdout_b.getvalue()), (
            "a module logger kept writing to the stdout sink it bound before the "
            "force_stderr pin (DF-CHIMERA-V2-34): the machine-mode stdout contract "
            "is broken"
        )
        assert "purity_probe_after_repin" in stderr_b.getvalue()
    finally:
        # Leave the session pinned to the real stderr, the state every later
        # test expects from a CLI / API / MCP entry point.
        configure_logging(Observability(use_stdout=False, langfuse={"enabled": False}), force_stderr=True)
