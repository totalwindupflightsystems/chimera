"""Rank-then-fuse pre-merge ranking (DF-CHIMERA-V2-102).

LLM-Blender PairRanker class: with ``rank: true`` on a formation, ONE cheap
scorer call scores every upstream output before the merge, the candidates are
sorted by score, and only the top ``kappa`` reach the aggregator prompt — while
every scored candidate is still recorded on the trace.

Hermetic: every provider call (workers, scorer, aggregator) is answered by a
scripted FakeGateway responder — no network, no live catalog.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from chimera.aggregator import parse_rank_scores
from chimera.config import ChimeraConfig
from chimera.engine import Engine
from chimera.gateway import GatewayError
from tests.conftest import CONFIG_DICT, FakeGateway, resp

#: 5 workers, 5 distinct models, so each worker's output text is identifiable
#: in the merge prompt by the model that produced it.
_WORKER_MODELS: list[str] = [
    "deepseek/deepseek-chat",
    "openrouter/qwen/qwen3-coder",
    "deepseek/deepseek-v4-flash",
    "openrouter/google/gemini-2.5-flash",
    "zai-coding-plan/glm-5.2",
]

#: Scorer fixture. Deliberately NOT in worker order: the top-2 must be
#: worker_4 + worker_2, so a passing test proves the outputs were SORTED by
#: score, not merely sliced in declaration order.
_SCORES: dict[str, float] = {
    "worker_1": 1.0,
    "worker_2": 8.0,
    "worker_3": 0.5,
    "worker_4": 9.5,
    "worker_5": 7.0,
}

_KAPPA = 2

#: Marker the scripted workers stamp into their answers.
_OUTPUT_MARKER = "OUTPUT-FROM-"


def _worker_model(stage_id: str) -> str:
    """Model configured for ``worker_N`` (1-based) in this fixture."""
    return _WORKER_MODELS[int(stage_id.rsplit("_", 1)[1]) - 1]


def _worker_output(model: str) -> str:
    return f"{_OUTPUT_MARKER}{model}"


def _responder(
    *,
    fail_scorer: bool = False,
    scores: dict[str, float] | None = None,
) -> Any:
    """Scripted provider: dispatcher-less workers, one scorer, one merge.

    The scorer call is recognised by its system prompt (the merge prompt and
    the worker prompts never contain it), which keeps the fixture independent
    of call ordering under the engine's parallel worker wave.
    """
    fixture_scores = _SCORES if scores is None else scores

    def _respond(
        model: str,
        messages: list[dict[str, str]],
        response_format: Any = None,
        **kw: Any,
    ) -> Any:
        system = messages[0]["content"] if messages else ""
        joined = json.dumps(messages)
        if "pre-merge scorer" in system:
            if fail_scorer:
                raise GatewayError("scorer upstream 503")
            return resp(json.dumps({"scores": fixture_scores}), model, tok_in=70, tok_out=9)
        if "Upstream outputs" in joined:  # aggregator / merge / audit
            return resp(f"[MERGED by {model}]", model, tok_in=100, tok_out=50)
        return resp(_worker_output(model), model, tok_in=20, tok_out=30)

    return _respond


def _config(
    *,
    rank: bool,
    kappa: int = _KAPPA,
    rank_model: str | None = None,
    n_workers: int = 5,
) -> ChimeraConfig:
    data = copy.deepcopy(CONFIG_DICT)
    formation: dict[str, Any] = {
        "workers": n_workers,
        "worker_models": _WORKER_MODELS[:n_workers],
        "aggregator": "default",
    }
    if rank:
        formation["rank"] = True
        formation["kappa"] = kappa
    if rank_model is not None:
        formation["rank_model"] = rank_model
    data["formations"]["ranked_fanout"] = formation
    return ChimeraConfig.model_validate(data)


def _scorer_calls(gw: FakeGateway) -> list[tuple[str, list[dict[str, str]], dict[str, Any]]]:
    return [call for call in gw.calls if "pre-merge scorer" in (call[1][0]["content"] if call[1] else "")]


@pytest.mark.asyncio
async def test_rank_then_fuse_feeds_only_top_kappa() -> None:
    """5 candidates, kappa=2 → trace records all 5, prompt carries exactly 2."""
    config = _config(rank=True)
    gw = FakeGateway(_responder())
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")

    aggregator = result.trace.aggregator
    assert aggregator is not None, "an explicit formation keeps its aggregator span"

    candidates = aggregator.ranked_candidates
    # AC-3: the trace records EVERY scored candidate (5), not just the kept ones.
    assert len(candidates) == 5
    assert [c.stage_id for c in candidates] == ["worker_4", "worker_2", "worker_5", "worker_1", "worker_3"]
    assert [c.rank for c in candidates] == [1, 2, 3, 4, 5]
    assert [c.score for c in candidates] == [9.5, 8.0, 7.0, 1.0, 0.5]
    assert [c.kept for c in candidates] == [True, True, False, False, False]
    assert aggregator.rank_kappa == _KAPPA
    assert aggregator.rank_error is None
    assert aggregator.rank_model == config.defaults.default_aggregator
    assert aggregator.rank_tokens_input == 70
    assert aggregator.rank_tokens_output == 9

    # AC-2/AC-3: the aggregator's recorded input contains exactly the top-2.
    prompt = aggregator.prompt
    kept = [c for c in candidates if c.kept]
    dropped = [c for c in candidates if not c.kept]
    for candidate in kept:
        assert _worker_output(_worker_model(candidate.stage_id)) in prompt
    for candidate in dropped:
        assert _worker_output(_worker_model(candidate.stage_id)) not in prompt
    assert "[rank 1/5, score 9.5]" in prompt

    fed = f"{len(kept)} of {len(candidates)} candidates"
    print(
        f"rank-then-fuse fed {fed} to the aggregator (kappa={_KAPPA}): "
        f"kept {', '.join(c.stage_id for c in kept)}; "
        f"ranked {', '.join(f'{c.stage_id}={c.score:g}' for c in candidates)}"
    )
    assert fed == "2 of 5 candidates"


@pytest.mark.asyncio
async def test_rank_off_is_byte_identical_to_pre_ranking_behaviour() -> None:
    """Default (rank absent) merges every output and never calls a scorer."""
    config = _config(rank=False)
    gw = FakeGateway(_responder())
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")

    aggregator = result.trace.aggregator
    assert aggregator is not None
    assert aggregator.ranked_candidates == []
    assert aggregator.rank_kappa is None
    assert aggregator.rank_model == ""
    assert aggregator.rank_error is None
    # No rank tags leak into an un-ranked merge prompt.
    assert "[rank " not in aggregator.prompt
    assert _scorer_calls(gw) == []
    # The span keeps its compact prompt summary (pre-DF-CHIMERA-V2-102 trace
    # output, byte for byte); the merge call itself still carried every output.
    merge_prompts = [call for call in gw.calls if "Upstream outputs" in json.dumps(call[1])]
    assert len(merge_prompts) == 1
    assert aggregator.prompt.startswith("merge stage 'aggregator' over upstream:")
    for stage_id in _SCORES:
        assert _worker_output(_worker_model(stage_id)) in json.dumps(merge_prompts[0][1])


@pytest.mark.asyncio
async def test_scorer_failure_keeps_every_candidate_in_the_merge() -> None:
    """A failed scorer pass degrades to un-ranked merging and traces the error."""
    config = _config(rank=True)
    gw = FakeGateway(_responder(fail_scorer=True))
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")

    aggregator = result.trace.aggregator
    assert aggregator is not None
    assert aggregator.ranked_candidates == []
    assert aggregator.rank_error is not None
    assert "503" in aggregator.rank_error
    assert len(_scorer_calls(gw)) == 1, "exactly one scorer attempt, no retry storm"
    # Best-effort: no worker output was lost.
    for stage_id in _SCORES:
        assert _worker_output(_worker_model(stage_id)) in aggregator.prompt


@pytest.mark.asyncio
async def test_unparseable_scorer_answer_keeps_every_candidate() -> None:
    """A scorer that answers prose with no scores cannot silently drop outputs."""
    config = _config(rank=True)
    gw = FakeGateway(_responder(scores={}))  # {} = valid JSON, zero usable scores
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")

    aggregator = result.trace.aggregator
    assert aggregator is not None
    assert aggregator.ranked_candidates == []
    assert aggregator.rank_error == "unparseable scorer response"
    for stage_id in _SCORES:
        assert _worker_output(_worker_model(stage_id)) in aggregator.prompt


@pytest.mark.asyncio
async def test_rank_model_override_and_unknown_fallback() -> None:
    """``rank_model`` picks the scorer; an unusable alias falls back to the stage model."""
    config = _config(rank=True, rank_model="openrouter/qwen/qwen3-coder")
    gw = FakeGateway(_responder())
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")
    aggregator = result.trace.aggregator
    assert aggregator is not None
    assert aggregator.rank_model == "openrouter/qwen/qwen3-coder"
    assert [call[0] for call in _scorer_calls(gw)] == ["openrouter/qwen/qwen3-coder"]

    fallback = ChimeraConfig.model_validate(
        {
            **copy.deepcopy(CONFIG_DICT),
            "formations": {
                **copy.deepcopy(CONFIG_DICT)["formations"],
                "ranked_fanout": {
                    "workers": 5,
                    "worker_models": _WORKER_MODELS,
                    "aggregator": "default",
                    "rank": True,
                    "kappa": _KAPPA,
                    "rank_model": "no-such/model",
                },
            },
        }
    )
    gw2 = FakeGateway(_responder())
    result2 = await Engine(fallback, gw2).deliberate("Rank these five answers", "ranked_fanout")
    aggregator2 = result2.trace.aggregator
    assert aggregator2 is not None
    assert aggregator2.rank_model == fallback.defaults.default_aggregator
    assert len(aggregator2.ranked_candidates) == 5


@pytest.mark.asyncio
async def test_kappa_at_or_above_candidate_count_skips_the_scorer_pass() -> None:
    """kappa >= candidates is a no-op: no scorer call, no rank fields."""
    config = _config(rank=True, kappa=5)
    gw = FakeGateway(_responder())
    result = await Engine(config, gw).deliberate("Rank these five answers", "ranked_fanout")

    aggregator = result.trace.aggregator
    assert aggregator is not None
    assert _scorer_calls(gw) == []
    assert aggregator.ranked_candidates == []
    for stage_id in _SCORES:
        assert _worker_output(_worker_model(stage_id)) in aggregator.prompt


def test_parse_rank_scores_tolerates_real_scorer_shapes() -> None:
    """Every shape a cheap model actually emits must still rank."""
    ids = ["worker_1", "worker_2", "worker_3"]

    assert parse_rank_scores('{"scores": {"worker_1": 7, "worker_2": "8.5"}}', ids) == {
        "worker_1": 7.0,
        "worker_2": 8.5,
    }
    # Fenced, chatty, and bare-map answers.
    assert parse_rank_scores('```json\n{"worker_1": 4, "worker_3": 9}\n```', ids) == {
        "worker_1": 4.0,
        "worker_3": 9.0,
    }
    assert parse_rank_scores("Here you go: worker_2: 6.5", ids) == {"worker_2": 6.5}
    # Hallucinated candidate ids can never rank a real output.
    assert parse_rank_scores('{"scores": {"worker_9": 10}}', ids) == {}
    assert parse_rank_scores("no numbers here", ids) == {}
