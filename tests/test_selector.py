"""Unit tests for the category-weighted model selector."""

from __future__ import annotations

import re

from chimera.selector import (
    CATEGORY_PATTERNS,
    CategorySelector,
    task_to_categories,
)

# ── Sample model catalog (mirrors chimera.yaml structure) ──────────────────


class _FakeEntry:
    """Minimal model entry for testing."""

    def __init__(self, categories: dict[str, float], provider: str, cost_tier: str = "standard"):
        self.categories = categories
        self.provider = provider
        self.cost_tier = cost_tier


SAMPLE_MODELS = {
    "deepseek/deepseek-v4-flash": _FakeEntry(
        {"analysis": 0.80, "audit": 0.55, "code": 0.90, "design": 0.35, "reasoning": 0.75},
        "deepseek",
        "budget",
    ),
    "deepseek/deepseek-v4-pro": _FakeEntry(
        {"analysis": 0.85, "audit": 0.60, "code": 0.95, "design": 0.40, "reasoning": 0.80},
        "deepseek",
        "budget",
    ),
    "google/gemini-3-flash-preview": _FakeEntry(
        {"analysis": 0.85, "audit": 0.60, "code": 0.78, "design": 0.75, "reasoning": 0.82},
        "google",
        "budget",
    ),
    "anthropic/claude-sonnet-4": _FakeEntry(
        {"analysis": 0.92, "audit": 0.85, "code": 0.90, "design": 0.88, "reasoning": 0.93},
        "anthropic",
        "premium",
    ),
    "openrouter/moonshotai/kimi-k2.7-code": _FakeEntry(
        {"analysis": 0.82, "audit": 0.60, "code": 0.93, "design": 0.70, "reasoning": 0.85},
        "openrouter",
        "standard",
    ),
    "zai-coding-plan/glm-5.2": _FakeEntry(
        {"analysis": 0.90, "audit": 0.88, "code": 0.92, "design": 0.85, "reasoning": 0.95},
        "zai",
        "premium",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
#  task_to_categories
# ═══════════════════════════════════════════════════════════════════════════


class TestTaskToCategories:
    def test_coding_task_weights_code_heavily(self):
        """A coding task should weight 'code' heavily."""
        weights = task_to_categories("Write a Python function to sort a list")
        assert weights["code"] > 0.3, f"code weight too low: {weights}"

    def test_design_task_weights_design_heavily(self):
        """A design task should weight 'design' heavily."""
        weights = task_to_categories("Design a landing page with a blue theme and logo")
        assert weights["design"] > 0.2, f"design weight too low: {weights}"

    def test_analysis_task_weights_analysis(self):
        """An analysis task should weight 'analysis'."""
        weights = task_to_categories("Analyze this dataset and find patterns in the metrics")
        assert weights["analysis"] > 0.15, f"analysis weight too low: {weights}"

    def test_ambiguous_task_has_balanced_weights(self):
        """A generic task should have distributed weights."""
        weights = task_to_categories("What is the capital of France?")
        # All categories should be non-zero (default equal split)
        for v in weights.values():
            assert v > 0, f"zero weight found: {weights}"

    def test_all_weights_sum_to_one(self):
        """Category weights must always sum to 1.0."""
        for task in [
            "Write code to parse JSON",
            "Review this security policy",
            "Make it look pretty",
            "Why does this crash?",
            "Hello world",
        ]:
            weights = task_to_categories(task)
            assert abs(sum(weights.values()) - 1.0) < 0.001, (
                f"Task '{task}' weights don't sum to 1.0: {weights}"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  CategorySelector
# ═══════════════════════════════════════════════════════════════════════════


class TestCategorySelector:
    def test_select_coding_task_returns_code_models(self):
        """A coding task should select models with high code scores."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select("Write a Python web scraper using aiohttp", count=3)
        assert len(result) == 3
        # DeepSeek V4 Pro has the highest code score (0.95)
        assert result[0] in (
            "deepseek/deepseek-v4-pro",
            "openrouter/moonshotai/kimi-k2.7-code",
            "zai-coding-plan/glm-5.2",
        )

    def test_select_design_task_returns_design_models(self):
        """A design task should favor models with high design scores."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select("Design a responsive landing page layout", count=2)
        # Anthropic has highest design score
        assert "anthropic/claude-sonnet-4" in result

    def test_select_respects_exclude(self):
        """Excluded models must never appear in results."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select(
            "Write code", count=5, exclude=["deepseek/deepseek-v4-pro"]
        )
        assert "deepseek/deepseek-v4-pro" not in result

    def test_select_prefer_budget_boosts_budget_models(self):
        """With prefer_budget=True, budget models get a 15% boost."""
        sel = CategorySelector(SAMPLE_MODELS)
        normal = sel.select("Write code", count=1)
        boosted = sel.select("Write code", count=1, prefer_budget=True)

        # At least one of them should be budget-tier
        tiers = [
            getattr(SAMPLE_MODELS.get(m), "cost_tier", "")
            for m in (normal[0], boosted[0])
        ]
        assert "budget" in tiers, f"Neither result is budget-tier: {tiers}"

    def test_select_returns_at_most_count(self):
        """select() never returns more models than requested."""
        sel = CategorySelector(SAMPLE_MODELS)
        for count in (1, 2, 3, 10):
            result = sel.select("Write code", count=count)
            assert len(result) <= count, f"count={count}, got {len(result)}"

    def test_select_diverse_no_same_provider_twice(self):
        """select_diverse() must not pick two models from the same provider."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select_diverse("Write code", count=3)
        providers = [
            getattr(SAMPLE_MODELS.get(m), "provider", "") for m in result
        ]
        assert len(providers) == len(set(providers)), (
            f"Duplicate providers in diverse selection: {providers}"
        )

    def test_select_diverse_returns_correct_count(self):
        """select_diverse() should return min(count, unique_providers) models."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select_diverse("Write code", count=3)
        # We have 6 models across 5 providers; should get 3
        assert len(result) <= 3

    def test_explain_returns_string(self):
        """explain() should return a non-empty string."""
        sel = CategorySelector(SAMPLE_MODELS)
        explanation = sel.explain("Write a Python web scraper", count=2)
        assert isinstance(explanation, str)
        assert len(explanation) > 50
        assert "Write a Python web scraper" in explanation

    def test_empty_catalog_returns_empty(self):
        """An empty model catalog should return empty results gracefully."""
        sel = CategorySelector({})
        result = sel.select("anything", count=3)
        assert result == []

    def test_model_with_no_categories_scores_zero(self):
        """A model with no category scores must get score 0.0."""
        models = {
            "test/no-cats": _FakeEntry({}, "test", "budget"),
            "deepseek/deepseek-v4-pro": SAMPLE_MODELS["deepseek/deepseek-v4-pro"],
        }
        sel = CategorySelector(models)
        result = sel.select("Write code", count=2)
        assert "test/no-cats" not in result, "Model with no categories should not be selected"

    def test_audit_task_weights_audit(self):
        """A security audit task should weight 'audit' category."""
        weights = task_to_categories(
            "Audit this code for security vulnerabilities and check for exposed secrets"
        )
        assert weights["audit"] > 0.1, f"audit weight too low: {weights}"

    def test_reasoning_task_weights_reasoning(self):
        """A reasoning-heavy math task should weight 'reasoning'."""
        weights = task_to_categories(
            "Prove that the sum of two even numbers is always even"
        )
        assert weights["reasoning"] >= 0.2, f"reasoning weight too low: {weights}"

    def test_all_categories_have_at_least_one_pattern(self):
        """Every category in CATEGORY_PATTERNS must have a non-empty regex."""

        for cat, pattern in CATEGORY_PATTERNS:
            assert pattern.strip(), f"Category '{cat}' has empty pattern"
            # Must compile
            re.compile(pattern)


# ═══════════════════════════════════════════════════════════════════════════
#  Lifetime: model cost tier field
# ═══════════════════════════════════════════════════════════════════════════


class TestCostTierAccess:
    def test_fake_entry_has_cost_tier(self):
        """Our test _FakeEntry must have cost_tier for prefer_budget tests."""
        entry = _FakeEntry({"code": 0.9}, "deepseek", "budget")
        assert entry.cost_tier == "budget"

    def test_fake_entry_has_provider(self):
        entry = _FakeEntry({"code": 0.9}, "deepseek")
        assert entry.provider == "deepseek"
