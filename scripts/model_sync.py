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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure chimera is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from chimera.provider_discovery import (  # noqa: E402
    _fetch_models_dev,
    _load_cache,
    _mtok_to_per_1k,
    _resolve_model_id,
    _save_cache,
)

# ── Constants ────────────────────────────────────────────────────────────────

#: Core providers we care about for model sync (must match PROVIDER_ID_MAP).
CORE_PROVIDERS: set[str] = {
    "openai", "anthropic", "deepseek", "google", "xai",
    "mistral", "moonshotai", "minimax", "alibaba", "zhipuai",
    "meta", "stepfun", "xiaomi",
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
    "embedding", "embeddings", "speech", "tts", "audio",
    "rerank", "reranker", "moderation", "guard",
    "dall-e", "dalle", "imagen", "imagegen", "image-gen",
    "whisper", "transcription", "translate",
    "text-embedding", "babbage", "davinci", "ada",
    "stable-diffusion", "sdxl", "midjourney",
    "video", "video-gen", "sora",
    "bge", "gte", "e5", "stella",
    "voxtral",  # Mistral speech/STT family (audio-in only; added 2026-08-04)
}

#: Model name substrings that indicate non-chat models.
SKIP_NAME_PATTERNS: list[str] = [
    "embedding", "embed", "speech", "tts", "audio",
    "whisper", "rerank", "moderation", "guard",
    "dall-e", "dalle", "imagen",
    "stable-diffusion", "sdxl",
    "bge-", "gte-", "e5-", "stella-",
    "vision", "ocr", "video",
    # Image generation
    "gpt-image", "chatgpt-image", "grok-imagine",
    # Audio/ASR
    "asr-", "-asr", "livetranslate",
    # Vision-only
    "-vl-", "vl-", "-vl",
    # Omni (multimodal, not text-centric)
    "-omni-", "omni-",
    # Non-text modalities
    "-tts", "tts-",
    # Image-preview (not text models)
    "-image-preview", "-image-quality",
    # Image/live/music/video-gen/robotics noise (added 2026-08-04)
    "-image", "lyria", "veo", "robotics",
    # Live/streaming modalities
    "-live", "live-",
]

#: Path for tracking already-seen candidate models.
SEEN_PATH: Path = REPO_ROOT / ".seen_models.json"


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


def _model_recency_score(provider_data: dict[str, Any], model_id: str) -> float:
    """Score a model by recency — higher is newer.

    Primary source is a numeric unix ``created`` timestamp (the OpenAI-style API
    shape); when that is absent — as it is for every row in the live models.dev
    cache — fall back to the ISO-8601 ``release_date`` and then ``last_updated``
    strings the cache actually carries. Models with no usable date at all fall
    back to family heuristics, then the ``RECENCY_DEFAULT`` of 40.0.
    Returns 0-100 where 100 = newest.
    """
    model_info = provider_data.get("models", {}).get(model_id, {})
    if not isinstance(model_info, dict):
        model_info = {}

    created = model_info.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool) and created > 0:
        # Convert Unix timestamp to days ago, then score
        return _score_days_ago((time.time() - created) / 86400)

    # No numeric timestamp — the live cache carries ISO-8601 date strings.
    for field in RECENCY_DATE_FIELDS:
        created_ts = _parse_iso_timestamp(model_info.get(field))
        if created_ts is not None:
            return _score_days_ago((time.time() - created_ts) / 86400)

    # No usable date — score by family-based heuristics
    return _family_recency_score(model_id)


def select_top_candidates(
    candidates: dict[str, list[dict[str, Any]]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Flatten provider candidates, sort newest-first, and take the top ``limit``.

    Pure selection used by ``--score`` (top 5) and ``--limit`` (top N): ordering
    is by ``recency_score`` descending (Python's stable sort keeps the input
    order for equal scores). ``limit <= 0`` returns every candidate.
    """
    flat: list[dict[str, Any]] = []
    for models in candidates.values():
        flat.extend(models)
    flat.sort(key=lambda x: x["recency_score"], reverse=True)
    if limit > 0:
        flat = flat[:limit]
    return flat


# ── Main logic ───────────────────────────────────────────────────────────────

def scan_models_dev() -> dict[str, list[dict[str, Any]]]:
    """Scan models.dev cache for new chat/reasoning models.

    Returns dict mapping provider_id → list of candidate model dicts.
    """
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

            provider_candidates.append({
                "model_id": model_id,
                "chimera_id": chimera_id,
                "family": family,
                "description": model_info.get("description", ""),
                "input_cost_mtok": input_cost,
                "output_cost_mtok": output_cost,
                "input_per_1k": _mtok_to_per_1k(input_cost) if input_cost else None,
                "output_per_1k": _mtok_to_per_1k(output_cost) if output_cost else None,
                "recency_score": recency,
                "provider": provider_id,
            })

        if provider_candidates:
            # Sort by recency (newest first)
            provider_candidates.sort(key=lambda x: x["recency_score"], reverse=True)
            candidates[provider_id] = provider_candidates

    return candidates


def format_report(
    candidates: dict[str, list[dict[str, Any]]],
    diff_only: bool = False,
    markdown: bool = False,
) -> str:
    """Format candidate models as a report string."""
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
            inp = f"${m['input_per_1k']:.6f}" if m['input_per_1k'] else "N/A"
            out = f"${m['output_per_1k']:.6f}" if m['output_per_1k'] else "N/A"
            rec = m["recency_score"]

            if markdown:
                lines.append(f"| `{m['model_id']}` | `{m['chimera_id']}` | {rec:.0f} | {inp} | {out} |")
            else:
                tag = " [NEW]" if m["chimera_id"] not in seen else ""
                lines.append(f"  {m['chimera_id']:50s} recency={rec:.0f}  inp={inp}  out={out}{tag}")

            total_new += 1

        if markdown:
            lines.append("")

    # Summary
    if markdown:
        lines.insert(0, "# Chimera Model Sync Report")
        lines.insert(1, "")
        lines.insert(2, f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.insert(3, f"**Candidates:** {total_new} new models across {len(candidates)} providers")
        lines.insert(4, "")
    else:
        header = f"Chimera Model Sync — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
        lines.insert(0, header)
        lines.insert(1, f"Candidates: {total_new} new models across {len(candidates)} providers")
        lines.insert(2, "")

    # Update seen models
    if diff_only or candidates:
        all_seen = seen | new_seen
        _save_seen(all_seen)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan models.dev for new Chimera candidates")
    parser.add_argument("--diff", action="store_true",
                        help="Show only newly-seen models (not previously reported)")
    parser.add_argument("--score", action="store_true",
                        help="LLM-score top 5 candidates (requires DEEPSEEK_API_KEY)")
    parser.add_argument("--output", type=str, default=None,
                        help="Write report to a markdown file")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to top N candidates (0 = all)")
    args = parser.parse_args()

    candidates = scan_models_dev()

    if args.limit > 0:
        # Flatten, re-sort by recency and keep the top N
        flat = select_top_candidates(candidates, limit=args.limit)

        # Rebuild providers dict
        limited: dict[str, list[dict[str, Any]]] = {}
        for m in flat:
            limited.setdefault(m["provider"], []).append(m)
        candidates = limited

    report = format_report(candidates, diff_only=args.diff, markdown=bool(args.output))

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


def _llm_score_candidates(candidates: dict[str, list[dict[str, Any]]]) -> None:
    """Use DeepSeek to score top candidates on Chimera's hierarchical category paths.

    Saves scored models to reports/model_scores_<timestamp>.yaml.
    """
    import urllib.request

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
        f"- `{m['chimera_id']}`: {m.get('description', m.get('family', ''))[:200]}"
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

    body = json.dumps({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }).encode()

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {deepseek_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        scored = json.loads(content)

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
