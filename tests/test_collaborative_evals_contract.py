"""Unit contract tests for collaborative-evaluation answer assertions."""

from tests.integration.test_collaborative_evals import _states_sqrt_two_is_irrational


def test_math_proof_conclusion_accepts_english_irrationality() -> None:
    assert _states_sqrt_two_is_irrational("The square root of 2 is irrational.")


def test_math_proof_conclusion_accepts_historical_latex_output() -> None:
    """GitHub run 40140359467 emitted a valid formal conclusion."""
    assert _states_sqrt_two_is_irrational("**Theorem.** \\(\\sqrt2\\notin\\mathbb Q\\).")


def test_math_proof_conclusion_rejects_a_different_radical() -> None:
    assert not _states_sqrt_two_is_irrational("\\sqrt3\\notin\\mathbb Q")
