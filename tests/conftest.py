"""Shared test fixtures and helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from chimera.config import ChimeraConfig
from chimera.gateway import GatewayResponse

# A compact, deterministic model catalog + formations mirroring chimera.yaml.example
CONFIG_DICT: dict[str, Any] = {
    "providers": {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
        "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        "anthropic": {"base_url": "https://api.anthropic.com/v1"},
        "deepseek": {"base_url": "https://api.deepseek.com/v1"},
    },
    "models": {
        "zai-coding-plan/glm-5.2": {
            "categories": {"code": 0.92, "analysis": 0.90, "design": 0.85,
                           "audit": 0.88, "reasoning": 0.95},
            "cost_tier": "premium",
            "provider": "zai",
        },
        "deepseek/deepseek-chat": {
            "categories": {"code": 0.95, "analysis": 0.85, "design": 0.40,
                           "audit": 0.60, "reasoning": 0.80},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "deepseek/deepseek-v4-flash": {
            "categories": {"code": 0.88, "analysis": 0.80, "design": 0.50,
                           "audit": 0.55, "reasoning": 0.75},
            "cost_tier": "budget",
            "provider": "deepseek",
        },
        "openrouter/qwen/qwen3-coder": {
            "categories": {"code": 0.91, "analysis": 0.72, "design": 0.45,
                           "audit": 0.50, "reasoning": 0.68},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "openrouter/google/gemini-2.5-flash": {
            "categories": {"code": 0.70, "analysis": 0.75, "design": 0.90,
                           "audit": 0.50, "reasoning": 0.65},
            "cost_tier": "budget",
            "provider": "openrouter",
        },
        "openrouter/anthropic/claude-sonnet-4": {
            "categories": {"code": 0.90, "analysis": 0.92, "design": 0.88,
                           "audit": 0.85, "reasoning": 0.93},
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
