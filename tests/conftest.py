"""Shared test fixtures and helpers."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from chimera.config import ChimeraConfig
from chimera.gateway import GatewayResponse

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _config_default_resolution_for_fresh_checkout() -> Any:
    """Keep default config resolution working in a checkout with no live config.

    ``chimera.yaml`` is a local-only, gitignored file (DF-CHIMERA-0916B-4): a
    fresh clone and CI have only the shipped ``chimera.yaml.example``. Tests that
    resolve the config through ``load_config()``/``create_app()`` would otherwise
    die with "No chimera.yaml found" in CI while passing on a developer box, so
    when the repo-root live config is absent we point ``CHIMERA_CONFIG`` at the
    shipped template — the same file ``chimera config init`` copies. A developer
    checkout with a real ``chimera.yaml`` (or an explicit ``CHIMERA_CONFIG``) is
    left untouched, and tests that clear the variable themselves (the CH-GAP-050
    config-less first-run cases) still see no config at all.
    """
    live = REPO_ROOT / "chimera.yaml"
    if live.is_file() or os.environ.get("CHIMERA_CONFIG"):
        yield
        return
    template = REPO_ROOT / "chimera.yaml.example"
    if not template.is_file():  # pragma: no cover - repo always ships it
        yield
        return
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("CHIMERA_CONFIG", str(template))
    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="session", autouse=True)
def _isolate_blocked_model_registry(
    tmp_path_factory: pytest.TempPathFactory,
) -> Any:
    """Keep the suite out of the developer's real guardrail block state.

    ``blocked_models.shared_registry`` persists to ``DEFAULT_STATE_PATH``
    (``~/.chimera/blocked-models.json``) — the SAME file the live ``chimera``
    service writes from real provider traffic. Every test that consults the
    registry (the dispatcher catalog, the selector, ``chimera models``' blocked
    section, engine failure handling) would otherwise pass or fail depending on
    whatever production last blocked, and the engine's failure paths RECORD
    blocks: one suite run left ``openrouter/google/gemini-2.5-flash`` blocked
    for the whole cooldown, which made the NEXT run fail
    ``tests/test_e2e.py::test_e2e_full_pipeline`` (the model vanished from the
    dispatcher catalog).

    Point the process-wide registry at a per-session temp state file. Tests
    that isolate themselves further still work: they save/restore whatever
    instance is installed here.
    """
    from chimera import blocked_models

    original = blocked_models.shared_registry
    state_path = tmp_path_factory.mktemp("blocked-models") / "blocked-models.json"
    blocked_models.set_shared_registry(
        blocked_models.ModelBlockRegistry(state_path=state_path)
    )
    try:
        yield
    finally:
        blocked_models.set_shared_registry(original)

# A compact, deterministic model catalog + formations mirroring chimera.yaml.example
# (category scores are PERCENT 0-100, the canonical scale the shipped templates,
# the live catalog and GET /v1/models all carry — see chimera.config
# CATEGORY_SCORE_MAX. A catalog on the docs' historical 0.0-1.0 scale is rescaled
# on load, so it must stay a LOCAL fixture in the tests that exercise that.)
CONFIG_DICT: dict[str, Any] = {
    "providers": {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
        "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        "anthropic": {"base_url": "https://api.anthropic.com/v1"},
        "deepseek": {"base_url": "https://api.deepseek.com/v1"},
    },
    "models": {
        "zai-coding-plan/glm-5.2": {
            "categories": {"code": 92.0, "analysis": 90.0, "design": 85.0,
                           "audit": 88.0, "reasoning": 95.0},
            "cost_tier": "premium",
            "provider": "zai",
        },
        "deepseek/deepseek-chat": {
            "categories": {"code": 95.0, "analysis": 85.0, "design": 40.0,
                           "audit": 60.0, "reasoning": 80.0},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "deepseek/deepseek-v4-flash": {
            "categories": {"code": 88.0, "analysis": 80.0, "design": 50.0,
                           "audit": 55.0, "reasoning": 75.0},
            "cost_tier": "budget",
            "provider": "deepseek",
        },
        "openrouter/qwen/qwen3-coder": {
            "categories": {"code": 91.0, "analysis": 72.0, "design": 45.0,
                           "audit": 50.0, "reasoning": 68.0},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "openrouter/google/gemini-2.5-flash": {
            "categories": {"code": 70.0, "analysis": 75.0, "design": 90.0,
                           "audit": 50.0, "reasoning": 65.0},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "openrouter/anthropic/claude-sonnet-4": {
            "categories": {"code": 90.0, "analysis": 92.0, "design": 88.0,
                           "audit": 85.0, "reasoning": 93.0},
            "cost_tier": "premium",
            "provider": "openrouter",
        },
    },
    "defaults": {
        "dispatcher": "zai-coding-plan/glm-5.2",
        "default_worker": "deepseek/deepseek-chat",
        "default_aggregator": "zai-coding-plan/glm-5.2",
    },
    "formations": {
        "auto": {"mode": "auto"},
        "simple": {"workers": 2, "aggregator": "default"},
        "debate": {
            "workers": 3,
            "aggregators": ["default", "openrouter/anthropic/claude-sonnet-4"],
            "merge": "best_of_n",
        },
        "audit": {
            "workers": 2,
            "aggregator": "default",
            "audit": "openrouter/anthropic/claude-sonnet-4",
        },
        "speed": {
            "workers": 2,
            "worker_models": [
                "deepseek/deepseek-v4-flash",
                "openrouter/qwen/qwen3-coder",
            ],
            "aggregator": "deepseek/deepseek-v4-flash",
        },
    },
    "observability": {"log_level": "warning", "trace_enabled": False,
                      "langfuse": {"enabled": False}},
    "server": {"host": "127.0.0.1", "port": 8000},
}


@pytest.fixture
def config() -> ChimeraConfig:
    return ChimeraConfig.model_validate(CONFIG_DICT)


@pytest.fixture
def config_file(tmp_path):
    """Write a real chimera.yaml in a tmp dir and return its path."""
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")
    return path


class FakeGateway:
    """Scriptable gateway for tests.

    ``responder(model, messages, **kwargs) -> GatewayResponse`` decides the
    response for each call. All calls are recorded in ``self.calls``.
    """

    def __init__(self, responder: Callable[..., GatewayResponse] | None = None) -> None:
        self.responder = responder
        self.calls: list[tuple[str, list[dict[str, str]], dict[str, Any]]] = []

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> GatewayResponse:
        self.calls.append((model, messages, {"temperature": temperature,
                                             "response_format": response_format, **kwargs}))
        if self.responder is not None:
            result = self.responder(model, messages, response_format=response_format,
                                    temperature=temperature, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return GatewayResponse(text=f"[fake response from {model}]",
                               model=model, tokens_input=10, tokens_output=20)


def resp(text: str, model: str, tok_in: int = 12, tok_out: int = 34) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=tok_in, tokens_output=tok_out)


def dispatch_json(
    *,
    workers: list[tuple[str, str]] | None = None,
    aggregator: str = "zai-coding-plan/glm-5.2",
    aggregator_instructions: str = "Merge the worker outputs.",
    extra_stages: list[dict[str, Any]] | None = None,
) -> str:
    """Build a valid dispatcher JSON payload string.

    ``workers`` is a list of ``(stage_id, model)`` pairs.
    """
    workers = workers or [("worker_1", "deepseek/deepseek-chat"),
                          ("worker_2", "openrouter/google/gemini-2.5-flash")]
    stages: list[dict[str, Any]] = []
    edges: list[list[str]] = []
    worker_ids = []
    for wid, wmodel in workers:
        stages.append({"id": wid, "kind": "worker", "model": wmodel, "depends_on": []})
        worker_ids.append(wid)
        edges.append([wid, "aggregator"])
    stages.append({"id": "aggregator", "kind": "aggregator", "model": aggregator,
                   "depends_on": list(worker_ids)})
    worker_prompts = [
        {"stage_id": wid, "model": wm, "prompt": f"Custom subtask for {wid}", "expected_output_schema": None}
        for wid, wm in workers
    ]
    stage_instructions: dict[str, str] = {}
    if extra_stages:
        for s in extra_stages:
            stages.append(s)
            for dep in s.get("depends_on", []):
                edges.append([dep, s["id"]])
            if s.get("kind") in {"audit", "merge"}:
                stage_instructions[s["id"]] = f"instructions for {s['id']}"
    payload = {
        "formation": {"stages": stages, "edges": edges},
        "worker_prompts": worker_prompts,
        "aggregator_instructions": aggregator_instructions,
        "stage_instructions": stage_instructions,
    }
    return json.dumps(payload)


def make_dispatcher_responder(config: ChimeraConfig,
                              payload: str | None = None) -> Callable[..., GatewayResponse]:
    """A responder that returns ``payload`` JSON for dispatcher calls, canned
    text for everything else (workers/judges)."""
    dispatcher_model = config.defaults.dispatcher
    _payload = payload or dispatch_json()

    def _responder(model: str, messages: list[dict[str, str]], **kw: Any) -> GatewayResponse:
        if model == dispatcher_model:
            return resp(_payload, model, tok_in=100, tok_out=200)
        # figure out which stage from prompt content
        joined = json.dumps(messages)
        if "merge" in joined or "aggregator" in joined.lower() and "Your job" in joined:
            return resp(f"[merged answer from {model}]", model, tok_in=50, tok_out=80)
        return resp(f"[worker output from {model}]", model, tok_in=20, tok_out=40)

    return _responder
