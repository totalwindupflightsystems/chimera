"""DF-CHIMERA-V2-119 — ``chimera --config P serve`` must serve config P.

The bug: the CLI loaded the config from the global ``--config`` flag (via
``_load_cfg`` → ``load_config(config_path)``) and then threw it away —
``chimera.api.server.run`` re-loaded the config with NO path, so the server
silently re-resolved from ``CHIMERA_CONFIG`` / the cwd walk-up and served a
DIFFERENT file than the one the user pointed at. Reproduced live before the
fix: a 4-model scratch config named by ``--config`` served the 6-model decoy
found in cwd (and named by ``CHIMERA_CONFIG``), and the scratch config's
``auth.enabled: true`` was dropped with it.

Coverage here:

* the AC4 money test: a REAL ``serve`` subprocess (free port, decoy
  ``chimera.yaml`` in cwd, decoy named by ``CHIMERA_CONFIG`` too) must
  expose exactly the 4 scratch models and enforce the scratch auth;
* precedence decided ONCE inside ``load_config`` (flag > env > cwd): the
  CLI forwards the config it loaded, so the object ``run`` receives is the
  one the flag named (unit-level, via the monkeypatched ``server.run``
  capture the existing serve tests use);
* the env path still works when no flag is given (guards against
  over-tightening the fix);
* a missing ``--config`` path stays a LOUD startup error (exit 2, one
  actionable line, no traceback, path named) — never a silent fallback;
* AC3's chosen contract: the global ``--config`` flag belongs BEFORE the
  subcommand, so ``chimera serve --config X`` is rejected with a usage
  error and ``serve --help`` does not advertise a per-command ``--config``.

Hermetic: no network (``provider_discovery: false`` on every fixture), no
provider key, no deliberation — the auth probe is a keyless POST that 401s
inside the auth dependency before any provider call.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

import httpx  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from tests.conftest import CONFIG_DICT  # noqa: E402

#: Env vars that would leak host state into the served config (ambient keys,
#: auth toggles, host/port overrides). Everything else passes through.
_CHIMERA_ENV_VARS = (
    "CHIMERA_CONFIG",
    "CHIMERA_HOST",
    "CHIMERA_PORT",
    "CHIMERA_AUTH_ENABLED",
    "CHIMERA_API_KEY",
    "CHIMERA_DISPATCHER",
    "CHIMERA_WORKER",
    "CHIMERA_AGGREGATOR",
)

#: List-mode auth stanza for the scratch config. ``/v1/models`` stays keyless
#: (docs/SECURITY.md open-endpoint list) while a keyless POST to
#: ``/v1/deliberate`` 401s — the externally observable proof that the SERVED
#: config has ``auth.enabled: true``.
_AUTH_LIST = {
    "enabled": True,
    "mode": "list",
    "keys": [{"name": "ci", "key": "df119-scratch-key"}],
}


def _config_dict_with_n_models(n: int, *, auth: dict[str, Any] | None = None) -> dict[str, Any]:
    """The conftest catalog trimmed to its first *n* models (+ their providers).

    CONFIG_DICT's insertion order starts with the models the ``defaults``
    reference (dispatcher/aggregator ``zai-coding-plan/glm-5.2``, worker
    ``deepseek/deepseek-chat``), so any n >= 2 keeps a self-consistent config.
    """
    cfg = dict(CONFIG_DICT)
    models = dict(list(CONFIG_DICT["models"].items())[:n])
    cfg["models"] = models
    cfg["providers"] = {p: CONFIG_DICT["providers"][p] for p in {m["provider"] for m in models.values()}}
    cfg["provider_discovery"] = False
    if auth is None:
        cfg.pop("auth", None)
    else:
        cfg["auth"] = auth
    return cfg


def _write_config(path: Path, cfg: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _serve_env(cwd_dir: Path, *, chimera_config: Path | None) -> dict[str, str]:
    """Env for a serve child: HOME + cwd sandboxed, decoy named by env."""
    env = dict(os.environ)
    for name in _CHIMERA_ENV_VARS:
        env.pop(name, None)
    if chimera_config is not None:
        env["CHIMERA_CONFIG"] = str(chimera_config)
    env["HOME"] = str(cwd_dir)  # keep ~/.chimera state out of the real home
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _poll_models(port: int, proc: subprocess.Popen[str], deadline_s: float = 45.0) -> dict[str, Any]:
    """GET /v1/models until the server answers (or raise with a timeout).

    A child that DIES mid-poll fails immediately with its output instead of
    burning the whole deadline against a port nobody will ever bind.
    """
    import time

    deadline = time.time() + deadline_s
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"serve child exited rc={proc.returncode} before readiness: {out}")
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=3.0)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retry until the deadline
            last_error = exc
            time.sleep(0.3)
    raise AssertionError(f"/v1/models never answered within {deadline_s}s: {last_error}")


@pytest.fixture
def serve_proc() -> Iterator[subprocess.Popen[str]]:
    """Yield a started serve subprocess and SIGTERM it on teardown."""
    holder: dict[str, subprocess.Popen[str]] = {}

    def _start(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
        proc = subprocess.Popen(
            [sys.executable, "-m", "chimera", *args],
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        holder["proc"] = proc
        return proc

    holder["start"] = _start  # type: ignore[assignment]
    yield holder  # type: ignore[misc]
    proc = holder.get("proc")
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def test_serve_flag_config_served_over_cwd_and_env(serve_proc, tmp_path) -> None:
    """AC1+AC2+AC4: the real server exposes exactly the ``--config`` models.

    Scratch: 4 models, auth enabled (list mode). Decoy: 6 models, auth off,
    sitting in the CHILD's cwd AND named by ``CHIMERA_CONFIG``. Before the
    fix this served 6 models and no auth.
    """
    scratch = _write_config(
        tmp_path / "scratch" / "chimera.yaml", _config_dict_with_n_models(4, auth=_AUTH_LIST)
    )
    decoy = _write_config(tmp_path / "repo" / "chimera.yaml", _config_dict_with_n_models(6))
    cwd_dir = decoy.parent
    port = _free_port()
    env = _serve_env(cwd_dir, chimera_config=decoy)
    proc = serve_proc["start"](["--config", str(scratch), "serve", "--port", str(port)], cwd_dir, env)

    models = _poll_models(port, proc)
    served_ids = [m["id"] for m in models["data"]]
    scratch_ids = set(_config_dict_with_n_models(4)["models"])
    assert len(served_ids) == 4, served_ids
    assert set(served_ids) == scratch_ids, served_ids

    # The scratch auth rides the same config: a keyless POST must 401 inside
    # the auth dependency (the decoy's auth-disabled config would let it
    # through — observed as 502 in the pre-fix reproduction).
    response = httpx.post(
        f"http://127.0.0.1:{port}/v1/deliberate",
        json={"prompt": "hi", "formation": "simple"},
        timeout=10.0,
    )
    assert response.status_code == 401, response.text


def test_serve_missing_config_path_fails_loud(serve_proc, tmp_path) -> None:
    """A nonexistent ``--config`` path is a loud startup error, not a fallback.

    Exit 2, one actionable line naming the path, no traceback. (Before the
    fix the flag path was already loud — but ``run``'s own re-load made a bad
    ``CHIMERA_CONFIG`` a raw FileNotFoundError traceback; the fix removes that
    second load entirely, so this stays the ONLY config error path.)
    """
    cwd_dir = tmp_path / "repo"
    cwd_dir.mkdir(parents=True)
    missing = tmp_path / "no-such" / "chimera.yaml"
    port = _free_port()
    env = _serve_env(cwd_dir, chimera_config=None)
    proc = serve_proc["start"](["--config", str(missing), "serve", "--port", str(port)], cwd_dir, env)
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 2, out
    assert f"{missing}" in out, out
    assert "Traceback" not in out, out
    assert "error:" in out, out


def test_cli_flag_beats_chimera_config_env(tmp_path, monkeypatch) -> None:
    """AC2, unit level: explicit ``--config`` outranks ``CHIMERA_CONFIG``.

    The precedence is decided ONCE inside ``load_config`` (explicit path >
    env > cwd walk-up); serve forwards the object it loaded, so the config
    captured by ``server.run`` is the flag's, never the env's.
    """
    scratch = _write_config(
        tmp_path / "scratch" / "chimera.yaml", _config_dict_with_n_models(4, auth=_AUTH_LIST)
    )
    decoy = _write_config(tmp_path / "repo" / "chimera.yaml", _config_dict_with_n_models(6))
    monkeypatch.setenv("CHIMERA_CONFIG", str(decoy))

    captured: dict = {}

    def _run(host, port, config=None):  # type: ignore[no-untyped-def]
        captured.update({"host": host, "port": port, "config": config})

    monkeypatch.setattr("chimera.api.server.run", _run)
    result = CliRunner().invoke(main, ["-c", str(scratch), "serve"])
    assert result.exit_code == 0, result.output
    assert captured["config"] is not None
    assert set(captured["config"].models) == set(_config_dict_with_n_models(4)["models"])


def test_cli_env_config_used_without_flag(tmp_path, monkeypatch) -> None:
    """No ``--config``: ``CHIMERA_CONFIG`` still resolves (fix must not over-tighten)."""
    decoy = _write_config(tmp_path / "repo" / "chimera.yaml", _config_dict_with_n_models(6))
    monkeypatch.setenv("CHIMERA_CONFIG", str(decoy))

    captured: dict = {}

    def _run(host, port, config=None):  # type: ignore[no-untyped-def]
        captured.update({"config": config})

    monkeypatch.setattr("chimera.api.server.run", _run)
    result = CliRunner().invoke(main, ["serve"])
    assert result.exit_code == 0, result.output
    assert captured["config"] is not None
    assert set(captured["config"].models) == set(CONFIG_DICT["models"])


def test_serve_subcommand_rejects_config_flag() -> None:
    """AC3 (chosen branch): ``chimera serve --config X`` is a usage error.

    ``--config`` is a GROUP-level flag (click convention in this CLI: group
    flags precede the subcommand — ``chimera --config P serve``), so the
    per-subcommand surface rejects it loudly instead of silently ignoring it.
    """
    result = CliRunner().invoke(main, ["serve", "--config", "/tmp/whatever.yaml"])
    assert result.exit_code != 0
    assert "No such option" in result.output
    assert "--config" in result.output

    help_result = CliRunner().invoke(main, ["serve", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "--config" not in help_result.output
