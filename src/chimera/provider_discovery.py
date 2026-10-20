"""Provider auto-discovery via models.dev.

Fetches ``https://models.dev/api.json`` (145 providers, per-model pricing
in $/MTok, base URLs, auth env vars) and auto-discovers which providers are
available by checking which environment variables are set.

Usage::

    from chimera.provider_discovery import discover_providers

    providers, model_pricing = discover_providers()
    # providers: dict[str, Provider] — ready to merge into chimera.yaml
    # model_pricing: dict[(provider, model_id), dict] — price row, $/1k tokens.
    #   The provider is the registry block that SUPPLIED the row, so two
    #   providers serving the same model id never overwrite each other.  The
    #   provider-agnostic winner (used only when a catalog entry's own provider
    #   has no row) is stored under the ``None`` provider key; resolve a
    #   catalog entry with :func:`resolve_model_pricing`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from chimera.task_router_registry import (
    TaskRouterRegistryError,
    load_task_router_registry,
    locate_task_router_models,
)

log = structlog.get_logger("chimera.provider_discovery")

#: Canonical models.dev API endpoint.
MODELS_DEV_URL: str = "https://models.dev/api.json"

#: Local cache path (relative to user config dir).
CACHE_PATH: str = "~/.chimera/models-dev-cache.json"

#: Cache TTL in seconds (30 minutes).
CACHE_TTL: int = 1800

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
    "tencent-tokenhub": "tencent",
    "sarvam": "sarvam",
    "stepfun": "stepfun",
    "xiaomi": "xiaomi",
}

#: Reseller / aggregator namespace blocks. Under a task-router source these
#: must never be lab-attributed: their ids are deliberately namespaced
#: (``openrouter/deepseek-v4-pro``), and mapping them onto lab keys would
#: collide with the owning lab's own pricing (DF-CHIMERA-V2-49).
RESELLER_NAMESPACE_IDS: frozenset[str] = frozenset({"openrouter", "kilo", "nano-gpt", "vercel", "llmgateway"})

#: Unambiguous lab markers inside a task-router model id. Rows under LANE
#: blocks (scheduling lanes such as xkiro, zai-glm, ollama-cloud — anything
#: that is neither a core-lab block nor a reseller namespace) are attributed
#: to their owning lab per model by these case-insensitive markers.
_LAB_ID_MARKERS: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"),
    ("gpt-", "openai"),
    ("deepseek", "deepseek"),
    ("gemini", "google"),
    ("grok", "xai"),
    ("glm", "zhipuai"),
    ("kimi", "moonshotai"),
    ("minimax", "minimax"),
    ("qwen", "alibaba"),
    ("mistral", "mistral"),
    ("llama", "meta"),
    ("step-", "stepfun"),
)


def lab_of_router_provider(provider_id: str, model_id: str) -> str | None:
    """Return the core lab a task-router (provider, model) row belongs to.

    Only LANE rows are attributed — blocks that are already core-lab shaped
    (``PROVIDER_ID_MAP`` keys) or reseller namespaces (``RESELLER_NAMESPACE_IDS``)
    return None: they resolve under their own id by design. Lane rows are
    attributed per model by an unambiguous lab marker in the id; a lane row
    with no marker (mixed lanes carry foreign models too) stays unattributed
    rather than being mis-attributed by block ownership.
    """
    if provider_id in PROVIDER_ID_MAP or provider_id in RESELLER_NAMESPACE_IDS:
        return None
    low = model_id.lower()
    for marker, lab in _LAB_ID_MARKERS:
        if marker in low:
            return lab
    return None


#: Map models.dev model IDs to Chimera model IDs.
#: Most follow ``provider/model-name`` pattern; this handles exceptions.
MODEL_ID_MAP: dict[str, str] = {
    # DeepSeek
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    # DeepSeek's own registry/API id for the flash SKU is ``deepseek-flash``
    # (models.dev lists both names in the ``deepseek`` block at identical
    # prices): the same model, so it must canonicalize onto the catalog id.
    # Without this alias the lab's own live row only ever reached
    # ``deepseek/deepseek-flash`` while the catalog id was priced by whichever
    # foreign gateway happened to write it (DF-CHIMERA-V2-93).
    "deepseek-flash": "deepseek/deepseek-v4-flash",
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
    # Tencent HY (unified to tencent/hy3-preview)
    "hy3-preview": "tencent/hy3-preview",
    "tencent/hy3-preview": "tencent/hy3-preview",
    "tencent/Hy3-preview": "tencent/hy3-preview",
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


#: Provider key of the provider-agnostic price view.  A row stored under
#: ``(None, model_id)`` was written for a model id that several registry blocks
#: share, so nothing identifies the gateway it belongs to; it is only used as a
#: coverage fallback when a catalog entry's own provider has no row for the id
#: (DF-CHIMERA-V2-93).
UNATTRIBUTED_PRICE_PROVIDER: None = None

#: One discovered price row.  ``input``/``output`` are $/1k tokens; the rest is
#: provenance, so a resolved price can always be traced back to the block and
#: raw model id it came from instead of silently being the last block to write.
PriceRow = dict[str, Any]

#: Discovered prices, keyed by ``(provider, chimera_model_id)``.  The provider is
#: the registry BLOCK that supplied the row — never the lab a lane row was
#: attributed to — so a gateway serving a same-named model can no longer
#: overwrite the row of the provider that actually answers for the catalog entry.
ModelPricing = dict[tuple[str | None, str], PriceRow]


def _price_rank(row_input: float, row_output: float, *, exact_name: bool) -> tuple[int, int]:
    """Rank competing rows for one ``(provider, model id)`` key.

    ``exact_name`` is True when the row's raw model id IS the model name of the
    resolved catalog id (no alias table involved).  A priced row outranks a
    zero-priced one (free-tier / unpublished cost) and an exact name outranks an
    alias-resolved one, so a block holding two names for the same SKU publishes
    the price of the name the catalog id actually uses.
    """
    return (1 if (row_input > 0 or row_output > 0) else 0, 1 if exact_name else 0)


def resolve_model_pricing(
    model_pricing: ModelPricing,
    provider: str,
    model_id: str,
) -> tuple[PriceRow | None, str]:
    """Resolve the discovered price of one catalog entry — provider first.

    Returns ``(row, tier)``:

    * ``"provider"`` — the catalog entry's OWN provider label supplied the row.
      Authoritative: no other provider's row for the same model id can reach it
      (DF-CHIMERA-V2-93).
    * ``"unattributed"`` — the entry's provider has no row for this id, so the
      provider-agnostic winner is used.  Coverage fallback, never silent: the
      row's provenance names the block it came from.
    * ``"none"`` — nothing discovered; the caller keeps the declared rate or the
      ``cost_tier`` default.
    """
    row = model_pricing.get((provider, model_id))
    if row is not None:
        return row, "provider"
    row = model_pricing.get((UNATTRIBUTED_PRICE_PROVIDER, model_id))
    if row is not None:
        return row, "unattributed"
    return None, "none"


def _mtok_to_per_1k(cost_mtok: float) -> float:
    """Convert $/MTok → $/1k tokens."""
    return cost_mtok / 1000.0


def _load_cache(*, ignore_ttl: bool = False) -> dict[str, Any] | None:
    """Load cached models.dev data, returning None if stale, missing, or corrupt.

    ``ignore_ttl=True`` skips the age check — used when a network fetch
    failed and the stale cache is the only data available.
    """
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
    if not isinstance(fetched_at, (int, float)) or isinstance(fetched_at, bool) or fetched_at <= 0:
        # Marker-less cache (e.g. written by an external tool with a plain
        # json.dump — DF-CHIMERA-V2-49): fall back to the file's mtime so a
        # fresh cache is a HIT instead of a ~infinite age and a pointless
        # network refetch on every load.
        try:
            fetched_at = path.stat().st_mtime
            log.info("provider_cache_marker_fallback", fetched_at=fetched_at)
        except OSError:
            fetched_at = 0
    age = time.time() - fetched_at
    if not ignore_ttl and age > CACHE_TTL:
        log.info("provider_cache_stale", age_s=int(age))
        return None
    # Ensure at least one provider entry exists
    provider_count = sum(
        1 for k, v in data.items() if k != "_fetched_at" and isinstance(v, dict) and "models" in v
    )
    if provider_count == 0:
        log.warning("provider_cache_empty", reason="no provider entries with models")
        return None
    log.info(
        "provider_cache_hit",
        age_s=int(age),
        providers=provider_count,
        stale=bool(ignore_ttl and age > CACHE_TTL),
    )
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


@dataclass(frozen=True)
class RegistrySnapshot:
    """One selected registry plus enough provenance for diagnostics."""

    data: dict[str, Any]
    source: str
    path: Path | None = None


def _load_models_dev_registry(*, force_refresh: bool = False) -> dict[str, Any]:
    """Load models.dev with the existing cache/network/stale-cache policy."""
    data: dict[str, Any] | None = None
    if not force_refresh:
        data = _load_cache()
    if data is not None:
        return data

    try:
        data = _fetch_models_dev()
        _save_cache(data)
        log.info("provider_fetch_ok", providers=len(data))
        return data
    except Exception as exc:
        log.warning("provider_fetch_failed", error=str(exc))
        # Fall back to stale cache — ignore TTL because the network is
        # unreachable and stale data is better than nothing.
        data = _load_cache(ignore_ttl=True)
        if data is None:
            log.warning("provider_no_data")
            return {}
        return data


def load_preferred_registry(*, force_refresh: bool = False) -> RegistrySnapshot:
    """Prefer task-router's JSONL registry, with models.dev as portable fallback.

    ``force_refresh`` retains its historical meaning: callers explicitly asking
    for a models.dev refresh bypass local task-router selection.  Normal config
    loading and model-sync scans prefer task-router whenever its table is valid.
    """
    if not force_refresh:
        try:
            path = locate_task_router_models()
            data = load_task_router_registry(path)
            log.info(
                "registry_source_selected",
                source="task-router",
                path=str(path),
                providers=len(data),
            )
            return RegistrySnapshot(data=data, source="task-router", path=path)
        except TaskRouterRegistryError as exc:
            # A task-router checkout is optional for installed Chimera users;
            # its normal absence is not a warning or a CLI-output regression.
            # Explicit or malformed sources still deserve an actionable warning.
            event = "registry_source_fallback"
            level = log.warning if os.environ.get("CHIMERA_TASK_ROUTER_MODELS_PATH") else log.info
            level(
                event,
                preferred="task-router",
                fallback="models.dev",
                reason=str(exc),
            )

    data = _load_models_dev_registry(force_refresh=force_refresh)
    return RegistrySnapshot(data=data, source="models.dev")


def merge_registry_with_models_dev(
    primary: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Union a primary registry (e.g. task-router) with models.dev rows.

    The primary is the pricing authority: where a provider block exists in
    both, the primary block wins wholesale. models.dev only contributes
    provider blocks the primary lacks (or fills a primary block that is not a
    dict), so a lab with no rows in the primary source still reaches the core
    scan. This is the mechanism behind DF-CHIMERA-V2-49's coverage restore:
    lane-named router blocks cannot cover every lab id, and the models.dev
    cache — already loaded as the sanctioned fallback — fills exactly those
    gaps without ever overriding a router row.
    """
    merged: dict[str, Any] = {k: v for k, v in primary.items() if k != "_fetched_at"}
    for pid, block in fallback.items():
        if pid == "_fetched_at" or not isinstance(block, dict):
            continue
        existing = merged.get(pid)
        if existing is None or not isinstance(existing, dict):
            merged[pid] = block
    return merged


def discover_providers(
    *,
    force_refresh: bool = False,
    api_keys: dict[str, str] | None = None,
) -> tuple[dict[str, dict[str, str]], ModelPricing]:
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
        model_pricing: ``{(provider, chimera_model_id): PriceRow}`` where
            ``input``/``output`` are $/1k tokens and the remaining keys name the
            block and raw model id the row came from.  Rows are scoped to the
            provider that PUBLISHED them (DF-CHIMERA-V2-93); the
            provider-agnostic winner is kept under ``(None, model_id)`` as a
            coverage fallback.  Resolve a catalog entry with
            :func:`resolve_model_pricing`.
    """
    # 1. Select task-router when available; force_refresh keeps the historical
    # models.dev refresh escape hatch for explicit callers.
    snapshot = load_preferred_registry(force_refresh=force_refresh)
    data = snapshot.data
    if not data:
        return {}, {}

    # Router blocks are lane-named and cannot cover every lab. Union the
    # models.dev cache UNDERNEATH (router rows win — pricing authority) so
    # pricing and provider registration keep models.dev-level coverage
    # (DF-CHIMERA-V2-49). Lane rows are then attributed to their owning lab
    # when resolving Chimera ids, so keys match the catalog.
    if snapshot.source == "task-router":
        data = merge_registry_with_models_dev(data, _load_models_dev_registry())

    # 2. Extract per-model pricing from ALL providers in the selected registry.
    #    Pricing data does NOT require API keys — it's public data.
    providers: dict[str, dict[str, str]] = {}
    # Prices are keyed by (provider, chimera_model_id) — DF-CHIMERA-V2-93.  Every
    # registry block publishes its own rows under its OWN provider id, so
    # ``clinepass``'s price for ``deepseek-v4-flash`` can no longer overwrite the
    # row ``deepseek`` publishes for the same model: the catalog entry's provider
    # label decides which of them prices the entry (resolve_model_pricing).
    model_pricing: ModelPricing = {}
    api_keys = api_keys or {}
    # Blocks that CAME FROM the task-router table (any block in the snapshot's
    # own data — lab blocks, lane blocks, reseller-namespace blocks).
    router_block_ids = (
        {k for k, v in snapshot.data.items() if isinstance(v, dict)}
        if snapshot.source == "task-router"
        else set()
    )
    # Pricing keys whose CURRENT value came from a router block; models.dev
    # fill blocks must not overwrite them (DF-CHIMERA-V2-49).  Guards the
    # provider-agnostic fallback view only — the provider-scoped view needs no
    # such rule, since a foreign block can no longer reach another provider's key.
    router_derived_keys: set[str] = set()
    # Rank of the row currently stored under each provider-scoped key, so the
    # tie-break inside one block is deterministic (see _price_rank).
    price_ranks: dict[tuple[str | None, str], tuple[int, int]] = {}

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
                # Under a task-router source, lane blocks store rows under the
                # lane id; attribute lane rows to their owning lab so the
                # resolved Chimera id matches the catalog key shape
                # (``deepseek/...`` not ``ollama-cloud/...``).  Attribution only
                # shapes the ID — the row still belongs to the lane's provider
                # key, which is what keeps same-lab rows from colliding.
                attribution_source = (
                    lab_of_router_provider(md_id, md_model_id) or md_id
                    if snapshot.source == "task-router"
                    else md_id
                )
                chimera_model_id = _resolve_model_id(attribution_source, md_model_id)
                new_input = _mtok_to_per_1k(float(cost_input))
                new_output = _mtok_to_per_1k(float(cost_output))
                row: PriceRow = {
                    "input": new_input,
                    "output": new_output,
                    "source_provider": chimera_name,
                    "source_model": md_model_id,
                    "registry": snapshot.source,
                    "attributed_lab": attribution_source if attribution_source != md_id else None,
                }

                # ── Provider-scoped view (authoritative, DF-CHIMERA-V2-93) ──
                # A block publishes its rows under its own id only.  Competing
                # rows for one key therefore all come from the SAME block; the
                # highest-ranked one wins and ties keep the first, so the result
                # never depends on which block the loop reached last.
                provider_key = (chimera_name, chimera_model_id)
                rank = _price_rank(
                    new_input,
                    new_output,
                    exact_name=md_model_id == chimera_model_id.rsplit("/", 1)[-1],
                )
                if rank > price_ranks.get(provider_key, (-1, -1)):
                    model_pricing[provider_key] = row
                    price_ranks[provider_key] = rank

                # ── Provider-agnostic view (coverage fallback) ──
                # The pre-scoping winner, kept so a catalog entry whose provider
                # publishes no row for the id still gets a discovered price —
                # recorded with its provenance rather than silently applied.
                fallback_key = (UNATTRIBUTED_PRICE_PROVIDER, chimera_model_id)
                existing = model_pricing.get(fallback_key)
                if (
                    existing is not None
                    and existing["input"] > 0
                    and existing["output"] > 0
                    and new_input == 0.0
                    and new_output == 0.0
                ):
                    # Prefer non-zero pricing: if we already have real pricing,
                    # don't overwrite with zero-cost entries from free-tier
                    # providers.
                    continue
                # DF-CHIMERA-V2-49: a pricing key derived from the task-router
                # source (the pricing authority) is FINAL — a later models.dev
                # fill block (openrouter, kilo, ...) must not overwrite it
                # through a MODEL_ID_MAP collision (e.g. a reseller's bare
                # ``deepseek-v4-pro`` row).
                router_derived = md_id in router_block_ids
                if chimera_model_id in router_derived_keys and not router_derived:
                    continue
                if router_derived:
                    router_derived_keys.add(chimera_model_id)
                model_pricing[fallback_key] = row

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

    provider_scoped_prices = sum(1 for key in model_pricing if key[0] is not None)
    log.info(
        "provider_discovery_done",
        providers=len(providers),
        models=provider_scoped_prices,
        unattributed=len(model_pricing) - provider_scoped_prices,
    )
    return providers, model_pricing
