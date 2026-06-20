"""Unit tests for the hierarchical category path model selector."""

from __future__ import annotations

import re

from chimera.selector import (
    PATH_PATTERNS,
    CategorySelector,
    task_to_paths,
)

# ── Sample model catalog (hierarchical paths, 0-100 scores) ────────────────


class _FakeEntry:
    """Minimal model entry for testing."""

    def __init__(self, categories: dict[str, float], provider: str, cost_tier: str = "standard"):
        self.categories = categories
        self.provider = provider
        self.cost_tier = cost_tier


SAMPLE_MODELS = {
    "deepseek/deepseek-v4-flash": _FakeEntry(
        {"technology_code/code_generation/python": 88, "technology_code/code_generation/sql": 80,
         "technology_code/data_science/analysis": 80},
        "deepseek", "budget",
    ),
    "deepseek/deepseek-v4-pro": _FakeEntry(
        {"technology_code/code_generation/python": 92, "technology_code/code_generation/sql": 87,
         "technology_code/data_science/analysis": 85, "academic_scientific/mathematics/algebra": 72},
        "deepseek", "budget",
    ),
    "google/gemini-3-flash-preview": _FakeEntry(
        {"technology_code/code_generation/python": 78, "technology_code/data_science/analysis": 85,
         "general_knowledge/reasoning/explanation": 82, "multimedia_processing/image/analysis": 80},
        "google", "budget",
    ),
    "anthropic/claude-sonnet-4": _FakeEntry(
        {"technology_code/code_generation/python": 90, "technology_code/data_science/analysis": 92,
         "creative_conversational/ux_writing/interface_copy": 88, "general_knowledge/reasoning/explanation": 93},
        "anthropic", "premium",
    ),
    "openrouter/moonshotai/kimi-k2.7-code": _FakeEntry(
        {"technology_code/code_generation/python": 95, "technology_code/code_generation/sql": 88,
         "technology_code/testing_debugging/error_analysis": 80},
        "openrouter", "standard",
    ),
    "zai-coding-plan/glm-5.2": _FakeEntry(
        {"technology_code/code_generation/python": 94, "technology_code/data_science/analysis": 90,
         "academic_scientific/mathematics/algebra": 85, "general_knowledge/reasoning/explanation": 93},
        "zai", "premium",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
#  task_to_paths
# ═══════════════════════════════════════════════════════════════════════════


class TestTaskToPaths:
    def test_coding_task_weights_python_path_heavily(self):
        """A coding task should weight Python code generation heavily."""
        weights = task_to_paths("Write a Python function to sort a list")
        assert "technology_code/code_generation/python" in weights, f"no python path: {weights}"

    def test_design_task_weights_ux_path(self):
        """A UI design task should weight UX writing path."""
        weights = task_to_paths("Design a landing page with a blue theme and logo")
        assert "creative_conversational/ux_writing/interface_copy" in weights, f"no ux path: {weights}"

    def test_analysis_task_weights_data_science(self):
        """An analysis task should weight data_science/analysis."""
        weights = task_to_paths("Analyze this dataset and find patterns in the metrics")
        assert "technology_code/data_science/analysis" in weights, f"no analysis path: {weights}"

    def test_ambiguous_task_defaults_to_general_knowledge(self):
        """A generic task should default to general knowledge paths."""
        weights = task_to_paths("What is the capital of France?")
        assert len(weights) > 0, f"empty weights: {weights}"
        # Should weight general knowledge
        assert any("general_knowledge" in p for p in weights), f"no general_knowledge: {weights}"

    def test_all_weights_sum_to_one(self):
        """Path weights must always sum to 1.0."""
        for task in [
            "Write code to parse JSON",
            "Review this security vulnerability",
            "Make it look pretty on mobile",
            "Why does this crash?",
            "Hello world",
        ]:
            weights = task_to_paths(task)
            assert abs(sum(weights.values()) - 1.0) < 0.001, (
                f"Task '{task}' weights don't sum to 1.0: {weights}"
            )

    def test_security_task_maps_to_error_analysis(self):
        """A security audit task should map to error_analysis path."""
        weights = task_to_paths("Audit this code for security vulnerabilities and check for exposed secrets")
        assert any("error_analysis" in p or "debugging" in p for p in weights), f"no security path: {weights}"

    def test_math_proof_task_maps_to_algebra(self):
        """A math proof task should map to algebra path."""
        weights = task_to_paths("Prove that the sum of two even numbers is always even")
        assert "academic_scientific/mathematics/algebra" in weights, f"no algebra: {weights}"


# ═══════════════════════════════════════════════════════════════════════════
#  CategorySelector
# ═══════════════════════════════════════════════════════════════════════════


class TestCategorySelector:
    def test_select_coding_task_returns_code_models(self):
        """A coding task should select models with high Python code scores."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select("Write a Python web scraper using aiohttp", count=3)
        assert len(result) == 3
        # Kimi has highest Python code score (95), then GLM-5.2 (94), then v4-pro (92)
        assert result[0] in ("openrouter/moonshotai/kimi-k2.7-code", "zai-coding-plan/glm-5.2")

    def test_select_design_task_returns_design_models(self):
        """A design task should favor models with high UX scores."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select("Design a responsive landing page layout", count=2)
        assert "anthropic/claude-sonnet-4" in result

    def test_select_respects_exclude(self):
        """Excluded models must never appear in results."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select("Write code", count=5, exclude=["deepseek/deepseek-v4-pro"])
        assert "deepseek/deepseek-v4-pro" not in result

    def test_select_prefer_budget_boosts_budget_models(self):
        """With prefer_budget=True, budget models get a 15% boost."""
        sel = CategorySelector(SAMPLE_MODELS)
        normal = sel.select("Write Python code", count=1)
        boosted = sel.select("Write Python code", count=1, prefer_budget=True)
        tiers = [
            getattr(SAMPLE_MODELS.get(m), "cost_tier", "") for m in (normal[0], boosted[0])
        ]
        assert "budget" in tiers, f"Neither result is budget-tier: {tiers}"

    def test_select_returns_at_most_count(self):
        """select() never returns more models than requested."""
        sel = CategorySelector(SAMPLE_MODELS)
        for count in (1, 2, 3, 10):
            result = sel.select("Write Python code", count=count)
            assert len(result) <= count, f"count={count}, got {len(result)}"

    def test_select_diverse_no_same_provider_twice(self):
        """select_diverse() must not pick two models from the same provider."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select_diverse("Write Python code", count=3)
        providers = [getattr(SAMPLE_MODELS.get(m), "provider", "") for m in result]
        assert len(providers) == len(set(providers)), f"Duplicate providers: {providers}"

    def test_select_diverse_returns_correct_count(self):
        """select_diverse() should return min(count, unique_providers) models."""
        sel = CategorySelector(SAMPLE_MODELS)
        result = sel.select_diverse("Write Python code", count=3)
        assert len(result) <= 3

    def test_explain_returns_string(self):
        """explain() should return a non-empty string."""
        sel = CategorySelector(SAMPLE_MODELS)
        explanation = sel.explain("Write a Python web scraper", count=2)
        assert isinstance(explanation, str)
        assert len(explanation) > 50
        assert "Python" in explanation

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
        result = sel.select("Write Python code", count=2)
        assert "test/no-cats" not in result, "Model with no categories should not be selected"

    def test_parent_path_fallback(self):
        """_resolve_path should fall back to parent paths."""
        model_cats = {"technology_code/code_generation": 85}
        score = CategorySelector._resolve_path(model_cats, "technology_code/code_generation/python")
        assert score == 85, f"parent fallback failed: {score}"

    def test_exact_path_match_wins(self):
        """_resolve_path should prefer exact match over parent."""
        model_cats = {"technology_code/code_generation": 80, "technology_code/code_generation/python": 90}
        score = CategorySelector._resolve_path(model_cats, "technology_code/code_generation/python")
        assert score == 90, f"exact match should win: {score}"

    def test_all_paths_have_valid_patterns(self):
        """Every path in PATH_PATTERNS must have a compilable regex."""
        for path, pattern in PATH_PATTERNS:
            assert pattern.strip(), f"Path '{path}' has empty pattern"
            re.compile(pattern)


# ═══════════════════════════════════════════════════════════════════════════
#  Lifetime: model cost tier field
# ═══════════════════════════════════════════════════════════════════════════


class TestCostTierAccess:
    def test_fake_entry_has_cost_tier(self):
        entry = _FakeEntry({"technology_code/code_generation/python": 90}, "deepseek", "budget")
        assert entry.cost_tier == "budget"

    def test_fake_entry_has_provider(self):
        entry = _FakeEntry({"technology_code/code_generation/python": 90}, "deepseek")
        assert entry.provider == "deepseek"
