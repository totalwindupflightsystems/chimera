"""Integration test fixtures — guarded by ``--run-integration`` flag.

These tests start a REAL uvicorn server and hit REAL provider APIs.
Without ``--run-integration`` they are automatically skipped so normal
``pytest`` runs stay fast and offline.

Usage::

    .venv/bin/python -m pytest tests/integration/ --run-integration -v

Two server instances are started (session-scoped):

* **live_server** (port 8810) — real ``chimera.yaml``, no auth, no rate
  limiting.  Used for E2E deliberation, API surface, and structured-output
  tests.
* **auth_server** (port 8811) — ``chimera.yaml`` variant with auth enabled
  (``CHIMERA_API_KEY``) and aggressive rate limiting (``burst_size=2``).
  Used for 401 / 400 / 429 error-path tests.

API keys are loaded from ``~/.hermes/.env`` at import time so the subprocess
servers inherit them via ``os.environ``.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest
import yaml

# ── Paths & constants ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")
CHIMERA_YAML = PROJECT_ROOT / "chimera.yaml"

LIVE_PORT = 8810
AUTH_PORT = 8811

#: A fixed test key injected into the auth-server's environment.
VALID_API_KEY = "chimera-integration-test-key"

#: Budget models only — keeps costs negligible and avoids OpenRouter.
BUDGET_MODELS = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
]

# ── Environment bootstrap ──────────────────────────────────────────────────


def _load_hermes_env() -> None:
    """Load API keys from ``~/.hermes/.env`` if not already in the environment."""
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and val and not os.environ.get(key):
            os.environ[key] = val


_load_hermes_env()


# ── pytest hooks ───────────────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run live integration tests (starts real server, hits real APIs)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: live integration test (requires --run-integration)",
    )
    config.addinivalue_line("markers", "slow: tests that call remote APIs")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="need --run-integration flag to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


# ── Server lifecycle helpers ───────────────────────────────────────────────

#: Track log-file paths so we can read diagnostics after teardown.
_server_logs: dict[int, str] = {}


def _start_server(
    port: int,
    config_path: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    """Start a uvicorn server in a subprocess.

    If *config_path* is ``None`` the server loads ``chimera.yaml`` from the
    project root (real config).  Otherwise it loads the specified YAML file.

    stdout is redirected to a temp **file** (not a pipe) to avoid the classic
    pipe-buffer deadlock: chimera.yaml has ``log_level: debug`` and LiteLLM
    is extremely verbose — a PIPE would fill the 64 KB OS buffer and block
    the server's write, causing the HTTP request to time out.
    """
    import tempfile

    if config_path:
        snippet = (
            "from chimera.api.server import create_app; "
            "from chimera.config import load_config; "
            "import uvicorn; "
            f"uvicorn.run(create_app(load_config({config_path!r})), "
            f"host='127.0.0.1', port={port})"
        )
    else:
        snippet = (
            "from chimera.api.server import create_app; "
            "import uvicorn; "
            f"uvicorn.run(create_app(), host='127.0.0.1', port={port})"
        )

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    with tempfile.NamedTemporaryFile(
        mode="w", prefix=f"chimera-{port}-", suffix=".log", delete=False,
    ) as log_fd:
        log_path = log_fd.name

    with open(log_path, "w") as log_fh:
        proc = subprocess.Popen(
            [VENV_PYTHON, "-c", snippet],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
    _server_logs[proc.pid] = log_path
    return proc


def _wait_ready(proc: subprocess.Popen[str], port: int, timeout: int = 45) -> bool:
    """Poll ``/v1/health/live`` until the server responds 200 or *timeout*."""
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False  # process exited early
        try:
            with httpx.Client() as client:
                r = client.get(f"{url}/v1/health/live", timeout=2.0)
                if r.status_code == 200:
                    return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, OSError):
            pass
        time.sleep(1.0)
    return False


def _stop_server(proc: subprocess.Popen[str]) -> None:
    """Terminate the server subprocess gracefully."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _dump_server_output(proc: subprocess.Popen[str]) -> str:
    """Read the last 3 000 chars of the server log file (for diagnostics)."""
    log_path = _server_logs.get(proc.pid)
    if log_path:
        try:
            with open(log_path) as f:
                return f.read()[-3000:]
        except OSError:
            pass
    return ""


# ── Config generation for the auth/rate-limit server ──────────────────────


def _make_auth_config(tmpdir: Path) -> Path:
    """Create a chimera.yaml variant with auth + rate limiting enabled."""
    with open(CHIMERA_YAML) as f:
        cfg = yaml.safe_load(f)

    cfg["auth"] = {"enabled": True, "mode": "env"}
    cfg["rate_limit"] = {
        "enabled": True,
        "burst_size": 2,
        "requests_per_minute": 2,
    }
    cfg["server"] = {"host": "127.0.0.1", "port": AUTH_PORT}
    cfg["observability"] = {"log_level": "warning", "trace_enabled": False}

    out = tmpdir / "chimera.yaml"
    with open(out, "w") as f:
        yaml.dump(cfg, f)
    return out


# ── Session-scoped server fixtures ─────────────────────────────────────────


@pytest.fixture(scope="session")
def live_server() -> str:
    """Start the real server with ``chimera.yaml`` on port 8810."""
    proc = _start_server(LIVE_PORT)
    try:
        if not _wait_ready(proc, LIVE_PORT):
            pytest.fail(
                f"Live server failed to start on port {LIVE_PORT}\n"
                f"{_dump_server_output(proc)}"
            )
        yield f"http://127.0.0.1:{LIVE_PORT}"
    finally:
        _stop_server(proc)


@pytest.fixture(scope="session")
def auth_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Start a server with auth + rate limiting enabled on port 8811."""
    tmpdir = tmp_path_factory.mktemp("auth_server")
    config_path = _make_auth_config(tmpdir)
    proc = _start_server(
        AUTH_PORT,
        config_path=str(config_path),
        extra_env={"CHIMERA_API_KEY": VALID_API_KEY},
    )
    try:
        if not _wait_ready(proc, AUTH_PORT):
            pytest.fail(
                f"Auth server failed to start on port {AUTH_PORT}\n"
                f"{_dump_server_output(proc)}"
            )
        yield f"http://127.0.0.1:{AUTH_PORT}"
    finally:
        _stop_server(proc)


# ── Convenience fixtures ───────────────────────────────────────────────────


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Valid auth headers for the auth server."""
    return {"Authorization": f"Bearer {VALID_API_KEY}"}


@pytest.fixture
def bad_auth_headers() -> dict[str, str]:
    """Invalid auth headers for 401 tests."""
    return {"Authorization": "Bearer this-key-is-wrong"}


@pytest.fixture
def budget_deliberate_payload() -> dict:
    """A minimal /v1/deliberate payload constrained to budget deepseek models."""
    return {
        "prompt": "What is 2+2? Reply with just the number.",
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
    }
