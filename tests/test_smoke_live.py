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
  hermetic, script stdlib-only.

Hermetic by construction: ``_http_json`` and ``_local_head`` are monkeypatched, so
no test opens a socket, spawns ``git``, or touches a live server.  Paths resolve
from this file, never the process cwd.
"""

from __future__ import annotations

import ast
import importlib.util
import re
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
) -> int:
    """Run ``main()`` against the stubbed HTTP layer; return the exit code."""
    stub = StubHTTP(routes)
    monkeypatch.setattr(smoke_live, "_http_json", stub)
    monkeypatch.setattr(smoke_live, "_local_head", lambda: COMMIT)
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


def test_keyless_only_run_exits_zero_and_never_warns(monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
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

    text = "\n".join(
        smoke_live.provider_health_lines(_details(providers, providers_configured=3), [])
    )

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


def test_healthy_run_prints_the_full_count(monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    """The all-healthy path still prints the count, with no WARNING."""
    _run_main(monkeypatch, _routes(v1_body=_v1_body(_healthy(5))))
    out = capsys.readouterr().out

    assert "providers: 5/5 healthy" in out
    assert smoke_live.UNHEALTHY_WARNING_PREFIX not in out


# --------------------------------------------------------------------------- #
# C4 — exit codes unchanged, provider health never fails the run
# --------------------------------------------------------------------------- #


def test_degraded_providers_do_not_fail_the_run(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
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


def test_health_probe_failure_still_continues(monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
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


def test_deployed_commit_warning_is_untouched(monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    """The pre-existing staleness warning still fires (unchanged behaviour)."""
    stub = StubHTTP(_routes(v1_body=_v1_body(_healthy(2))))
    monkeypatch.setattr(smoke_live, "_http_json", stub)
    monkeypatch.setattr(smoke_live, "_local_head", lambda: "0000000")
    monkeypatch.setattr(sys, "argv", ["smoke_live.py", "--base-url", BASE])

    code = smoke_live.main()
    out = capsys.readouterr().out

    assert code == 0
    assert f"WARNING: deployed commit {COMMIT} != local HEAD 0000000" in out
    assert "providers: 2/2 healthy" in out


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
