"""Category-weighted model selector for programmatic model ranking.

The config catalog already has per-model category scores (analysis, code,
reasoning, design, audit).  This module provides a deterministic selector
that scores models against a task's required categories and returns the
best-fit models — no LLM call needed.

Usage::

    from chimera.selector import CategorySelector

    selector = CategorySelector(config.models)
    best = selector.select("Write a Python web scraper", count=3)
    # → ["deepseek/deepseek-v4-flash", "openrouter/moonshotai/kimi-k2.7-code", ...]

The selector is wired into the dispatcher when ``selector: category_weighted``
is set in the config defaults (or ``mode: programmatic`` in the formation).
"""

from __future__ import annotations

import re
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
#  Task → category keyword heuristics
# ═══════════════════════════════════════════════════════════════════════════

#: Category keywords — each tuple of (category_name, keywords_regex).
#: A task matching more keywords for a category gets a higher weight for that
#: category.  Order matters: earlier patterns are checked first.
CATEGORY_PATTERNS: list[tuple[str, str]] = [
    # code
    (
        "code",
        r"(?i)\b("
        r"code|program|script|function|class|implement|refactor|debug|bug|fix"
        r"|api|endpoint|route|query|sql|database|migration|schema|algorithm"
        r"|type|typescript|python|rust|golang|javascript|java|c\+\+|regex"
        r"|unit.?test|test.?case|compiler|parser|build|deploy|docker"
        r"|lint|dependency|package|module|import|sdk|library"
        r")\b"
    ),
    # reasoning
    (
        "reasoning",
        r"(?i)\b("
        r"reason|think|logic|deduction|inference|proof|theorem|math|equation"
        r"|puzzle|paradox|riddle|contradiction|why|explain|analyze|evaluate"
        r"|compare|contrast|decision|strategy|problem|plan|architecture|design.*system"
        r")\b"
    ),
    # analysis
    (
        "analysis",
        r"(?i)\b("
        r"data|analyze|explain|break.?down|review|audit|inspect|examine"
        r"|investigate|diagnose|trace|profile|benchmark|metric|statistics"
        r"|trend|pattern|insight|summarize|report|research|paper|study"
        r")\b"
    ),
    # design
    (
        "design",
        r"(?i)\b("
        r"design|ui|ux|interface|layout|style|css|color|palette|typography"
        r"|visual|aesthetic|logo|banner|brand|theme|animation|graphic|art"
        r"|creative|generate.*image|draw|illustrat|wireframe|mockup|prototype"
        r")\b"
    ),
    # audit
    (
        "audit",
        r"(?i)\b("
        r"audit|security|vulnerability|exploit|attack|threat|risk|compliance"
        r"|policy|governance|legal|privacy|gdpr|sensitive|secret|password"
        r"|token|key|credential|validate|verify|check|review.*code|code.?review"
        r")\b"
    ),
]


def task_to_categories(task: str) -> dict[str, float]:
    """Map a task description to category weights via keyword matching.

    Each category gets a weight proportional to how many of its keywords
    appear in the task.  Normalized to sum to 1.0.
    """
    scores: dict[str, int] = {cat: 0 for cat, _ in CATEGORY_PATTERNS}

    for category, pattern in CATEGORY_PATTERNS:
        matches = re.findall(pattern, task)
        scores[category] = len(matches)

    total = sum(scores.values())
    if total == 0:
        # Default: everything gets equal weight (analysis + reasoning dominate)
        return {cat: 1.0 / len(CATEGORY_PATTERNS) for cat, _ in CATEGORY_PATTERNS}

    return {cat: v / total for cat, v in scores.items()}


# ═══════════════════════════════════════════════════════════════════════════
#  Category Selector
# ═══════════════════════════════════════════════════════════════════════════


class CategorySelector:
    """Scores and ranks models by category weights for a given task."""

    def __init__(self, models: dict[str, Any]) -> None:
        """*models* is ``config.models`` — a dict of model_id → ModelEntry."""
        self._models = models

    def score(self, task: str) -> dict[str, float]:
        """Return ``{model_id: score, ...}`` for every model in the catalog.

        Score = sum over categories of ``task_weight[cat] * model_score[cat]``.
        """
        task_weights = task_to_categories(task)
        results: dict[str, float] = {}

        for model_id, entry in self._models.items():
            model_cats = getattr(entry, "categories", {})
            if not model_cats:
                results[model_id] = 0.0
                continue

            score = 0.0
            for cat, weight in task_weights.items():
                score += weight * model_cats.get(cat, 0.0)
            results[model_id] = score

        return results

    def select(
        self,
        task: str,
        count: int = 3,
        *,
        exclude: list[str] | None = None,
        prefer_budget: bool = False,
    ) -> list[str]:
        """Return the top *count* model IDs for *task*.

        *count* — how many models to return (default 3 for a typical panel).
        *exclude* — model IDs to skip (e.g. dispatcher model, aggregator model).
        *prefer_budget* — when True, budget-tier models get a +15% boost.
        """
        exclude_set = set(exclude or [])
        scores = self.score(task)

        # Apply budget preference if requested
        if prefer_budget:
            for mid, entry in self._models.items():
                if getattr(entry, "cost_tier", "") == "budget":
                    scores[mid] = scores.get(mid, 0.0) * 1.15

        # Sort descending by score, filter excluded and zero-score models
        ranked = sorted(
            ((mid, s) for mid, s in scores.items() if mid not in exclude_set and s > 0.0),
            key=lambda x: x[1],
            reverse=True,
        )

        return [mid for mid, _ in ranked[:count]]

    def select_diverse(
        self,
        task: str,
        count: int = 3,
        *,
        exclude: list[str] | None = None,
    ) -> list[str]:
        """Like ``select()`` but enforces provider diversity — at most one
        model per provider in the result.
        """
        exclude_set = set(exclude or [])
        scores = self.score(task)

        # Group by provider
        by_provider: dict[str, list[tuple[str, float]]] = {}
        for mid, s in scores.items():
            if mid in exclude_set:
                continue
            entry = self._models.get(mid)
            provider = getattr(entry, "provider", "unknown") if entry else "unknown"
            by_provider.setdefault(provider, []).append((mid, s))

        # Take top model from each provider, then sort globally
        provider_tops: list[tuple[str, float]] = []
        for _provider, entries in by_provider.items():
            entries.sort(key=lambda x: x[1], reverse=True)
            provider_tops.append(entries[0])

        provider_tops.sort(key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in provider_tops[:count]]

    def explain(self, task: str, count: int = 3) -> str:
        """Return a human-readable explanation of model selection for *task*."""
        task_weights = task_to_categories(task)
        scores = self.score(task)
        selected = self.select(task, count=count)

        lines = [
            f"Task: {task[:80]}",
            f"Category weights: {task_weights}",
            "",
            f"Top {count} models:",
        ]
        for i, mid in enumerate(selected):
            entry = self._models.get(mid)
            cats = getattr(entry, "categories", {}) if entry else {}
            lines.append(
                f"  {i + 1}. {mid} — score={scores.get(mid, 0):.3f}  "
                f"cats={cats}"
            )

        return "\n".join(lines)
