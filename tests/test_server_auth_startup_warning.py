"""DF-CHIMERA-V2-56 — loud serve-startup warning for an empty auth key env.

A fresh ``chimera config init`` followed by ``chimera serve`` WITHOUT
``CHIMERA_API_KEY`` starts healthy (``/v1/health/live`` says alive) and then
rejects every authenticated call with 401 ``Invalid API key.`` — a fresh
user's first dead end reads like a broken key rather than a missing one.

The fix under test here: the serve startup path (``chimera.api.server.run``,
the single entrypoint behind BOTH the CLI ``serve`` command and the Docker
``CMD``) prints ONE loud warning line — naming the literal variable
``CHIMERA_API_KEY`` and the config stanza ``auth.mode`` — BEFORE uvicorn
binds the port. The warning goes to stderr via rich, the same channel the
CLI uses for its ``error:`` lines (DF-CHIMERA-V2-3 keeps stdout for
machine-readable payload only).

Auth behavior itself is untouched: no bypass, no default key, and no key
material ever appears in the warning or in these tests — assertions are on
the PRESENCE/ABSENCE of the variable name, never on a value (the only key
strings here are the suite's established ``test-secret-key`` placeholders).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

import yaml  # noqa: E402

from chimera.api.server import run  # noqa: E402
from tests.conftest import CONFIG_DICT  # noqa: E402


def _serve_config_dict(**auth: Any) -> dict[str, Any]:
    """CONFIG_DICT plus an explicit ``auth`` stanza."""
    cfg = dict(CONFIG_DICT)
    cfg["auth"] = auth
    return cfg


def _run_serve(
    tmp_path,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    cfg_dict: dict[str, Any],
) -> dict[str, Any]:
    """Run the real ``run()`` entrypoint with uvicorn mocked out.

    Mirrors ``TestRunEntrypoint``: write chimera.yaml into tmp_path, clear
    ``CHIMERA_CONFIG`` (the conftest fresh-checkout fixture sets it when the
    repo root has no live config, and it outranks the cwd walk-up), chdir,
    then call ``run()`` and capture what uvicorn would have been handed.
    """
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")
    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    uvicorn_called: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, host: str, port: int) -> None:
        uvicorn_called["host"] = host
        uvicorn_called["port"] = port

    with patch("uvicorn.run", side_effect=fake_uvicorn_run):
        run()
    return uvicorn_called


class TestServeStartupAuthKeyWarning:
    """The warning fires at startup, on stderr, and only when it should."""

    @pytest.mark.parametrize(
        ("env_value", "case"),
        [(None, "unset"), ("", "empty"), ("   ", "whitespace-only")],
    )
    def test_warns_when_auth_env_key_missing(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        env_value: str | None,
        case: str,
    ) -> None:
        """auth.enabled=true + auth.mode: env + no key env → ONE loud line."""
        if env_value is None:
            monkeypatch.delenv("CHIMERA_API_KEY", raising=False)
        else:
            monkeypatch.setenv("CHIMERA_API_KEY", env_value)

        uvicorn_called = _run_serve(tmp_path, monkeypatch, _serve_config_dict(enabled=True, mode="env"))

        captured = capsys.readouterr()
        # Both greppable anchors the acceptance requires: the literal env var
        # name and the config stanza name.
        assert "CHIMERA_API_KEY" in captured.err, (
            f"[{case}] startup stderr must name CHIMERA_API_KEY\n--- stderr ---\n{captured.err[-2000:]}"
        )
        assert "auth.mode" in captured.err, (
            f"[{case}] startup stderr must name the auth.mode stanza\n--- stderr ---\n{captured.err[-2000:]}"
        )
        # House stdout purity (DF-CHIMERA-V2-3): the warning is operational
        # truth and belongs on stderr, never on the machine-readable stdout.
        assert "CHIMERA_API_KEY" not in captured.out
        # The warning precedes a normal startup: uvicorn was still handed the
        # app and the configured bind address (a warning, not a refusal).
        assert uvicorn_called["host"] == "127.0.0.1"
        assert uvicorn_called["port"] == 8000

    def test_silent_when_auth_env_key_set(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """With CHIMERA_API_KEY actually set, startup stays quiet."""
        monkeypatch.setenv("CHIMERA_API_KEY", "test-secret-key")
        _run_serve(tmp_path, monkeypatch, _serve_config_dict(enabled=True, mode="env"))
        captured = capsys.readouterr()
        assert "CHIMERA_API_KEY" not in captured.err
        assert "CHIMERA_API_KEY" not in captured.out

    def test_silent_when_auth_disabled(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Auth disabled (the default deployment) → no warning, key or not."""
        monkeypatch.delenv("CHIMERA_API_KEY", raising=False)
        _run_serve(tmp_path, monkeypatch, _serve_config_dict(enabled=False, mode="env"))
        captured = capsys.readouterr()
        assert "CHIMERA_API_KEY" not in captured.err
        assert "CHIMERA_API_KEY" not in captured.out

    def test_silent_for_list_mode(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``auth.mode: list`` reads keys from config, not the env — silent."""
        monkeypatch.delenv("CHIMERA_API_KEY", raising=False)
        auth = {
            "enabled": True,
            "mode": "list",
            "keys": [{"key": "test-secret-key", "name": "t"}],
        }
        _run_serve(tmp_path, monkeypatch, _serve_config_dict(**auth))
        captured = capsys.readouterr()
        assert "CHIMERA_API_KEY" not in captured.err
        assert "CHIMERA_API_KEY" not in captured.out
