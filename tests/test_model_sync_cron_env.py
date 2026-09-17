"""Auto-score key-resolution tests for scripts/model_sync_cron.py — DF-CHIMERA-V2-12.

``main()`` gated its auto-score step on ``os.environ.get("DEEPSEEK_API_KEY")``,
but the scheduled runner's process environment does NOT carry that key — it
only exists in ``~/.hermes/.env``. Every scheduled run therefore printed
"⚠️  DEEPSEEK_API_KEY not set — skipping auto-score." and the LLM scoring path
never executed (observed 2026-09-17: the first run in 7 days with a real new
candidate, ``alibaba/kimi-k3``, was silently skipped and had to be hand-scored).

These tests drive the wrapper fully offline — ``subprocess.run`` mocked, the
repo root redirected to a tmp dir, the Hermes dotenv path redirected through
``CHIMERA_HERMES_DOTENV`` — and pin the resolver contract:

* the key is resolved with ``load_config()``'s precedence:
  process env > repo ``.env`` > Hermes dotenv, and the run reports which source
  supplied it (never the key value);
* a resolved key is injected into the scoring child's environment explicitly;
* a key that resolves nowhere keeps the existing skip message and clean exit;
* the zero-candidate short-circuit still runs BEFORE the key check;
* the module needs no chimera deps (it must import under a bare interpreter).

They never read the developer's real ``~/.hermes/.env``, so they pass on a
machine where that file does not exist.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
WRAPPER_PATH = REPO / "scripts" / "model_sync_cron.py"

#: Values used as the "key" in these tests. Deliberately not key-shaped so the
#: repo's secret scanner has nothing to match.
DOTENV_KEY = "dotenv-only-value-abc123"
PROCESS_KEY = "process-env-value-xyz789"

NON_ZERO_REPORT = "**Candidates:** 2 new models to review\n"
ZERO_REPORT = "**Candidates:** 0 new models to review\n"


def _load_wrapper() -> ModuleType:
    """Load scripts/model_sync_cron.py as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("model_sync_cron", WRAPPER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["model_sync_cron"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Recorder:
    """Stand-in for ``subprocess.run`` that records argv + child env."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        self.calls.append({"cmd": [str(c) for c in cmd], "env": dict(kwargs.get("env") or {})})
        return SimpleNamespace(returncode=0, stdout="mocked sync output\n", stderr="")

    @property
    def score_calls(self) -> list[dict[str, Any]]:
        """Calls whose argv forwards ``--score`` (the auto-scoring step)."""
        return [c for c in self.calls if "--score" in c["cmd"]]


class _Cron:
    """Test harness: wrapper module + redirected repo root + redirected dotenv."""

    def __init__(self, wrapper: ModuleType, repo_root: Path, dotenv: Path, recorder: _Recorder):
        self.wrapper = wrapper
        self.repo_root = repo_root
        self.dotenv = dotenv
        self.recorder = recorder

    def seed_report(self, text: str) -> Path:
        path = self.repo_root / "reports" / "latest.md"
        path.write_text(text, encoding="utf-8")
        return path

    def seed_dotenv(self, text: str) -> Path:
        self.dotenv.write_text(text, encoding="utf-8")
        return self.dotenv


@pytest.fixture
def cron(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Cron:
    """Wrapper harness with no dependency on the developer's machine state."""
    wrapper = _load_wrapper()
    repo_root = tmp_path / "repo"
    (repo_root / "reports").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    monkeypatch.setattr(wrapper, "REPO_ROOT", repo_root)

    dotenv = tmp_path / "hermes-dotenv" / ".env"
    dotenv.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(wrapper.HERMES_DOTENV_ENV, str(dotenv))

    monkeypatch.delenv(wrapper.SCORE_KEY_ENV, raising=False)

    recorder = _Recorder()
    monkeypatch.setattr(subprocess, "run", recorder.run)
    return _Cron(wrapper, repo_root, dotenv, recorder)


# --- (a) dotenv supplies the key -> scoring runs ----------------------------- #


def test_dotenv_key_runs_scoring_and_names_its_source(cron: _Cron, capsys: Any) -> None:
    """Key absent from the process env, present in the dotenv -> scoring runs."""
    cron.seed_dotenv(f"# hermes fleet keys\nOTHER_KEY=unused\nDEEPSEEK_API_KEY={DOTENV_KEY}\n")
    cron.seed_report(NON_ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert cron.recorder.score_calls, f"--score was never forwarded; calls={cron.recorder.calls}"
    child_env = cron.recorder.score_calls[0]["env"]
    assert child_env["DEEPSEEK_API_KEY"] == DOTENV_KEY
    # The run reports the SOURCE, never the key value.
    assert f"DEEPSEEK_API_KEY resolved from {cron.dotenv}" in out
    assert DOTENV_KEY not in out
    assert "skipping auto-score" not in out
    # The diff step still runs first, un-scored.
    assert "--score" not in cron.recorder.calls[0]["cmd"]


def test_dotenv_key_is_used_when_repo_env_lacks_it(cron: _Cron, capsys: Any) -> None:
    """A repo .env without the key falls through to the Hermes dotenv file."""
    (cron.repo_root / ".env").write_text("OPENROUTER_API_KEY=unrelated\n", encoding="utf-8")
    cron.seed_dotenv(f"DEEPSEEK_API_KEY={DOTENV_KEY}\n")
    cron.seed_report(NON_ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert cron.recorder.score_calls
    assert cron.recorder.score_calls[0]["env"]["DEEPSEEK_API_KEY"] == DOTENV_KEY
    assert f"DEEPSEEK_API_KEY resolved from {cron.dotenv}" in out


# --- (b) process env keeps precedence --------------------------------------- #


def test_process_env_wins_over_stale_dotenv(
    cron: _Cron, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key in the process env beats a different (stale) dotenv value."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", PROCESS_KEY)
    cron.seed_dotenv(f"DEEPSEEK_API_KEY={DOTENV_KEY}\n")
    cron.seed_report(NON_ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert cron.recorder.score_calls
    child_env = cron.recorder.score_calls[0]["env"]
    assert child_env["DEEPSEEK_API_KEY"] == PROCESS_KEY
    assert child_env["DEEPSEEK_API_KEY"] != DOTENV_KEY
    assert f"DEEPSEEK_API_KEY resolved from {cron.wrapper.PROCESS_ENV_SOURCE}" in out
    assert PROCESS_KEY not in out
    assert DOTENV_KEY not in out


def test_repo_dotenv_wins_over_hermes_dotenv(cron: _Cron, capsys: Any) -> None:
    """Precedence inside the file tier: repo .env beats the Hermes dotenv."""
    (cron.repo_root / ".env").write_text(f"DEEPSEEK_API_KEY={PROCESS_KEY}\n", encoding="utf-8")
    cron.seed_dotenv(f"DEEPSEEK_API_KEY={DOTENV_KEY}\n")
    cron.seed_report(NON_ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert cron.recorder.score_calls
    assert cron.recorder.score_calls[0]["env"]["DEEPSEEK_API_KEY"] == PROCESS_KEY
    assert f"DEEPSEEK_API_KEY resolved from {cron.repo_root / '.env'}" in out


# --- (c) key nowhere -> unchanged skip behaviour ----------------------------- #


def test_key_available_nowhere_skips_and_exits_cleanly(cron: _Cron, capsys: Any) -> None:
    """An empty dotenv + no process env keeps the skip branch and a clean exit."""
    cron.seed_dotenv("# no keys here\n")
    cron.seed_report(NON_ZERO_REPORT)

    result = cron.wrapper.main()  # must not raise / SystemExit
    out = capsys.readouterr().out

    assert result is None
    assert "DEEPSEEK_API_KEY not set — skipping auto-score." in out
    assert cron.recorder.score_calls == []
    # The diff step still ran.
    assert len(cron.recorder.calls) == 1


def test_missing_dotenv_file_skips_cleanly(cron: _Cron, capsys: Any) -> None:
    """No dotenv file at all behaves like an empty one (no crash)."""
    assert not cron.dotenv.exists()
    cron.seed_report(NON_ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert "DEEPSEEK_API_KEY not set — skipping auto-score." in out
    assert cron.recorder.score_calls == []


# --- (d) zero candidates short-circuits before the key check ----------------- #


def test_zero_candidates_short_circuits_before_key_check(
    cron: _Cron, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With 0 new models the run stops before scoring, even when the key resolves."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", PROCESS_KEY)
    cron.seed_dotenv(f"DEEPSEEK_API_KEY={DOTENV_KEY}\n")
    cron.seed_report(ZERO_REPORT)

    cron.wrapper.main()
    out = capsys.readouterr().out

    assert cron.recorder.score_calls == []
    assert "No new models found. Done." in out
    assert "resolved from" not in out


# --- resolver unit contracts ------------------------------------------------- #


def test_hermes_dotenv_path_defaults_to_home_and_honours_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Hermes dotenv path is home-resolved, never a hardcoded absolute path."""
    wrapper = _load_wrapper()

    monkeypatch.delenv(wrapper.HERMES_DOTENV_ENV, raising=False)
    assert wrapper._hermes_dotenv_path() == Path("~/.hermes/.env").expanduser()

    monkeypatch.setenv(wrapper.HERMES_DOTENV_ENV, "~/alt/hermes.env")
    assert wrapper._hermes_dotenv_path() == Path("~").expanduser() / "alt" / "hermes.env"

    monkeypatch.setenv(wrapper.HERMES_DOTENV_ENV, "/tmp/alt-hermes.env")
    assert wrapper._hermes_dotenv_path() == Path("/tmp/alt-hermes.env")


def test_parse_dotenv_tolerates_quotes_comments_and_whitespace(cron: _Cron) -> None:
    """The local parser mirrors chimera.config._load_hermes_dotenv."""
    cron.seed_dotenv(
        "# a comment\n"
        "\n"
        "   \n"
        '  DEEPSEEK_API_KEY = "quoted-value"  \n'
        "SINGLE='single-quoted'\n"
        "NO_EQUALS_LINE\n"
        "TRAILING=value=with=equals\n"
        "EMPTY=\n"
    )
    parsed = cron.wrapper._parse_dotenv(cron.dotenv)

    assert parsed["DEEPSEEK_API_KEY"] == "quoted-value"
    assert parsed["SINGLE"] == "single-quoted"
    assert parsed["TRAILING"] == "value=with=equals"
    assert parsed["EMPTY"] == ""
    assert "NO_EQUALS_LINE" not in parsed


def test_resolve_score_key_returns_empty_pair_when_absent(cron: _Cron) -> None:
    """Nothing resolvable -> ("", "") so the caller's falsy check stays simple."""
    cron.seed_dotenv("DEEPSEEK_API_KEY=\nOTHER=x\n")
    assert cron.wrapper._resolve_score_key() == ("", "")


# --- source invariants (criteria D + E) -------------------------------------- #


def test_no_hardcoded_absolute_home_path_in_wrapper() -> None:
    """Criterion D: no /home/<user> (or any absolute home) path in the source."""
    source = WRAPPER_PATH.read_text(encoding="utf-8")
    assert not re.search(r"/home/[A-Za-z0-9_.-]+", source), "hardcoded home path in wrapper"


def test_no_top_level_chimera_import() -> None:
    """Criterion E: the wrapper must not import chimera at module level."""
    tree = ast.parse(WRAPPER_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("chimera") for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or not node.module.startswith("chimera")


def test_wrapper_imports_under_bare_interpreter(tmp_path: Path) -> None:
    """Criterion E, dynamically: import it with site-packages disabled (-S)."""
    probe = tmp_path / "probe_import.py"
    probe.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('wrapper', {str(WRAPPER_PATH)!r})\n"
        "assert spec is not None and spec.loader is not None\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "assert hasattr(mod, 'main') and hasattr(mod, '_resolve_score_key')\n"
        "assert 'chimera' not in sys.modules\n"
        "print('BARE_IMPORT_OK')\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-S", str(probe)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )

    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert "BARE_IMPORT_OK" in proc.stdout
