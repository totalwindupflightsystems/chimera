"""Provider auto-discovery via models.dev.

Fetches ``https://models.dev/api.json`` (145 providers, per-model pricing
in $/MTok, base URLs, auth env vars) and auto-discovers which providers are
available by checking which environment variables are set.

Usage::

    from chimera.provider_discovery import discover_providers

    providers, model_pricing = discover_providers()
    # providers: dict[str, Provider] — ready to merge into chimera.yaml
    # model_pricing: dict[str, dict] — model_id → {input, output} per 1k tokens
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("chimera.provider_discovery")

#: Canonical models.dev API endpoint.
MODELS_DEV_URL: str = "https://models.dev/api.json"

#: Local cache path (relative to user config dir).
CACHE_PATH: str = "~/.chimera/models-dev-cache.json"

#: Cache TTL in seconds (24 hours).
CACHE_TTL: int = 86400

#: Map models.dev provider IDs to Chimera provider names.
#: Most match 1:1; this table handles the exceptions.
PROVIDER_ID_MAP: dict[str, str] = {
    "deepseek": "deepseek",
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "xai": "xai",
    "moonshotai": "moonshot",
    "minimax": "minimax",
    "alibaba": "alibaba",
    "zhipuai": "zai",
    "mistral": "mistral",
    "meta": "meta",
    "nvidia": "nvidia",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "tencent": "tencent",
    "sarvam": "sarvam",
    "stepfun": "stepfun",
    "xiaomi": "xiaomi",
}

#: Map models.dev model IDs to Chimera model IDs.
#: Most follow ``provider/model-name`` pattern; this handles exceptions.
MODEL_ID_MAP: dict[str, str] = {
    # DeepSeek
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-reasoner": "deepseek/deepseek-reasoner",
    "deepseek-chat": "deepseek/deepseek-chat",
    # OpenAI → openrouter prefix
    "gpt-5.5": "openrouter/openai/gpt-5.5",
    "gpt-5.5-pro": "openrouter/openai/gpt-5.5-pro",
    # Anthropic
    "claude-opus-4-8": "anthropic/claude-opus-4.8",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
    "claude-fable-5": "openrouter/anthropic/claude-fable-5",
    # Kimi
    "kimi-k2.7-code": "openrouter/moonshotai/kimi-k2.7-code",
    "kimi-k2.6": "openrouter/moonshotai/kimi-k2.6",
    # MiniMax
    "MiniMax-M3": "openrouter/minimax/minimax-m3",
    # GLM
    "glm-5.2": "zai-coding-plan/glm-5.2",
    "glm-5-turbo": "z-ai/glm-5-turbo",
    "glm-5": "z-ai/glm-5",
    # Qwen
    "qwen3.7-max": "openrouter/qwen/qwen3.7-max",
    "qwen3.7-plus": "openrouter/qwen/qwen3.7-plus",
    "qwen3-coder-plus": "openrouter/qwen/qwen3-coder",
    # Grok
    "grok-4.20-0309-non-reasoning": "openrouter/x-ai/grok-4.20",
    "grok-4.20-0309-reasoning": "openrouter/x-ai/grok-4.20-multi-agent",
    "grok-4.3": "openrouter/x-ai/grok-4.3",
    # Google
    "gemini-3.1-pro-preview": "google/gemini-3.1-pro-preview",
    "gemini-3.5-flash": "google/gemini-3.5-flash",
    "gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview": "google/gemini-3-flash-preview",
    "gemini-3-pro-preview": "google/gemini-3-pro-preview",
}


def _resolve_model_id(provider_id: str, model_id: str) -> str:
    """Map a models.dev (provider_id, model_id) pair to a Chimera model ID.

    Checks ``MODEL_ID_MAP`` first, then falls back to
    ``{chimera_provider}/{model_id}``.
    """
    mapped = MODEL_ID_MAP.get(model_id)
    if mapped:
        return mapped
    chimera_provider = PROVIDER_ID_MAP.get(provider_id, provider_id)
    return f"{chimera_provider}/{model_id}"


def _mtok_to_per_1k(cost_mtok: float) -> float:
    """Convert $/MTok → $/1k tokens."""
    return cost_mtok / 1000.0


def _load_cache() -> dict[str, Any] | None:
    """Load cached models.dev data, returning None if stale or missing."""
    path = Path(CACHE_PATH).expanduser()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    fetched_at = data.get("_fetched_at", 0)
    if time.time() - fetched_at > CACHE_TTL:
        log.info("provider_cache_stale", age_s=int(time.time() - fetched_at))
        return None
    log.info("provider_cache_hit", age_s=int(time.time() - fetched_at))
    return data


def _save_cache(data: dict[str, Any]) -> None:
    """Persist models.dev data to local cache."""
    path = Path(CACHE_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["_fetched_at"] = time.time()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _fetch_models_dev() -> dict[str, Any]:
    """Fetch models.dev api.json, returning the raw JSON dict."""
    import urllib.request

    req = urllib.request.Request(
        MODELS_DEV_URL,
        headers={"Accept": "application/json", "User-Agent": "Chimera/0.2"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_providers(
    *,
    force_refresh: bool = False,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, float]]]:
    """Auto-discover available providers and model pricing from models.dev.

    Returns:
        providers: ``{provider_name: {base_url, api_key_env}}``
        model_pricing: ``{chimera_model_id: {input: float, output: float}}``
            where input/output are $/1k tokens.
    """
    # 1. Load from cache or fetch
    data: dict[str, Any] | None = None
    if not force_refresh:
        data = _load_cache()
    if data is None:
        try:
            data = _fetch_models_dev()
            _save_cache(data)
            log.info("provider_fetch_ok", providers=len(data))
        except Exception as exc:
            log.warning("provider_fetch_failed", error=str(exc))
            data = _load_cache()  # fall back to stale cache
            if data is None:
                log.warning("provider_no_data")
                return {}, {}

    # 2. Discover which providers have API keys set
    providers: dict[str, dict[str, str]] = {}
    model_pricing: dict[str, dict[str, float]] = {}

    for md_id, md_provider in data.items():
        if md_id in ("_fetched_at",):
            continue
        if not isinstance(md_provider, dict):
            continue

        env_vars = md_provider.get("env", [])
        if not isinstance(env_vars, list):
            env_vars = [env_vars] if env_vars else []

        # Check if ANY of the required env vars is set
        api_key = None
        for env_var in env_vars:
            val = os.environ.get(env_var)
            if val and val.strip() and not val.startswith("${"):
                api_key = val
                break

        if api_key is None:
            continue

        chimera_name = PROVIDER_ID_MAP.get(md_id, md_id)
        base_url = md_provider.get("api", "")
        if base_url and not base_url.endswith("/v1"):
            if "/v1" not in base_url:
                base_url = base_url.rstrip("/") + "/v1"

        providers[chimera_name] = {
            "base_url": base_url,
            "api_key_env": env_vars[0] if env_vars else "",
        }

        # 3. Extract per-model pricing
        md_models = md_provider.get("models", {})
        if not isinstance(md_models, dict):
            continue
        for md_model_id, md_model in md_models.items():
            if not isinstance(md_model, dict):
                continue
            cost = md_model.get("cost", {})
            if not isinstance(cost, dict):
                continue
            cost_input = cost.get("input")
            cost_output = cost.get("output")
            if cost_input is None or cost_output is None:
                continue
            chimera_model_id = _resolve_model_id(md_id, md_model_id)
            model_pricing[chimera_model_id] = {
                "input": _mtok_to_per_1k(float(cost_input)),
                "output": _mtok_to_per_1k(float(cost_output)),
            }

    log.info(
        "provider_discovery_done",
        providers=len(providers),
        models=len(model_pricing),
    )
    return providers, model_pricing
