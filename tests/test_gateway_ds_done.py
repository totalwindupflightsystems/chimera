"""Tests for non-stream response body with trailing data: [DONE] sentinel.

Regression for DF-CHIMERA-V2-63: 9router upstream appends a literal
"data: [DONE]" line after non-stream JSON bodies. A strict JSON client
hits parse errors; _extract_text must strip the sentinel so the returned
text is clean.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from chimera.gateway import _extract_text


def _make_mock_result(content: str) -> MagicMock:
    """Build a minimal mock LiteLLM completion result.

    ``choices[0].message.content`` is set to *content*.
    """
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    result = MagicMock()
    result.choices = [choice]
    return result


class TestNonStreamDataDoneSentinel:
    """DF-CHIMERA-V2-63: _extract_text must tolerate trailing data: [DONE]."""

    def test_clean_content_returns_as_is(self) -> None:
        result = _make_mock_result("pong")
        assert _extract_text(result) == "pong"

    def test_content_with_data_done_suffix_strips_sentinel(self) -> None:
        """When the response body contains a trailing 'data: [DONE]' line,
        _extract_text must return the clean content without it."""
        result = _make_mock_result("pong\ndata: [DONE]\n\n")
        assert _extract_text(result) == "pong"

    def test_content_with_data_done_no_trailing_newlines(self) -> None:
        result = _make_mock_result("pong\ndata: [DONE]")
        assert _extract_text(result) == "pong"

    def test_multi_line_answer_with_data_done_suffix(self) -> None:
        """Multi-line model answers followed by the sentinel are handled."""
        answer = "First line\nSecond line\nThird line"
        result = _make_mock_result(f"{answer}\ndata: [DONE]\n\n")
        assert _extract_text(result) == answer

    def test_content_still_has_data_done_when_no_suffix_present(self) -> None:
        """Edge case: if 'data: [DONE]' appears *inside* the answer (not at
        the very end), it should NOT be stripped — only the trailing
        sentinel is removed."""
        result = _make_mock_result("Answer: data: [DONE] is in the middle")
        assert _extract_text(result) == "Answer: data: [DONE] is in the middle"

    def test_empty_content_with_data_done_returns_empty(self) -> None:
        result = _make_mock_result("\ndata: [DONE]\n\n")
        assert _extract_text(result) == ""

    def test_whitespace_content_with_data_done_strips_sentinel(self) -> None:
        """Whitespace-only content still returns the cleaned whitespace
        (the upstream is_empty flag catches blanks, not _extract_text)."""
        result = _make_mock_result("   \n   data: [DONE]\n\n")
        # Sentiel stripped → whitespace remains; returns as-is
        assert _extract_text(result) == "   \n   "
