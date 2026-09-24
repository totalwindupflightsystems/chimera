"""Scan models.dev for new chat/reasoning models not yet in the Chimera catalog.

Usage:
    cd ~/chimera-v2 && source .venv/bin/activate
    python3 scripts/model_sync.py                        # full report to stdout
    python3 scripts/model_sync.py --diff                 # only newly-seen models
    python3 scripts/model_sync.py --score                # LLM-score top 5 candidates
    python3 scripts/model_sync.py --output reports/latest.md  # markdown report

The script filters to 13 core providers, skips embeddings/speech/rerank/legacy
models, and scores candidates by recency. Reports are saved to reports/
(timestamped copies). A .seen_models.json file tracks already-reported
candidates so --diff shows only new finds.

Since DF-CHIMERA-V2-26 the scan ALSO sweeps a RESELLER_WATCH list of
aggregator/reseller models.dev rows (openrouter, kilo, nano-gpt, vercel,
llmgateway) in the same pass. A frontier release that lands first in a
reseller row (e.g. StepFun step-5-preview, 2026-09-18/20) is no longer
invisible: attributed finds are reported under "Reseller Watch" with a
hypothesized owning lab, unattributable ones under an explicit "Blind Spot".
Those sections are informational and NOT recorded in .seen_models.json —
they re-appear on every run until the model surfaces in a core row or is
admitted to the catalog.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure chimera is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from chimera.provider_discovery import (  # noqa: E402
    PROVIDER_ID_MAP,
    _fetch_models_dev,
    _load_cache,
    _mtok_to_per_1k,
    _resolve_model_id,
    _save_cache,
    load_preferred_registry,
)

# ── Constants ────────────────────────────────────────────────────────────────

#: Core providers we care about for model sync (must match PROVIDER_ID_MAP).
CORE_PROVIDERS: set[str] = {
    "openai",
    "anthropic",
    "deepseek",
    "google",
    "xai",
    "mistral",
    "moonshotai",
    "minimax",
    "alibaba",
    "zhipuai",
    "meta",
    "stepfun",
    "xiaomi",
}

#: Provider display names.
PROVIDER_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "google": "Google",
    "xai": "xAI",
    "mistral": "Mistral",
    "moonshotai": "Moonshot (Kimi)",
    "minimax": "MiniMax",
    "alibaba": "Alibaba (Qwen)",
    "zhipuai": "ZhipuAI (GLM)",
    "meta": "Meta",
    "stepfun": "StepFun",
    "xiaomi": "Xiaomi",
}

#: Model families to skip (embeddings, speech, rerank, legacy, etc.).
SKIP_FAMILIES: set[str] = {
    "embedding",
    "embeddings",
    "speech",
    "tts",
    "audio",
    "rerank",
    "reranker",
    "moderation",
    "guard",
    "dall-e",
    "dalle",
    "imagen",
    "imagegen",
    "image-gen",
    "whisper",
    "transcription",
    "translate",
    "text-embedding",
    "babbage",
    "davinci",
    "ada",
    "stable-diffusion",
    "sdxl",
    "midjourney",
    "video",
    "video-gen",
    "sora",
    "bge",
    "gte",
    "e5",
    "stella",
    "voxtral",  # Mistral speech/STT family (audio-in only; added 2026-08-04)
}

#: Model name substrings that indicate non-chat models.
SKIP_NAME_PATTERNS: list[str] = [
    "embedding",
    "embed",
    "speech",
    "tts",
    "audio",
    "whisper",
    "rerank",
    "moderation",
    "guard",
    "dall-e",
    "dalle",
    "imagen",
    "stable-diffusion",
    "sdxl",
    "bge-",
    "gte-",
    "e5-",
    "stella-",
    "vision",
    "ocr",
    "video",
    # Image generation
    "gpt-image",
    "chatgpt-image",
    "grok-imagine",
    # Audio/ASR
    "asr-",
    "-asr",
    "livetranslate",
    # Vision-only
    "-vl-",
    "vl-",
    "-vl",
    # Omni (multimodal, not text-centric)
    "-omni-",
    "omni-",
    # Non-text modalities
    "-tts",
    "tts-",
    # Image-preview (not text models)
    "-image-preview",
    "-image-quality",
    # Image/live/music/video-gen/robotics noise (added 2026-08-04)
    "-image",
    "lyria",
    "veo",
    "robotics",
    # Live/streaming modalities
    "-live",
    "live-",
]

#: Path for tracking already-seen candidate models.
SEEN_PATH: Path = REPO_ROOT / ".seen_models.json"

#: Reseller / aggregator models.dev rows scanned IN THE SAME PASS as the core
#: providers (DF-CHIMERA-V2-26). Frontier releases often land here first, namespaced
#: under the owning lab (e.g. ``stepfun/step-5-preview`` in the nano-gpt row).
RESELLER_WATCH: set[str] = {
    "openrouter",
    "kilo",
    "nano-gpt",
    "vercel",
    "llmgateway",
}

#: Known lab prefixes used to attribute a reseller id whose basename carries a
#: family hint instead of a lab path segment (e.g. ``claude-sonnet-4-6``).
_LAB_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("gemini", "google"),
    ("grok", "xai"),
    ("deepseek", "deepseek"),
    ("glm", "zhipuai"),
    ("kimi", "moonshotai"),
    ("minimax", "minimax"),
    ("qwen", "alibaba"),
    ("mistral", "mistral"),
    ("llama", "meta"),
    ("step-", "stepfun"),
    ("ernie", "baidu"),
)

#: Map a models.dev provider id to the lab prefix used in reseller ids.
#: Most match 1:1; this table handles the exceptions (mirrors PROVIDER_ID_MAP).
_RESALE_LAB_PREFIXES: dict[str, str] = {
    "moonshotai": "moonshot",
    "zhipuai": "zai",
    "xai": "x-ai",
    "alibaba": "qwen",
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "deepseek": "deepseek",
    "meta": "meta",
    "mistral": "mistral",
    "minimax": "minimax",
    "stepfun": "stepfun",
    "xiaomi": "xiaomi",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_chat_model(model_id: str, family: str | None = None) -> bool:
    """Return True if the model is a chat/completion/reasoning model."""
    lower = model_id.lower()

    # Explicitly skip known non-chat families
    if family and family.lower() in SKIP_FAMILIES:
        return False

    # Skip by name patterns
    for pat in SKIP_NAME_PATTERNS:
        if pat in lower:
            return False

    # Skip obvious non-chat prefixes
    skip_prefixes = ("davinci", "babbage", "curie", "ada-")
    return not any(lower.startswith(p) for p in skip_prefixes)


def _load_chimera_models() -> set[str]:
    """Return the set of model IDs from the current chimera.yaml catalog."""
    from chimera.config import load_config

    config = load_config()
    return set(config.models.keys())


def _load_seen() -> set[str]:
    """Load the set of already-reported candidate model IDs."""
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_seen(seen: set[str]) -> None:
    """Save the set of already-reported candidate model IDs."""
    SEEN_PATH.write_text(json.dumps(sorted(seen), indent=2))


#: Day buckets for the 0-100 recency scale (inclusive upper bounds, in days).
RECENCY_BUCKETS: tuple[tuple[float, float], ...] = (
    (7, 100.0),
    (30, 90.0),
    (90, 70.0),
    (180, 50.0),
)
RECENCY_OLDEST: float = 30.0
RECENCY_DEFAULT: float = 40.0

#: Date fields carried by models.dev rows, in preference order. The live cache
#: (``~/.chimera/models-dev-cache.json``) stores ISO-8601 date strings here —
#: it does NOT carry the numeric unix ``created`` key the OpenAI-style API uses.
RECENCY_DATE_FIELDS: tuple[str, ...] = ("release_date", "last_updated")


def _score_days_ago(days_ago: float) -> float:
    """Map an age in days onto the 0-100 recency scale (newer = higher)."""
    for max_days, score in RECENCY_BUCKETS:
        if days_ago <= max_days:
            return score
    return RECENCY_OLDEST


def _parse_iso_timestamp(value: Any) -> float | None:
    """Parse an ISO-8601 date/datetime (or unix timestamp) into a UTC timestamp.

    Accepts ``"2026-06-13"``, ``"2026-06-13T10:00:00Z"``, ``"2026-06-13T10:00:00+00:00"``,
    ``"2026/06/13"`` and numeric unix timestamps (int/float or numeric string).

    Returns ``None`` for anything unparseable — a malformed date in the provider
    cache must never raise, because this runs inside the model-sync cron.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        # Numeric string — a unix timestamp written as text.
        return float(text)
    except ValueError:
        pass

    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _family_recency_score(model_id: str) -> float:
    """Score a model by family/version heuristics — the date-less tie-break."""
    lower = model_id.lower()
    # Newer model families score higher
    if "4.3" in lower or "4.20" in lower:
        return 85.0  # Grok 4.x
    if "5.5" in lower:
        return 90.0  # GPT-5.5
    if "5.2" in lower:
        return 88.0  # GPT-5.2 / GLM-5.2
    if "k2.7" in lower or "k2.6" in lower:
        return 85.0  # Kimi K2.x
    if "claude" in lower and ("4.8" in lower or "4.7" in lower):
        return 85.0  # Claude 4.x
    if "gemini-3" in lower:
        return 85.0  # Gemini 3.x
    if "v4" in lower:
        return 80.0  # DeepSeek v4
    if "m2.7" in lower or "m2.5" in lower:
        return 80.0  # MiniMax M2.x

    return RECENCY_DEFAULT  # default


def _model_recency_timestamp(provider_data: dict[str, Any], model_id: str) -> float | None:
    """Resolve the UTC timestamp a model's recency score is derived from.

    This is the single source of truth behind both the score and the
    ``recency_ts`` carried on each candidate dict: the numeric unix ``created``
    timestamp first (the OpenAI-style API shape), then the ISO-8601
    ``release_date`` / ``last_updated`` strings the live models.dev cache
    actually carries.

    Returns ``None`` when the row has no usable date at all — i.e. when the
    score comes from the family heuristic table or the ``RECENCY_DEFAULT`` of
    40.0. A malformed date never raises (this runs inside the model-sync cron).
    """
    model_info = provider_data.get("models", {}).get(model_id, {})
    if not isinstance(model_info, dict):
        model_info = {}

    created = model_info.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool) and created > 0:
        return float(created)

    # No numeric timestamp — the live cache carries ISO-8601 date strings.
    for field in RECENCY_DATE_FIELDS:
        created_ts = _parse_iso_timestamp(model_info.get(field))
        if created_ts is not None:
            return created_ts

    return None


def _model_recency_score(provider_data: dict[str, Any], model_id: str) -> float:
    """Score a model by recency — higher is newer.

    Primary source is a numeric unix ``created`` timestamp (the OpenAI-style API
    shape); when that is absent — as it is for every row in the live models.dev
    cache — fall back to the ISO-8601 ``release_date`` and then ``last_updated``
    strings the cache actually carries. Models with no usable date at all fall
    back to family heuristics, then the ``RECENCY_DEFAULT`` of 40.0.
    Returns 0-100 where 100 = newest.

    The date itself is resolved by ``_model_recency_timestamp()`` (the same
    helper ``scan_models_dev()`` uses to populate ``recency_ts``).
    """
    recency_ts = _model_recency_timestamp(provider_data, model_id)
    if recency_ts is not None:
        return _score_days_ago((time.time() - recency_ts) / 86400)

    # No usable date — score by family-based heuristics
    return _family_recency_score(model_id)


def _recency_sort_key(candidate: dict[str, Any]) -> tuple[float, int, float, str]:
    """Deterministic newest-first ordering key for candidate dicts.

    ``(recency_score DESC, dated-before-undated, recency_ts DESC, model_id ASC)``.

    The bucket score is coarse (7/30/90/180 days), so every candidate inside one
    bucket scores identically; the resolved date is what orders those ties by
    real newness instead of by model id or input order. Candidates with no
    usable date at all (family heuristics / ``RECENCY_DEFAULT``) sort last
    within their score group, deterministically by ``model_id`` ascending.
    """
    score = candidate.get("recency_score")
    score = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else 0.0
    recency_ts = candidate.get("recency_ts")
    dated = isinstance(recency_ts, (int, float)) and not isinstance(recency_ts, bool)
    return (
        -score,
        0 if dated else 1,
        -float(recency_ts) if dated else 0.0,
        str(candidate.get("model_id", "")),
    )


def select_top_candidates(
    candidates: dict[str, list[dict[str, Any]]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Flatten provider candidates, sort newest-first, and take the top ``limit``.

    Pure selection used by ``--score`` (top 5) and ``--limit`` (top N): ordering
    is by ``recency_score`` descending, and equal-score buckets are broken by the
    resolved ``recency_ts`` descending — so ties inside one bucket are ordered by
    real newness, not alphabetically by model id or by input/provider order.
    Candidates carrying no usable date (family heuristics / ``RECENCY_DEFAULT``)
    sort last within their score group, deterministically by ``model_id``
    ascending. ``limit <= 0`` returns every candidate.
    """
    flat: list[dict[str, Any]] = []
    for models in candidates.values():
        flat.extend(models)
    flat.sort(key=_recency_sort_key)
    if limit > 0:
        flat = flat[:limit]
    return flat


# ── Main logic ───────────────────────────────────────────────────────────────


def scan_models_dev(
    cache: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Scan registry data for new chat/reasoning models.

    ``cache`` accepts an already-selected models.dev-compatible registry.  When
    omitted, the legacy models.dev cache/refresh path remains available for
    direct callers and focused tests.

    Returns dict mapping provider_id → list of candidate model dicts.
    """
    if cache is None:
        cache = _load_cache()
    if cache is None:
        # Cache missing or stale (CACHE_TTL is 30 min) — refresh from the
        # network before giving up. Without this, the cron wrapper fails on
        # almost every scheduled run (observed 3 consecutive weeks, Aug
        # 15-17 2026) because the cache is only refreshed on demand by
        # server startup/gateway activity. Fall back to the stale cache if
        # the network is unreachable — old data beats no data.
        print("INFO: models.dev cache missing or stale — refreshing from network...")
        try:
            _save_cache(_fetch_models_dev())
            cache = _load_cache()
        except Exception as exc:
            print(f"WARNING: models.dev refresh failed ({exc}) — using stale cache")
            cache = _load_cache(ignore_ttl=True)
        if cache is None:
            print(
                "ERROR: models.dev cache is stale or missing. "
                "Run `chimera models` to refresh the provider cache."
            )
            sys.exit(1)

    chimera_models = _load_chimera_models()

    candidates: dict[str, list[dict[str, Any]]] = {}

    for provider_id in sorted(CORE_PROVIDERS):
        if provider_id not in cache:
            continue
        provider_data = cache[provider_id]
        if not isinstance(provider_data, dict):
            continue

        models = provider_data.get("models", {})
        provider_candidates: list[dict[str, Any]] = []

        for model_id, model_info in sorted(models.items()):
            if not isinstance(model_info, dict):
                continue

            family = model_info.get("family", "")

            # Skip non-chat models
            if not _is_chat_model(model_id, family):
                continue

            # Resolve to Chimera ID
            chimera_id = _resolve_model_id(provider_id, model_id)

            # Skip already in catalog
            if chimera_id in chimera_models:
                continue

            # Extract pricing
            cost = model_info.get("cost", {})
            input_cost = cost.get("input") if isinstance(cost, dict) else None
            output_cost = cost.get("output") if isinstance(cost, dict) else None

            recency = _model_recency_score(provider_data, model_id)
            # Additive: the resolved date behind `recency` (same helper/source),
            # so selection can break equal-score ties by real newness. None when
            # the score came from the family heuristics / RECENCY_DEFAULT.
            recency_ts = _model_recency_timestamp(provider_data, model_id)

            provider_candidates.append(
                {
                    "model_id": model_id,
                    "chimera_id": chimera_id,
                    "family": family,
                    "description": model_info.get("description", ""),
                    "input_cost_mtok": input_cost,
                    "output_cost_mtok": output_cost,
                    "input_per_1k": _mtok_to_per_1k(input_cost) if input_cost else None,
                    "output_per_1k": _mtok_to_per_1k(output_cost) if output_cost else None,
                    "recency_score": recency,
                    "recency_ts": recency_ts,
                    "provider": provider_id,
                }
            )

        if provider_candidates:
            # Sort by recency (newest first, date tie-break inside a bucket)
            provider_candidates.sort(key=_recency_sort_key)
            candidates[provider_id] = provider_candidates

    return candidates


def _attribute_lab(model_id: str, family: str | None = None) -> str | None:
    """Hypothesize the owning lab for a reseller-rows model id, or None.

    Two signals, in order:

    1. id shape — the first path segment of a namespaced id
       (``stepfun/step-5-preview`` → ``stepfun``), checked against the known
       core lab ids (PROVIDER_ID_MAP keys, via ``_RESALE_LAB_PREFIXES``);
    2. family / basename prefix — a known lab family prefix
       (``claude-sonnet-4-6`` → ``anthropic``).

    Returns ``None`` for genuinely unattributable ids — those are blind-spot
    candidates, never silently dropped.
    """
    basename = model_id.rsplit("/", 1)[-1]
    first_segment = model_id.split("/", 1)[0] if "/" in model_id else ""

    # 1. Namespaced id: first path segment is a known lab.
    if first_segment:
        for lab_id, lab_prefix in _RESALE_LAB_PREFIXES.items():
            if first_segment.lower() == lab_prefix:
                return lab_id
        if first_segment.lower() in PROVIDER_ID_MAP:
            return first_segment.lower()

    # 2. Family or basename prefix carries a known lab family hint.
    for source in (family or "", basename):
        low = source.lower()
        for prefix, lab_id in _LAB_FAMILY_PREFIXES:
            if low.startswith(prefix):
                return lab_id

    return None


def scan_reseller_watch(
    cache: dict[str, Any],
    core_basenames: set[str],
    chimera_models: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan the RESELLER_WATCH rows for models the core scan cannot see.

    Returns ``(watch, blind)`` — both sorted newest-first:

    * ``watch``: NEW chat models found only in reseller rows whose owning lab
      could be hypothesized from the id shape / family prefix. Each entry is a
      candidate dict (same shape as the core scan) plus ``lab`` (the
      hypothesized owning lab) and ``reseller_rows`` (the reseller rows that
      carry it, newest-first).
    * ``blind``: the same, for ids that could NOT be attributed — the explicit
      blind-spot list.

    Dedupe rules (deliberately coarse, at BASENAME level): an id whose basename
    already appears in a core row is not reported (the core scan sees that
    model); an id whose basename matches the basename of an admitted catalog
    id is not reported (admitted — a namespaced reseller id never equals its
    resolved Chimera id, so the comparison is done on basenames).
    """
    chimera_models = chimera_models if chimera_models is not None else _load_chimera_models()
    catalog_basenames = {cid.rsplit("/", 1)[-1] for cid in chimera_models}

    aggregated: dict[str, dict[str, Any]] = {}

    for provider_id in sorted(RESELLER_WATCH):
        provider_data = cache.get(provider_id)
        if not isinstance(provider_data, dict):
            continue
        models = provider_data.get("models", {})
        if not isinstance(models, dict):
            continue

        for model_id, model_info in sorted(models.items()):
            if not isinstance(model_info, dict):
                continue
            if not _is_chat_model(model_id, model_info.get("family", "")):
                continue
            # Already visible to the core scan, or already admitted to the
            # catalog (basename-level comparison — see docstring).
            basename = model_id.rsplit("/", 1)[-1]
            if basename in core_basenames or basename in catalog_basenames:
                continue

            chimera_id = _resolve_model_id(provider_id, model_id)

            cost = model_info.get("cost", {})
            input_cost = cost.get("input") if isinstance(cost, dict) else None
            output_cost = cost.get("output") if isinstance(cost, dict) else None
            recency = _model_recency_score(provider_data, model_id)
            recency_ts = _model_recency_timestamp(provider_data, model_id)

            entry = aggregated.setdefault(
                model_id,
                {
                    "model_id": model_id,
                    "chimera_id": chimera_id,
                    "family": model_info.get("family", ""),
                    "description": model_info.get("description", ""),
                    "input_cost_mtok": input_cost,
                    "output_cost_mtok": output_cost,
                    "input_per_1k": _mtok_to_per_1k(input_cost) if input_cost else None,
                    "output_per_1k": _mtok_to_per_1k(output_cost) if output_cost else None,
                    "recency_score": recency,
                    "recency_ts": recency_ts,
                    "provider": provider_id,
                    "lab": None,
                    "reseller_rows": [],
                },
            )
            entry["reseller_rows"].append(provider_id)
            # Keep the best (newest) date/price data across carriers.
            if recency_ts is not None and (entry["recency_ts"] is None or recency_ts > entry["recency_ts"]):
                entry["recency_ts"] = recency_ts
                entry["recency_score"] = recency

    watch: list[dict[str, Any]] = []
    blind: list[dict[str, Any]] = []
    for entry in aggregated.values():
        entry["lab"] = _attribute_lab(entry["model_id"], entry["family"])
        (watch if entry["lab"] else blind).append(entry)

    watch.sort(key=_recency_sort_key)
    blind.sort(key=_recency_sort_key)
    return watch, blind


def scan_all() -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """One cache pass: the core scan plus the reseller watch, with scan scope.

    Returns ``(candidates, watch, blind, scope)`` where ``scope`` states which
    provider ids are IN (core + reseller) and how many models.dev rows are OUT
    of scope — the report prints this on every run.
    """
    snapshot = load_preferred_registry()
    cache = snapshot.data
    if not cache:
        print(
            "ERROR: neither task-router nor models.dev supplied a usable registry. "
            "Set CHIMERA_TASK_ROUTER_MODELS_PATH or run `chimera models` to refresh."
        )
        sys.exit(1)

    candidates = scan_models_dev(cache)
    core_basenames = {
        m["model_id"] for models in candidates.values() for m in models
    } | _load_chimera_models() or set()
    watch, blind = scan_reseller_watch(cache, core_basenames)

    scope: dict[str, Any] = {
        "core": sorted(CORE_PROVIDERS),
        "reseller": sorted(RESELLER_WATCH),
        "out_of_scope": sum(1 for pid in cache if pid not in CORE_PROVIDERS and pid not in RESELLER_WATCH),
    }
    return candidates, watch, blind, scope


def _format_scope_statement(scope: dict[str, Any] | None, markdown: bool) -> list[str]:
    """The scan-scope lines: which provider ids are IN, how many rows are OUT.

    Printed on EVERY run (header + footer). ``scope=None`` falls back to the
    configured lists — used when the report is formatted without a cache pass.
    """
    core = sorted(scope["core"]) if scope else sorted(CORE_PROVIDERS)
    reseller = sorted(scope["reseller"]) if scope else sorted(RESELLER_WATCH)
    out_count = int(scope["out_of_scope"]) if scope else 0

    scope_line = (
        f"Scan scope — IN: core providers ({', '.join(core)}); "
        f"reseller watch ({', '.join(reseller)}). "
        f"OUT: {out_count} other models.dev rows (not scanned)."
    )
    policy_line = (
        "Reseller Watch / Blind Spot sections are informational and NOT recorded "
        "in .seen_models.json — reseller-only finds are re-reported on every run "
        "until they appear in a core row or are admitted to the catalog."
    )
    if markdown:
        return [f"**{scope_line}**", "", f"*{policy_line}*", ""]
    return [scope_line, policy_line, ""]


def _format_reseller_section(
    title: str,
    entries: list[dict[str, Any]],
    markdown: bool,
    show_lab: bool,
) -> list[str]:
    """One reseller report section ("Reseller Watch" or "Blind Spot")."""
    if not entries:
        return [f"## {title}", "", f"None this run — no {title.lower()} candidates.", ""]

    lines: list[str] = [f"## {title}", ""]
    if markdown:
        lines.append("| Model | Lab | Rows | Recency | Input/1k | Output/1k |")
        lines.append("|-------|-----|------|---------|----------|-----------|")
    else:
        lines.append(f"  {title} — {len(entries)} candidates")

    for m in entries:
        inp = f"${m['input_per_1k']:.6f}" if m["input_per_1k"] else "N/A"
        out = f"${m['output_per_1k']:.6f}" if m["output_per_1k"] else "N/A"
        rec = m["recency_score"]
        rows = ", ".join(m["reseller_rows"])
        lab = m.get("lab") or "unattributed"
        if markdown:
            model_cell = f"`{m['model_id']}`"
            lab_cell = f"`{lab}`" if show_lab else lab
            lines.append(f"| {model_cell} | {lab_cell} | {rows} | {rec:.0f} | {inp} | {out} |")
        else:
            lines.append(
                f"  {m['model_id']:50s} lab={lab if show_lab else '-':12s} "
                f"rows=[{rows}]  recency={rec:.0f}  inp={inp}  out={out}"
            )

    lines.append("")
    return lines


def format_report(
    candidates: dict[str, list[dict[str, Any]]],
    diff_only: bool = False,
    markdown: bool = False,
    reseller_watch: list[dict[str, Any]] | None = None,
    blind_spot: list[dict[str, Any]] | None = None,
    scope: dict[str, Any] | None = None,
) -> str:
    """Format candidate models as a report string.

    ``reseller_watch`` / ``blind_spot`` are the two lists from
    ``scan_reseller_watch()``; ``scope`` is the dict from ``scan_all()``. All
    three are optional so existing callers/tests keep working: when omitted,
    the sections render as "None this run" and the scope statement falls back
    to the configured lists.
    """
    reseller_watch = reseller_watch or []
    blind_spot = blind_spot or []
    seen = _load_seen()

    lines: list[str] = []
    new_seen: set[str] = set()

    total_new = 0

    for provider_id, models in candidates.items():
        provider_name = PROVIDER_NAMES.get(provider_id, provider_id)

        # Filter for --diff mode
        if diff_only:
            models = [m for m in models if m["chimera_id"] not in seen]
            if not models:
                continue

        new_seen.update(m["chimera_id"] for m in models)

        if markdown:
            lines.append(f"## {provider_name} (`{provider_id}`)")
            lines.append("")
            lines.append("| Model | Chimera ID | Recency | Input/1k | Output/1k |")
            lines.append("|-------|-----------|---------|----------|-----------|")
        else:
            lines.append(f"\n{'=' * 70}")
            lines.append(f"  {provider_name} ({provider_id}) — {len(models)} candidates")
            lines.append(f"{'=' * 70}")

        for m in models:
            inp = f"${m['input_per_1k']:.6f}" if m["input_per_1k"] else "N/A"
            out = f"${m['output_per_1k']:.6f}" if m["output_per_1k"] else "N/A"
            rec = m["recency_score"]

            if markdown:
                lines.append(f"| `{m['model_id']}` | `{m['chimera_id']}` | {rec:.0f} | {inp} | {out} |")
            else:
                tag = " [NEW]" if m["chimera_id"] not in seen else ""
                lines.append(f"  {m['chimera_id']:50s} recency={rec:.0f}  inp={inp}  out={out}{tag}")

            total_new += 1

        if markdown:
            lines.append("")

    # Reseller watch + blind spot — informational, never tracked in .seen_models.json
    lines.extend(_format_reseller_section("Reseller Watch", reseller_watch, markdown, show_lab=True))
    lines.extend(_format_reseller_section("Blind Spot", blind_spot, markdown, show_lab=False))
    policy = (
        "Reseller Watch / Blind Spot sections are informational and NOT recorded "
        "in .seen_models.json — reseller-only finds are re-reported on every run "
        "until they appear in a core row or are admitted to the catalog."
    )
    lines.append(policy)
    lines.append("")

    # Summary
    if markdown:
        header = [
            "# Chimera Model Sync Report",
            "",
            f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Candidates:** {total_new} new models across {len(candidates)} providers",
            "",
        ]
        header.extend(_format_scope_statement(scope, markdown=True))
        lines = header + lines
    else:
        header = [f"Chimera Model Sync — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"]
        header.append(f"Candidates: {total_new} new models across {len(candidates)} providers")
        header.append("")
        header.extend(_format_scope_statement(scope, markdown=False))
        lines = header + lines

    # Footer: scope statement again + explicit tracking policy.
    lines.append("---")
    lines.append("")
    lines.extend(_format_scope_statement(scope, markdown))

    # Update seen models — CORE finds only. Reseller watch/blind ids are
    # deliberately NOT recorded: they are re-reported every run until the
    # model surfaces in a core row or is admitted to the catalog.
    if diff_only or candidates:
        all_seen = seen | new_seen
        _save_seen(all_seen)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan models.dev for new Chimera candidates")
    parser.add_argument(
        "--diff", action="store_true", help="Show only newly-seen models (not previously reported)"
    )
    parser.add_argument(
        "--score", action="store_true", help="LLM-score top 5 candidates (requires DEEPSEEK_API_KEY)"
    )
    parser.add_argument("--output", type=str, default=None, help="Write report to a markdown file")
    parser.add_argument("--limit", type=int, default=0, help="Limit to top N candidates (0 = all)")
    parser.add_argument(
        "--diff-json",
        type=str,
        default=None,
        metavar="PATH",
        help="With --diff: save the post-diff-filter candidate set as JSON "
        "(the step-1 side of the cron pipeline)",
    )
    parser.add_argument(
        "--score-from",
        type=str,
        default=None,
        metavar="PATH",
        help="Score the candidates from a saved --diff-json file instead of "
        "re-scanning (standalone; no cache pass, no .seen_models update)",
    )
    args = parser.parse_args()

    # --score-from is standalone: it consumes a saved diff file and never
    # touches the models.dev cache or .seen_models.json (the cron wrapper's
    # step 1 already did both — DF-CHIMERA-V2-37).
    if args.score_from:
        _score_from_file(args.score_from)
        return

    candidates, watch, blind, scope = scan_all()

    if args.diff_json:
        # Save the NEW finds (the same set --diff would report) before
        # format_report() marks them seen, so step 3 of the cron pipeline can
        # score exactly this set instead of re-deriving an empty diff.
        seen_ids = _load_seen()
        diff_set: dict[str, list[dict[str, Any]]] = {}
        for provider_id, models in candidates.items():
            fresh = [m for m in models if m["chimera_id"] not in seen_ids]
            if fresh:
                diff_set[provider_id] = fresh
        diff_json_path = Path(args.diff_json)
        diff_json_path.parent.mkdir(parents=True, exist_ok=True)
        diff_json_path.write_text(json.dumps(diff_set, indent=2))
        print(f"Diff candidates saved to {diff_json_path}")

    if args.limit > 0:
        # Flatten, re-sort by recency and keep the top N
        flat = select_top_candidates(candidates, limit=args.limit)

        # Rebuild providers dict
        limited: dict[str, list[dict[str, Any]]] = {}
        for m in flat:
            limited.setdefault(m["provider"], []).append(m)
        candidates = limited

    report = format_report(
        candidates,
        diff_only=args.diff,
        markdown=bool(args.output),
        reseller_watch=watch,
        blind_spot=blind,
        scope=scope,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Also save timestamped copy
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        ts_path = output_path.parent / f"{output_path.stem}_{ts}{output_path.suffix}"
        ts_path.write_text(report)
        output_path.write_text(report)
        print(f"Report saved to {output_path} (and {ts_path})")
    else:
        print(report)

    # --score: LLM-score top 5 candidates
    if args.score and candidates:
        _llm_score_candidates(candidates)

    # --score-from: same scorer, but the candidates come from the saved diff
    # file (--score-from path) rather than a re-derived (already-empty) diff.
    if args.score_from and candidates:
        _llm_score_candidates(candidates)


# ── LLM scoring (``--score``) ────────────────────────────────────────────────

#: DeepSeek chat-completions endpoint used by ``--score``.
SCORE_ENDPOINT: str = "https://api.deepseek.com/v1/chat/completions"

#: Model that scores candidates. Reasoning models share this endpoint, so the
#: reply may carry ``content=""`` + ``finish_reason="length"`` (see
#: ``_extract_json_object``); the retry ladder below handles that.
SCORE_MODEL: str = "deepseek-v4-flash"

#: Token budget for the first scoring call; doubled on a truncated reply.
SCORE_MAX_TOKENS: int = 8192

#: Hard ceiling for the retry ladder — a reply truncated even here is an error.
SCORE_MAX_TOKENS_CEILING: int = 32768


def _extract_json_object(text: str | None) -> dict[str, Any]:
    """Parse a JSON object out of a model reply, tolerating fences and prose.

    Raises ``ValueError`` with a diagnostic message — never a bare
    ``json.JSONDecodeError``. An empty ``content`` is the signature of a
    reasoning model that spent its entire ``max_tokens`` budget on
    ``reasoning_content`` and returned ``finish_reason="length"``; the caller
    retries with a larger budget and needs to be able to tell that apart from
    a genuinely unparsable reply.
    """
    if not text or not text.strip():
        raise ValueError("empty model content (reasoning likely consumed the whole max_tokens budget)")

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"no JSON object in model content: {stripped[:120]!r}") from None
        return json.loads(stripped[start : end + 1])


def _score_request_body(model: str, prompt: str, max_tokens: int) -> bytes:
    """Build the JSON request body for one scoring call."""
    return json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
    ).encode()


def _post_score_request(
    model: str,
    prompt: str,
    max_tokens: int,
    api_key: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """POST one scoring request to DeepSeek and return the decoded response."""
    import urllib.request

    req = urllib.request.Request(
        SCORE_ENDPOINT,
        data=_score_request_body(model, prompt, max_tokens),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _score_llm_reply(
    prompt: str,
    api_key: str,
    post: Callable[[str, str, int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ask DeepSeek to score the candidates, retrying a truncated reply.

    ``deepseek-v4-flash`` is a reasoning model: at a small ``max_tokens`` the
    whole budget goes to ``reasoning_content`` and ``content`` comes back
    empty with ``finish_reason="length"`` — the 2026-09-18 cron run failed with
    ``Expecting value: line 1 column 1 (char 0)`` for exactly this reason.
    Doubling the budget on that signal (up to ``SCORE_MAX_TOKENS_CEILING``)
    leaves room for the JSON payload; anything else raises.
    """
    post = post or _post_score_request
    budget = SCORE_MAX_TOKENS

    while True:
        data = post(SCORE_MODEL, prompt, budget, api_key)
        choices = data.get("choices") or [{}]
        choice = choices[0] or {}
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")

        try:
            return _extract_json_object(message.get("content"))
        except ValueError as exc:
            truncated = finish_reason == "length"
            if not truncated or budget >= SCORE_MAX_TOKENS_CEILING:
                raise ValueError(
                    f"{exc} (model={SCORE_MODEL}, finish_reason={finish_reason}, max_tokens={budget})"
                ) from None
            budget = min(budget * 2, SCORE_MAX_TOKENS_CEILING)


def _score_from_file(path_str: str) -> None:
    """Score the candidates saved by a previous ``--diff --diff-json`` run.

    Standalone companion of ``--score-from`` (DF-CHIMERA-V2-37): the cron
    wrapper's step 1 consumes the diff and records it in ``.seen_models.json``,
    so step 3 can no longer re-derive it — instead it scores EXACTLY the saved
    set. This fixes the "new find with an old release_date is never scored"
    defect: the saved set is precisely the new finds, so top-5 selection only
    orders within that (small) pool.

    Never touches the models.dev cache or ``.seen_models.json``. Exits 2 on a
    missing/malformed file (usage error, not a scan failure).
    """
    path = Path(path_str)
    try:
        diff_set = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read diff candidates from {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(diff_set, dict):
        print(f"ERROR: {path} does not contain a candidates object", file=sys.stderr)
        sys.exit(2)

    candidates: dict[str, list[dict[str, Any]]] = {
        provider: models for provider, models in diff_set.items() if models
    }
    if not candidates:
        print("Diff candidates file is empty — nothing to score.")
        return
    _llm_score_candidates(candidates)


def _llm_score_candidates(candidates: dict[str, list[dict[str, Any]]]) -> None:
    """Use DeepSeek to score top candidates on Chimera's hierarchical category paths.

    Saves scored models to reports/model_scores_<timestamp>.yaml.
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("\n⚠️  --score requires DEEPSEEK_API_KEY in environment. Skipping.")
        return

    # Flatten and take top 5 (pure selection — no network, no API key needed)
    top5 = select_top_candidates(candidates, limit=5)

    # Build prompt with model info and category paths
    from chimera.selector import PATH_PATTERNS

    category_paths = sorted({p for p, _ in PATH_PATTERNS})
    path_list = "\n".join(f"- {p}" for p in category_paths)

    model_descriptions = "\n".join(
        f"- `{m['chimera_id']}`: {m.get('description', m.get('family', ''))[:200]}" for m in top5
    )

    prompt = f"""You are evaluating LLM models for inclusion in the Chimera multi-model deliberation system.

Chimera uses a hierarchical category system to route tasks to the right model.
Each model is scored 0-100 on relevant categories.
Only score categories where the model genuinely excels (≥60).

Available category paths:
{path_list}

Candidate models to evaluate:
{model_descriptions}

For each model, assign scores (0-100, whole numbers only, ≥60) on the relevant category paths. Return JSON:

```json
{{
  "models": [
    {{
      "chimera_id": "provider/model-name",
      "cost_tier": "budget|standard|premium",
      "scores": {{
        "path/to/category": 85,
        "path/to/another": 70
      }},
      "reasoning": "Brief justification for scores"
    }}
  ]
}}
```

Only include paths where score ≥60. Use whole numbers only.
Be conservative — only score categories the model is known to excel at
based on benchmarks and provider claims."""

    try:
        scored = _score_llm_reply(prompt, deepseek_key)

        # Save to YAML
        reports_dir = REPO_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        score_path = reports_dir / f"model_scores_{ts}.yaml"

        import yaml as yaml_lib

        score_path.write_text(yaml_lib.dump(scored, default_flow_style=False, sort_keys=False))
        print(f"\n✅ Model scores saved to {score_path}")

    except Exception as e:
        print(f"\n❌ LLM scoring failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
