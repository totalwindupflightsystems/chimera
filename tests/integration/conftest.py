"""Integration test fixtures — guarded by ``--run-integration`` flag.

These tests start a REAL uvicorn server and hit REAL provider APIs.
Without ``--run-integration`` they are automatically skipped so normal
``pytest`` runs stay fast and offline.

Usage::

    .venv/bin/python -m pytest tests/integration/ --run-integration -v

Two server instances are started (session-scoped):

* **live_server** (port 8810) — the resolved ``chimera.yaml`` (the live file
  when present, else a copy of the tracked example template), no auth, no rate
  limiting.  Used for E2E deliberation, API surface, and structured-output
  tests.
* **auth_server** (port 8811) — a variant of the resolved config with auth
  enabled (``CHIMERA_API_KEY``) and aggressive rate limiting (``burst_size=2``).
  Used for 401 / 400 / 429 error-path tests.

API keys are loaded from ``~/.hermes/.env`` at import time so the subprocess
servers inherit them via ``os.environ``.

The YAML both servers run against is resolved by :func:`_resolve_config_path`,
NOT hard-coded: ``chimera.yaml`` is untracked + gitignored
(DF-CHIMERA-0916B-4), so a fresh clone or CI runner has only the tracked
``chimera.yaml.example``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest
import yaml

# ── Paths & constants ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")

#: The live, untracked, gitignored config (DF-CHIMERA-0916B-4).
LIVE_CONFIG_NAME = "chimera.yaml"
#: The tracked bootstrap template the repo ships instead.
EXAMPLE_CONFIG_NAME = "chimera.yaml.example"

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

    *config_path* is the resolved YAML the server should load (see
    :func:`_resolve_config_path`); ``None`` falls back to chimera's own default
    lookup, which needs a repo-root ``chimera.yaml`` that a fresh checkout lacks.

    stdout is redirected to a temp **file** (not a pipe) to avoid the classic
    pipe-buffer deadlock: chimera.yaml has ``log_level: debug`` and LiteLLM
    is extremely verbose — a PIPE would fill the 64 KB OS buffer and block
    the server's write, causing the HTTP request to time out.
    """
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


# ── Config path resolution (fresh-checkout safe) ───────────────────────────

#: Materialized copies of the tracked example template, keyed by resolved
#: project root — a module-level cache so both session fixtures share ONE copy.
_MATERIALIZED_CONFIGS: dict[str, Path] = {}


def _materialize_example_config(project_root: Path, example: Path) -> Path:
    """Copy the tracked example template into a temp dir OUTSIDE the repo.

    The copy is cached per project root so the ``live_server`` and ``auth_server``
    fixtures share a single file.  It deliberately never lands inside the repo:
    writing ``<project_root>/chimera.yaml`` would fabricate a "live config" in a
    fresh checkout (and could shadow the real one on a developer box).
    """
    key = str(Path(project_root).resolve())
    cached = _MATERIALIZED_CONFIGS.get(key)
    if cached is not None and cached.is_file():
        return cached

    tmpdir = Path(tempfile.mkdtemp(prefix="chimera-it-config-"))
    target = tmpdir / LIVE_CONFIG_NAME  # named so load_config sees a config file
    shutil.copyfile(example, target)
    _MATERIALIZED_CONFIGS[key] = target
    print(
        f"[integration] no live {LIVE_CONFIG_NAME} in {project_root}: "
        f"using a copy of the EXAMPLE template {example} at {target}",
        flush=True,
    )
    return target


def _resolve_config_path(
    project_root: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the chimera YAML the integration servers run against.

    ``chimera.yaml`` is untracked + gitignored (DF-CHIMERA-0916B-4), so a fresh
    clone or CI runner has only the tracked ``chimera.yaml.example``.  Hard-coding
    the live path is what made the CI ``integration`` job red on every push
    (``FileNotFoundError`` at fixture setup, tests/integration/conftest.py:209);
    resolving here keeps the suite green on a developer box AND a fresh checkout.

    Resolution order — the first of these that exists and is a file wins:

    1. ``CHIMERA_CONFIG`` from the environment.  It is an *optional* override, so
       a set-but-missing path is not an error — it falls through to the arms
       below (a stale pointer must not take the suite down);
    2. ``<project_root>/chimera.yaml`` — the live local config.  When it exists
       nothing else changes: same file, same bytes, no temp file written;
    3. ``<project_root>/chimera.yaml.example`` — the tracked template, copied
       into a session-scoped temp dir outside the repo (one line is printed);
    4. otherwise a ``RuntimeError`` naming the remedy, instead of a bare
       ``FileNotFoundError`` from ``open()``.

    *env* defaults to ``os.environ`` and is injectable so the fallback arms are
    testable hermetically — see ``tests/test_integration_config_fallback.py``.
    """
    if env is None:
        env = os.environ

    project_root = Path(project_root)
    env_config = env.get("CHIMERA_CONFIG")
    if env_config:
        env_path = Path(env_config)
        if env_path.is_file():
            return env_path

    live = project_root / LIVE_CONFIG_NAME
    if live.is_file():
        return live

    example = project_root / EXAMPLE_CONFIG_NAME
    if example.is_file():
        return _materialize_example_config(project_root, example)

    raise RuntimeError(
        "No chimera configuration available for the integration suite. Looked for "
        f"CHIMERA_CONFIG (env: {env_config or 'unset'}), {live}, and {example}. "
        f"Remedy: run `chimera config init` in {project_root} to create a live "
        f"{LIVE_CONFIG_NAME}, or set CHIMERA_CONFIG=/path/to/{LIVE_CONFIG_NAME}."
    )


# ── Config generation for the auth/rate-limit server ──────────────────────


def _make_auth_config(tmpdir: Path) -> Path:
    """Create a chimera.yaml variant with auth + rate limiting enabled."""
    with open(_resolve_config_path()) as f:
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
    """Start the real server on port 8810 with the RESOLVED config.

    The config is passed explicitly so a fresh checkout (no live ``chimera.yaml``)
    boots from the materialized example template instead of relying on
    ``create_app()``'s own lookup finding nothing.
    """
    proc = _start_server(LIVE_PORT, config_path=str(_resolve_config_path()))
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


@pytest.fixture(autouse=True)
def _reset_singletons(live_server: str) -> None:
    """Reset shared state between tests so no cross-test contamination."""
    with httpx.Client() as client:
        r = client.post(f"{live_server}/web/debug/reset", timeout=5.0)
        assert r.status_code == 200, f"Reset failed: {r.status_code}"


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
