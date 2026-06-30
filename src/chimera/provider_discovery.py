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
    "claude-opus-4-7": "anthropic/claude-opus-4.7",
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
    "qwen3-coder-plus": "openrouter/qwen/qwen3-coder-plus",
    "qwen3-coder-flash": "openrouter/qwen/qwen3-coder-flash",
    "qwen3-coder-next": "qwen/qwen3-coder-next",
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

#: Known base URLs for providers where models.dev doesn't include them.
#: Populated from official provider docs. Keys are Chimera provider names.
_PROVIDER_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "cohere": "https://api.cohere.ai/v1",
    "perplexity": "https://api.perplexity.ai",
    "meta": "https://api.meta.ai/v1",
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
    """Load cached models.dev data, returning None if stale, missing, or corrupt."""
    path = Path(CACHE_PATH).expanduser()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # Validate structure: must be a dict with provider entries and _fetched_at
    if not isinstance(data, dict):
        log.warning("provider_cache_invalid", reason="not a dict")
        return None
    fetched_at = data.get("_fetched_at", 0)
    if time.time() - fetched_at > CACHE_TTL:
        log.info("provider_cache_stale", age_s=int(time.time() - fetched_at))
        return None
    # Ensure at least one provider entry exists
    provider_count = sum(1 for k, v in data.items()
                         if k != "_fetched_at" and isinstance(v, dict) and "models" in v)
    if provider_count == 0:
        log.warning("provider_cache_empty", reason="no provider entries with models")
        return None
    log.info("provider_cache_hit",
             age_s=int(time.time() - fetched_at),
             providers=provider_count)
    return data


def _save_cache(data: dict[str, Any]) -> None:
    """Persist models.dev data to local cache (atomic write)."""
    path = Path(CACHE_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["_fetched_at"] = time.time()
    # Atomic write: temp file → rename, so concurrent readers never see
    # a half-written file.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


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
    api_keys: dict[str, str] | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, float]]]:
    """Auto-discover available providers and model pricing from models.dev.

    Pricing data is extracted from ALL providers in the cache regardless of
    API key availability -- it is public data that does not require auth.
    Providers are only registered when API keys are actually available.

    Args:
        force_refresh: If True, skip cache and re-fetch from models.dev.
        api_keys: Optional dict of ``{chimera_provider_name: api_key}``.
            When provided, a provider is considered available if its
            chimera name is in this dict (even if no env var is set).
            This bridges ``chimera.yaml``'s ``api_keys`` section with
            the env-var-based discovery from models.dev.

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

    # 2. Extract per-model pricing from ALL providers in cache.
    #    Pricing data does NOT require API keys — it's public data.
    providers: dict[str, dict[str, str]] = {}
    model_pricing: dict[str, dict[str, float]] = {}
    api_keys = api_keys or {}

    for md_id, md_provider in data.items():
        if md_id in ("_fetched_at",):
            continue
        if not isinstance(md_provider, dict):
            continue

        chimera_name = PROVIDER_ID_MAP.get(md_id, md_id)

        # ── Pricing extraction (always runs, no auth needed) ──
        md_models = md_provider.get("models", {})
        if isinstance(md_models, dict):
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
                new_input = _mtok_to_per_1k(float(cost_input))
                new_output = _mtok_to_per_1k(float(cost_output))
                # Prefer non-zero pricing: if we already have real pricing,
                # don't overwrite with zero-cost entries from free-tier providers.
                existing = model_pricing.get(chimera_model_id)
                if existing is not None and existing["input"] > 0 and existing["output"] > 0:
                    if new_input == 0.0 and new_output == 0.0:
                        continue
                model_pricing[chimera_model_id] = {
                    "input": new_input,
                    "output": new_output,
                }

        # ── Provider discovery (requires API key) ──
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

        # Fall back to config.api_keys — keys stored in chimera.yaml
        # rather than environment variables.
        if api_key is None and chimera_name in api_keys:
            api_key = api_keys[chimera_name]

        # Skip provider registration if no key found, or if key is an
        # empty/unresolved placeholder.  ``${VAR}`` tokens that didn't
        # resolve produce empty strings; an empty key means the provider
        # is not actually available.
        if not api_key:
            continue

        base_url = md_provider.get("api", "")
        # Fall back to known base URLs for providers where models.dev
        # doesn't include them (e.g. Anthropic, Google, OpenAI, xAI).
        if not base_url:
            base_url = _PROVIDER_BASE_URLS.get(chimera_name, "")
        if base_url and not base_url.endswith("/v1") and "/v1" not in base_url:
            base_url = base_url.rstrip("/") + "/v1"

        providers[chimera_name] = {
            "base_url": base_url,
            "api_key_env": env_vars[0] if env_vars else "",
        }

    log.info(
        "provider_discovery_done",
        providers=len(providers),
        models=len(model_pricing),
    )
    return providers, model_pricing
