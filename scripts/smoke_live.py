#!/usr/bin/env python3
"""Live end-to-end smoke test for a deployed Chimera deliberation service.

Runs a REAL deliberation against a running `chimera serve` instance and
proves the README promise ("one API call, a team of models, one answer")
still works: workers were dispatched, an aggregator merged them, and the
client received a usable merged answer.

This is the cheap pre-flight check for provider/auth/format regressions
(INT-ZAI-001 class): /v1/health can say "alive" while the first real call
fails. This script is that first real call, automated.

The provider-health report is class-aware (DF-CHIMERA-V2-4). Providers with no
configured API key (``error_class: missing_credentials``) are reported as INFO —
they are expected on a fresh install; a provider whose probe never landed inside
the budget (``slow``, DF-CHIMERA-V2-27) and one whose live probe is disabled
(``probe_skipped``) are INFO too, since neither measured a failure; while every
other class (``timeout``, ``auth``, ``quota``, ``api``, ``unknown``) warns with
its class and, for a quota failure, the provider's own reset-time message.
NEITHER case changes the exit code: only the deliberation decides pass/fail.

Exit codes:
    0 — merged answer received and non-empty
    1 — deliberation failed (clear, actionable diagnostics printed)
    2 — usage/config error

Usage:
    python scripts/smoke_live.py                 # default: localhost:8765, formation=simple
    python scripts/smoke_live.py --formation auto
    python scripts/smoke_live.py --base-url http://host:port
    CHIMERA_API_KEY=... python scripts/smoke_live.py   # when auth is enabled

Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import NamedTuple

DEFAULT_BASE_URL = "http://localhost:8765"
DEFAULT_PROMPT = "What is the capital of France? Answer in one short sentence."
SMOKE_FORMATION = "simple"  # deterministic 2-worker + aggregator pipeline, cheap

#: ``error_class`` meaning "no API key resolved for this provider".  A fresh
#: install legitimately has these, so they are INFORMATION, not a degradation.
KEYLESS_ERROR_CLASS = "missing_credentials"

#: ``error_class`` meaning "the probe never answered inside the budget"
#: (DF-CHIMERA-V2-27).  Nothing was measured about the provider beyond its
#: latency, so — like keyless — this is INFORMATION rather than a degradation:
#: it is reported on its own line with the measured wait, and it never decides
#: the exit code.  A provider that failed a DIFFERENT way (connection refused,
#: 5xx, auth, quota) still warns.
SLOW_ERROR_CLASS = "slow"

#: ``error_class`` meaning "the live probe is disabled for this provider"
#: (``providers.<name>.health_probe: false``, DF-CHIMERA-V2-27).  An operator
#: choice, not a defect — reported as information so the omission is visible.
PROBE_SKIPPED_ERROR_CLASS = "probe_skipped"

#: The degradation warning's prefix, as one constant: the keyless path must NOT
#: emit it, and a literal in two places is how the two cases drift back into the
#: identical wording this script is being fixed for.
UNHEALTHY_WARNING_PREFIX = "WARNING: providers reported unhealthy by /v1/health"


class ProviderIssue(NamedTuple):
    """One unhealthy provider as reported by ``/v1/health``.

    ``error_class`` is the machine-readable reason (``missing_credentials``,
    ``timeout``, ``auth``, ``quota``, ``api`` — or ``unknown`` when the payload
    omits it); ``error`` is the provider's own text when the payload carries it.
    """

    name: str
    error_class: str = "unknown"
    error: str = ""


def classify_provider_health(details: dict) -> list[ProviderIssue]:
    """Unhealthy providers from a ``/v1/health`` ``details`` payload.

    Pure: reads ``details["providers"][<name>]`` and nothing else — no I/O, no
    config, no network.  An entry is unhealthy when it says ``healthy: false``
    (or omits ``healthy``: absent evidence is not proof of health).  The result
    is sorted by provider name so the report is deterministic.
    """
    providers = details.get("providers") if isinstance(details, dict) else None
    if not isinstance(providers, dict):
        return []
    issues: list[ProviderIssue] = []
    for name, entry in providers.items():
        info = entry if isinstance(entry, dict) else {}
        if info.get("healthy"):
            continue
        issues.append(
            ProviderIssue(
                name=str(name),
                error_class=str(info.get("error_class") or "unknown"),
                error=str(info.get("error") or ""),
            )
        )
    return sorted(issues, key=lambda issue: issue.name)


def _message_without_class_prefix(error: str, error_class: str) -> str:
    """The provider's own message, without ``/v1/health``'s ``<class>: `` prefix.

    The producer writes ``error`` as ``f"{error_class}: {exc}"``, so printing the
    class beside the raw text would read ``zai [timeout]: timeout: no response``.
    Only a literal leading ``<class>:`` (either separator spelling) is removed; a
    free-text provider message is returned unchanged.
    """
    text = (error or "").strip()
    for spelling in (error_class, error_class.replace("_", "-"), error_class.replace("-", "_")):
        head = f"{spelling}:"
        if spelling and text.lower().startswith(head.lower()):
            return text[len(head) :].strip()
    return text


def provider_health_lines(details: dict, unhealthy_providers: list[str] | None = None) -> list[str]:
    """The provider-health report for a ``/v1/health`` payload, split by MEANING.

    Three cases that used to print identical wording are different findings:

    * ``missing_credentials`` — no API key resolved for the provider.  Expected
      on a fresh install, so it is an INFO line: the deliberation that follows is
      the actual proof this deployment works.
    * ``slow`` (DF-CHIMERA-V2-27) — the server's probe never landed inside the
      budget, so nothing about the provider was measured except its latency.
      Also an INFO line naming the measured wait: it is a standing condition to
      be aware of, not a degradation to act on.
    * ``probe_skipped`` — the operator disabled the live probe for that
      provider.  INFO for the same reason: an explicit choice, and the line
      keeps the omission visible.
    * every other class (``timeout``, ``auth``, ``quota``, ``api``, ``unknown``
      …) — a real degradation, so it is a WARNING naming each provider with its
      class.  A ``quota`` provider also surfaces its own message (reset time)
      when the payload carries it in ``error``.

    The healthy/total count is computed from the payload's provider map — never
    from ``providers_configured``, which counts CONFIGURED providers and says
    nothing about whether any of them answered.  Within the map, an entry only
    counts as healthy when the payload proves it: ``healthy: true`` AND a
    non-empty ``model_tested`` (CH-GAP-053).  Note-only entries (no models
    configured, so nothing was probed) are ``healthy: false`` since the server
    made that honest; the conjunction keeps the count right even against an
    older payload that still claims ``healthy: true`` for one.  Pure:
    rendering only, no I/O, and no influence on the exit code (``main`` owns
    that).
    """
    details = details if isinstance(details, dict) else {}
    providers = details.get("providers")
    if not isinstance(providers, dict) or not providers:
        # No per-provider detail at all: the probe itself failed SERVER-side.  In
        # that case /v1/health names every configured provider in
        # `unhealthy_providers` (none was proven healthy) and puts the reason in
        # `details.error` — report that instead of claiming a healthy count.
        names = (
            [str(name) for name in unhealthy_providers]
            if isinstance(unhealthy_providers, (list, tuple))
            else []
        )
        if not names:
            return ["providers: no per-provider health data in the /v1/health response"]
        reason = str(details.get("error") or "").strip()
        suffix = f": {reason}" if reason else ""
        return [
            f"{UNHEALTHY_WARNING_PREFIX} (no per-provider detail, error_class "
            f"unknown): {', '.join(names)}{suffix}"
        ]

    issues = classify_provider_health(details)
    # CH-GAP-053: healthy = proven healthy (flag true AND a model actually
    # tested), not merely "not in the issues list".  A note-only entry (no
    # models configured) proves nothing and must not pad the count.
    proven_healthy = sum(
        1
        for entry in providers.values()
        if isinstance(entry, dict) and entry.get("healthy") and str(entry.get("model_tested") or "").strip()
    )
    lines = [f"providers: {proven_healthy}/{len(providers)} healthy"]

    keyless = [issue.name for issue in issues if issue.error_class == KEYLESS_ERROR_CLASS]
    if keyless:
        lines.append(
            "INFO: providers without a configured API key "
            f"(expected on a fresh install): {', '.join(keyless)} — the "
            "deliberation below is the actual proof this deployment works."
        )

    # DF-CHIMERA-V2-27: a provider whose probe never landed inside the budget
    # was reported by the server as `slow`, not as a failure — nothing about
    # the provider was measured except its latency. Like the keyless case it
    # is INFORMATION: reported (so the standing condition stays visible) but
    # never dressed as a degradation the operator must act on.
    slow = [issue.name for issue in issues if issue.error_class == SLOW_ERROR_CLASS]
    if slow:
        names = []
        for issue in issues:
            if issue.error_class != SLOW_ERROR_CLASS:
                continue
            message = _message_without_class_prefix(issue.error, issue.error_class)
            names.append(f"{issue.name} [{issue.error_class}]" + (f": {message}" if message else ""))
        lines.append(
            "INFO: providers slower than the probe budget (not a failure — "
            "the probe never landed; a real call may still work): " + "; ".join(names)
        )

    skipped = [issue.name for issue in issues if issue.error_class == PROBE_SKIPPED_ERROR_CLASS]
    if skipped:
        lines.append(
            "INFO: providers whose live health probe is disabled "
            f"(health_probe: false): {', '.join(skipped)} — status and this "
            "report say nothing about them."
        )

    degraded = [
        issue
        for issue in issues
        if issue.error_class
        not in (
            KEYLESS_ERROR_CLASS,
            SLOW_ERROR_CLASS,
            PROBE_SKIPPED_ERROR_CLASS,
        )
    ]
    if degraded:
        rendered = []
        for issue in degraded:
            message = _message_without_class_prefix(issue.error, issue.error_class)
            rendered.append(f"{issue.name} [{issue.error_class}]" + (f": {message}" if message else ""))
        lines.append(f"{UNHEALTHY_WARNING_PREFIX}: " + "; ".join(rendered))
    return lines


def _http_json(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict]:
    """Send an HTTP request and return (status, parsed JSON body)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"detail": raw}


def _local_head() -> str | None:
    """Best-effort local git HEAD (short). None when not a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return out or None
    except Exception:
        return None


#: The commits in a deployment gap, and the concrete command that reproduces the
#: diff by hand.  ``<running>`` is the commit ``/health`` reports, ``<HEAD>`` is
#: local ``git rev-parse HEAD``; expand BOTH to full shas before diffing.
#: The pathspec below IS ``MATERIAL_PATHS`` — the command is built from it, so
#: the documented command and the executed scope cannot drift apart.
MATERIAL_PATHS = ("src/", "scripts/", "tests/", "pyproject.toml")

MATERIAL_DIFF_COMMAND_TEMPLATE = "git diff --name-only <running>..<HEAD> -- " + " ".join(MATERIAL_PATHS)

#: The ancestry check the classification depends on: a gap is only classifiable
#: when the running commit is an ANCESTOR of HEAD (a rewind/divergence is not a
#: stale deployment, it is a different tree, so it must not be guessed at).
ANCESTRY_COMMAND_TEMPLATE = "git merge-base --is-ancestor <running> <HEAD>"

#: What a STALE classification obliges the operator to do — one string, printed by
#: the script AND quoted in AGENTS.md, so the documented contract and the runtime
#: evidence cannot drift into two different requirements.
RELOAD_REQUIREMENT = (
    "reload the supervised service (sudo systemctl restart chimera), or record an "
    "explicit deferral in this tick"
)

#: Reproduces the version-banner helper: a bare checkout without git is normal.
GIT_UNAVAILABLE_REASON = "git unavailable (not a git checkout, or `git` not on PATH)"

#: ``/health``'s own sentinel for "built outside a git checkout" (server.py
#: ``_running_commit``).  It is NOT a commit, so it can never be verified.
UNKNOWN_COMMIT = "unknown"

#: Deployment-parity classification.  ``CURRENT`` and ``CODE_CURRENT`` both mean
#: no reload is owed — the difference is whether there was a gap at all, which is
#: what a foreman narrative needs to be able to say.  ``UNVERIFIABLE`` means the
#: evidence was insufficient: never a staleness verdict, never a reload claim.
DEPLOY_STATUS_CURRENT = "CURRENT"
DEPLOY_STATUS_CODE_CURRENT = "CODE-CURRENT"
DEPLOY_STATUS_STALE = "STALE"
DEPLOY_STATUS_UNVERIFIABLE = "UNVERIFIABLE"


class DeploymentParity(NamedTuple):
    """One deployment-parity verdict, with the evidence behind it.

    ``status`` is one of the ``DEPLOY_STATUS_*`` constants; ``reason`` explains an
    ``UNVERIFIABLE`` verdict (empty otherwise); ``material_paths`` holds the
    changed tracked paths inside the material scope, and is therefore non-empty
    exactly when ``status`` is ``STALE``.
    """

    status: str
    running_commit: str
    head_commit: str
    material_paths: tuple[str, ...] = ()
    reason: str = ""


def _git_run(args: list[str], cwd: str | None = None) -> tuple[int | None, str]:
    """Run one ``git`` command without a shell; return ``(returncode, stdout)``.

    ``args`` is passed as argv with ``shell`` left off, so a commit string from
    an HTTP response can never be interpreted as shell syntax.  ``None`` as the
    return code means git could not be run AT ALL (absent, unrunnable, timed
    out); a nonzero code means git ran and refused.  Both are failures the
    caller must treat as "no evidence", never as "no difference".
    """
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _resolve_commit(commit: str, run: object, cwd: str | None) -> str | None:
    """The full sha ``commit`` resolves to, or None when it cannot be verified."""
    code, out = run(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"], cwd)  # type: ignore[operator]
    return out.splitlines()[0].strip() if code == 0 and out.strip() else None


def classify_deployment_parity(
    running_commit: object,
    head_commit: object,
    *,
    run: object = None,
    cwd: str | None = None,
) -> DeploymentParity:
    """Classify the gap between the commit ``/health`` reports and local HEAD.

    The whole point (DF-CHIMERA-V2-45) is that the ANSWER must come from git
    evidence, never from a commit subject or a narrative: the incident had
    ``/health`` at ``0fc54d5`` while HEAD already held an 11-file ``src/`` wave,
    and the gap was written off as "board-only delta, expected" purely because a
    subject line said so.

    The classification, in order:

    * identical commits -> ``CURRENT``; no git command is run at all;
    * a missing/blank/``unknown`` commit on either side -> ``UNVERIFIABLE``;
    * a commit that does not resolve -> ``UNVERIFIABLE`` (a sha the local repo
      has never seen proves nothing about what is deployed);
    * running NOT an ancestor of HEAD -> ``UNVERIFIABLE`` (HEAD was rewound or
      diverged, so "behind by N" is not even the right question);
    * otherwise one path-scoped diff over ``MATERIAL_PATHS``: a NON-EMPTY diff is
      ``STALE`` (the running code predates material code) and an EMPTY diff is
      ``CODE_CURRENT`` (bookkeeping/board-only gap — the running code IS current
      for everything that matters).

    ``run`` is the git runner (``_git_run``), injectable so the classification is
    testable without spawning a process; a runner that raises is treated as a git
    failure, not an exception in the operator's smoke test.  Pure with respect to
    its inputs: it reads no config, no secrets, and no environment.
    """
    runner = _git_run if run is None else run
    running = str(running_commit or "").strip()
    head = str(head_commit or "").strip()

    if not running or running == UNKNOWN_COMMIT:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"/health reported no usable commit ({running_commit!r})",
        )
    if not head or head == UNKNOWN_COMMIT:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"local HEAD is not usable ({head_commit!r}) — run this from the checkout",
        )
    if running == head:
        return DeploymentParity(DEPLOY_STATUS_CURRENT, running, head)

    try:
        running_full = _resolve_commit(running, runner, cwd)
        head_full = _resolve_commit(head, runner, cwd)
    except Exception:  # a runner that raises is a git failure, not a crash
        running_full = head_full = None
    if running_full is None or head_full is None:
        unresolved = running if running_full is None else head
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"git could not resolve commit {unresolved} ({GIT_UNAVAILABLE_REASON})",
        )
    if running_full == head_full:
        return DeploymentParity(DEPLOY_STATUS_CURRENT, running, head)

    try:
        code, _ = runner(
            ["git", "merge-base", "--is-ancestor", running_full, head_full],
            cwd,
        )
    except Exception:
        code = None
    if code is None:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"{GIT_UNAVAILABLE_REASON} — the ancestry of {running} in {head} is unproven",
        )
    if code == 1:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=(
                f"running commit {running} is not an ancestor of HEAD {head} "
                "(HEAD was rewound or diverged) — the gap cannot be sized"
            ),
        )
    if code != 0:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"git merge-base exited {code} for {running} vs {head}",
        )

    diff_args = [
        "git",
        "diff",
        "--name-only",
        f"{running_full}..{head_full}",
        "--",
        *MATERIAL_PATHS,
    ]
    try:
        diff_code, diff_out = runner(diff_args, cwd)
    except Exception:
        diff_code, diff_out = None, ""
    if diff_code != 0:
        return DeploymentParity(
            DEPLOY_STATUS_UNVERIFIABLE,
            running,
            head,
            reason=f"{GIT_UNAVAILABLE_REASON} — the path-scoped diff of {running}..{head} failed",
        )

    paths = tuple(line.strip() for line in diff_out.splitlines() if line.strip())
    if paths:
        return DeploymentParity(DEPLOY_STATUS_STALE, running, head, material_paths=paths)
    return DeploymentParity(DEPLOY_STATUS_CODE_CURRENT, running, head)


def deployment_parity_lines(parity: DeploymentParity) -> list[str]:
    """Render a :class:`DeploymentParity` as the evidence an operator reads.

    Pure rendering, one line per finding, and deliberately LOUD about the two
    verdicts that need action — but it never claims a reload happened: only a
    post-reload ``/health`` commit plus a passing smoke can do that.  It also
    never decides the exit code (``main`` owns that).
    """
    if parity.status == DEPLOY_STATUS_CURRENT:
        # code-current: no gap at all
        return [
            f"deployment: CURRENT — running commit {parity.running_commit} == local "
            f"HEAD {parity.head_commit}: no gap, so no reload is owed."
        ]

    scope = ", ".join(MATERIAL_PATHS)
    if parity.status == DEPLOY_STATUS_CODE_CURRENT:
        return [
            f"deployment: CODE-CURRENT — running commit {parity.running_commit} is an "
            f"ancestor of local HEAD {parity.head_commit}, and the path-scoped diff "
            f"over {scope} is EMPTY: a bookkeeping/board-only gap, so the service does "
            "NOT run older code and no reload is owed."
        ]

    if parity.status == DEPLOY_STATUS_STALE:
        lines = [
            f"deployment: STALE — running commit {parity.running_commit} is behind local "
            f"HEAD {parity.head_commit} and {len(parity.material_paths)} material path(s) "
            f"changed under {scope}:",
        ]
        lines.extend(f"  - {path}" for path in parity.material_paths)
        lines.append(
            f"REQUIREMENT: {RELOAD_REQUIREMENT}; then re-run this smoke and "
            "confirm /health reports the new commit."
        )
        return lines

    return [
        f"deployment: UNVERIFIABLE — {parity.reason}. No staleness verdict is made and "
        "no reload is claimed; get the git evidence (see AGENTS.md, deploy section) "
        "before acting on this line."
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("CHIMERA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--formation",
        default=SMOKE_FORMATION,
        help=f"formation to run (default: {SMOKE_FORMATION}; try 'auto' for the full dispatcher)",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CHIMERA_API_KEY", ""),
        help="API key for protected deployments (or set CHIMERA_API_KEY)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # 1) Liveness + running commit (staleness visibility, CH-GAP-039/047)
    status, health = _http_json(f"{base}/health", timeout=10)
    if status != 200 or health.get("status") != "alive":
        print(
            f"SMOKE FAIL: /health not alive (status={status}) — is `chimera serve` running on {base}?",
            file=sys.stderr,
        )
        print(f"  body: {json.dumps(health)[:300]}", file=sys.stderr)
        return 1
    running_commit = health.get("commit")
    print(f"service: alive  commit={running_commit}  models={health.get('uptime_models')}")

    head = _local_head()
    if running_commit or head:
        # DF-CHIMERA-V2-45: classify the gap from GIT EVIDENCE — a real code delta
        # (STALE) and a bookkeeping/board-only gap (CODE-CURRENT) are different
        # findings, and neither is guessed from a commit subject.  The evidence is
        # printed prominently but never decides the exit code below.
        for line in deployment_parity_lines(classify_deployment_parity(running_commit, head)):
            print(line)

    # 2) Provider health battery. The report is class-aware (DF-CHIMERA-V2-4):
    #    keyless providers are informational, real classes warn, and the
    #    degradation is NEVER the verdict — the deliberation below is the actual
    #    proof, and it alone decides the exit code.
    status, v1 = _http_json(f"{base}/v1/health", timeout=60)
    if status == 200:
        for line in provider_health_lines(v1.get("details"), v1.get("unhealthy_providers")):
            print(line)
    else:
        print(f"WARNING: /v1/health probe failed (status={status}) — continuing to the real call")

    # 3) The real thing: a live deliberation
    print(f"deliberating (formation={args.formation}) ...")
    status, body = _http_json(
        f"{base}/v1/deliberate",
        method="POST",
        body={"prompt": args.prompt, "formation": args.formation},
        api_key=args.api_key or None,
        timeout=args.timeout,
    )

    if status == 401:
        print("SMOKE FAIL: 401 unauthorized — the deployment requires an API key.", file=sys.stderr)
        print("  Set CHIMERA_API_KEY (or pass --api-key) and re-run.", file=sys.stderr)
        return 1
    if status == 422:
        detail = body.get("detail", body)
        print(f"SMOKE FAIL: 422 — request rejected ({detail}).", file=sys.stderr)
        print(
            "  Unknown formation? Run `chimera formations` or GET /v1/formations for the list.",
            file=sys.stderr,
        )
        return 1
    if status == 503:
        print("SMOKE FAIL: 503 — server busy (queue full). Retry in a few seconds.", file=sys.stderr)
        return 1
    if status != 200:
        print(f"SMOKE FAIL: /v1/deliberate returned HTTP {status}", file=sys.stderr)
        print(f"  body: {json.dumps(body)[:500]}", file=sys.stderr)
        return 1

    answer = (body.get("answer") or "").strip()
    if not answer:
        print(
            "SMOKE FAIL: HTTP 200 but empty answer — check server logs "
            "(journalctl -u chimera -n 50) for upstream provider errors.",
            file=sys.stderr,
        )
        return 1

    trace = body.get("trace") or {}
    print(f"request_id: {body.get('request_id')}")
    print(f"trace.source: {trace.get('source')}")
    print("merged answer:")
    print("---")
    print(answer)
    print("---")
    print("SMOKE PASS: live deliberation returned a merged answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
