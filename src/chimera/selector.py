"""Category-weighted model selector using Bane's hierarchical category paths.

Models are scored on whole-number 0-100 scales against slash-delimited
category paths (e.g. ``technology_code/code_generation/python``).  The
selector maps a task description to the most relevant paths via keyword
matching, then ranks models by a weighted sum over those paths.

Usage::

    from chimera.selector import CategorySelector

    selector = CategorySelector(config.models)
    best = selector.select("Write a Python web scraper", count=3)
    # → ["deepseek/deepseek-v4-flash", "kimi-k2.7-code", ...]
"""

from __future__ import annotations

import re
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
#  Task → category path keyword heuristics
# ═══════════════════════════════════════════════════════════════════════════

#: Maps category paths to keyword regexes.  A task matching keywords for a
#: path gets a weight for that path.  Derived from Bane's hierarchical
#: category tree (32 leaf paths).
PATH_PATTERNS: list[tuple[str, str]] = [
    # ── technology_code ──
    ("technology_code/code_generation/python",
     r"(?i)\b(python|py|django|flask|fastapi|pydantic|pip|poetry)\b"),
    ("technology_code/code_generation/javascript",
     r"(?i)\b(javascript|js|typescript|ts|node|react|vue|angular|svelte|next|nuxt|npm|yarn)\b"),
    ("technology_code/code_generation/sql",
     r"(?i)\b(sql|query|select|insert|update|delete|join|migration|schema|postgres|mysql|sqlite)\b"),
    ("technology_code/code_generation/shell",
     r"(?i)\b(shell|bash|sh|zsh|script|cli|terminal|command.*line|awk|sed|grep)\b"),
    ("technology_code/system_design/architecture",
     r"(?i)\b(architecture|system.*design|microservice|monolith|scal|distributed|design.*pattern|component|module|layer|abstraction)\b"),
    ("technology_code/system_design/devops",
     r"(?i)\b(devops|ci.*cd|deploy|docker|kubernetes|k8s|terraform|ansible|pipeline|infrastructure|cloud|aws|gcp|azure)\b"),
    ("technology_code/testing_debugging/unit_tests",
     r"(?i)\b(test|pytest|unittest|jest|mocha|coverage|mock|stub|fixture|assert|tdd)\b"),
    ("technology_code/testing_debugging/error_analysis",
     r"(?i)\b(debug|traceback|stack.?trace|exception|error|crash|bug|fix|root.?cause|diagnose|vulnerability|security|exploit|audit.*code|code.*review)\b"),
    ("technology_code/data_science/analysis",
     r"(?i)\b(data|dataset|analysis|analytics|statistics|csv|pandas|numpy|jupyter|notebook|visualization|chart|graph|plot|dashboard|metrics|pattern)\b"),
    ("technology_code/data_science/modeling",
     r"(?i)\b(model|train|inference|ml|machine.*learning|ai|neural|deep.*learning|regression|classification|clustering|pytorch|tensorflow|sklearn|fine.?tune)\b"),
    ("technology_code/data_interaction/database/sql",
     r"(?i)\b(database|db|sql|nosql|mongo|redis|postgres|mysql|sqlite|orm|query)\b"),
    ("technology_code/data_interaction/file_based/json",
     r"(?i)\b(json|yaml|toml|csv|xml|parse|serialize|deserialize|marshal|encode|decode)\b"),

    # ── complex_reasoning_agency ──
    ("complex_reasoning_agency/multi_step_planning/task_decomposition",
     r"(?i)\b(plan|decompose|break.*down|subtask|step|workflow|pipeline|orchestrat|coordinate|multi.?step|sequence)\b"),
    ("complex_reasoning_agency/tool_use/code_execution",
     r"(?i)\b(tool|execute|run|automate|agent|autonomous|call|invoke|dispatch|trigger)\b"),
    ("complex_reasoning_agency/self_correction/debugging",
     r"(?i)\b(self.?correct|iterate|revise|improve|refine|debug|fix.*error|retry|feedback|learn)\b"),

    # ── academic_scientific ──
    ("academic_scientific/formal_writing/research_paper",
     r"(?i)\b(research|paper|thesis|dissertation|academic|journal|cite|reference|literature.*review|bibliography|abstract|methodology)\b"),
    ("academic_scientific/mathematics/statistics",
     r"(?i)\b(statistics|probability|distribution|regression|hypothesis|p.?value|confidence|variance|std|deviation|bayesian)\b"),
    ("academic_scientific/mathematics/algebra",
     r"(?i)\b(algebra|equation|polynomial|linear|matrix|vector|eigen|determinant|quadratic|factor|proof|prove|theorem|lemma|corollary|number.*theory)\b"),
    ("academic_scientific/mathematics/calculus",
     r"(?i)\b(calculus|derivative|integral|limit|differential|gradient|optimization|convergence|series|taylor|rigorous|analysis.*proof)\b"),

    # ── creative_conversational ──
    ("creative_conversational/creative_writing/storytelling",
     r"(?i)\b(story|narrative|fiction|character|plot|dialogue|novel|poem|poetry|creative.*writing|world.?build)\b"),
    ("creative_conversational/ux_writing/interface_copy",
     r"(?i)\b(ux|ui|interface|copy|button|label|tooltip|onboarding|microcopy|error.*message|toast|notification|landing.*page|layout|design|responsive|wireframe|mockup|prototype)\b"),

    # ── general_knowledge ──
    ("general_knowledge/reasoning/explanation",
     r"(?i)\b(explain|why|how|what.*is|describe|elaborate|clarify|define|meaning|concept)\b"),
    ("general_knowledge/reasoning/logic_puzzle",
     r"(?i)\b(puzzle|riddle|brain.?teaser|lateral.*thinking|paradox|syllogism|deduction|logic.*problem)\b"),
    ("general_knowledge/fact_retrieval/definitions",
     r"(?i)\b(definition|define|meaning|term|acronym|glossary|what.*does|stands.*for)\b"),
    ("general_knowledge/fact_retrieval/historical_events",
     r"(?i)\b(history|when.*did|who.*was|event|date|timeline|era|century|ancient|medieval|modern.*history)\b"),

    # ── business_finance ──
    ("business_finance/marketing/copywriting",
     r"(?i)\b(marketing|copy|ad|advertisement|slogan|tagline|pitch|sales|landing.*page|conversion|seo|email.*campaign)\b"),
    ("business_finance/legal_document/analysis",
     r"(?i)\b(legal|law|contract|agreement|compliance|regulation|policy|gdpr|privacy|terms.*service|liability)\b"),

    # ── language_translation ──
    ("language_translation/translation/language_to_language",
     r"(?i)\b(translate|translation|localize|locale|i18n|l10n|language.*to|english.*to|spanish|french|german|chinese|japanese)\b"),
    ("language_translation/summarization/abstractive",
     r"(?i)\b(summarize|summary|tldr|condense|digest|abstract|synopsis|overview|recap|brief)\b"),
    ("language_translation/linguistic_analysis/sentiment",
     r"(?i)\b(sentiment|tone|emotion|polarity|positive|negative|neutral|opinion|attitude|mood)\b"),

    # ── multimedia_processing ──
    ("multimedia_processing/image/analysis",
     r"(?i)\b(image|photo|picture|analyze.*image|ocr|object.*detection|classify.*image|describe.*image|what.*in.*(image|picture|photo))\b"),
    ("multimedia_processing/image/generation",
     r"(?i)\b(generate.*image|create.*image|draw|illustrat|render|banner|logo|poster|artwork|dall.?e|midjourney|stable.*diffusion)\b"),
]


def task_to_paths(task: str) -> dict[str, float]:
    """Map a task description to hierarchical path weights via keyword matching.

    Each path gets a weight proportional to how many of its keywords
    appear in the task.  Normalized to sum to 1.0.
    """
    scores: dict[str, int] = {}

    for path, pattern in PATH_PATTERNS:
        matches = re.findall(pattern, task)
        if matches:
            scores[path] = len(matches)

    total = sum(scores.values())
    if total == 0:
        # Default: general reasoning + fact retrieval
        return {
            "general_knowledge/reasoning/explanation": 0.5,
            "general_knowledge/fact_retrieval/definitions": 0.5,
        }

    return {path: v / total for path, v in scores.items()}


# ═══════════════════════════════════════════════════════════════════════════
#  Category Selector
# ═══════════════════════════════════════════════════════════════════════════


class CategorySelector:
    """Scores and ranks models by hierarchical category paths for a given task.

    Models carry whole-number 0-100 scores on specific category paths.
    The selector matches task keywords against these paths, then ranks
    models by a weighted sum: for each task-relevant path, multiply the
    task weight by the model's score on that path (or a parent path).
    """

    def __init__(self, models: dict[str, Any]) -> None:
        """*models* is ``config.models`` — a dict of model_id → ModelEntry."""
        self._models = models

    def score(self, task: str) -> dict[str, float]:
        """Return ``{model_id: score, ...}`` for every model in the catalog.

        Score = sum over matched paths of ``task_weight[path] * model_score[path]``.
        Falls back to parent-path matching when the exact path isn't scored.
        """
        task_weights = task_to_paths(task)
        results: dict[str, float] = {}

        for model_id, entry in self._models.items():
            model_cats = getattr(entry, "categories", {})
            if not model_cats:
                results[model_id] = 0.0
                continue

            total = 0.0
            for path, weight in task_weights.items():
                model_score = self._resolve_path(model_cats, path)
                total += weight * model_score
            results[model_id] = total

        return results

    @staticmethod
    def _resolve_path(model_cats: dict[str, float], path: str) -> float:
        """Look up a model's score for *path*, falling back to parent paths.

        If the model has an exact score for ``path``, return it.  Otherwise
        try progressively shorter prefixes (popping the last segment) until
        a match is found or the root is reached.
        """
        if path in model_cats:
            return model_cats[path]

        # Try parent paths
        segments = path.split("/")
        while segments:
            segments.pop()
            if not segments:
                break
            parent = "/".join(segments)
            if parent in model_cats:
                return model_cats[parent]

        return 0.0

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
        task_weights = task_to_paths(task)
        scores = self.score(task)
        selected = self.select(task, count=count)

        lines = [
            f"Task: {task[:80]}",
            f"Path weights: {dict(list(task_weights.items())[:5])}",
            "",
            f"Top {count} models:",
        ]
        for i, mid in enumerate(selected):
            entry = self._models.get(mid)
            cats = getattr(entry, "categories", {}) if entry else {}
            relevant = {p: s for p, s in cats.items()
                       if any(p.startswith(tp) or tp.startswith(p) for tp in task_weights)}
            lines.append(
                f"  {i + 1}. {mid} — score={scores.get(mid, 0):.1f}  "
                f"relevant={dict(list(relevant.items())[:3])}"
            )

        return "\n".join(lines)
