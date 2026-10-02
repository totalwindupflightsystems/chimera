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

Since DF-CHIMERA-V2-50 the core scan ALSO dedupes against the catalog at
BASENAME level (the same comparison the reseller watch uses): a candidate
admitted under a namespaced prefix (e.g. ``openrouter/minimax/minimax-m3``)
never resolves to that exact catalog key from its bare row, so it re-reported
as new. It is now SKIPPED, recorded in .seen_models.json with the basename
match marker, and stated on the report as an explicit SKIP line instead of
inflating the headline.

Since DF-CHIMERA-V2-64 the ``--diff`` SEEN comparison resolves basenames too
(the same one ``_basename`` helper): a candidate's ``chimera_id`` is the
LANE-resolved id, so the same model can reach a later run under a different
id shape (``openai/gpt-6-sol`` one day, ``openai/openai/gpt-6-sol`` the next)
and re-reported as a new find even though it was already seen. The comparison
remains an equality on the whole trailing segment — never a prefix — so an
entry for ``foo-v2`` still never covers ``foo-v3``.

Since DF-CHIMERA-V2-65 the report separates PROVIDER CLASSES. The task-router
registry also carries the fleet's scheduling LANES (xkiro, openai-codex, ...),
and lane SKUs attributed to a core lab were printed under the lab's header and
counted in the "N new models across M providers" headline (measured 09-28:
5 of 7 rows were lane rows, yet the headline claimed 13 providers). Candidates
whose ``provider`` is not a core lab now render in a separate "Task-Router
Lane Providers" section with the lane named — never dropped (the lane registry
surfaced real releases such as kimi-k2.8-preview) — and the headline counts
core-lab candidates only, with lane finds stated as a separate count. Registry
ALIAS rows (``alias_of`` set — e.g. the openai-codex ``gpt-daybreak-*-latest``
pointers to already-catalogued ids) are never counted as new models: they are
skipped with a stated trail and rendered in an explicit "Alias Skips" section
naming ``alias_of``.
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
    _fetch_models_dev,  # noqa: F401  (patch seam: tests monkeypatch this name)
    _load_cache,  # noqa: F401  (patch seam: tests monkeypatch this name)
    _load_models_dev_registry,
    _mtok_to_per_1k,
    _resolve_model_id,
    _save_cache,  # noqa: F401  (patch seam: tests monkeypatch this name)
    lab_of_router_provider,
    load_preferred_registry,
    merge_registry_with_models_dev,
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

#: Task-router LANE ids (scheduling lanes, not labs) mapped to the owning core
#: lab whose models they serve — shared with provider_discovery (single
#: source); consumed here through the alias below.
_LAB_OF_ROUTER_PROVIDER = lab_of_router_provider


def _lab_of_router_provider(provider_id: str, model_id: str) -> str | None:
    """Core lab owning a task-router (provider, model) row (see provider_discovery)."""
    return lab_of_router_provider(provider_id, model_id)


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


def _basename(model_id: str) -> str:
    """The segment after the last ``/`` — the dedupe key of both scan paths.

    THE one basename helper (DF-CHIMERA-V2-50): the reseller watch compares
    basenames because a namespaced reseller id never equals its resolved
    Chimera id, and the core scan now compares basenames because a catalog
    entry admitted under a non-bare prefix (``openrouter/``, ``router9/``,
    ...) is invisible to an exact-id comparison from its bare row. Both paths
    call this symbol so the two definitions can never drift apart.
    """
    return model_id.rsplit("/", 1)[-1]


#: The empty catalog — the frozen default of ``_basename_match``. A module
#: default argument binds ONCE at import time; binding the empty set here
#: guarantees a bare call can never dedupe against a stale snapshot of a
#: populated catalog (tests pin this).
_EMPTY_CATALOG: frozenset[str] = frozenset()


def _basename_match(model_id: str, catalog: set[str] | frozenset[str] | None = None) -> str | None:
    """Return the catalog id whose BASENAME matches ``model_id``'s, or None.

    Case-insensitive on the basename (the catalog carries
    ``router9/mmx/MiniMax-M3`` while models.dev ships ``minimax-m3`` casing);
    prefix-sensitive by design so ``foo-v3`` never matches ``foo-v2``. When
    several catalog entries share the basename the FIRST match in sorted
    order is returned — deterministic across runs.

    ``catalog=None`` binds to the frozen ``_EMPTY_CATALOG`` default: a bare
    call matches nothing instead of silently consulting an import-time
    snapshot of a live catalog.
    """
    if catalog is None:
        catalog = _EMPTY_CATALOG
    target = _basename(model_id).lower()
    for cid in sorted(catalog):
        if _basename(cid).lower() == target:
            return cid
    return None


#: Marker appended to a seen entry when a candidate was skipped by the
#: catalog-basename comparison (DF-CHIMERA-V2-50): ``<id> [basename=<catalog-id>]``.
#: One constant pair so the writer (``format_report``) and the reader
#: (``_seen_entry_id``) can never disagree about the encoding.
SEEN_MARKER_PREFIX: str = " [basename="
SEEN_MARKER_SUFFIX: str = "]"


def _seen_entry_id(entry: str) -> str:
    """The candidate id a seen-file entry records, with any marker stripped.

    Pre-DF-CHIMERA-V2-50 files hold plain ids; the DF-CHIMERA-V2-50 writer
    appends ``SEEN_MARKER_PREFIX <catalog-id> SEEN_MARKER_SUFFIX`` to the entry
    it records for a basename-skipped candidate. Both shapes load as plain
    strings (backward compatible), so any comparison on the id half must strip
    the marker first.
    """
    return entry.split(SEEN_MARKER_PREFIX, 1)[0]


def _alias_of(model_info: Any) -> str | None:
    """The id a registry model row aliases (``alias_of`` field), or ``None``.

    DF-CHIMERA-V2-65: task-router vendor-program rows carry ``alias_of`` (e.g.
    ``gpt-daybreak-blue-latest`` → ``gpt-5.6-sol``), a MOVING pointer — an
    alias must never be counted as a new model. Accepts the model-info dict a
    scan loop already holds; a non-dict or absent/blank field is not an alias.
    """
    if not isinstance(model_info, dict):
        return None
    alias = model_info.get("alias_of")
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    return None


def _seen_match(model_id: str, seen: set[str] | frozenset[str]) -> str | None:
    """Return the seen entry that already covers ``model_id``, or ``None``.

    Three comparisons, in order (DF-CHIMERA-V2-64):

    1. EXACT — the original filter: ``model_id`` itself is a seen entry.
    2. MARKER — a seen entry that IS this candidate's id followed by the
       DF-CHIMERA-V2-50 marker (``<id> [basename=<catalog-id>]``). The id must
       occupy the whole entry up to the marker's leading space, so the marker
       branch can never prefix-match a longer id either.
    3. BASENAME — the trailing segment after the last ``/``, compared for
       WHOLE-segment equality and case-insensitively — the same rule
       ``_basename_match`` applies to the catalog, via the one ``_basename``
       helper, so the two dedupe paths cannot drift.

    Why 3 is needed: ``chimera_id`` is the LANE-resolved id, while the seen
    file records the id shape a model happened to carry on the day it was
    first seen. A later lane resolving a different shape therefore never
    matched by string equality and re-reported the model as new — measured
    2026-09-26: 7 diff rows, 6 of them re-reports (``openai/openai/gpt-6-sol``
    after ``openai/gpt-6-sol``, ``xai/x-ai/grok-4.7`` after ``xai/grok-4.7``,
    ``zai/z-ai/glm-5.3-flashx`` after ``zai/glm-5.3-flashx``).

    The comparison stays an EQUALITY, never a prefix, so the filter is exactly
    as strict as before: a plain entry for ``openai/gpt-6-sol`` still does not
    cover ``openai/gpt-6-sol-mini`` — a different, longer basename. When
    several seen entries share the basename the FIRST in sorted order wins, so
    the answer is deterministic across runs.
    """
    if model_id in seen:
        return model_id
    marker = f"{model_id} "
    target = _basename(model_id).lower()
    basename_hit: str | None = None
    for entry in sorted(seen):
        if entry.startswith(marker):
            return entry
        if basename_hit is None and _basename(_seen_entry_id(entry)).lower() == target:
            basename_hit = entry
    return basename_hit


def _load_seen() -> set[str]:
    """Load the set of already-reported candidate model IDs.

    Entries are plain id strings (pre-DF-CHIMERA-V2-50 files) or id strings
    carrying a `` [basename=<catalog-id>]`` marker appended when a candidate
    was skipped by the catalog-basename comparison — both load as plain
    strings, so old files stay readable and old readers keep working.
    """
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


#: Skips from the LAST ``scan_models_dev()`` call — the report trail that
#: keeps the headline honest (each skipped candidate is STATED, not silently
#: dropped). One entry per skip: basename skips carry
#: ``{model_id, chimera_id, provider, catalog_id}`` (DF-CHIMERA-V2-50); alias
#: skips carry ``{model_id, chimera_id, provider, alias_of}``
#: (DF-CHIMERA-V2-65). Cleared at the start of every scan;
#: ``format_report()`` renders it and never writes it.
LAST_SCAN_SKIPS: list[dict[str, Any]] = []

#: Historical name of ``LAST_SCAN_SKIPS`` (the trail held only basename skips
#: before DF-CHIMERA-V2-65). The alias keeps the existing seam name working —
#: both names always reference the SAME list object.
LAST_BASENAME_SKIPS: list[dict[str, Any]] = LAST_SCAN_SKIPS


def _core_lab_member(lab_block: Any, model_id: str) -> bool:
    """True when the lab's OWN registry block carries this model id.

    DF-CHIMERA-V2-67: the report splits candidates by the row's ``provider``
    field, but a genuine core-lab release can reach a run ONLY through lane
    provider rows (the core block's models.dev fill row is deliberately
    skipped in favour of the router row — router pricing is the authority,
    DF-CHIMERA-V2-49). Membership in the lab's merged block is the promotion
    signal. Compared at BASENAME level (case-insensitive, the same shared
    helper both dedupe paths use): lane rows arrive under different prefix
    shapes for one model (``gpt-6.1-sol``, ``openai/gpt-6.1-sol``,
    ``openai/openai/gpt-6.1-sol``) while the lab block carries one of those
    shapes — whole-basename equality keeps ``foo-v3`` from matching ``foo-v2``.
    """
    if not isinstance(lab_block, dict):
        return False
    models = lab_block.get("models", {})
    if not isinstance(models, dict):
        return False
    target = _basename(model_id).lower()
    return any(_basename(block_id).lower() == target for block_id in models)


def scan_models_dev(
    cache: dict[str, Any] | None = None,
    snapshot: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    """Scan registry data for new chat/reasoning models.

    ``cache`` accepts an already-selected models.dev-compatible registry.  When
    omitted, the preferred-registry path loads the task-router table when
    valid (merging models.dev rows underneath so labs the router table cannot
    cover still reach the core scan — DF-CHIMERA-V2-49) and falls back to the
    models.dev cache/refresh path otherwise. ``snapshot`` may pass an explicit
    ``RegistrySnapshot`` (tests, or a caller that already selected a source);
    its provenance drives the lane-attribution pass. When ``cache`` is given
    without a snapshot, the source is assumed to be models.dev-shaped.

    Returns dict mapping provider_id → list of candidate model dicts.
    Catalog entries sharing a candidate's basename skip the candidate
    (DF-CHIMERA-V2-50); each skip is also appended to the module-level
    ``LAST_BASENAME_SKIPS`` report trail so ``format_report()`` can state it.
    """
    if snapshot is None and cache is None:
        snapshot = load_preferred_registry()
        if not snapshot.data:
            print(
                "ERROR: neither task-router nor models.dev supplied a usable "
                "registry. Set CHIMERA_TASK_ROUTER_MODELS_PATH or run "
                "`chimera models` to refresh."
            )
            sys.exit(1)
    if snapshot is not None:
        snapshot_source = snapshot.source
        if cache is None:
            if snapshot_source == "task-router":
                # Router blocks are lane-named and cannot cover every core
                # lab. Union the models.dev cache UNDERNEATH (router rows
                # win — they are the pricing authority) so coverage returns
                # to 13/13. The fill goes through the ``_load_cache`` seam so
                # tests can mock a fixture cache; on a miss, load models.dev
                # from disk/network.
                fill = _load_cache()
                if fill is None:
                    fill = _load_models_dev_registry()
                cache = merge_registry_with_models_dev(snapshot.data, fill)
            else:
                cache = snapshot.data
    else:
        snapshot_source = "models.dev"
    if not cache:
        print(
            "ERROR: models.dev cache is stale or missing. Run `chimera models` to refresh the provider cache."
        )
        sys.exit(1)
    merged_cache = cache

    chimera_models = _load_chimera_models()

    candidates: dict[str, list[dict[str, Any]]] = {}
    LAST_SCAN_SKIPS.clear()

    # Router-covered (lab, model_id) pairs, computed BEFORE the block scan so
    # a models.dev fill row for an id the router also carries (under a lane)
    # is skipped — the lane pass below supplies it with router pricing, which
    # is the authority (DF-CHIMERA-V2-49).
    router_covered: set[tuple[str, str]] = set()
    if snapshot is not None and snapshot.source == "task-router":
        for lane_id, lane_block in snapshot.data.items():
            if lane_id == "_fetched_at" or not isinstance(lane_block, dict):
                continue
            if lane_id in CORE_PROVIDERS:
                continue  # router lab blocks: the merged lab block IS router data
            for model_id, model_info in lane_block.get("models", {}).items():
                if not isinstance(model_info, dict):
                    continue
                lab = _lab_of_router_provider(lane_id, model_id)
                if lab and lab in CORE_PROVIDERS:
                    router_covered.add((lab, model_id))

    def _scan_core_block(
        provider_id: str,
        provider_data: dict[str, Any],
        bucket: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Collect core candidates from one provider block into ``bucket``."""
        models = provider_data.get("models", {})
        provider_candidates: list[dict[str, Any]] = []

        for model_id, model_info in sorted(models.items()):
            if not isinstance(model_info, dict):
                continue

            family = model_info.get("family", "")

            # Skip non-chat models
            if not _is_chat_model(model_id, family):
                continue

            # An ALIAS row is a moving pointer to another model id
            # (DF-CHIMERA-V2-65) — never a new model. Stated, not dropped:
            # the skip lands on the report's Alias Skips section.
            alias_target = _alias_of(model_info)
            if alias_target is not None:
                LAST_SCAN_SKIPS.append(
                    {
                        "model_id": model_id,
                        "chimera_id": _resolve_model_id(provider_id, model_id),
                        "provider": provider_id,
                        "alias_of": alias_target,
                    }
                )
                continue

            # A models.dev fill row for an id the router also carries (under a
            # lane) is supplied by the lane pass with router pricing instead.
            if (provider_id, model_id) in router_covered:
                continue

            # Resolve to Chimera ID
            chimera_id = _resolve_model_id(provider_id, model_id)

            # Skip already in catalog — exact resolved id first (primary),
            # then the basename comparison the reseller watch uses (a catalog
            # entry admitted under a non-bare prefix never equals the resolved
            # id of its bare-row sibling — DF-CHIMERA-V2-50).
            if chimera_id in chimera_models:
                continue
            basename_match = _basename_match(model_id, chimera_models)
            if basename_match is not None:
                LAST_BASENAME_SKIPS.append(
                    {
                        "model_id": model_id,
                        "chimera_id": chimera_id,
                        "provider": provider_id,
                        "catalog_id": basename_match,
                    }
                )
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
            bucket[provider_id] = provider_candidates

    for provider_id in sorted(CORE_PROVIDERS):
        provider_data = merged_cache.get(provider_id)
        if not isinstance(provider_data, dict):
            continue
        _scan_core_block(provider_id, provider_data, candidates)

    # Task-router rows stored under LANE ids carry core-lab models too —
    # attribute each lane row to its owning lab and scan it under that lab's
    # bucket (DF-CHIMERA-V2-49). A model already attributed to the lab from
    # the lab's own block must not duplicate: the lane scan skips ids the lab
    # block already produced.
    if snapshot is not None and snapshot.source == "task-router":
        lane_rows: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = {}
        for lane_id, lane_block in snapshot.data.items():
            if lane_id == "_fetched_at" or not isinstance(lane_block, dict):
                continue
            if lane_id in CORE_PROVIDERS:
                continue  # lab block — already scanned above
            for model_id, model_info in lane_block.get("models", {}).items():
                if not isinstance(model_info, dict):
                    continue
                lab = _lab_of_router_provider(lane_id, model_id)
                if lab and lab in CORE_PROVIDERS:
                    lane_rows.setdefault(lab, []).append((lane_id, model_id, model_info))

        for lab, rows in lane_rows.items():
            lane_candidates: list[dict[str, Any]] = []
            already = {c["model_id"] for c in candidates.get(lab, [])}
            # Basename-level twins (DF-CHIMERA-V2-67): one release re-carried
            # by several lanes under different prefix shapes (``gpt-6.1-sol``
            # vs ``openai/gpt-6.1-sol``) counts ONCE — measured 09-30, the
            # same openai release arrived via commandcode AND xkiro. Seeded
            # with the lab bucket's existing basenames so a lane twin of a
            # core-scan row is dropped too.
            already_base = {_basename(c["model_id"]).lower() for c in candidates.get(lab, [])}
            admitted_base: dict[str, int] = {}  # basename -> index in lane_candidates
            for lane_id, model_id, model_info in rows:
                if model_id in already:
                    continue
                already.add(model_id)
                if not _is_chat_model(model_id, model_info.get("family", "")):
                    continue
                # Alias guard mirrors the core loop (DF-CHIMERA-V2-65).
                alias_target = _alias_of(model_info)
                if alias_target is not None:
                    LAST_SCAN_SKIPS.append(
                        {
                            "model_id": model_id,
                            "chimera_id": _resolve_model_id(lab, model_id),
                            "provider": lane_id,
                            "alias_of": alias_target,
                        }
                    )
                    continue
                # Resolve against the ATTRIBUTED lab so the chimera id matches
                # the catalog key shape (deepseek/..., not ollama-cloud/...).
                chimera_id = _resolve_model_id(lab, model_id)
                if chimera_id in chimera_models:
                    continue
                cost = model_info.get("cost", {})
                input_cost = cost.get("input") if isinstance(cost, dict) else None
                output_cost = cost.get("output") if isinstance(cost, dict) else None
                recency = _model_recency_score({}, model_id)
                recency_ts = _model_recency_timestamp({}, model_id)
                entry: dict[str, Any] = {
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
                    "provider": lane_id,
                }
                # DF-CHIMERA-V2-67 promotion signal: the model id resolves to
                # the attributed lab's OWN (merged) registry block, so this is
                # a lane-CARRIED core-lab release, not a lane-only SKU. The
                # report promotes it to the core section; ``provider`` keeps
                # the lane id so the row's provenance stays visible.
                if _core_lab_member(merged_cache.get(lab), model_id):
                    entry["core_lab_member"] = True
                base = _basename(model_id).lower()
                twin_idx = admitted_base.get(base)
                if base in already_base or twin_idx is not None:
                    # Same release under another prefix shape: keep ONE row.
                    # The row carrying pricing wins over a priceless twin
                    # (the 09-30 commandcode row had no cost, the xkiro twin
                    # did); a twin of a core-scan row is simply dropped.
                    if (
                        twin_idx is not None
                        and lane_candidates[twin_idx]["input_cost_mtok"] is None
                        and input_cost is not None
                    ):
                        lane_candidates[twin_idx] = entry
                    continue
                admitted_base[base] = len(lane_candidates)
                lane_candidates.append(entry)
            if lane_candidates:
                lane_candidates.sort(key=_recency_sort_key)
                existing = candidates.get(lab, [])
                candidates[lab] = sorted(existing + lane_candidates, key=_recency_sort_key)

    return candidates


def _routable_id(candidate: dict[str, Any]) -> str:
    """Routable Chimera-gateway admission key for one candidate (DF-CHIMERA-V2-68).

    The gateway's admission rule strips EXACTLY ONE leading provider segment
    and routes on what remains, so an admission key is routable only when
    removing its first segment yields the id the serving lane actually
    serves upstream.

    * ``model_id`` carries no ``/`` — the lane-resolved ``chimera_id``
      (``<lab>/<model_id>``) is already that key; one strip yields
      ``model_id`` exactly.
    * ``model_id`` already carries a prefix (lane-carried rows: the
      attribution resolves against the LAB, so ``chimera_id`` doubles the
      prefix — measured: ``openai/gpt-6.1-sol`` attributed to lab ``openai``
      rendered ``openai/openai/gpt-6.1-sol``, which is NOT routable). The
      routable key is ``<serving-lane>/<upstream-id>``: ``model_id`` with
      any redundant ``<serving-lane>/`` leading segment collapsed (a lane
      SKU carried as ``deepseek/deepseek-v4.1-flash-fast`` ON the
      ``deepseek`` lane is already ``<lane>/<upstream-id>``), else
      ``<serving-lane>/<model_id>`` (``openrouter/openai/gpt-6.1-sol``).
      One strip yields exactly the id the lane serves.

    The serving lane is the row's ``provider`` — the lane id for
    lane-carried rows, the core provider id for core-scan rows (both are
    the upstream that serves ``model_id``). Falls back to the chimera_id's
    first segment when ``provider`` is absent.
    """
    model_id = candidate["model_id"]
    if "/" not in model_id:
        return candidate["chimera_id"]
    lane = candidate.get("provider") or candidate["chimera_id"].split("/", 1)[0]
    if model_id.startswith(f"{lane}/"):
        # Already <serving-lane>/<upstream-id> — the id IS the routable key.
        return model_id
    return f"{lane}/{model_id}"


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
    catalog_basenames = {_basename(cid) for cid in chimera_models}

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
            # catalog (basename-level comparison — see docstring). The
            # basename comes from the SAME shared helper the core scan uses
            # (DF-CHIMERA-V2-50) so the two paths cannot drift.
            basename = _basename(model_id)
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


def _measured_core_labs(cache: dict[str, Any], snapshot: Any = None) -> set[str]:
    """Labs the active source view actually contributes core rows for.

    A lab is measured IN when the merged cache holds a dict block for it, or —
    under a task-router source — when any lane block carries a model the
    lane-attribution logic assigns to that lab. The constant CORE_PROVIDERS
    list is intent, not coverage (DF-CHIMERA-V2-49).
    """
    measured: set[str] = {pid for pid in cache if pid in CORE_PROVIDERS and isinstance(cache[pid], dict)}
    if snapshot is not None and snapshot.source == "task-router":
        for lane_id, lane_block in snapshot.data.items():
            if lane_id == "_fetched_at" or lane_id in CORE_PROVIDERS:
                continue
            if not isinstance(lane_block, dict):
                continue
            for model_id in lane_block.get("models", {}):
                lab = _lab_of_router_provider(lane_id, model_id)
                if lab:
                    measured.add(lab)
    return measured


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
    if not snapshot.data:
        print(
            "ERROR: neither task-router nor models.dev supplied a usable registry. "
            "Set CHIMERA_TASK_ROUTER_MODELS_PATH or run `chimera models` to refresh."
        )
        sys.exit(1)
    # One merged view for the WHOLE pass (DF-CHIMERA-V2-49): task-router rows
    # are the pricing authority, models.dev rows fill the labs and reseller
    # blocks the router table cannot cover. Core scan, lane attribution,
    # reseller watch and the measured scope all read the same merged cache.
    cache = snapshot.data
    if snapshot.source == "task-router":
        # Same seam: fixture cache when mocked, real models.dev otherwise.
        fill = _load_cache()
        if fill is None:
            fill = _load_models_dev_registry()
        cache = merge_registry_with_models_dev(snapshot.data, fill)

    # MEASURED scope (DF-CHIMERA-V2-49): a lab is IN only when the active
    # source view actually contains a block for it (own block — lane rows are
    # scanned under their owning lab regardless). The constant CORE_PROVIDERS
    # list is intent, not coverage, and must not be printed as if every lab
    # had rows behind it.
    measured_labs = _measured_core_labs(cache, snapshot)
    candidates = scan_models_dev(cache, snapshot=snapshot)
    core_basenames = {
        m["model_id"] for models in candidates.values() for m in models
    } | _load_chimera_models() or set()
    watch, blind = scan_reseller_watch(cache, core_basenames)

    # MEASURED lanes (DF-CHIMERA-V2-65): under a task-router source, every
    # non-lab provider row IS a scheduling lane (xkiro, openai-codex, ...);
    # the report must state them separately so a lane flood can never inflate
    # the core-lab headline. A models.dev source contributes no lane rows.
    if snapshot is not None and snapshot.source == "task-router":
        measured_lanes = sorted(
            pid
            for pid, block in snapshot.data.items()
            if pid != "_fetched_at" and pid not in CORE_PROVIDERS and isinstance(block, dict)
        )
    else:
        measured_lanes = []

    scope: dict[str, Any] = {
        "core": sorted(measured_labs),
        "reseller": sorted(RESELLER_WATCH),
        "lanes": measured_lanes,
        "out_of_scope": sum(1 for pid in cache if pid not in CORE_PROVIDERS and pid not in RESELLER_WATCH),
    }
    return candidates, watch, blind, scope


def _format_scope_statement(scope: dict[str, Any] | None, markdown: bool) -> list[str]:
    """The scan-scope lines: which provider ids are IN, how many rows are OUT.

    Printed on EVERY run (header + footer). ``scope=None`` falls back to the
    configured lists — used when the report is formatted without a cache pass.
    Since DF-CHIMERA-V2-65 the statement also names the task-router LANE ids
    in scope separately from the core labs.
    """
    core = sorted(scope["core"]) if scope else sorted(CORE_PROVIDERS)
    reseller = sorted(scope["reseller"]) if scope else sorted(RESELLER_WATCH)
    lanes = sorted(scope.get("lanes", [])) if scope else []
    out_count = int(scope["out_of_scope"]) if scope else 0

    scope_line = (
        f"Scan scope — IN: core providers ({', '.join(core)}); "
        f"reseller watch ({', '.join(reseller)}). "
        f"OUT: {out_count} other models.dev rows (not scanned)."
    )
    lane_line: str | None = None
    if lanes:
        scope_line += f" Task-router lanes scanned ({', '.join(lanes)})."
        lane_line = (
            "Task-router lane finds are scheduling-lane SKUs, not core-lab "
            "candidates: they are reported in their own section with the lane "
            "named and are never counted in the core-lab headline — except a "
            "lane row whose model id resolves to the owning lab's own "
            "registry block (a lane-carried core release), which is promoted "
            "to that lab's core section (DF-CHIMERA-V2-67)."
        )
    policy_line = (
        "Reseller Watch / Blind Spot sections are informational and NOT recorded "
        "in .seen_models.json — reseller-only finds are re-reported on every run "
        "until they appear in a core row or are admitted to the catalog."
    )
    if markdown:
        out = [f"**{scope_line}**"]
        if lane_line:
            out.append(f"*{lane_line}*")
        out.extend(["", f"*{policy_line}*", ""])
        return out
    out = [scope_line]
    if lane_line:
        out.append(lane_line)
    out.extend([policy_line, ""])
    return out


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

    # Provider-class split (DF-CHIMERA-V2-65): the core loop attributes lane
    # SKUs (candidates whose ``provider`` is a scheduling lane id, not a lab)
    # into the lab's bucket — honest attribution, wrong REPORT surface. The
    # split is per CANDIDATE (a mixed bucket holds both): a row whose
    # ``provider`` is not in CORE_PROVIDERS is a LANE find — rendered in the
    # dedicated lane section with the lane named, never dropped, never counted
    # in the core-lab headline. A lab key with only lane rows behind it
    # renders NO core section at all.
    #
    # Promotion (DF-CHIMERA-V2-67): a lane row the scanner flagged
    # ``core_lab_member`` — its model id resolves to the attributed lab's OWN
    # registry block — is a lane-CARRIED core-lab release, not a lane SKU. It
    # renders in the lab's core section and counts in the core headline;
    # ``provider`` keeps the lane id so the row's provenance stays visible.
    core_candidates: dict[str, list[dict[str, Any]]] = {}
    lane_candidates: dict[str, list[dict[str, Any]]] = {}
    for provider_id, models in candidates.items():
        for m in models:
            if m.get("provider") in CORE_PROVIDERS or m.get("core_lab_member"):
                core_candidates.setdefault(provider_id, []).append(m)
            else:
                lane_candidates.setdefault(m.get("provider") or provider_id, []).append(m)

    lines: list[str] = []
    new_seen: set[str] = set()

    core_new = 0
    lane_new = 0

    for provider_id, models in core_candidates.items():
        provider_name = PROVIDER_NAMES.get(provider_id, provider_id)

        # Filter for --diff mode: the seen comparison is ``_seen_match()`` —
        # exact id, then a seen basename-marker entry (``<id>
        # [basename=<catalog-id>]``), then BASENAME resolution
        # (DF-CHIMERA-V2-64). ``chimera_id`` is the LANE-resolved id, so the
        # same model reaches a later run under a different prefix shape
        # (``openai/gpt-6-sol`` → ``openai/openai/gpt-6-sol``,
        # ``zai/glm-5.3-flashx`` → ``zai/z-ai/glm-5.3-flashx``) and exact
        # string equality alone re-reported it as new. A plain entry still
        # cannot prefix-match a longer id (equality on the whole basename).
        if diff_only:
            models = [m for m in models if _seen_match(m["chimera_id"], seen) is None]
            if not models:
                continue
        new_seen.update(m["chimera_id"] for m in models)

        # DF-CHIMERA-V2-68: the "Chimera ID" column renders the ROUTABLE
        # admission key; when it differs from the lane-resolved chimera_id
        # (prefixed model_id under a lane), the lane-resolved id stays
        # visible in a second column — never silently dropped.
        show_lane_resolved = any(_routable_id(m) != m["chimera_id"] for m in models)

        if markdown:
            lines.append(f"## {provider_name} (`{provider_id}`)")
            lines.append("")
            if show_lane_resolved:
                lines.append("| Model | Chimera ID | Lane-resolved | Recency | Input/1k | Output/1k |")
                lines.append("|-------|-----------|---------------|---------|----------|-----------|")
            else:
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
            rid = _routable_id(m)

            if markdown:
                if show_lane_resolved:
                    lane_cell = f"`{m['chimera_id']}`" if rid != m["chimera_id"] else "—"
                    lines.append(f"| `{m['model_id']}` | `{rid}` | {lane_cell} | {rec:.0f} | {inp} | {out} |")
                else:
                    lines.append(f"| `{m['model_id']}` | `{rid}` | {rec:.0f} | {inp} | {out} |")
            else:
                # Same seen comparison as the --diff filter (DF-CHIMERA-V2-64):
                # a model first seen under another lane-resolved id shape is
                # not NEW any more.
                tag = " [NEW]" if _seen_match(m["chimera_id"], seen) is None else ""
                note = f"  lane-resolved={m['chimera_id']}" if rid != m["chimera_id"] else ""
                lines.append(f"  {rid:50s} recency={rec:.0f}  inp={inp}  out={out}{tag}{note}")

            core_new += 1

        if markdown:
            lines.append("")

    # Task-router LANE finds (DF-CHIMERA-V2-65): their own section, provider
    # named, separated from every core-lab section. --diff filters with the
    # same _seen_match comparison the core loop uses; a lane with nothing
    # fresh renders nothing (the headline still states the lane totals).
    # Rendered lane ids are recorded in new_seen (DF-CHIMERA-V2-67) so a lane
    # find reports ONCE instead of re-reporting on every run.
    if lane_candidates:
        lane_fresh: dict[str, list[dict[str, Any]]] = {}
        for lane_id, models in lane_candidates.items():
            fresh = [m for m in models if not diff_only or _seen_match(m["chimera_id"], seen) is None]
            if fresh:
                lane_fresh[lane_id] = fresh
        new_seen.update(m["chimera_id"] for models in lane_fresh.values() for m in models)
        if lane_fresh:
            lines.append("## Task-Router Lane Providers (fleet scheduling lanes — not core labs)")
            lines.append("")
            for lane_id in sorted(lane_fresh):
                models = lane_fresh[lane_id]
                # DF-CHIMERA-V2-68: same routable-key rendering as the core
                # tables — lane SKUs are the canonical double-prefix case.
                show_lane_resolved = any(_routable_id(m) != m["chimera_id"] for m in models)
                if markdown:
                    lines.append(f"### Lane `{lane_id}`")
                    lines.append("")
                    if show_lane_resolved:
                        lines.append(
                            "| Model | Chimera ID | Lane-resolved | Recency | Input/1k | Output/1k |"
                        )
                        lines.append("|-------|-----------|---------------|---------|----------|-----------|")
                    else:
                        lines.append("| Model | Chimera ID | Recency | Input/1k | Output/1k |")
                        lines.append("|-------|-----------|---------|----------|-----------|")
                else:
                    lines.append(f"\n{'-' * 70}")
                    lines.append(f"  Lane {lane_id} — {len(models)} candidates")
                    lines.append(f"{'-' * 70}")
                for m in models:
                    inp = f"${m['input_per_1k']:.6f}" if m["input_per_1k"] else "N/A"
                    out = f"${m['output_per_1k']:.6f}" if m["output_per_1k"] else "N/A"
                    rec = m["recency_score"]
                    rid = _routable_id(m)
                    if markdown:
                        if show_lane_resolved:
                            lane_cell = f"`{m['chimera_id']}`" if rid != m["chimera_id"] else "—"
                            lines.append(
                                f"| `{m['model_id']}` | `{rid}` | {lane_cell} | {rec:.0f} | {inp} | {out} |"
                            )
                        else:
                            lines.append(f"| `{m['model_id']}` | `{rid}` | {rec:.0f} | {inp} | {out} |")
                    else:
                        tag = " [NEW]" if _seen_match(m["chimera_id"], seen) is None else ""
                        note = f"  lane-resolved={m['chimera_id']}" if rid != m["chimera_id"] else ""
                        lines.append(f"  {rid:50s} recency={rec:.0f}  inp={inp}  out={out}{tag}{note}")
                    lane_new += 1
                if markdown:
                    lines.append("")
            if not markdown:
                lines.append("")

    # Basename skips (DF-CHIMERA-V2-50): stated, never silently dropped — the
    # headline counts only NEW finds, and the SKIP lines name the catalog
    # entry each candidate already matches by basename. The trail is read
    # from the LAST scan (LAST_SCAN_SKIPS); tests that format reports
    # without a scan simply see none.
    basename_skips = [s for s in LAST_SCAN_SKIPS if "alias_of" not in s]
    if basename_skips:
        lines.append("## Basename Skips (already admitted under another prefix)")
        lines.append("")
        for skip in basename_skips:
            catalog_id = skip["catalog_id"]
            note = f"{SEEN_MARKER_PREFIX}{catalog_id}{SEEN_MARKER_SUFFIX}"
            if markdown:
                lines.append(
                    f"- SKIP `{skip['chimera_id']}` — already admitted as `{catalog_id}` (basename match)"
                )
            else:
                lines.append(f"  SKIP {skip['chimera_id']:50s} basename-match → {catalog_id}")
            new_seen.add(f"{skip['chimera_id']}{note}")
        lines.append("")

    # Alias skips (DF-CHIMERA-V2-65): a registry row carrying ``alias_of`` is
    # a MOVING pointer to another model id, never a new model. Stated with the
    # alias target so the underlying release stays visible; never counted in
    # the headline and never recorded in .seen_models.json.
    alias_skips = [s for s in LAST_SCAN_SKIPS if "alias_of" in s]
    if alias_skips:
        lines.append("## Alias Skips (registry alias rows — never counted as new models)")
        lines.append("")
        for skip in alias_skips:
            if markdown:
                lines.append(
                    f"- SKIP `{skip['chimera_id']}` (provider `{skip['provider']}`) — "
                    f"alias_of `{skip['alias_of']}`"
                )
            else:
                lines.append(
                    f"  SKIP {skip['chimera_id']:50s} alias_of → {skip['alias_of']}"
                    f"  (provider: {skip['provider']})"
                )
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

    # Summary (DF-CHIMERA-V2-65): the headline counts CORE-lab candidates and
    # core providers only — a lane flood can never inflate "across N providers"
    # again — and states the lane finds as an explicit separate count right
    # beside it ("plus K task-router lane finds").
    lane_clause = f", plus {lane_new} task-router lane find" + ("s" if lane_new != 1 else "")
    if markdown:
        header = [
            "# Chimera Model Sync Report",
            "",
            f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Candidates:** {core_new} new models across {len(core_candidates)} providers{lane_clause}",
            "",
        ]
        header.extend(_format_scope_statement(scope, markdown=True))
        lines = header + lines
    else:
        header = [f"Chimera Model Sync — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"]
        header.append(
            f"Candidates: {core_new} new models across {len(core_candidates)} providers{lane_clause}"
        )
        header.append("")
        header.extend(_format_scope_statement(scope, markdown=False))
        lines = header + lines

    # Footer: scope statement again + explicit tracking policy.
    lines.append("---")
    lines.append("")
    lines.extend(_format_scope_statement(scope, markdown))

    # Update seen models — core finds (including promoted lane-carried core
    # releases), rendered LANE finds (DF-CHIMERA-V2-67 — a lane find reports
    # once, not every run), plus the basename-skips trail (each skip is
    # recorded as ``<id> [basename=<catalog-id>]`` so tomorrow's run filters
    # the diff honestly instead of re-reporting it). Reseller watch/blind ids
    # are still deliberately NOT recorded: they are re-reported every run
    # until the model surfaces in a core row or is admitted to the catalog.
    if diff_only or candidates or LAST_SCAN_SKIPS:
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
        # score exactly this set instead of re-deriving an empty diff. The
        # filter is the SAME `_seen_match()` comparison `--diff` uses
        # (DF-CHIMERA-V2-64) — otherwise the saved file would still carry the
        # lane-id re-reports the printed report drops.
        seen_ids = _load_seen()
        diff_set: dict[str, list[dict[str, Any]]] = {}
        for provider_id, models in candidates.items():
            fresh = [m for m in models if _seen_match(m["chimera_id"], seen_ids) is None]
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

#: DOCUMENTED cap on the scoring payload (DF-CHIMERA-V2-57): the prompt embeds
#: only the recency-selected top N candidates, so a lane-namespace flood
#: (the 2026-09-25 run's scan carried ~225 finds) can never scale the call.
SCORE_CANDIDATE_LIMIT: int = 5

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

    Concatenated objects (DF-CHIMERA-V2-57: the 2026-09-25 cron run's reply
    was two complete JSON objects back to back, so a first-brace-to-last-brace
    slice is still invalid JSON) are handled by ``raw_decode`` at the first
    ``{``: a trailing second object is ignored and the FIRST object wins.
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
        pass

    # Scan only TOP-LEVEL braces (string-aware, DF-CHIMERA-V2-57): rescanning
    # at every ``{`` could return a fragment nested inside a broken outer
    # object — e.g. a reply truncated (finish_reason="length") after the first
    # array element — which would silently bypass the caller's truncation
    # ladder and score garbage. Concatenated complete objects and
    # brace-carrying prose both parse from a top-level start; a truncated
    # outer object leaves only its own top-level start, which fails, and the
    # named error below lets the ladder decide.
    starts: list[int] = []
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(stripped):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                starts.append(i)
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1

    decoder = json.JSONDecoder()
    detail = "no object found"
    for start in starts[:16]:  # bound the scan — a pathological reply cannot drive an O(n²) walk
        try:
            obj, _end = decoder.raw_decode(stripped[start:])
            return obj
        except json.JSONDecodeError as exc:
            detail = str(exc)
    raise ValueError(f"no JSON object in model content: {stripped[:120]!r} ({detail})") from None


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


def _attach_routable_ids(
    scored: dict[str, Any],
    top_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Guarantee every scored model carries its routable admission key (DF-CHIMERA-V2-68).

    The LLM is ASKED to echo ``routable_id``, but the YAML contract must not
    depend on the reply's obedience: each scored entry is matched back to its
    candidate (by ``routable_id`` or by the legacy ``chimera_id`` echo) and
    the routable key is written in from the candidate record — so the scored
    YAML never carries a double-prefix lane-resolved id as its only key.
    Unmatched entries (hallucinated ids) are left untouched.
    """
    by_routable = {_routable_id(m): m for m in top_candidates}
    by_chimera = {m["chimera_id"]: m for m in top_candidates}
    models = scored.get("models")
    if not isinstance(models, list):
        return scored
    for entry in models:
        if not isinstance(entry, dict):
            continue
        cand = by_routable.get(entry.get("routable_id") or "") or by_chimera.get(
            entry.get("chimera_id") or ""
        )
        if cand is None:
            continue
        entry["routable_id"] = _routable_id(cand)
        entry.setdefault("chimera_id", cand["chimera_id"])
    return scored


def _llm_score_candidates(candidates: dict[str, list[dict[str, Any]]]) -> None:
    """Use DeepSeek to score top candidates on Chimera's hierarchical category paths.

    Saves scored models to reports/model_scores_<timestamp>.yaml.

    On a scoring failure the named reason goes to stderr and the error is
    re-raised as ``SystemExit(1)`` (DF-CHIMERA-V2-57): the cron pipeline must
    never exit 0 having silently produced no score file — the wrapper already
    treats a non-zero step-3 exit as an explicit WARNING.
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("\n⚠️  --score requires DEEPSEEK_API_KEY in environment. Skipping.")
        return

    # Flatten and take the top candidates (pure selection — no network, no API
    # key needed). The cap is documented at SCORE_CANDIDATE_LIMIT: the prompt
    # embeds only the recency-selected top N models.
    top5 = select_top_candidates(candidates, limit=SCORE_CANDIDATE_LIMIT)

    # Build prompt with model info and category paths
    from chimera.selector import PATH_PATTERNS

    category_paths = sorted({p for p, _ in PATH_PATTERNS})
    path_list = "\n".join(f"- {p}" for p in category_paths)

    model_descriptions = "\n".join(
        # DF-CHIMERA-V2-68: the scorer scores the ROUTABLE admission key
        # (``_routable_id``), with the lane-resolved chimera_id named inline
        # when the two differ — never the double-prefix shape as the id.
        f"- `{_routable_id(m)}`"
        + (f" (lane-resolved chimera_id: `{m['chimera_id']}`)" if _routable_id(m) != m["chimera_id"] else "")
        + f": {m.get('description', m.get('family', ''))[:200]}"
        for m in top5
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
      "routable_id": "serving-lane/model-id",
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

Echo each model's id EXACTLY as listed above into ``routable_id`` (the routable
admission key); keep the lane-resolved chimera_id in ``chimera_id`` when one
was shown.
Only include paths where score ≥60. Use whole numbers only.
Be conservative — only score categories the model is known to excel at
based on benchmarks and provider claims."""

    try:
        scored = _score_llm_reply(prompt, deepseek_key)
        # DF-CHIMERA-V2-68: the YAML's id contract is enforced, not prompted.
        scored = _attach_routable_ids(scored, top5)

        # Save to YAML
        reports_dir = REPO_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        score_path = reports_dir / f"model_scores_{ts}.yaml"

        import yaml as yaml_lib

        score_path.write_text(yaml_lib.dump(scored, default_flow_style=False, sort_keys=False))
        print(f"\n✅ Model scores saved to {score_path}")

    except Exception as e:
        # DF-CHIMERA-V2-57: naming the failure and exiting non-zero is the
        # contract — the old swallow-and-return let the script exit 0 with no
        # score file (the 2026-09-25 cron run "succeeded" having produced
        # nothing). Both the reason and the trace go to stderr; the wrapper's
        # step 3 already treats a non-zero exit as an explicit WARNING.
        print(f"\n❌ LLM scoring failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
