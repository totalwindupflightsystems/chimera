"""Reply-parsing / retry tests for the ``--score`` path in scripts/model_sync.py — DF-CHIMERA-V2-13.

The 2026-09-18 scheduled run auto-scored a candidate and died with
``❌ LLM scoring failed: Expecting value: line 1 column 1 (char 0)``. The cause
is the reasoning-model shape on the shared DeepSeek endpoint:
``deepseek-v4-flash`` spent the entire ``max_tokens`` budget on
``reasoning_content``, so the reply arrived with ``content=""`` and
``finish_reason="length"``. The old code called ``json.loads(content)`` directly
and reported the parse error instead of the token starvation, and it could
never have recovered from it (fixed 4096-token budget, no retry).

These tests are entirely offline (no network, no API key) and pin the fixed
contract:

* ``_extract_json_object()`` parses plain, fenced and prose-wrapped JSON;
  an empty reply and a JSON-less reply raise ``ValueError`` with a message
  that names the cause instead of a bare ``JSONDecodeError``;
* ``_score_request_body()`` carries the model, the token budget and the
  ``json_object`` response format;
* ``_score_llm_reply()`` doubles the budget on ``finish_reason="length"`` and
  retries, up to ``SCORE_MAX_TOKENS_CEILING``, and raises a message carrying
  the real budget/finish reason once the ceiling is reached or the reply was
  truncated for another reason.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"

#: Fixed "now" for recency fixtures — newer candidates carry larger timestamps.
NOW_BASE = time.time()

#: Deliberately not key-shaped so the repo's secret scanner has nothing to match.
TEST_KEY = "scoring-test-key-not-real"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


model_sync = _load_module("model_sync_scoring", SYNC_PATH)


def _reply(content: str | None, finish_reason: str = "stop") -> dict[str, Any]:
    """A DeepSeek-shaped response body."""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ]
    }


# --- _extract_json_object ---------------------------------------------------- #


def test_extract_plain_json_object() -> None:
    assert model_sync._extract_json_object('{"models": []}') == {"models": []}


def test_extract_fenced_json_object() -> None:
    text = '```json\n{"models": [{"chimera_id": "a/b"}]}\n```'
    assert model_sync._extract_json_object(text) == {"models": [{"chimera_id": "a/b"}]}


def test_extract_json_object_with_surrounding_prose() -> None:
    text = 'Sure — here are the scores:\n{"models": []}\nLet me know if you want more.'
    assert model_sync._extract_json_object(text) == {"models": []}


def test_extract_empty_content_reports_token_starvation() -> None:
    with pytest.raises(ValueError) as exc:
        model_sync._extract_json_object("")
    assert "empty model content" in str(exc.value)
    assert "max_tokens" in str(exc.value)


def test_extract_none_content_reports_token_starvation() -> None:
    with pytest.raises(ValueError) as exc:
        model_sync._extract_json_object(None)
    assert "empty model content" in str(exc.value)


def test_extract_jsonless_content_reports_no_json_object() -> None:
    with pytest.raises(ValueError) as exc:
        model_sync._extract_json_object("I cannot score these models.")
    assert "no JSON object in model content" in str(exc.value)


# --- _score_request_body ----------------------------------------------------- #


def test_score_request_body_carries_budget_and_format() -> None:
    body = json.loads(model_sync._score_request_body("deepseek-v4-flash", "score these", 12345))
    assert body["model"] == "deepseek-v4-flash"
    assert body["max_tokens"] == 12345
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [{"role": "user", "content": "score these"}]


def test_first_scoring_budget_clears_the_reasoning_budget_that_failed() -> None:
    """The failing run starved 4096 tokens; the first attempt must exceed that."""
    assert model_sync.SCORE_MAX_TOKENS > 4096
    assert model_sync.SCORE_MAX_TOKENS_CEILING >= model_sync.SCORE_MAX_TOKENS * 2


# --- _score_llm_reply -------------------------------------------------------- #


def test_score_reply_returns_on_first_attempt() -> None:
    calls: list[tuple[str, int]] = []

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        calls.append((model, max_tokens))
        return _reply('{"models": [{"chimera_id": "mistral/zai-glm-5-3"}]}')

    out = model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert out == {"models": [{"chimera_id": "mistral/zai-glm-5-3"}]}
    assert calls == [(model_sync.SCORE_MODEL, model_sync.SCORE_MAX_TOKENS)]


def test_score_reply_retries_with_doubled_budget_when_reasoning_starves_it() -> None:
    budgets: list[int] = []

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        budgets.append(max_tokens)
        if len(budgets) == 1:  # reasoning ate the whole budget — the 2026-09-18 shape
            return _reply("", finish_reason="length")
        return _reply('{"models": []}')

    assert model_sync._score_llm_reply("prompt", "key", post=fake_post) == {"models": []}
    assert budgets == [model_sync.SCORE_MAX_TOKENS, model_sync.SCORE_MAX_TOKENS * 2]


def test_score_reply_retries_then_raises_at_the_ceiling() -> None:
    budgets: list[int] = []

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        budgets.append(max_tokens)
        return _reply("", finish_reason="length")

    with pytest.raises(ValueError) as exc:
        model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert budgets[-1] == model_sync.SCORE_MAX_TOKENS_CEILING
    assert budgets == sorted(budgets)
    message = str(exc.value)
    assert "finish_reason=length" in message
    assert f"max_tokens={model_sync.SCORE_MAX_TOKENS_CEILING}" in message


def test_score_reply_does_not_retry_a_reply_truncated_for_other_reasons() -> None:
    """``content_filter`` (or any non-``length`` finish) is a hard error, not a retry."""
    calls = 0

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _reply("", finish_reason="content_filter")

    with pytest.raises(ValueError) as exc:
        model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert calls == 1
    assert "finish_reason=content_filter" in str(exc.value)


def test_score_reply_handles_malformed_response_shape() -> None:
    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        return {}

    with pytest.raises(ValueError) as exc:
        model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert "empty model content" in str(exc.value)


# --- concatenated-JSON replies + the no-silent-success contract (DF-CHIMERA-V2-57) --- #
#
# The 2026-09-25 12:00 cron run failed with ``LLM scoring failed: Extra data:
# line 2 column 1 (char 24)`` and wrote NO model_scores_*.yaml: the model
# returned two JSON objects back to back and the brace-slice fallback fed the
# whole concatenation back to ``json.loads``. Two contract halves are pinned
# here: a reply of concatenated objects scores from the FIRST object, and an
# unparseable non-truncation reply exits non-zero with a named reason — never
# exit 0 with no score file.


def test_extract_concatenated_json_objects_scores_from_the_first() -> None:
    """Two objects back to back: the first object is the reply's payload."""
    text = '{"models": [{"chimera_id": "a/b"}]}\n{"models": [{"chimera_id": "c/d"}]}'
    assert model_sync._extract_json_object(text) == {"models": [{"chimera_id": "a/b"}]}


def test_extract_concatenated_json_objects_with_blank_line_separation() -> None:
    text = '{"models": []}\n\n{"scores": 1}'
    assert model_sync._extract_json_object(text) == {"models": []}


def test_extract_unparseable_content_names_the_parse_error() -> None:
    text = '{"models": [{"chimera_id": "a/b"}}, {"oops": '
    with pytest.raises(ValueError) as exc:
        model_sync._extract_json_object(text)
    message = str(exc.value)
    assert "no JSON object in model content" in message
    assert "Extra data" in message or "Expecting" in message  # the underlying parse error


def test_score_reply_concatenated_objects_scores_from_the_first() -> None:
    """End-to-end reply shape of the 2026-09-25 failure — finish_reason=stop."""
    calls: list[int] = []

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        calls.append(max_tokens)
        return _reply('{"models": [{"chimera_id": "a/b"}]}\n{"models": [{"chimera_id": "c/d"}]}')

    out = model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert out == {"models": [{"chimera_id": "a/b"}]}
    assert calls == [model_sync.SCORE_MAX_TOKENS]  # no retry — parsed on the first call


def test_score_reply_unparseable_content_raises_named_reason_no_retry() -> None:
    """A parse-failed reply with finish_reason=stop is a hard, NAMED error."""
    calls = 0

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _reply('{"broken": ')

    with pytest.raises(ValueError) as exc:
        model_sync._score_llm_reply("prompt", "key", post=fake_post)
    message = str(exc.value)
    assert "no JSON object in model content" in message  # the parse error, named
    assert "finish_reason=stop" in message  # the finish reason, named
    assert calls == 1  # parse failure is NOT the truncation ladder's trigger


def test_score_reply_length_ladder_still_doubles_on_truncated_content() -> None:
    """Regression guard for the ladder's other half: truncated CONTENT retries.

    The concatenation fix must not turn a genuinely truncated reply
    (finish_reason=length) into a hard error — the 2026-09-18 contract.
    """
    budgets: list[int] = []

    def fake_post(model: str, prompt: str, max_tokens: int, api_key: str) -> dict[str, Any]:
        budgets.append(max_tokens)
        if len(budgets) == 1:
            return _reply('{"models": [{"chimera_id": "a/b"', finish_reason="length")
        return _reply('{"models": [{"chimera_id": "a/b"}]}')

    out = model_sync._score_llm_reply("prompt", "key", post=fake_post)
    assert out == {"models": [{"chimera_id": "a/b"}]}
    assert budgets == [model_sync.SCORE_MAX_TOKENS, model_sync.SCORE_MAX_TOKENS * 2]


class TestSilentSuccessContract:
    """``--score`` / ``--score-from`` must never exit 0 with no score file."""

    def _candidates(self) -> dict[str, list[dict[str, Any]]]:
        return {"openai": [{"chimera_id": "openai/m-1", "model_id": "m-1", "description": "d"}]}

    def test_scoring_failure_exits_nonzero_with_named_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        def broken_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
            raise ValueError(
                "no JSON object in model content "
                "(model=deepseek-v4-flash, finish_reason=stop, max_tokens=8192)"
            )

        monkeypatch.setattr(model_sync, "_score_llm_reply", broken_reply)
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        with pytest.raises(SystemExit) as excinfo:
            model_sync._llm_score_candidates(self._candidates())

        assert excinfo.value.code == 1
        # The named reason reaches stderr, not a swallowed stdout note.
        err = capsys.readouterr().err
        assert "LLM scoring failed" in err
        assert "finish_reason=stop" in err
        # And the silent-success hole stays closed: no score file appeared.
        assert not list((tmp_path / "reports").glob("model_scores_*.yaml"))

    def test_scoring_success_still_writes_the_score_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """Control for the exit path: the happy contract is unchanged."""

        def good_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
            return {"models": [{"chimera_id": "openai/m-1"}]}

        monkeypatch.setattr(model_sync, "_score_llm_reply", good_reply)
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        model_sync._llm_score_candidates(self._candidates())  # no SystemExit

        files = list((tmp_path / "reports").glob("model_scores_*.yaml"))
        assert len(files) == 1
        assert "chimera_id" in files[0].read_text(encoding="utf-8")
        assert "Model scores saved to" in capsys.readouterr().out


def test_score_prompt_is_capped_to_the_documented_top_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scoring payload must not scale with a candidate flood (cap = 5).

    The 2026-09-25 run's scan carried ~225 candidates; the prompt embeds only
    the recency-selected top ``SCORE_CANDIDATE_LIMIT`` of them — pinned here so
    the cap cannot silently regress to "embed everything".
    """
    assert model_sync.SCORE_CANDIDATE_LIMIT == 5
    many = {
        "prov": [
            {
                "chimera_id": f"prov/m-{i:02d}",
                "model_id": f"m-{i:02d}",
                "description": f"candidate {i}",
                "recency_score": 100.0,
                "recency_ts": float(NOW_BASE - i * 86400),
                "provider": "prov",
            }
            for i in range(12)
        ]
    }
    prompts: list[str] = []

    def fake_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
        prompts.append(prompt)
        return {"models": []}

    monkeypatch.setenv("DEEPSEEK_API_KEY", "scoring-test-key-not-real")
    monkeypatch.setattr(model_sync, "_score_llm_reply", fake_reply)
    monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)

    model_sync._llm_score_candidates(many)

    prompt = prompts[0]
    embedded = [f"prov/m-{i:02d}" for i in range(12) if f"prov/m-{i:02d}" in prompt]
    assert embedded == [f"prov/m-{i:02d}" for i in range(model_sync.SCORE_CANDIDATE_LIMIT)]
