"""DF-CHIMERA-V2-76 — loud serve-startup warning for an inert auth key env.

The inverse of DF-CHIMERA-V2-56 (tested in
``test_server_auth_startup_warning.py``): a fresh user following the README
quickstart exports ``CHIMERA_API_KEY`` alone and gets a fully UNAUTHENTICATED
server — ``load_config`` only lets the env var take effect through
``auth.enabled`` in ``chimera.yaml`` (or the ``CHIMERA_AUTH_ENABLED``
toggle), so the export is silently inert and nothing anywhere said so.

The fix under test here: the serve startup path (``chimera.api.server.run``,
the single entrypoint behind BOTH the CLI ``serve`` command and the Docker
``CMD``) prints ONE loud warning line — naming the literal variable
``CHIMERA_API_KEY`` and the ``auth.enabled`` stanza — BEFORE uvicorn binds
the port, on stderr, the same channel the DF-CHIMERA-V2-56 warning uses
(DF-CHIMERA-V2-3 keeps stdout for machine-readable payload only).

Auth behavior itself is untouched: no auth gets enabled, no config gets
mutated, and no key material ever appears in the warning or in these tests —
assertions are on the PRESENCE/ABSENCE of the variable name, never on a
value (the only key strings here are the suite's established
``test-secret-key`` placeholders).
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

    Mirrors ``test_server_auth_startup_warning.py``: write chimera.yaml into
    tmp_path, clear ``CHIMERA_CONFIG`` (it outranks the cwd walk-up), chdir,
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


class TestServeStartupKeyButAuthDisabledWarning:
    """The warning fires at startup, on stderr, and only when it should."""

    @pytest.mark.parametrize(
        ("env_value", "case"),
        [("test-secret-key", "plain"), ("  test-secret-key  ", "whitespace-padded")],
    )
    def test_warns_when_key_set_but_auth_disabled(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        env_value: str,
        case: str,
    ) -> None:
        """auth disabled + CHIMERA_API_KEY exported → ONE loud line."""
        monkeypatch.setenv("CHIMERA_API_KEY", env_value)

        uvicorn_called = _run_serve(tmp_path, monkeypatch, _serve_config_dict(enabled=False, mode="env"))

        captured = capsys.readouterr()
        # Greppable anchors: the literal env var name, the disabled state,
        # and the two switches that WOULD have made the export take effect.
        assert "CHIMERA_API_KEY" in captured.err, (
            f"[{case}] startup stderr must name CHIMERA_API_KEY\n--- stderr ---\n{captured.err[-2000:]}"
        )
        assert "unauthenticated" in captured.err, (
            f"[{case}] stderr must say the server is unauthenticated\n--- stderr ---\n{captured.err[-2000:]}"
        )
        assert "auth.enabled" in captured.err, (
            f"[{case}] stderr must name the auth.enabled stanza\n--- stderr ---\n{captured.err[-2000:]}"
        )
        assert "CHIMERA_AUTH_ENABLED" in captured.err, (
            f"[{case}] stderr must name the auth toggle\n--- stderr ---\n{captured.err[-2000:]}"
        )
        # House stdout purity (DF-CHIMERA-V2-3): the warning is operational
        # truth and belongs on stderr, never on the machine-readable stdout.
        assert "CHIMERA_API_KEY" not in captured.out
        # The warning precedes a normal startup: uvicorn was still handed the
        # app and the configured bind address (a warning, not a refusal), and
        # the helper stayed read-only — no config was flipped to enable auth.
        assert uvicorn_called["host"] == "127.0.0.1"
        assert uvicorn_called["port"] == 8000

    @pytest.mark.parametrize(
        ("env_value", "case"),
        [(None, "unset"), ("", "empty"), ("   ", "whitespace-only")],
    )
    def test_silent_when_auth_disabled_and_key_not_set(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        env_value: str | None,
        case: str,
    ) -> None:
        """No env var → no behavior change, no warning (the default path)."""
        if env_value is None:
            monkeypatch.delenv("CHIMERA_API_KEY", raising=False)
        else:
            monkeypatch.setenv("CHIMERA_API_KEY", env_value)

        _run_serve(tmp_path, monkeypatch, _serve_config_dict(enabled=False, mode="env"))
        captured = capsys.readouterr()
        assert "CHIMERA_API_KEY" not in captured.err
        assert "CHIMERA_API_KEY" not in captured.out

    @pytest.mark.parametrize("mode", ["env", "list"])
    def test_silent_when_auth_enabled(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        mode: str,
    ) -> None:
        """Auth enabled + key exported → the export works; startup stays quiet."""
        monkeypatch.setenv("CHIMERA_API_KEY", "test-secret-key")
        auth: dict[str, Any] = (
            {"enabled": True, "mode": "env"}
            if mode == "env"
            else {"enabled": True, "mode": "list", "keys": [{"key": "test-secret-key", "name": "t"}]}
        )
        _run_serve(tmp_path, monkeypatch, _serve_config_dict(**auth))
        captured = capsys.readouterr()
        assert "CHIMERA_API_KEY" not in captured.err
        assert "CHIMERA_API_KEY" not in captured.out
