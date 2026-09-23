"""Score-from-file + unambiguous cron summary tests — DF-CHIMERA-V2-37.

Two defects this pins down:

1. ``model_sync_cron.py`` step 3 re-ran ``model_sync.py --diff --score`` after
   step 1 had already consumed the diff (``--diff`` marks candidates seen), so
   step 3's own diff was EMPTY and its stdout printed
   ``Candidates: 0 new models across 13 providers`` directly beneath a report
   whose own header said ``**Candidates:** 5 new models``. Worse, ``--score``'s
   top-5-by-recency selection ran against that empty set, so a genuinely new
   find with an old ``release_date`` could never be scored.

2. The wrapper's final stdout could contradict the report file it had just
   written.

The fix: step 1 saves its diff set as JSON (``--diff-json``), step 3 scores
exactly that saved set (``--score-from <file>``, standalone, no cache pass),
and the wrapper ends with one parsed-from-the-file summary line
``Report: reports/latest.md — N new models``.

All tests are offline: the scoring LLM call is monkeypatched, no network, no
real key, no real cache.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"
WRAPPER_PATH = REPO / "scripts" / "model_sync_cron.py"

#: Fixed "now" for recency fixtures — an OLD release_date is 400 days back.
NOW = time.time()
OLD_TS = NOW - 400 * 86400

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


model_sync = _load_module("model_sync_score_from", SYNC_PATH)


def _cand(
    chimera_id: str,
    recency_score: float = 70.0,
    recency_ts: float | None = NOW,
    description: str = "a candidate",
) -> dict[str, Any]:
    """One candidate dict in the shape ``scan_models_dev()`` produces."""
    model_id = chimera_id.split("/", 1)[1] if "/" in chimera_id else chimera_id
    provider = chimera_id.split("/", 1)[0] if "/" in chimera_id else "unknown"
    return {
        "model_id": model_id,
        "chimera_id": chimera_id,
        "family": "",
        "description": description,
        "input_cost_mtok": None,
        "output_cost_mtok": None,
        "input_per_1k": None,
        "output_per_1k": None,
        "recency_score": recency_score,
        "recency_ts": recency_ts,
        "provider": provider,
    }


# --- model_sync.py --score-from (standalone) --------------------------------- #


class TestScoreFromStandalone:
    """``model_sync.py --score-from <file>`` scores exactly the file's ids."""

    def _seed_diff(self, tmp_path: Path) -> Path:
        diff_file = tmp_path / "diff.json"
        diff_file.write_text(
            json.dumps(
                {
                    "stepfun": [_cand("stepfun/step-5-preview", recency_score=100.0, recency_ts=NOW - 86400)],
                    "zhipuai": [
                        _cand(
                            "zhipuai/glm-5-legacy",
                            recency_score=30.0,
                            recency_ts=OLD_TS,
                            description="old release_date find",
                        )
                    ],
                }
            ),
            encoding="utf-8",
        )
        return diff_file

    def test_scores_exactly_the_ids_in_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """The saved diff set IS the scoring input — including the old-date find."""
        diff_file = self._seed_diff(tmp_path)
        captured: dict[str, str] = {}

        def fake_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
            captured["prompt"] = prompt
            captured["key"] = api_key
            return {"models": []}

        monkeypatch.setattr(model_sync, "_score_llm_reply", fake_reply)
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--score-from", str(diff_file)])

        model_sync.main()

        prompt = captured["prompt"]
        assert "stepfun/step-5-preview" in prompt
        # THE REGRESSION: a candidate with an OLD release_date that step 1 found
        # is scored — under the old flow the re-derived diff was empty and it
        # never reached the scorer.
        assert "zhipuai/glm-5-legacy" in prompt
        assert "old release_date find" in prompt
        # An id NOT in the file never reaches the prompt.
        assert "openai/some-other-model" not in prompt
        assert captured["key"] == TEST_KEY

    def test_does_not_touch_the_cache_or_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """--score-from is standalone: no scan_all() pass, so no cache refresh."""

        def forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("scan_all() must not run for --score-from")

        monkeypatch.setattr(model_sync, "scan_all", forbidden)
        diff_file = self._seed_diff(tmp_path)
        monkeypatch.setattr(model_sync, "_score_llm_reply", lambda *a, **k: {"models": []})
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--score-from", str(diff_file)])

        model_sync.main()  # must not raise
        assert "ERROR" not in capsys.readouterr().out

    def test_missing_file_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--score-from", str(tmp_path / "nope.json")])
        with pytest.raises(SystemExit) as excinfo:
            model_sync.main()
        assert excinfo.value.code == 2

    def test_malformed_file_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--score-from", str(bad)])
        with pytest.raises(SystemExit) as excinfo:
            model_sync.main()
        assert excinfo.value.code == 2

    def test_empty_diff_file_makes_no_llm_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        empty = tmp_path / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        calls: list[str] = []

        monkeypatch.setattr(
            model_sync,
            "_score_llm_reply",
            lambda *a, **k: calls.append("called") or {"models": []},
        )
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--score-from", str(empty)])

        model_sync.main()
        assert calls == []
        assert "nothing to score" in capsys.readouterr().out


# --- model_sync.py --diff-json (step 1 saves its diff set) ------------------- #


class TestDiffJson:
    def test_diff_json_is_the_saved_new_find_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """--diff-json writes exactly the NEW finds (seen ids excluded)."""
        seen_path = tmp_path / "seen.json"
        seen_path.write_text(json.dumps(["zhipuai/already-seen"]), encoding="utf-8")

        candidates = {
            "zhipuai": [
                _cand("zhipuai/already-seen"),
                _cand("zhipuai/glm-5-legacy", recency_score=30.0, recency_ts=OLD_TS),
            ],
            "stepfun": [_cand("stepfun/step-5-preview", recency_score=100.0)],
        }
        monkeypatch.setattr(
            model_sync,
            "scan_all",
            lambda: (candidates, [], [], {"core": [], "reseller": [], "out_of_scope": 0}),
        )
        monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)

        out_json = tmp_path / "out" / "diff.json"
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--diff", "--diff-json", str(out_json)])
        model_sync.main()

        saved = json.loads(out_json.read_text(encoding="utf-8"))
        assert set(saved.keys()) == {"zhipuai", "stepfun"}
        saved_ids = [m["chimera_id"] for models in saved.values() for m in models]
        assert sorted(saved_ids) == ["stepfun/step-5-preview", "zhipuai/glm-5-legacy"]
        assert "zhipuai/already-seen" not in saved_ids
        # The old-date candidate is carried verbatim (recency fields intact).
        legacy = next(
            m for models in saved.values() for m in models if m["chimera_id"] == "zhipuai/glm-5-legacy"
        )
        assert legacy["recency_ts"] == OLD_TS


# --- backward compat: --diff and --diff --score still parse and behave ------- #


class TestBackwardCompat:
    def test_diff_argv_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        monkeypatch.setattr(
            model_sync, "scan_all", lambda: ({}, [], [], {"core": [], "reseller": [], "out_of_scope": 0})
        )
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--diff"])

        model_sync.main()  # argparse surface unchanged: parses and runs
        assert "Chimera Model Sync" in capsys.readouterr().out

    def test_diff_score_argv_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        candidates = {"stepfun": [_cand("stepfun/step-5-preview", recency_score=100.0)]}
        monkeypatch.setattr(
            model_sync,
            "scan_all",
            lambda: (candidates, [], [], {"core": [], "reseller": [], "out_of_scope": 0}),
        )
        scored_with: list[dict[str, Any]] = []
        monkeypatch.setattr(model_sync, "_llm_score_candidates", lambda cands: scored_with.append(cands))
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)
        monkeypatch.setattr(sys, "argv", ["model_sync.py", "--diff", "--score"])

        model_sync.main()

        # Exactly one scoring call, with the scanned candidates (standalone
        # --diff --score behaviour unchanged).
        assert len(scored_with) == 1
        assert scored_with[0] == candidates
        assert "Chimera Model Sync" in capsys.readouterr().out


# --- cron wrapper: no contradiction, unambiguous summary --------------------- #


class _PoisonRecorder:
    """subprocess.run stand-in whose outputs mirror the REAL failure shape.

    A bare ``--diff`` re-run WITHOUT ``--output`` (the old step 3) prints the
    plain-text summary line ``Candidates: 0 new models ...`` — that is the
    poison string. Step 1 (with ``--output``) only prints "Report saved to ...".
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, cmd: list[Any], **kwargs: Any) -> SimpleNamespace:
        cmd_s = [str(c) for c in cmd]
        self.calls.append(cmd_s)
        if "--score-from" in cmd_s:
            return SimpleNamespace(returncode=0, stdout="SCORED\n", stderr="")
        if "--output" in cmd_s:
            return SimpleNamespace(returncode=0, stdout="Report saved to latest.md\n", stderr="")
        # Bare --diff (re-)run without --output: the old step 3's empty diff.
        return SimpleNamespace(
            returncode=0, stdout="Candidates: 0 new models across 13 providers\n", stderr=""
        )


FIVE_REPORT = "# Chimera Model Sync Report\n\n**Candidates:** 5 new models across 13 providers\n"
ZERO_REPORT = "**Candidates:** 0 new models across 13 providers\n"


@pytest.fixture
def cron(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path, _PoisonRecorder]:
    wrapper = _load_module("model_sync_cron_df37", WRAPPER_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "reports").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    monkeypatch.setattr(wrapper, "REPO_ROOT", repo_root)
    monkeypatch.delenv(wrapper.SCORE_KEY_ENV, raising=False)

    dotenv = tmp_path / "dotenv" / ".env"
    dotenv.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(wrapper.HERMES_DOTENV_ENV, str(dotenv))

    recorder = _PoisonRecorder()
    monkeypatch.setattr(wrapper.subprocess, "run", recorder.run)
    return wrapper, repo_root, recorder


class TestCronWrapper:
    def test_step3_scores_saved_diff_and_never_prints_zero_line(
        self, cron: tuple[ModuleType, Path, _PoisonRecorder], monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """THE contradiction scenario: report says 5, stdout must not say 0."""
        wrapper, repo_root, recorder = cron
        (repo_root / "reports" / "latest.md").write_text(FIVE_REPORT, encoding="utf-8")
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        wrapper.main()
        out = capsys.readouterr().out

        # The old bug: step 3's empty --diff printed "Candidates: 0 new models"
        # right under the report. Must never appear again.
        assert "Candidates: 0 new models" not in out
        # Step 3 scores the SAVED diff file, it does not re-run --diff.
        score_calls = [c for c in recorder.calls if "--score-from" in c]
        assert len(score_calls) == 1, f"calls={recorder.calls}"
        assert "--diff" not in score_calls[0]
        assert "--score" not in score_calls[0]  # no legacy --diff --score either
        # Exactly two subprocess calls: step 1 diff (with --diff-json), step 3 score-from.
        assert len(recorder.calls) == 2
        assert "--diff-json" in recorder.calls[0]

    def test_summary_line_is_parsed_from_the_report_file(
        self, cron: tuple[ModuleType, Path, _PoisonRecorder], monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """The final summary states what the REPORT contains, not the child's stdout."""
        wrapper, repo_root, _ = cron
        (repo_root / "reports" / "latest.md").write_text(FIVE_REPORT, encoding="utf-8")
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        wrapper.main()
        out = capsys.readouterr().out

        assert "Report: reports/latest.md — 5 new models" in out
        # The poisoned child stdout ("Candidates: 0 ...") must not be echoed anywhere.
        assert "0 new models" not in out

    def test_bailout_path_also_prints_the_summary(
        self, cron: tuple[ModuleType, Path, _PoisonRecorder], monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        wrapper, repo_root, recorder = cron
        (repo_root / "reports" / "latest.md").write_text(ZERO_REPORT, encoding="utf-8")

        wrapper.main()
        out = capsys.readouterr().out

        assert "Report: reports/latest.md — 0 new models" in out
        assert "No new models found. Done." in out
        assert len(recorder.calls) == 1  # step 3 never runs on empty days

    def test_no_key_still_summarizes(
        self, cron: tuple[ModuleType, Path, _PoisonRecorder], capsys: Any
    ) -> None:
        wrapper, repo_root, recorder = cron
        (repo_root / "reports" / "latest.md").write_text(FIVE_REPORT, encoding="utf-8")

        wrapper.main()
        out = capsys.readouterr().out

        assert "DEEPSEEK_API_KEY not set — skipping auto-score." in out
        assert "Report: reports/latest.md — 5 new models" in out
        assert len(recorder.calls) == 1  # only step 1; no scoring, no empty re-diff
