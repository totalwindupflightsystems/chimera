"""DF-CHIMERA-V2-33 — the built-in ``auto`` formation resolves without a config entry.

``docs/CONFIG.md``'s full example defines ONLY custom formations (no ``auto:``
key), yet the user-facing formation validation added in DF-CHIMERA-V2-7 treats
``auto`` as just another name that must exist in ``config.formations`` — so
every docs-following user's FIRST run (``chimera run "say hi"``, the ``auto``
default) exited 2 with ``Unknown formation: auto``.

``auto`` is a BUILT-IN formation backed by ``Config.auto_formation``
(AutoFormationConfig, default_factory in ``src/chimera/config.py``). It must be
resolvable even when the user's config does not list it. The internal
dispatcher fallback is untouched (pinned by
``tests/test_dispatcher.py::test_dispatcher_unknown_formation_uses_auto``); what
changes is the user-facing edge: the literal name ``auto`` is always valid, an
explicit ``auto:`` entry in formations still wins, and genuinely unknown names
are still rejected with exit 2 / 422 (DF-CHIMERA-V2-7 preserved).

Surfaces covered here: CLI (exit code via CliRunner), REST (``/v1/deliberate``),
web session chat (``/web/sessions/{id}/chat``), and MCP (``chimera_deliberate``),
each against the docs-faithful custom-only config.

Also pins DF-CHIMERA-V2-35's docs fix: the fixed percent-integer example weights
load with ZERO ``category_scale_normalized`` warnings (the old 0.90-style
fractions emitted one on every load).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import structlog.testing
import yaml

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.config as config_mod  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.cli.main import _validate_formation, main  # noqa: E402
from chimera.config import ChimeraConfig, load_config  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


@pytest.fixture(autouse=True)
def _no_global_logging_repin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``configure_logging`` for every consumer module this file drives.

    The CLI/MCP/REST paths under test legitimately call
    ``configure_logging(..., force_stderr=True)``, which repins the GLOBAL
    structlog sink to stderr for the rest of the pytest process — test files
    sorted after this one then find their own warnings missing from captured
    stdout (test_gateway.py / test_health_providers.py broke exactly this way
    when this file landed). The stub keeps the surfaces' behavior observable
    (warnings still emit, just through whatever sink the outer test process
    configured) while the file stops being a cross-file polluter.
    """
    import chimera.api.server as api_server_mod
    import chimera.cli.main as cli_main_mod
    import chimera.mcp.server as mcp_server_mod

    monkeypatch.setattr(api_server_mod, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(cli_main_mod, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(mcp_server_mod, "configure_logging", lambda *a, **k: None)


PY_PATH = "technology_code/code_generation/python"

# ── The docs-faithful config ────────────────────────────────────────────────
#
# Mirrors docs/CONFIG.md's Full Example: FLAT ``defaults`` (a nested
# ``defaults: dispatcher: {...}`` block fails pydantic validation), one custom
# DAG formation, percent-integer category weights — and NO ``auto`` key.


def _custom_only_config_dict() -> dict[str, Any]:
    return {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com/v1"},
            "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        },
        "defaults": {
            "dispatcher": "deepseek/deepseek-v4-flash",
            "default_worker": "deepseek/deepseek-v4-pro",
            "default_aggregator": "deepseek/deepseek-v4-flash",
            "lock_dispatcher": False,
            "lock_aggregator": True,
        },
        "formations": {
            "my-custom-chain": {
                "dag": {
                    "stages": [
                        {
                            "id": "analyzer",
                            "kind": "worker",
                            "model": "deepseek/deepseek-v4-pro",
                            "depends_on": [],
                        },
                        {
                            "id": "reviewer",
                            "kind": "aggregator",
                            "model": "zai-coding-plan/glm-5.2",
                            "depends_on": ["analyzer"],
                        },
                        {
                            "id": "finalizer",
                            "kind": "merge",
                            "model": "deepseek/deepseek-v4-flash",
                            "depends_on": ["reviewer"],
                        },
                    ],
                    "edges": [["analyzer", "reviewer"], ["reviewer", "finalizer"]],
                },
            },
        },
        "models": {
            "deepseek/deepseek-v4-flash": {
                "categories": {
                    "technology_code/code_generation/python": 90,
                    "technology_code/data_science/analysis": 80,
                    "general_knowledge/reasoning/explanation": 75,
                    "creative_conversational/ux_writing/interface_copy": 35,
                    "technology_code/testing_debugging/error_analysis": 55,
                },
                "cost_tier": "budget",
                "provider": "deepseek",
            },
            "zai-coding-plan/glm-5.2": {
                "categories": {
                    "technology_code/code_generation/python": 92,
                    "technology_code/data_science/analysis": 90,
                    "general_knowledge/reasoning/explanation": 95,
                    "creative_conversational/ux_writing/interface_copy": 85,
                    "technology_code/testing_debugging/error_analysis": 88,
                },
                "cost_tier": "premium",
                "provider": "zai",
            },
        },
    }


def _custom_plus_explicit_auto_dict() -> dict[str, Any]:
    """Same catalog, but the user ALSO defines ``auto:`` with a fixed DAG.

    An explicit definition must WIN over the built-in: the run must use the
    config's structure, not the dispatcher-designed auto path.
    """
    doc = _custom_only_config_dict()
    doc["formations"] = {
        "auto": {
            "dag": {
                "stages": [
                    {"id": "solo", "kind": "worker", "model": "zai-coding-plan/glm-5.2", "depends_on": []},
                    {
                        "id": "final",
                        "kind": "merge",
                        "model": "deepseek/deepseek-v4-flash",
                        "depends_on": ["solo"],
                    },
                ],
                "edges": [["solo", "final"]],
            },
        },
        "my-custom-chain": doc["formations"]["my-custom-chain"],
    }
    return doc


def _resp(text: str, model: str, tok_in: int, tok_out: int) -> GatewayResponse:
    return GatewayResponse(
        text=text,
        model=model,
        tokens_input=tok_in,
        tokens_output=tok_out,
    )


def _catalog_responder(response_format_first: bool = True):  # type: ignore[no-untyped-def]
    """FakeGateway responder over the docs-faithful catalog.

    Dispatcher calls (``response_format``) get a valid dispatch JSON; aggregator
    calls get the merged answer; everything else is a worker reply.
    """
    payload = dispatch_json(
        workers=[
            ("worker_1", "deepseek/deepseek-v4-flash"),
            ("worker_2", "zai-coding-plan/glm-5.2"),
        ],
        aggregator="deepseek/deepseek-v4-flash",
        aggregator_instructions="Merge the worker outputs.",
    )

    def responder(model, messages, response_format=None, **kw):  # noqa: ANN001, ANN003
        if response_format is not None:
            return _resp(payload, model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    return responder


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def custom_only_config() -> ChimeraConfig:
    return ChimeraConfig.model_validate(_custom_only_config_dict())


@pytest.fixture
def custom_only_config_file(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """The docs-faithful config as a real file, with HOME + dotenv isolated.

    HOME is pointed at an empty temp dir (and the ~/.hermes/.env cache
    pre-empted with an empty dict) so the suite never reads real credentials
    and never touches the network: provider discovery is stubbed to a no-op.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(config_mod, "_hermes_dotenv_cache", {})
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        lambda **kw: ({}, {}),
    )
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(_custom_only_config_dict()), encoding="utf-8")
    return path


@pytest.fixture
def explicit_auto_config_file(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """A config where the user explicitly defines ``auto:`` — their entry wins."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(config_mod, "_hermes_dotenv_cache", {})
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        lambda **kw: ({}, {}),
    )
    path = tmp_path / "chimera.yaml"
    path.write_text(
        yaml.safe_dump(_custom_plus_explicit_auto_dict()),
        encoding="utf-8",
    )
    return path


def _spy(monkeypatch):  # type: ignore[no-untyped-def]
    """Install a spy Engine + gateway; return the record of what they saw."""
    record: dict[str, list] = {"built": [], "calls": [], "gateway_built": []}

    class SpyEngine:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            record["built"].append((args, kwargs))

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN003
            record["calls"].append((prompt, formation, kwargs))
            from types import SimpleNamespace

            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source="auto",
                answer_stage_id="aggregator",
                worker_failures=[],
                dispatch_note=None,
            )
            return SimpleNamespace(answer="ok", trace=trace)

    def spy_gateway(*args, **kwargs):  # noqa: ANN002, ANN003
        record["gateway_built"].append((args, kwargs))
        return None

    monkeypatch.setattr("chimera.cli.main.Engine", SpyEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", spy_gateway)
    return record


# ---------------------------------------------------------------------------
# The pure helper (unit level)
# ---------------------------------------------------------------------------


def test_validate_formation_accepts_auto_when_not_in_config(
    custom_only_config,
) -> None:
    """THE regression: ``auto`` is valid even when formations has no ``auto``."""
    assert "auto" not in custom_only_config.formations
    assert _validate_formation(custom_only_config, "auto", None) is None


def test_validate_formation_still_rejects_unknown_on_custom_only_config(
    custom_only_config,
    capsys,
) -> None:
    """DF-CHIMERA-V2-7 is NOT weakened: ``nope`` still exits 2."""
    with pytest.raises(SystemExit) as excinfo:
        _validate_formation(custom_only_config, "nope", None)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "nope" in err
    assert "Available formations: my-custom-chain" in err
    assert "chimera formations" in err


# ---------------------------------------------------------------------------
# CLI end-to-end (CliRunner)
# ---------------------------------------------------------------------------


def test_cli_default_run_on_custom_only_config_does_not_exit_2(
    custom_only_config_file,
    monkeypatch,
) -> None:
    """``chimera run "..."`` with no -f on a custom-only config must run."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main,
        ["-c", str(custom_only_config_file), "--quiet", "reply with the word ok"],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}: {result.stderr}"
    assert result.stdout.strip() == "ok"
    assert record["calls"][0][1] == "auto"


def test_cli_explicit_auto_flag_on_custom_only_config(
    custom_only_config_file,
    monkeypatch,
) -> None:
    """``-f auto`` on a custom-only config must run, not exit 2."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main,
        ["-c", str(custom_only_config_file), "-f", "auto", "--quiet", "reply with the word ok"],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}: {result.stderr}"
    assert result.stdout.strip() == "ok"
    assert record["calls"][0][1] == "auto"


def test_cli_explicit_auto_formation_still_wins(
    explicit_auto_config_file,
    monkeypatch,
) -> None:
    """A user-defined ``auto:`` entry is honored — the run proceeds."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main,
        ["-c", str(explicit_auto_config_file), "-f", "auto", "--quiet", "reply with the word ok"],
    )
    assert result.exit_code == 0, f"exit {result.exit_code}: {result.stderr}"
    assert record["calls"][0][1] == "auto"


def test_cli_unknown_formation_on_custom_only_config_exits_2(
    custom_only_config_file,
    monkeypatch,
) -> None:
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main,
        ["-c", str(custom_only_config_file), "-f", "nope", "--quiet", "hi"],
    )
    assert result.exit_code == 2, result.output
    assert "nope" in result.stderr
    assert "Available formations: my-custom-chain" in result.stderr
    assert record["calls"] == []


# ---------------------------------------------------------------------------
# REST surface (/v1/deliberate)
# ---------------------------------------------------------------------------


def _rest_client(config):  # type: ignore[no-untyped-def]
    gateway = FakeGateway(_catalog_responder())
    engine = Engine(config, gateway)
    app = create_app(config=config, engine=engine)
    return TestClient(app), gateway


def _catalog_responder():  # type: ignore[no-untyped-def]
    return _catalog_responder_impl()


def _catalog_responder_impl():  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):  # noqa: ANN001, ANN003
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    return responder


def test_rest_default_formation_on_custom_only_config_deliberates(
    custom_only_config,
) -> None:
    """POST /v1/deliberate with no formation on a custom-only config → 200."""
    client, gateway = _rest_client(custom_only_config)
    r = client.post("/v1/deliberate", json={"prompt": "hi"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["answer"] == "FINAL ANSWER"
    assert data["trace"]["formation"] == "auto"
    assert data["trace"]["source"] == "auto"
    assert gateway.calls


def test_rest_explicit_auto_formation_on_custom_only_config(
    custom_only_config,
) -> None:
    client, _ = _rest_client(custom_only_config)
    r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["trace"]["formation"] == "auto"


def test_rest_unknown_formation_still_422_on_custom_only_config(
    custom_only_config,
) -> None:
    client, gateway = _rest_client(custom_only_config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "nope"},
    )
    assert r.status_code == 422, r.text
    assert "Unknown formation" in r.json()["detail"]
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# REST: an explicitly-defined auto wins over the built-in (dispatcher behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_uses_explicit_auto_preset_over_builtin(
    explicit_auto_config_file,
) -> None:
    """A config-defined ``auto:`` DAG wins: source == preset, config stages."""
    from chimera.dispatcher import Dispatcher

    cfg = load_config(explicit_auto_config_file)
    gw = FakeGateway(lambda m, msg, **k: _resp(dispatch_json(), m, 100, 200))
    outcome = await Dispatcher(cfg, gw).dispatch("task", "auto")
    assert outcome.result.source == "preset"
    assert [s.id for s in outcome.result.formation.stages] == ["solo", "final"]


@pytest.mark.asyncio
async def test_dispatcher_builtin_auto_path_untouched(custom_only_config) -> None:
    """Without an explicit entry, the name ``auto`` runs the dispatcher DESIGN."""
    from chimera.dispatcher import Dispatcher

    gw = FakeGateway(_catalog_responder_impl())
    outcome = await Dispatcher(custom_only_config, gw).dispatch("task", "auto")
    assert outcome.result.source == "auto"


# ---------------------------------------------------------------------------
# Web session chat surface
# ---------------------------------------------------------------------------


def _web_client(config):  # type: ignore[no-untyped-def]
    import chimera.web.routes as web_routes
    from chimera.web.session import SessionManager
    from chimera.web.sse import SSEBroadcaster

    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    gateway = FakeGateway(_catalog_responder_impl())
    engine = Engine(config, gateway)
    app = create_app(config=config, engine=engine)
    return TestClient(app), gateway


def test_web_default_formation_on_custom_only_config_deliberates(
    custom_only_config,
) -> None:
    client, gateway = _web_client(custom_only_config)
    session_id = client.post("/web/sessions").json()["session_id"]
    r = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["answer"]
    assert gateway.calls


def test_web_unknown_formation_still_422_on_custom_only_config(
    custom_only_config,
) -> None:
    client, gateway = _web_client(custom_only_config)
    session_id = client.post("/web/sessions").json()["session_id"]
    r = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "nope"},
    )
    assert r.status_code == 422, r.text
    assert "Unknown formation" in r.json()["detail"]
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# MCP surface
# ---------------------------------------------------------------------------


def _mcp_server(config):  # type: ignore[no-untyped-def]
    pytest.importorskip("mcp")
    from chimera.mcp.server import build_server

    engine = Engine(config, FakeGateway(_catalog_responder_impl()))
    return build_server(config=config, engine=engine)


async def _call_tool(server, name: str, **arguments):  # type: ignore[no-untyped-def]
    result = await server._tool_manager.call_tool(name, arguments)
    if isinstance(result, str):
        return json.loads(result)
    text = getattr(result, "text", None)
    if text is not None:
        return json.loads(text)
    return result


@pytest.mark.asyncio
async def test_mcp_default_formation_on_custom_only_config_deliberates(
    custom_only_config,
) -> None:
    server = _mcp_server(custom_only_config)
    data = await _call_tool(server, "chimera_deliberate", prompt="hello")
    assert data["answer"] == "FINAL ANSWER"
    assert data["trace"]["formation"] == "auto"


@pytest.mark.asyncio
async def test_mcp_unknown_formation_still_reported_on_custom_only_config(
    custom_only_config,
) -> None:
    server = _mcp_server(custom_only_config)
    data = await _call_tool(
        server,
        "chimera_deliberate",
        prompt="hello",
        formation="nope",
    )
    assert data["error"] == "unknown_formation"
    assert data["formation"] == "nope"
    assert data["available"] == ["my-custom-chain"]


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-35 — the fixed docs example loads with ZERO scale warnings
# ---------------------------------------------------------------------------


def test_fixed_docs_example_loads_without_scale_warnings(
    custom_only_config_file,
) -> None:
    """Percent-integer example weights → no ``category_scale_normalized``.

    The OLD docs example (0.90/0.80/... fractions) emitted one warning per
    load. The fixed example must load silently.
    """
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(custom_only_config_file)
    scale_records = [e for e in logs if e["event"] == "category_scale_normalized"]
    assert scale_records == []
    assert cfg.models["deepseek/deepseek-v4-flash"].categories[PY_PATH] == 90.0
    assert "auto" not in cfg.formations
