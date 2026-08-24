#!/usr/bin/env python3
"""Live end-to-end smoke test for a deployed Chimera deliberation service.

Runs a REAL deliberation against a running `chimera serve` instance and
proves the README promise ("one API call, a team of models, one answer")
still works: workers were dispatched, an aggregator merged them, and the
client received a usable merged answer.

This is the cheap pre-flight check for provider/auth/format regressions
(INT-ZAI-001 class): /v1/health can say "alive" while the first real call
fails. This script is that first real call, automated.

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

DEFAULT_BASE_URL = "http://localhost:8765"
DEFAULT_PROMPT = "What is the capital of France? Answer in one short sentence."
SMOKE_FORMATION = "simple"  # deterministic 2-worker + aggregator pipeline, cheap


def _http_json(url: str, method: str = "GET", body: dict | None = None,
               api_key: str | None = None, timeout: float = 120.0) -> tuple[int, dict]:
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
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return out or None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("CHIMERA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--formation", default=SMOKE_FORMATION,
                        help=f"formation to run (default: {SMOKE_FORMATION}; "
                             "try 'auto' for the full dispatcher)")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--api-key", default=os.environ.get("CHIMERA_API_KEY", ""),
                        help="API key for protected deployments (or set CHIMERA_API_KEY)")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # 1) Liveness + running commit (staleness visibility, CH-GAP-039/047)
    status, health = _http_json(f"{base}/health", timeout=10)
    if status != 200 or health.get("status") != "alive":
        print(f"SMOKE FAIL: /health not alive (status={status}) — "
              f"is `chimera serve` running on {base}?", file=sys.stderr)
        print(f"  body: {json.dumps(health)[:300]}", file=sys.stderr)
        return 1
    running_commit = health.get("commit")
    print(f"service: alive  commit={running_commit}  models={health.get('uptime_models')}")

    head = _local_head()
    if running_commit and head and running_commit != head:
        print(f"WARNING: deployed commit {running_commit} != local HEAD {head} "
              f"— service runs older code; restart it (sudo systemctl restart chimera).")

    # 2) Provider health battery (warn on degradation, don't hard-fail here —
    #    the deliberation below is the actual proof)
    status, v1 = _http_json(f"{base}/v1/health", timeout=60)
    if status == 200:
        details = v1.get("details", {})
        provs = details.get("providers", {})
        unhealthy = [n for n, p in provs.items() if not p.get("healthy")]
        if unhealthy:
            print(f"WARNING: providers reported unhealthy by /v1/health: {', '.join(unhealthy)}")
        else:
            print(f"providers: {details.get('providers_configured')}/"
                  f"{details.get('providers_configured')} healthy")
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
        print("  Unknown formation? Run `chimera formations` or "
              "GET /v1/formations for the list.", file=sys.stderr)
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
        print("SMOKE FAIL: HTTP 200 but empty answer — check server logs "
              "(journalctl -u chimera -n 50) for upstream provider errors.", file=sys.stderr)
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
