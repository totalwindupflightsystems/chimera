"""Hermetic tests for ``scripts/smoke_live.py``'s provider-health reporting — DF-CHIMERA-V2-4.

Context (measured by the foreman on tick 246, not assumed).  A live run printed::

    WARNING: providers reported unhealthy by /v1/health: zai
    ...
    SMOKE PASS

``SMOKE PASS`` / exit 0 was correct — the degradation did not fail the run — but
the line read like one, and it was byte-identical for a REAL degradation
(``timeout``) and for a fresh install's missing key (``missing_credentials``), so
the operator could not tell "hardened deployment, one provider down" from "nobody
configured keys yet".  The healthy branch was worse than unhelpful: it printed
``providers: {providers_configured}/{providers_configured} healthy`` — configured
over configured — so it claimed everything was healthy regardless of the payload
(live: 9 provider entries, 1 unhealthy, printed 9/9).

``/v1/health`` already carried what the report needed: top-level
``unhealthy_providers`` plus ``details.providers.<name>.error_class``.  These
tests pin the class-aware rendering:

* C1 — keyless-only payload: informational line, NEVER the degradation warning,
  naming the providers and saying keyless is expected on a fresh install;
* C2 — real classes: one WARNING naming each provider WITH its class, and a
  ``quota`` provider surfacing the provider's own message (reset time);
* C3 — the healthy/total count comes from the payload's provider map, never from
  ``providers_configured`` (regression test for the 9/9 bug);
* C4 — exit codes unchanged (only the deliberation decides pass/fail), tests
  hermetic, script stdlib-only;
* C5 — proven-healthy counting (CH-GAP-053): an entry counts as healthy only
  with ``healthy: true`` AND a non-empty ``model_tested`` — a note-only
  provider (no models configured, nothing probed) pads the total, never the
  healthy count.

The same file covers DF-CHIMERA-V2-45 — path-scoped deployment parity.  ``main()``
used to print a bare "deployed commit X != local HEAD Y — service runs older
code" whenever the two strings differed, with no look at WHAT differed.  The
incident that filed the row had ``/health`` reporting ``0fc54d5`` while ``HEAD``
already held an 11-file ``src/`` wave; a foreman narrative read the gap as
"board-only delta, expected" and exited green.  A bookkeeping-only gap and a real
code gap are different findings, and neither may be guessed from commit subjects:

* C6 — a delta under ``src/``/``scripts/``/``tests/``/``pyproject.toml`` is
  STALE, names the changed material paths, and requires a restart or an explicit
  deferral;
* C7 — a gap touching nothing under that scope is CODE-CURRENT
  (bookkeeping/board-only) and never says the service runs older code;
* C8 — missing, ``unknown``, unresolvable, non-ancestor, git-unavailable and
  git-failure cases all classify UNVERIFIABLE with the reason, and claim no
  restart;
* C9 — the evidence is printed prominently but the deliberation still owns the
  exit code, and AGENTS.md documents the exact command and the contract.

Hermetic by construction: ``_http_json``, ``_local_head`` and ``_git_run``
are monkeypatched, so no test opens a socket, touches a live server, or spawns
``git`` — except
``test_real_git_repo_scopes_the_diff_and_the_ancestry_check``, which runs
``git`` against a throwaway repository under ``tmp_path`` (no network, no
remote) to prove the real argv shape: rev-parse resolution, the ancestry
direction, and the path-scoped diff.  Paths resolve from this file, never the
process cwd.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "smoke_live.py"
SERVER_PATH = REPO / "src" / "chimera" / "api" / "server.py"

#: The base URL every stubbed route is keyed on — never resolved, never dialled.
BASE = "http://smoke.test:8765"

#: The commit the stubbed service reports (== the stubbed local HEAD, so the
#: deployed-commit warning stays out of the assertions unless a test asks for it).
COMMIT = "abc1234"

#: A deliberate answer payload that must produce exit 0.
ANSWER_PAYLOAD: dict[str, Any] = {
    "answer": "The capital of France is Paris.",
    "request_id": "req-1",
    "trace": {"source": "dispatch"},
}


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


smoke_live = _load_module("smoke_live", SCRIPT_PATH)


# --------------------------------------------------------------------------- #
# payload + stub helpers
# --------------------------------------------------------------------------- #


def _healthy(n: int) -> dict[str, dict[str, Any]]:
    """``n`` healthy provider entries, shaped like the real ones."""
    return {f"p{index}": {"healthy": True, "model_tested": f"p{index}/model"} for index in range(n)}


def _issue(error_class: str | None, error: str | None = None, *, healthy: bool = False) -> dict[str, Any]:
    """One provider entry; ``error_class=None`` omits the field entirely."""
    entry: dict[str, Any] = {"healthy": healthy}
    if error is not None:
        entry["error"] = error
    if error_class is not None:
        entry["error_class"] = error_class
    return entry


def _details(
    providers: dict[str, Any] | None,
    *,
    providers_configured: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """A ``/v1/health`` ``details`` object."""
    configured = len(providers or {}) if providers_configured is None else providers_configured
    details: dict[str, Any] = {
        "config_loaded": True,
        "models_configured": 42,
        "providers_configured": configured,
        "commit": COMMIT,
    }
    if providers is not None:
        details["providers"] = providers
    if error is not None:
        details["error"] = error
    return details


def _v1_body(
    providers: dict[str, Any] | None,
    *,
    providers_configured: int | None = None,
    unhealthy: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """A ``/v1/health`` body: top-level ``unhealthy_providers`` + ``details``."""
    names = list(unhealthy or [])
    return {
        "status": "degraded" if names else "healthy",
        "unhealthy_providers": names,
        "details": _details(providers, providers_configured=providers_configured, error=error),
    }


class StubHTTP:
    """``_http_json`` stand-in: exact-URL routing, every call recorded."""

    def __init__(self, routes: dict[str, tuple[int, dict[str, Any]]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> tuple[int, dict[str, Any]]:
        self.calls.append((url, method, body))
        if url not in self.routes:
            raise AssertionError(f"unexpected (network) request: {method} {url}")
        return self.routes[url]

    def urls(self) -> list[str]:
        return [url for url, _, _ in self.calls]


def _routes(
    *,
    v1_body: dict[str, Any] | None = None,
    v1_status: int = 200,
    deliberate: tuple[int, dict[str, Any]] = (200, ANSWER_PAYLOAD),
    health: tuple[int, dict[str, Any]] | None = None,
) -> dict[str, tuple[int, dict[str, Any]]]:
    """The three routes ``main()`` may touch, all canned."""
    return {
        f"{BASE}/health": health or (200, {"status": "alive", "commit": COMMIT, "uptime_models": 42}),
        f"{BASE}/v1/health": (v1_status, v1_body if v1_body is not None else _v1_body(_healthy(3))),
        f"{BASE}/v1/deliberate": deliberate,
    }


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, tuple[int, dict[str, Any]]],
    *,
    git: Any = None,
) -> int:
    """Run ``main()`` against the stubbed HTTP layer; return the exit code.

    ``_git_run`` is replaced too: by default with a fake that reports git as
    UNAVAILABLE, so a test that reaches a commit gap without asking for a
    specific git behaviour gets an honest UNVERIFIABLE instead of silently
    spawning the enclosing checkout's ``git``.
    """
    stub = StubHTTP(routes)
    monkeypatch.setattr(smoke_live, "_http_json", stub)
    monkeypatch.setattr(smoke_live, "_local_head", lambda: COMMIT)
    monkeypatch.setattr(smoke_live, "_git_run", git if git is not None else FakeGit(fail="unavailable"))
    monkeypatch.setattr(sys, "argv", ["smoke_live.py", "--base-url", BASE])
    return smoke_live.main()


def _warning_lines(lines: list[str]) -> list[str]:
    """The degradation-warning lines in a rendered report."""
    return [line for line in lines if line.startswith(smoke_live.UNHEALTHY_WARNING_PREFIX)]


# --------------------------------------------------------------------------- #
# C1 — keyless providers are information, not a degradation
# --------------------------------------------------------------------------- #


def test_keyless_class_constant_matches_the_producer() -> None:
    """Drift guard: the class this script special-cases is the one src emits.

    If the producer renames ``missing_credentials``, the script would silently
    demote the message back to a WARNING (a fresh install reading as broken) —
    so the literal is pinned against the server source, at no runtime cost.
    """
    text = SERVER_PATH.read_text(encoding="utf-8")
    assert f'"{smoke_live.KEYLESS_ERROR_CLASS}"' in text, (
        f"src/chimera/api/server.py no longer emits error_class "
        f"{smoke_live.KEYLESS_ERROR_CLASS!r} — update KEYLESS_ERROR_CLASS in scripts/smoke_live.py"
    )
    assert "timeout" in text and "quota" in text


def test_keyless_only_renders_info_not_the_degradation_warning() -> None:
    """C1: the fresh-install case names the providers, and does NOT warn."""
    providers = _healthy(8)
    providers["zai"] = _issue(
        "missing_credentials", "missing-credentials: no API key resolved for provider 'zai'"
    )
    providers["google"] = _issue(
        "missing_credentials", "missing-credentials: no API key resolved for provider 'google'"
    )
    providers["deepseek"] = {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"}

    lines = smoke_live.provider_health_lines(_details(providers), ["google", "zai"])
    text = "\n".join(lines)

    assert smoke_live.UNHEALTHY_WARNING_PREFIX not in text, f"keyless providers must not warn:\n{text}"
    assert not [line for line in lines if line.startswith("WARNING")], f"no WARNING expected:\n{text}"
    info = [line for line in lines if line.startswith("INFO")]
    assert len(info) == 1, f"exactly one informational line expected:\n{text}"
    assert "zai" in info[0] and "google" in info[0], "the keyless providers must be named"
    assert "fresh install" in info[0], "the line must say keyless providers are expected on a fresh install"
    assert "deliberation" in info[0] and "proof" in info[0], (
        "the line must say the deliberation is the real proof of a working deployment"
    )
    assert "providers: 9/11 healthy" in lines, f"the count must come from the map:\n{text}"


def test_keyless_only_run_exits_zero_and_never_warns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C1/C4 at the script level: stderr/stdout carry no degradation warning, exit 0."""
    providers = _healthy(8)
    providers["zai"] = _issue("missing_credentials", "missing-credentials: no API key resolved")
    code = _run_main(monkeypatch, _routes(v1_body=_v1_body(providers, unhealthy=["zai"])))
    captured = capsys.readouterr()

    assert code == 0, captured.out
    assert "SMOKE PASS" in captured.out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX not in captured.out + captured.err
    assert "fresh install" in captured.out
    assert "zai" in captured.out


# --------------------------------------------------------------------------- #
# C2 — real classes warn, per provider, with the class
# --------------------------------------------------------------------------- #


def test_real_classes_warn_once_naming_each_provider_with_its_class() -> None:
    """C2: one WARNING, every provider named, each with its own ``error_class``."""
    providers = {
        "zai": _issue("timeout", "timeout: no response within 10.0s"),
        "openai": _issue("quota", "quota: Rate limit exceeded; reset at 2026-09-19T00:00:00Z"),
        "anthropic": _issue("auth", "auth: invalid API key"),
        "mystery": _issue(None, "provider said no"),
        "deepseek": {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"},
    }

    lines = smoke_live.provider_health_lines(_details(providers), ["anthropic", "openai", "mystery", "zai"])
    warnings = _warning_lines(lines)

    assert len(warnings) == 1, f"exactly one degradation warning expected:\n{lines}"
    warning = warnings[0]
    assert "zai [timeout]: no response within 10.0s" in warning
    assert "anthropic [auth]: invalid API key" in warning
    assert "mystery [unknown]: provider said no" in warning, "a missing error_class must read as unknown"
    assert "providers: 1/5 healthy" in lines


def test_quota_provider_surfaces_its_own_reset_message() -> None:
    """C2: the quota failure carries the provider's message, verbatim and undoubled."""
    providers = {
        "openai": _issue("quota", "quota: Rate limit exceeded; reset at 2026-09-19T00:00:00Z"),
        "deepseek": {"healthy": True},
    }

    text = "\n".join(smoke_live.provider_health_lines(_details(providers), ["openai"]))

    assert "openai [quota]" in text
    assert "reset at 2026-09-19T00:00:00Z" in text, "the provider's own reset time must surface"
    assert "quota: quota" not in text, "the class prefix must not be printed twice"


def test_class_without_error_text_still_names_the_class() -> None:
    """A class-only entry renders as ``name [class]`` with no dangling colon."""
    providers = {"zai": {"healthy": False, "error_class": "timeout"}}

    warning = _warning_lines(smoke_live.provider_health_lines(_details(providers), ["zai"]))[0]

    assert "zai [timeout]" in warning
    assert "timeout]:" not in warning


def test_mixed_payload_separates_keyless_from_degraded() -> None:
    """A payload with both cases prints both, and the keyless name stays out of the WARNING."""
    providers = {
        "google": _issue("missing_credentials", "missing-credentials: no API key resolved"),
        "zai": _issue("timeout", "timeout: no response within 10.0s"),
        "deepseek": {"healthy": True},
    }

    lines = smoke_live.provider_health_lines(_details(providers), ["google", "zai"])
    warnings = _warning_lines(lines)
    infos = [line for line in lines if line.startswith("INFO")]

    assert len(warnings) == 1 and len(infos) == 1
    assert "google" in infos[0] and "google" not in warnings[0]
    assert "zai" in warnings[0] and "zai" not in infos[0]


def test_classification_is_pure_and_sorted() -> None:
    """``classify_provider_health`` reads the payload only, in a deterministic order."""
    providers = {
        "zeta": _issue("timeout", "timeout: slow"),
        "alpha": _issue("auth", "auth: bad key"),
        "healthy_one": {"healthy": True},
        "beta": _issue("missing_credentials"),
    }

    issues = smoke_live.classify_provider_health(_details(providers))

    assert [issue.name for issue in issues] == ["alpha", "beta", "zeta"]
    assert [(issue.error_class, issue.error) for issue in issues] == [
        ("auth", "auth: bad key"),
        ("missing_credentials", ""),
        ("timeout", "timeout: slow"),
    ]
    assert smoke_live.classify_provider_health({}) == []
    assert smoke_live.classify_provider_health(None) == []  # type: ignore[arg-type]


def test_missing_healthy_flag_counts_as_unhealthy() -> None:
    """Absent evidence is not proof of health (the pre-fix filter's own semantics)."""
    issues = smoke_live.classify_provider_health(_details({"zai": {"error": "boom"}}))

    assert [(issue.name, issue.error_class) for issue in issues] == [("zai", "unknown")]


# --------------------------------------------------------------------------- #
# C3 — the count comes from the payload's provider map
# --------------------------------------------------------------------------- #


def test_eight_of_nine_prints_8_9() -> None:
    """C3: 9 provider entries, 8 healthy -> ``8/9`` (never configured/configured)."""
    providers = _healthy(8)
    providers["zai"] = _issue("timeout", "timeout: no response within 10.0s")

    lines = smoke_live.provider_health_lines(_details(providers, providers_configured=9), ["zai"])

    assert "providers: 8/9 healthy" in lines


def test_count_ignores_providers_configured() -> None:
    """C3: ``providers_configured`` says nothing about who answered — never use it."""
    providers = _healthy(9)

    text = "\n".join(smoke_live.provider_health_lines(_details(providers, providers_configured=3), []))

    assert "providers: 9/9 healthy" in text
    assert "3/3" not in text, "configured-over-configured is the bug being fixed"


def test_run_prints_the_payload_count_not_the_configured_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C3 end to end: a 9-entry payload with 1 bad provider prints ``8/9`` to stdout."""
    providers = _healthy(8)
    providers["zai"] = _issue("timeout", "timeout: no response within 10.0s")
    _run_main(monkeypatch, _routes(v1_body=_v1_body(providers, providers_configured=99, unhealthy=["zai"])))
    out = capsys.readouterr().out

    assert "providers: 8/9 healthy" in out
    assert "99/99" not in out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX in out


def test_healthy_run_prints_the_full_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The all-healthy path still prints the count, with no WARNING."""
    _run_main(monkeypatch, _routes(v1_body=_v1_body(_healthy(5))))
    out = capsys.readouterr().out

    assert "providers: 5/5 healthy" in out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX not in out


def test_note_only_providers_do_not_pad_the_healthy_count() -> None:
    """C5 (CH-GAP-053): 8 model-tested healthy + 2 note-only entries -> ``8/10``.

    A provider with no models configured was never probed — it inflates the
    total but must never pad the healthy count.
    """
    providers = _healthy(8)
    providers["empty_a"] = {"healthy": False, "note": "no models configured for provider"}
    providers["empty_b"] = {"healthy": False, "note": "no models configured for provider"}

    lines = smoke_live.provider_health_lines(_details(providers), ["empty_a", "empty_b"])

    assert "providers: 8/10 healthy" in lines


def test_proven_healthy_requires_a_model_tested() -> None:
    """C5 (CH-GAP-053) per shape: ``healthy: true`` alone is NOT proven healthy.

    A stale payload that still claims ``healthy: true`` for a note-only entry
    must not pad the count either — the flag/model conjunction is the
    contract, not membership in the issues list.
    """
    providers = {
        "real": {"healthy": True, "model_tested": "real/model"},
        "claimed": {"healthy": True, "note": "no models configured for provider"},
        "blank_model": {"healthy": True, "model_tested": "   "},
        "not_a_dict": "garbage",
    }

    lines = smoke_live.provider_health_lines(
        _details(providers),
        ["claimed", "blank_model", "not_a_dict"],
    )

    assert "providers: 1/4 healthy" in lines


# --------------------------------------------------------------------------- #
# C4 — exit codes unchanged, provider health never fails the run
# --------------------------------------------------------------------------- #


def test_degraded_providers_do_not_fail_the_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every provider unhealthy + a good deliberation = exit 0 (only the call decides)."""
    providers = {name: _issue("timeout", "timeout: no response within 10.0s") for name in _healthy(3)}

    code = _run_main(
        monkeypatch,
        _routes(v1_body=_v1_body(providers, unhealthy=sorted(providers))),
    )
    captured = capsys.readouterr()

    assert code == 0, captured.out + captured.err
    assert "SMOKE PASS" in captured.out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX in captured.out


@pytest.mark.parametrize(
    ("case", "deliberate"),
    [
        ("http_500", (500, {"detail": "boom"})),
        ("http_401", (401, {"detail": "unauthorized"})),
        ("http_422", (422, {"detail": "unknown formation"})),
        ("empty_answer", (200, {"answer": "   ", "request_id": "req-1"})),
    ],
)
def test_deliberation_failures_still_exit_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    deliberate: tuple[int, dict[str, Any]],
) -> None:
    """C4: the provider block never decides the verdict — these failures still exit 1."""
    code = _run_main(monkeypatch, _routes(deliberate=deliberate))
    captured = capsys.readouterr()

    assert code == 1, f"{case}: {captured.out}{captured.err}"
    assert "SMOKE PASS" not in captured.out


def test_health_probe_failure_still_continues(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-200 ``/v1/health`` warns and continues to the real call, exit 0."""
    code = _run_main(monkeypatch, _routes(v1_body={}, v1_status=500))
    captured = capsys.readouterr()

    assert code == 0, captured.out + captured.err
    assert "WARNING: /v1/health probe failed (status=500)" in captured.out
    assert "SMOKE PASS" in captured.out


def test_probe_error_payload_names_the_configured_providers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Server-side probe failure: no per-provider detail, so name the top-level list."""
    body = _v1_body(None, unhealthy=["zai", "openai"], error="boom")

    code = _run_main(monkeypatch, _routes(v1_body=body))
    out = capsys.readouterr().out

    assert code == 0
    assert smoke_live.UNHEALTHY_WARNING_PREFIX in out
    assert "zai, openai" in out
    assert "boom" in out
    assert "providers: 0/0 healthy" not in out, "an absent provider map must not read as healthy"


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-45 — path-scoped deployment parity (helpers)
# --------------------------------------------------------------------------- #

#: The target commit in a gap scenario — differ from COMMIT, and never resolve it
#: against the enclosing checkout.
BEHIND = "0fc54d5"

#: The 11-file wave from the incident, trimmed to what the report must name.
WAVE_PATHS = ("src/chimera/web/routes.py", "src/chimera/web/trace_viz.py")


class FakeGit:
    """Scriptable ``_git_run`` stand-in: no process is ever spawned.

    ``resolve`` maps a commit string to the full sha git would print (``None``
    for an unresolvable commit); ``ancestor`` answers ``merge-base
    --is-ancestor``; ``diff`` is the ``--name-only`` stdout.  ``fail`` simulates
    git being absent (``_git_run`` returns ``(None, "")``).  Every argv is
    recorded so a test can pin the exact command shape.
    """

    def __init__(
        self,
        *,
        resolve: dict[str, str | None] | None = None,
        ancestor: bool = True,
        ancestor_exit: int | None = None,
        diff: str = "",
        diff_exit: int = 0,
        fail: str | None = None,
    ) -> None:
        self.resolve = dict(resolve or {})
        self.ancestor = ancestor
        self.ancestor_exit = ancestor_exit
        self.diff = diff
        self.diff_exit = diff_exit
        self.fail = fail
        self.commands: list[tuple[str, ...]] = []
        self.calls = 0

    def __call__(self, args: list[str], cwd: str | None = None) -> tuple[int | None, str]:
        self.commands.append(tuple(args))
        self.calls += 1
        if self.fail:
            return None, ""
        if args[:3] == ["git", "rev-parse", "--verify"]:
            # argv is ["git", "rev-parse", "--verify", "<commit>^{commit}"], so the
            # commit is args[3] — indexing args[4] raised IndexError, which the
            # classifier correctly treats as a git failure, so EVERY diff scenario
            # silently degraded to UNVERIFIABLE and the suite never exercised the
            # STALE/CODE-CURRENT branches at all.
            commit = args[3].removesuffix("^{commit}")
            resolved = self.resolve.get(commit, None)
            return (0, resolved) if resolved else (1, "")
        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            if self.ancestor_exit is not None:
                # A git that RAN and refused with a code other than the ancestry
                # answer — the classifier must report that code, not read it as 0.
                return self.ancestor_exit, ""
            return (0 if self.ancestor else 1), ""
        if args[:2] == ["git", "diff"]:
            return self.diff_exit, self.diff if self.diff_exit == 0 else ""
        raise AssertionError(f"unexpected git command: {args}")

    def diff_commands(self) -> list[tuple[str, ...]]:
        return [command for command in self.commands if command[:2] == ("git", "diff")]


def _git_with(running: str = BEHIND, head: str = COMMIT, **kwargs: Any) -> FakeGit:
    """A ``FakeGit`` that resolves both commits, so the gap reaches the diff."""
    resolve = {str(running): _full_sha(str(running)), str(head): _full_sha(str(head))}
    resolve.update(kwargs.pop("resolve", {}))
    return FakeGit(resolve=resolve, **kwargs)


def _full_sha(commit: str) -> str:
    """The 40-char sha ``git rev-parse --verify`` would print for ``commit``.

    The classifier expands both commits before diffing, so a test that pins the
    diff RANGE must expect the expanded form, not the short spelling the caller
    passed in.
    """
    return commit.ljust(40, "0")


def _classify(git: FakeGit, running: str = BEHIND, head: str = COMMIT) -> Any:
    """Run the production classifier with the injected git runner."""
    return smoke_live.classify_deployment_parity(running, head, run=git)


def _emit(parity: Any) -> str:
    """The rendered evidence for a classification."""
    return "\n".join(smoke_live.deployment_parity_lines(parity))


# --------------------------------------------------------------------------- #
# C6 — a material code delta is STALE and names what changed
# --------------------------------------------------------------------------- #


def test_material_scope_is_exactly_the_four_entries() -> None:
    """The scope is one constant, and the documented command is built from it."""
    assert smoke_live.MATERIAL_PATHS == ("src/", "scripts/", "tests/", "pyproject.toml"), (
        "the material-code scope changed — it is the whole discriminator"
    )
    expected = "git diff --name-only <running>..<HEAD> -- " + " ".join(smoke_live.MATERIAL_PATHS)
    assert expected == smoke_live.MATERIAL_DIFF_COMMAND_TEMPLATE, (
        "the documented command and the executed scope have drifted apart"
    )


def test_code_delta_is_stale_and_names_the_material_paths() -> None:
    """C6: a non-empty scoped diff is STALE and names every changed path."""
    git = _git_with(diff="\n".join(WAVE_PATHS) + "\n")

    parity = _classify(git)

    assert parity.status == smoke_live.DEPLOY_STATUS_STALE
    assert tuple(parity.material_paths) == WAVE_PATHS, "the changed paths must be named"
    rendered = _emit(parity)
    assert "STALE" in rendered
    for path in WAVE_PATHS:
        assert path in rendered, f"{path} must appear in the evidence:\n{rendered}"
    assert "restart" in rendered.lower(), "a material gap must require a reload"


def test_stale_diff_is_path_scoped_and_never_a_shell() -> None:
    """C6: exactly one diff, with the four-entry pathspec, argv-only (no shell)."""
    git = _git_with(diff="src/chimera/web/routes.py\n")

    _classify(git)

    diffs = git.diff_commands()
    assert len(diffs) == 1, f"exactly one scoped diff expected: {git.commands}"
    command = list(diffs[0])
    assert command[0] == "git" and all(isinstance(part, str) for part in command)
    assert command[:3] == ["git", "diff", "--name-only"]
    assert command[3] == f"{_full_sha(BEHIND)}..{_full_sha(COMMIT)}", (
        f"the diff range must be the RESOLVED full shas, running..HEAD: {command}"
    )
    assert command[4] == "--"
    assert tuple(command[5:]) == smoke_live.MATERIAL_PATHS, (
        f"the diff pathspec must be the material scope exactly: {command}"
    )
    assert not any("|" in part or ";" in part or "&&" in part for part in command), (
        "no shell metacharacters may reach git"
    )


def test_stale_gap_evidence_is_prominent_and_requires_a_restart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C6 end to end: the gap is reported as STALE with an actionable requirement."""
    git = _git_with(diff="\n".join(WAVE_PATHS) + "\n")
    routes = _routes(health=(200, {"status": "alive", "commit": BEHIND, "uptime_models": 42}))

    code = _run_main(monkeypatch, routes, git=git)
    out = capsys.readouterr().out

    assert code == 0, out
    assert "STALE" in out
    assert WAVE_PATHS[0] in out
    assert "systemctl restart chimera" in out, "the reload command must be actionable"
    assert "board-only" not in out, "a material gap is not bookkeeping-only"
    assert "runs older code" not in out, "the removed generic guess must be gone"
    assert "SMOKE PASS" in out


# --------------------------------------------------------------------------- #
# C7 — a bookkeeping/board-only gap is CODE-CURRENT, never a code deployment
# --------------------------------------------------------------------------- #


def test_empty_scoped_diff_is_code_current() -> None:
    """C7: a valid ancestor gap with nothing material in it is CODE-CURRENT."""
    parity = _classify(_git_with(diff=""))

    assert parity.status == smoke_live.DEPLOY_STATUS_CODE_CURRENT
    assert tuple(parity.material_paths) == ()
    rendered = _emit(parity)
    assert "CODE-CURRENT" in rendered
    assert "runs older code" not in rendered, "an empty material diff must not claim stale code"
    assert "STALE" not in rendered


def test_bookkeeping_gap_never_warns_about_old_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C7 end to end: the board-only gap is classified, and no WARNING is printed."""
    git = _git_with(diff="")
    routes = _routes(health=(200, {"status": "alive", "commit": BEHIND, "uptime_models": 42}))

    code = _run_main(monkeypatch, routes, git=git)
    out = capsys.readouterr().out

    assert code == 0, out
    assert "CODE-CURRENT" in out
    assert "WARNING" not in out, f"a bookkeeping gap is not a warning:\n{out}"
    assert "runs older code" not in out
    assert BEHIND in out and COMMIT in out, "both commits must still be visible"


def test_equal_commits_are_current_without_a_diff() -> None:
    """C7: identical commits classify current and never shell out to git."""
    git = _git_with()

    parity = _classify(git, running=COMMIT, head=COMMIT)

    assert parity.status == smoke_live.DEPLOY_STATUS_CURRENT
    assert git.calls == 0, f"an equal commit pair needs no git at all: {git.commands}"
    rendered = _emit(parity)
    assert rendered.startswith("deployment: CURRENT"), rendered
    assert "CODE-CURRENT" not in rendered
    assert "STALE" not in rendered
    assert "runs older code" not in rendered


def test_short_and_full_spellings_of_one_commit_are_current() -> None:
    """Both names resolving to the same commit is not a gap (short vs full sha)."""
    full = "abcdef0123456789abcdef0123456789abcdef01"
    git = FakeGit(resolve={COMMIT: full, full: full})

    parity = _classify(git, running=COMMIT, head=full)

    assert parity.status == smoke_live.DEPLOY_STATUS_CURRENT
    assert not git.diff_commands(), "no diff is needed once the two names agree"


# --------------------------------------------------------------------------- #
# C8 — unknown / missing / non-ancestor / no-git all fail honestly
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("case", "running", "head", "git"),
    [
        ("missing_commit", None, COMMIT, _git_with()),
        ("unknown_commit", "unknown", COMMIT, _git_with()),
        ("missing_head", BEHIND, None, _git_with()),
        ("unknown_head", BEHIND, "unknown", _git_with()),
        ("unresolvable_running", BEHIND, COMMIT, _git_with(resolve={BEHIND: None})),
        ("unresolvable_head", BEHIND, COMMIT, _git_with(resolve={COMMIT: None})),
        ("non_ancestor", BEHIND, COMMIT, _git_with(ancestor=False)),
        ("git_unavailable", BEHIND, COMMIT, _git_with(fail="unavailable")),
    ],
)
def test_unverifiable_cases_are_unverifiable_with_a_reason(
    case: str, running: str | None, head: str | None, git: FakeGit
) -> None:
    """C8: every ambiguous shape classifies UNVERIFIABLE, with the reason, no guess."""
    parity = _classify(git, running=running, head=head)  # type: ignore[arg-type]
    rendered = _emit(parity)

    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE, f"{case}: {rendered}"
    assert "UNVERIFIABLE" in rendered, f"{case}: {rendered}"
    assert parity.reason, f"{case}: the reason must be stated: {rendered}"
    assert "STALE" not in rendered.replace("UNVERIFIABLE", ""), f"{case}: {rendered}"
    assert "CODE-CURRENT" not in rendered, f"{case}: never guess code-current either"
    assert "runs older code" not in rendered
    assert not git.diff_commands(), f"{case}: an unclassifiable gap must not diff"


def test_non_ancestor_reason_names_the_divergence() -> None:
    """C8: a rewound/diverged HEAD says so, instead of reading as a clean gap."""
    parity = _classify(_git_with(ancestor=False))

    assert "ancestor" in parity.reason.lower(), parity.reason
    assert BEHIND in parity.reason and COMMIT in parity.reason


def test_unverifiable_run_claims_no_restart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C8 end to end: no restart is claimed, and the deliberation still decides."""
    routes = _routes(health=(200, {"status": "alive", "commit": BEHIND, "uptime_models": 42}))

    code = _run_main(monkeypatch, routes, git=FakeGit(fail="unavailable"))
    out = capsys.readouterr().out

    assert code == 0, out
    assert "UNVERIFIABLE" in out
    assert "restart" not in out.lower(), f"nothing may claim a restart: {out}"
    assert "STALE" not in out and "CODE-CURRENT" not in out


def test_unknown_running_commit_is_named_in_the_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A wheel install reporting ``unknown`` is unverifiable, and says that much."""
    routes = _routes(health=(200, {"status": "alive", "commit": "unknown", "uptime_models": 2}))

    code = _run_main(monkeypatch, routes, git=_git_with())
    out = capsys.readouterr().out

    assert code == 0, out
    assert "UNVERIFIABLE" in out
    assert "unknown" in out
    assert "STALE" not in out and "CODE-CURRENT" not in out


def test_resolving_git_runner_is_bounded_and_never_raises() -> None:
    """A runner that raises is a git failure, not a crash in the operator's tool."""

    def exploding(args: list[str], cwd: str | None = None) -> tuple[int | None, str]:
        raise RuntimeError("git exploded")

    parity = _classify(exploding)  # type: ignore[arg-type]

    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE


def test_nonzero_merge_base_exit_is_reported_not_read_as_ancestor() -> None:
    """A merge-base that RAN and failed must not be mistaken for exit 0.

    ``--is-ancestor`` answers with 0/1; anything else (a corrupt object store, a
    bad pathspec, a killed git) is a git FAILURE. Reading it as 0 would fall
    through to the diff and could then report a confident STALE/CODE-CURRENT
    from evidence git never produced — the exact guessed verdict this row exists
    to eliminate.
    """
    git = _git_with(diff="src/chimera/web/routes.py\n", ancestor_exit=128)

    parity = _classify(git)

    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE, _emit(parity)
    assert "128" in parity.reason, f"the exit code must be named: {parity.reason}"
    assert not git.diff_commands(), "a failed ancestry check must not proceed to the diff"
    assert "STALE" not in _emit(parity).replace("UNVERIFIABLE", "")


def test_failed_scoped_diff_is_unverifiable_never_code_current() -> None:
    """A diff git could not run is missing evidence, not proof of no change.

    This is the sharpest branch: the diff is the ONLY thing separating STALE
    from CODE-CURRENT, so a failed diff read as "no output" would print
    CODE-CURRENT — a false all-clear, which the contract calls worse than an
    honest UNVERIFIABLE.
    """
    git = _git_with(diff_exit=128)

    parity = _classify(git)

    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE, _emit(parity)
    assert git.diff_commands(), "the diff must have been attempted"
    rendered = _emit(parity)
    assert "CODE-CURRENT" not in rendered, f"a failed diff must not read as no-change: {rendered}"
    assert "runs older code" not in rendered


# --------------------------------------------------------------------------- #
# C9 — the evidence is printed, the deliberation still decides
# --------------------------------------------------------------------------- #


def test_stale_evidence_never_decides_the_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C9: STALE + a failed deliberation still exits 1; the exit code is the call's."""
    git = _git_with(diff="src/chimera/web/routes.py\n")
    routes = _routes(
        health=(200, {"status": "alive", "commit": BEHIND, "uptime_models": 42}),
        deliberate=(500, {"detail": "boom"}),
    )

    code = _run_main(monkeypatch, routes, git=git)
    captured = capsys.readouterr()

    assert code == 1, captured.out
    assert "STALE" in captured.out, "the deployment evidence is still reported"
    assert "SMOKE PASS" not in captured.out


def test_dead_health_endpoint_still_short_circuits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-alive /health still exits 1 immediately, with no deployment verdict."""
    git = _git_with(diff="src/chimera/web/routes.py\n")
    routes = _routes(health=(200, {"status": "starting", "commit": BEHIND, "uptime_models": 0}))

    code = _run_main(monkeypatch, routes, git=git)
    captured = capsys.readouterr()

    assert code == 1, captured.out
    assert "SMOKE FAIL: /health not alive" in captured.err
    assert "deployment:" not in captured.out, "liveness is checked before parity"
    assert git.calls == 0, "a dead service needs no git evidence"


def test_real_git_repo_scopes_the_diff_and_the_ancestry_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real git runner: scoped diff, ancestry direction, no shell, no crash.

    ``FakeGit`` pins the argv the classifier builds; this test proves the argv
    means what the classifier thinks it means, against a throwaway repository
    built under ``tmp_path`` (no network, no remote, no live service).
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }

    def git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return proc.stdout.strip()

    git("init", "-q")
    (repo / "src" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base wave touching src")
    running = git("rev-parse", "--short", "HEAD")

    # A bookkeeping-only commit: nothing in the material scope changes.
    (repo / "docs" / "notes.md").write_text("board\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "chore: board bookkeeping only")
    bookkeeping_head = git("rev-parse", "HEAD")

    monkeypatch.chdir(repo)
    parity = smoke_live.classify_deployment_parity(running, bookkeeping_head, run=smoke_live._git_run)
    assert parity.status == smoke_live.DEPLOY_STATUS_CODE_CURRENT, _emit(parity)

    # A material commit: src/ changes, and now the gap is STALE.
    (repo / "src" / "mod.py").write_text("VALUE = 2\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "feat: change src code")
    material_head = git("rev-parse", "HEAD")

    parity = smoke_live.classify_deployment_parity(running, material_head, run=smoke_live._git_run)
    assert parity.status == smoke_live.DEPLOY_STATUS_STALE, _emit(parity)
    assert parity.material_paths == ("src/mod.py",), parity.material_paths

    # An unresolvable commit is unverifiable, not stale.
    parity = smoke_live.classify_deployment_parity("0" * 40, material_head, run=smoke_live._git_run)
    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE, _emit(parity)

    # Ancestry direction: HEAD is NOT an ancestor of the older commit.
    parity = smoke_live.classify_deployment_parity(material_head, running, run=smoke_live._git_run)
    assert parity.status == smoke_live.DEPLOY_STATUS_UNVERIFIABLE, _emit(parity)
    assert "ancestor" in parity.reason.lower(), parity.reason


# --------------------------------------------------------------------------- #
# C9 — the contract is documented where the foreman reads it
# --------------------------------------------------------------------------- #


def test_agents_md_documents_the_command_and_the_evidence_contract() -> None:
    """C9: AGENTS.md carries the exact commands and the STALE/current/honest rules."""
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    assert smoke_live.MATERIAL_DIFF_COMMAND_TEMPLATE in text, (
        "AGENTS.md must carry the exact path-scoped diff command a foreman runs"
    )
    assert smoke_live.ANCESTRY_COMMAND_TEMPLATE in text, (
        "AGENTS.md must carry the ancestry check the classification depends on"
    )
    for path in smoke_live.MATERIAL_PATHS:
        assert path in text, f"AGENTS.md must name the scope entry {path}"
    assert "STALE" in text, "AGENTS.md must name the stale classification"
    assert "CODE-CURRENT" in text, "AGENTS.md must name the bookkeeping-only classification"
    assert "UNVERIFIABLE" in text, "AGENTS.md must say an unclassifiable gap says so"
    assert "bookkeeping-only" in text or "board-only" in text, (
        "AGENTS.md must state that a non-material gap is not a code deployment"
    )
    assert smoke_live.RELOAD_REQUIREMENT in text, (
        "AGENTS.md must carry the same reload/deferral requirement the script prints"
    )


def test_the_three_expected_routes_are_the_only_requests(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stub raises on any other URL — this proves the script's request set."""
    stub = StubHTTP(_routes())
    monkeypatch.setattr(smoke_live, "_http_json", stub)
    monkeypatch.setattr(smoke_live, "_local_head", lambda: COMMIT)
    monkeypatch.setattr(sys, "argv", ["smoke_live.py", "--base-url", BASE])

    assert smoke_live.main() == 0
    capsys.readouterr()
    assert stub.urls() == [f"{BASE}/health", f"{BASE}/v1/health", f"{BASE}/v1/deliberate"]


# --------------------------------------------------------------------------- #
# C5 — the new report is documented where a reader looks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("doc", ["README.md", "docs/USAGE.md"])
def test_docs_document_the_class_aware_report(doc: str) -> None:
    """C5: both docs state the keyless/degraded split and who decides pass/fail."""
    text = (REPO / doc).read_text(encoding="utf-8")

    assert smoke_live.UNHEALTHY_WARNING_PREFIX in text, f"{doc} must show the degradation warning"
    assert "missing_credentials" in text, f"{doc} must name the keyless error_class"
    assert "fresh install" in text, f"{doc} must say keyless providers are expected on a fresh install"
    assert "providers_configured" in text, f"{doc} must say the count is not configured/configured"
    assert "<healthy>/<total>" in text, f"{doc} must show the count's shape"
    assert re.search(r"(never fails the run|never changes the exit code)", text), (
        f"{doc} must state that provider health never decides the exit code"
    )


# --------------------------------------------------------------------------- #
# C4 — stdlib-only, proven from the source's AST (not a grep)
# --------------------------------------------------------------------------- #


def test_script_is_stdlib_only_and_never_imports_chimera() -> None:
    """C4: the smoke test must run from a bare checkout — stdlib imports only."""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])

    assert roots, "no imports parsed — the AST scan is not testing anything"
    non_stdlib = sorted(root for root in roots if root not in sys.stdlib_module_names)
    assert not non_stdlib, f"non-stdlib imports in scripts/smoke_live.py: {non_stdlib}"
    assert "chimera" not in roots, "the smoke test must not import the chimera package at runtime"


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-27 — a slow provider is reported, but not as a degradation
# --------------------------------------------------------------------------- #


def test_slow_provider_is_information_not_a_degradation_warning() -> None:
    """A ``slow`` provider gets its own INFO line and does NOT warn.

    The server no longer calls this condition a degradation; the script must
    agree, or it would re-print the false alarm the server stopped emitting.
    The measured wait still surfaces, so the standing condition stays visible.
    """
    providers = {
        "hermes": _issue("slow", "slow: no response within 10.0s (probe waited 11.01s)"),
        "deepseek": {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"},
    }

    lines = smoke_live.provider_health_lines(_details(providers), ["hermes"])

    assert _warning_lines(lines) == [], f"a slow provider must not warn:\n{lines}"
    infos = [line for line in lines if line.startswith("INFO")]
    assert len(infos) == 1, lines
    assert "hermes [slow]" in infos[0]
    assert "probe waited 11.01s" in infos[0], "the measured wait must surface"
    assert "providers: 1/2 healthy" in lines


def test_slow_provider_never_fails_the_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: a slow-only provider block still exits 0 on a good call."""
    providers = {
        "hermes": _issue("slow", "slow: no response within 10.0s (probe waited 11.01s)"),
        "deepseek": {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"},
    }
    code = _run_main(
        monkeypatch,
        _routes(v1_body=_v1_body(providers, unhealthy=[])),
    )
    captured = capsys.readouterr()

    assert code == 0, captured.out + captured.err
    assert "SMOKE PASS" in captured.out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX not in captured.out + captured.err
    assert "hermes" in captured.out


def test_slow_and_real_class_still_warn_side_by_side() -> None:
    """The distinction survives a mixed payload: only the real failure warns."""
    providers = {
        "hermes": _issue("slow", "slow: no response within 10.0s (probe waited 11.01s)"),
        "anthropic": _issue("auth", "auth: invalid API key"),
        "deepseek": {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"},
    }

    lines = smoke_live.provider_health_lines(_details(providers), ["anthropic", "hermes"])
    warnings = _warning_lines(lines)

    assert len(warnings) == 1, lines
    assert "anthropic [auth]" in warnings[0]
    assert "hermes" not in warnings[0], "the slow provider must stay out of the WARNING"
    assert any("hermes [slow]" in line for line in lines if line.startswith("INFO"))


def test_probe_skipped_provider_is_named_as_information() -> None:
    """``probe_skipped`` is reported (the omission is visible), never a warning."""
    providers = {
        "hermes": {
            "healthy": False,
            "note": "probe_skipped: live health probe disabled for provider",
            "error_class": "probe_skipped",
        },
        "deepseek": {"healthy": True, "model_tested": "deepseek/deepseek-v4-flash"},
    }

    lines = smoke_live.provider_health_lines(_details(providers), ["hermes"])

    assert _warning_lines(lines) == [], f"a skipped probe must not warn:\n{lines}"
    infos = [line for line in lines if line.startswith("INFO")]
    assert len(infos) == 1 and "hermes" in infos[0]
    assert "health_probe: false" in infos[0]
