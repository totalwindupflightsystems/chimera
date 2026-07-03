#!/usr/bin/env python3
"""Weekly model sync: scan models.dev for new chat models not in Chimera catalog.

Usage:
    python3 scripts/model_sync.py                    # generate report to stdout
    python3 scripts/model_sync.py --diff             # show only gap changes
    python3 scripts/model_sync.py --score            # also attempt LLM scoring (needs key)
    python3 scripts/model_sync.py --output report.md # write markdown report

Cache TTL: 24h (re-fetches if stale), same as provider_discovery.py.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

MODELS_DEV_URL = "https://models.dev/api.json"
CACHE_PATH = Path.home() / ".chimera" / "models-dev-cache.json"
CACHE_TTL = 86400  # 24 hours
CHIMERA_DIR = Path(__file__).resolve().parent.parent if "__file__" in dir() else Path.cwd()

# Providers we care about for deliberation (chat/reasoning models)
CORE_PROVIDERS = {
    "openai", "google", "anthropic", "deepseek", "xai",
    "mistral", "meta", "moonshotai", "minimax", "zhipuai",
    "alibaba", "tencent", "perplexity",
}

# Families that are NOT relevant for deliberation
SKIP_FAMILIES = {
    "text-embedding", "embedding", "whisper", "speech", "tts",
    "dall-e", "rerank", "esmfold", "paligemma",
}

# Model names to skip (legacy/embedding/speech models)
SKIP_PATTERNS = [
    "embed", "whisper", "tts", "dall-e", "dalle",
    "moderation", "rerank", "transcription",
]

# Minimum release year to consider "new" (2025+)
MIN_YEAR = 2025

# Output directory for reports
REPORTS_DIR = CHIMERA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_models_dev_cache() -> dict:
    """Load models.dev data: cache if fresh, else fetch."""
    # Try cache first
    if CACHE_PATH.is_file():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            fetched_at = data.get("_fetched_at", 0)
            age_h = (time.time() - fetched_at) / 3600
            provider_count = sum(
                1 for k, v in data.items()
                if k != "_fetched_at" and isinstance(v, dict) and "models" in v
            )
            if age_h < 24 and provider_count > 0:
                print(f"[cache] Using cached data ({age_h:.1f}h old, {provider_count} providers)",
                      file=sys.stderr)
                return data
            else:
                print(f"[cache] Cache stale ({age_h:.1f}h, {provider_count} providers), re-fetching...",
                      file=sys.stderr)
        except Exception as e:
            print(f"[cache] Load failed: {e}, re-fetching...", file=sys.stderr)

    # Fetch fresh
    import urllib.request
    print(f"[fetch] Fetching {MODELS_DEV_URL}...", file=sys.stderr)
    req = urllib.request.Request(
        MODELS_DEV_URL,
        headers={"Accept": "application/json", "User-Agent": "Chimera-ModelSync/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        data["_fetched_at"] = time.time()
        # Atomic write
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(CACHE_PATH)
        print(f"[fetch] Saved {len(data)} entries to cache", file=sys.stderr)
        return data
    except Exception as e:
        print(f"[fetch] Failed: {e}", file=sys.stderr)
        # Fall back to stale cache
        if CACHE_PATH.is_file():
            print("[fetch] Falling back to stale cache", file=sys.stderr)
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return {}


def resolve_chimera_id(provider_id: str, model_id: str) -> str:
    """Map models.dev (provider, model) → Chimera model ID."""
    from chimera.provider_discovery import PROVIDER_ID_MAP, MODEL_ID_MAP
    mapped = MODEL_ID_MAP.get(model_id)
    if mapped:
        return mapped
    chimera_provider = PROVIDER_ID_MAP.get(provider_id, provider_id)
    return f"{chimera_provider}/{model_id}"


def should_skip_model(model_data: dict) -> bool:
    """Filter out non-chat models (embeddings, speech, legacy, etc.)."""
    family = (model_data.get("family") or "").lower()
    model_id = (model_data.get("id") or "").lower()
    desc = (model_data.get("description") or "").lower()

    # Skip known non-chat families
    for sf in SKIP_FAMILIES:
        if sf.lower() in family or sf.lower() in model_id:
            return True

    # Skip by pattern
    for pattern in SKIP_PATTERNS:
        if pattern.lower() in model_id or pattern.lower() in desc:
            return True

    # Skip if no chat/reasoning capability indicated
    # (models.dev 'attachment', 'reasoning', 'tool_call' flags)
    is_reasoning = model_data.get("reasoning", False)
    is_tool_call = model_data.get("tool_call", False)
    if not is_reasoning and not is_tool_call and not any(
        kw in desc for kw in ["chat", "assistant", "agent", "reason", "code"]
    ):
        return True

    return False


def get_model_age_score(release_date: str) -> float:
    """Newer models get higher scores. 0-1 scale."""
    if not release_date:
        return 0.5
    try:
        parts = release_date.split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        # Score: 2025 models > 2024 models >> older
        if year >= 2026:
            return 1.0
        if year == 2025:
            return 0.8 + (month / 12.0) * 0.2  # 0.8-1.0
        if year == 2024:
            return 0.3 + (month / 12.0) * 0.5  # 0.3-0.8
        return max(0.0, 0.1 - (2024 - year) * 0.05)  # decays for older
    except (ValueError, IndexError):
        return 0.5


# ── Main scan ────────────────────────────────────────────────────────────────

def scan(diff_only: bool = False) -> dict:
    """Scan for new models and return structured results."""

    # Load catalog
    sys.path.insert(0, str(CHIMERA_DIR / "src"))
    from chimera.config import load_config
    config = load_config()
    catalog_ids = set(config.models.keys())

    # Load models.dev
    cache = load_models_dev_cache()

    # Discover new relevant models
    new_models = []
    for provider_id, prov_data in cache.items():
        if provider_id == "_fetched_at" or not isinstance(prov_data, dict):
            continue
        if provider_id not in CORE_PROVIDERS:
            continue

        models = prov_data.get("models", {})
        if not isinstance(models, dict):
            continue

        for model_id, model_data in models.items():
            if not isinstance(model_data, dict):
                continue

            chimera_id = resolve_chimera_id(provider_id, model_id)
            if chimera_id in catalog_ids:
                continue

            if should_skip_model(model_data):
                continue

            release_date = model_data.get("release_date", "")
            age_score = get_model_age_score(release_date)

            # Only include reasonably new/relevant models
            if age_score < 0.3:
                continue

            cost = model_data.get("cost", {})
            if not isinstance(cost, dict):
                cost = {}

            new_models.append({
                "chimera_id": chimera_id,
                "provider_id": provider_id,
                "model_id": model_id,
                "release_date": release_date,
                "family": model_data.get("family", ""),
                "description": (model_data.get("description", "") or "")[:200],
                "cost_input_mtok": cost.get("input", 0) or 0,
                "cost_output_mtok": cost.get("output", 0) or 0,
                "age_score": age_score,
                "is_reasoning": model_data.get("reasoning", False),
                "is_tool_call": model_data.get("tool_call", False),
                "context_window": (model_data.get("limit") or {}).get("context", 0),
                "max_output": (model_data.get("limit") or {}).get("output", 0),
            })

    # Sort by age_score desc, then cost desc (expensive = usually more capable)
    new_models.sort(key=lambda m: (m["age_score"], m["cost_input_mtok"]), reverse=True)

    # Track already-reported models to avoid duplicates across runs
    seen_file = REPORTS_DIR / ".seen_models.json"
    seen: set = set()
    if seen_file.exists():
        try:
            seen = set(json.loads(seen_file.read_text(encoding="utf-8")))
        except Exception:
            seen = set()

    # Update seen set
    new_seen = seen.copy()
    for m in new_models:
        new_seen.add(m["chimera_id"])
    seen_file.write_text(json.dumps(sorted(new_seen), indent=2), encoding="utf-8")

    if diff_only:
        new_models = [m for m in new_models if m["chimera_id"] not in seen]

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "catalog_count": len(catalog_ids),
        "candidate_count": len(new_models),
        "new_since_last": len([m for m in new_models if m["chimera_id"] not in seen]),
        "candidates": new_models[:40],  # top 40 by relevance
        "all_candidates_count": len(new_models),
    }


# ── Report formatting ────────────────────────────────────────────────────────

def format_report(results: dict) -> str:
    """Format scan results as markdown report."""
    lines = [
        "# Chimera Model Sync Report",
        "",
        f"**Scan time:** {results['scan_time']}",
        f"**Catalog:** {results['catalog_count']} models",
        f"**New candidates:** {results['candidate_count']} ({results['new_since_last']} since last sync)",
        "",
        "---",
        "",
        "## Top Candidates by Relevance",
        "",
        "| # | Model ID | Family | Released | Cost ($/MTok) | Context | Age |",
        "|---|----------|--------|----------|---------------|---------|-----|",
    ]

    for i, m in enumerate(results["candidates"], 1):
        cost_str = f"${m['cost_input_mtok']} / ${m['cost_output_mtok']}"
        ctx_str = f"{m['context_window'] // 1000}k" if m['context_window'] else "?"
        age_str = f"{m['age_score']:.2f}"
        date_str = m['release_date'] or "?"
        lines.append(
            f"| {i} | `{m['chimera_id']}` | {m['family']} | {date_str} | {cost_str} | {ctx_str} | {age_str} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Candidate Details",
        "",
    ])

    for m in results["candidates"]:
        flags = []
        if m["is_reasoning"]:
            flags.append("🧠 reasoning")
        if m["is_tool_call"]:
            flags.append("🔧 tool-call")
        flags_str = ", ".join(flags) if flags else "chat-only"
        lines.extend([
            f"### `{m['chimera_id']}`",
            f"- **Provider:** {m['provider_id']}",
            f"- **Family:** {m['family']}",
            f"- **Released:** {m['release_date']}",
            f"- **Cost:** ${m['cost_input_mtok']}/MTok in, ${m['cost_output_mtok']}/MTok out",
            f"- **Context:** {m['context_window']} in, {m['max_output']} out",
            f"- **Capabilities:** {flags_str}",
            f"- **Description:** {m['description']}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## To Add a Model",
        "",
        "1. Verify it exists on OpenRouter: `site:openrouter.ai <model-name>`",
        "2. Check provider announcement confirms name",
        "3. Score on 32 hierarchical category paths (see `references/category-paths.md`)",
        "4. Add to `chimera.yaml` with `cost_tier` + `categories` scores",
        "5. Sync `chimera.yaml.example` and `chimera.yaml.docker`",
        "",
        "## Notes",
        "",
        "- Auto-generated by `scripts/model_sync.py`",
        "- Skip rules: embeddings, speech, rerank, legacy pre-2025 models",
        f"- Only {len(CORE_PROVIDERS)} core providers scanned",
        "",
    ])

    return "\n".join(lines)


# ── LLM Scoring ───────────────────────────────────────────────────────────────

# 32 hierarchical category paths from Chimera's PATH_PATTERNS (selector.py)
CATEGORY_PATHS = [
    "technology_code/code_generation/python",
    "technology_code/code_generation/javascript",
    "technology_code/code_generation/sql",
    "technology_code/code_generation/shell",
    "technology_code/system_design/architecture",
    "technology_code/system_design/devops",
    "technology_code/testing_debugging/unit_tests",
    "technology_code/testing_debugging/error_analysis",
    "technology_code/data_science/analysis",
    "technology_code/data_science/modeling",
    "technology_code/data_interaction/database/sql",
    "technology_code/data_interaction/file_based/json",
    "complex_reasoning_agency/multi_step_planning/task_decomposition",
    "complex_reasoning_agency/tool_use/code_execution",
    "complex_reasoning_agency/self_correction/debugging",
    "academic_scientific/formal_writing/research_paper",
    "academic_scientific/mathematics/statistics",
    "academic_scientific/mathematics/algebra",
    "academic_scientific/mathematics/calculus",
    "creative_conversational/creative_writing/storytelling",
    "creative_conversational/ux_writing/interface_copy",
    "general_knowledge/reasoning/explanation",
    "general_knowledge/reasoning/logic_puzzle",
    "general_knowledge/fact_retrieval/definitions",
    "general_knowledge/fact_retrieval/historical_events",
    "business_finance/marketing/copywriting",
    "business_finance/legal_document/analysis",
    "language_translation/translation/language_to_language",
    "language_translation/summarization/abstractive",
    "language_translation/linguistic_analysis/sentiment",
    "multimedia_processing/image/analysis",
    "multimedia_processing/image/generation",
]

SCORING_PROMPT = """You are a model evaluator for the Chimera multi-model deliberation system.
Below are the 32 hierarchical category paths used by the system. Score this
model on each path where it has genuine capability. Scores are whole numbers
60-100, where 60 = basic competence and 100 = best-in-class. Only include
paths where score ≥ 60. Omit paths where the model is weak.

CATEGORY PATHS (use these EXACT strings):
  technology_code/code_generation/python
  technology_code/code_generation/javascript
  technology_code/code_generation/sql
  technology_code/code_generation/shell
  technology_code/system_design/architecture
  technology_code/system_design/devops
  technology_code/testing_debugging/unit_tests
  technology_code/testing_debugging/error_analysis
  technology_code/data_science/analysis
  technology_code/data_science/modeling
  technology_code/data_interaction/database/sql
  technology_code/data_interaction/file_based/json
  complex_reasoning_agency/multi_step_planning/task_decomposition
  complex_reasoning_agency/tool_use/code_execution
  complex_reasoning_agency/self_correction/debugging
  academic_scientific/formal_writing/research_paper
  academic_scientific/mathematics/statistics
  academic_scientific/mathematics/algebra
  academic_scientific/mathematics/calculus
  creative_conversational/creative_writing/storytelling
  creative_conversational/ux_writing/interface_copy
  general_knowledge/reasoning/explanation
  general_knowledge/reasoning/logic_puzzle
  general_knowledge/fact_retrieval/definitions
  general_knowledge/fact_retrieval/historical_events
  business_finance/marketing/copywriting
  business_finance/legal_document/analysis
  language_translation/translation/language_to_language
  language_translation/summarization/abstractive
  language_translation/linguistic_analysis/sentiment
  multimedia_processing/image/analysis
  multimedia_processing/image/generation

Model: {name}
Provider: {provider}
Family: {family}
Description: {description}
Capabilities: {capabilities}
Cost: ${cost_in}/MTok in, ${cost_out}/MTok out
Context window: {context} tokens in, {max_output} out

Return a JSON object with a "scored_paths" map. Use ONLY paths from the
list above. Do NOT invent new paths. Example:
{{"scored_paths": {{"technology_code/code_generation/python": 85}}}}"""


def score_models(candidates: list[dict], max_models: int = 5,
                 api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-v4-flash") -> list[dict]:
    """Score top candidates on the 32 category paths using an LLM.

    Returns list of dicts with ``chimera_id``, ``scored_paths``, ``cost_tier``.
    """
    import urllib.request

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("[score] ERROR: No DEEPSEEK_API_KEY found in env", file=sys.stderr)
        return []

    scored = []
    for i, m in enumerate(candidates[:max_models]):
        # Determine cost tier
        avg_cost = (m["cost_input_mtok"] + m["cost_output_mtok"]) / 2
        if avg_cost >= 5:
            cost_tier = "premium"
        elif avg_cost >= 0.5:
            cost_tier = "standard"
        else:
            cost_tier = "budget"

        caps = []
        if m.get("is_reasoning"):
            caps.append("reasoning")
        if m.get("is_tool_call"):
            caps.append("tool-call")
        caps_str = ", ".join(caps) if caps else "chat"

        prompt = SCORING_PROMPT.format(
            name=m["chimera_id"],
            provider=m["provider_id"],
            family=m.get("family", ""),
            description=m.get("description", ""),
            capabilities=caps_str,
            cost_in=m.get("cost_input_mtok", 0),
            cost_out=m.get("cost_output_mtok", 0),
            context=m.get("context_window", 0),
            max_output=m.get("max_output", 0),
        )

        print(f"[score] Scoring {i+1}/{min(len(candidates), max_models)}: {m['chimera_id']}...",
              file=sys.stderr)

        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            paths = parsed.get("scored_paths", {})

            # Validate paths are in our known set
            valid_paths = {}
            for path, score in paths.items():
                if path in CATEGORY_PATHS and isinstance(score, (int, float)):
                    valid_paths[path] = int(score)
                else:
                    print(f"[score]   Warning: unknown path '{path}' = {score}",
                          file=sys.stderr)

            scored.append({
                "chimera_id": m["chimera_id"],
                "scored_paths": valid_paths,
                "cost_tier": cost_tier,
                "cost_per_1k_input": round(m["cost_input_mtok"] / 1000, 6) if m["cost_input_mtok"] else None,
                "cost_per_1k_output": round(m["cost_output_mtok"] / 1000, 6) if m["cost_output_mtok"] else None,
                "provider": m["provider_id"],
            })
            print(f"[score]   Got {len(valid_paths)} scored paths (tier={cost_tier})",
                  file=sys.stderr)

        except Exception as e:
            print(f"[score]   FAILED: {e}", file=sys.stderr)

    return scored


def format_scored_yaml(scored: list[dict]) -> str:
    """Format scored models as chimera.yaml model entries."""
    lines = ["# Scored model entries for chimera.yaml", ""]
    for m in scored:
        lines.append(f"  {m['chimera_id']}:")
        lines.append(f"    provider: {m['provider']}")
        lines.append(f"    cost_tier: {m['cost_tier']}")
        if m.get("cost_per_1k_input") and m.get("cost_per_1k_output"):
            lines.append(f"    cost_per_1k_input: {m['cost_per_1k_input']}")
            lines.append(f"    cost_per_1k_output: {m['cost_per_1k_output']}")
        lines.append("    categories:")
        for path, score in sorted(m["scored_paths"].items()):
            lines.append(f"      {path}: {score}")
        lines.append("")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    diff_only = "--diff" in sys.argv
    do_score = "--score" in sys.argv
    output_path = None

    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    results = scan(diff_only=diff_only)
    report = format_report(results)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"[output] Wrote report to {output_path}", file=sys.stderr)
    else:
        print(report)

    # Also save timestamped copy
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ts_path = REPORTS_DIR / f"model_sync_{ts}.md"
    ts_path.write_text(report, encoding="utf-8")
    print(f"[output] Saved timestamped copy: {ts_path}", file=sys.stderr)

    # LLM scoring
    if do_score:
        candidates = results.get("candidates", [])
        if not candidates:
            print("[score] No new candidates to score", file=sys.stderr)
        else:
            scored = score_models(candidates, max_models=5)
            if scored:
                yaml_out = format_scored_yaml(scored)
                scored_path = REPORTS_DIR / f"model_scores_{ts}.yaml"
                scored_path.write_text(yaml_out, encoding="utf-8")
                print(f"\n[score] Saved scored entries to {scored_path}", file=sys.stderr)
                print(yaml_out)
            else:
                print("[score] No models scored (check API key)", file=sys.stderr)
