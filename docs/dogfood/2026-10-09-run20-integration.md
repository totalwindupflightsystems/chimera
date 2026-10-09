# Dogfood Run 20 — 2026-10-09 (Concurrent Load + Failure Resilience)

**Angle:** the surfaces runs 1–19 never touched — an OPERATOR driving the
gateway under concurrent load (the documented `queue` backpressure, F5), and
the FAILURE_RESILIENCE.md C2 promise (one dead worker → graceful degraded
answer) observed from each client surface. Run 19 (same day) took the
fresh-box CLI failure-path angle; this run is additive, per the repeat-run rule.

**Promise under test:** "Four simultaneous API clients each get their own
panel deliberation; one dead worker model degrades the answer gracefully and
visibly; the queue sheds load instead of breaking."

## What I did (live gateway :8765, commit 18bb00d, CODE-CURRENT, smoke PASS)

1. Config shape probe (read-only, through the app's own loader): `queue:
   max_concurrent=10, max_queue_depth=100`, `rate_limit.enabled=false`, no
   circuit breakers configured — the documented defaults.
2. Fired 4 simultaneous `POST /v1/deliberate` (simple formation): **all 200,
   4/4 unique answers, 49.4s total wall**; per-request walls 18.9 / 25.2 /
   42.0 / 49.4s. Warm single-request latency same tick: 8.3–10.5s. The
   slowest request waited ~4x with zero wait feedback (→ DF-CHIMERA-V2-77 P3).
3. Failure-resilience probe: `worker_model` override to
   `cliproxy/deepseek,deepseek-v4-flash` (configured, NO credentials — the
   health endpoint's `unhealthy_providers` names it). Results, twice, cold:
   - `POST /v1/deliberate`: **200 in 8.3–10.5s** with a real merged answer.
     `trace.worker_failures` carries stage_id/model/error ("call failed after
     3 attempts: litellm.InternalServerError: Missing credentials"),
     per-stage records show the dead workers with 0 tokens. C2 promise HELD,
     machine-readably, on this surface.
   - `POST /v1/chat/completions` (the OpenAI drop-in): **200,
     finish_reason=stop, chimera_degraded_reasons=null** — the same hard
     worker failure is invisible to an OpenAI-SDK third party (→
     DF-CHIMERA-V2-75 P2). The failure-marker design exists end to end
     (engine.py worker_failures; CLI dropped-worker warnings) but the chat
     surface maps only `degraded_reasons`, documented as token-limit-only.
4. Error contract (negative probe): `worker_model: bogus/model-does-not-exist`
   → 400 with an exact, teachable message ("must be declared in the `models:`
   catalog section … see docs/CONFIG.md") — best-in-class error copy.
5. Fresh-install leg (ephemeral bunker, las-bunker-02, agent 1b594f64,
   destroyed + verified gone): clean Debian 13.7, Python 3.13.5. Public GitHub
   clone **10s** (HEAD 0e5de41, same as control host), `python3 -m venv +
   pip install -e '.[full]'` **65s, RC=0**, `config init` OK, `formations`
   OK. Documented smoke: real `chimera --quiet -f simple run` with an
   existing credential (DEEPSEEK_API_KEY via the control-host fleet env;
   nothing minted, nothing printed): **RC=0, 22s, real merged answer**.
   Serve leg on the same agent: boots healthy on 0.2.7/0e5de41.
6. Auth leg on the fresh agent: `CHIMERA_API_KEY=k` alone → `POST
   /v1/deliberate` served with NO Authorization header (auth silently OFF).
   Adding `CHIMERA_AUTH_ENABLED=true` → no key 401 / wrong key 401 / valid
   key accepted — the documented contract, exactly. The gap is the inverse
   case: key exported, auth disabled, zero warnings (→ DF-CHIMERA-V2-76 P2).
   My own first auth probe was operator error (the docs are correct);
   the finding is the silent-open door, not a broken guard.

## Verdict

**SHIPPABLE** (11th consecutive). Concurrency holds (4/4 unique, no cross-talk,
no errors), failure resilience is real and machine-readable on /v1/deliberate,
error contracts teach, fresh install is frictionless (10s clone + 65s install).
The one trust defect: the OpenAI drop-in surface hides hard worker failures.

## Perf (Step 2b)

- Headline op (simple deliberation): warm REST 8.3–10.5s; 4x concurrent
  18.9–49.4s (queue-wait dominated, no per-request feedback).
- CLI cold process: wall 31.3 / 64.5 / 62.6s; `time -p` user 2.8–3.8s +
  sys 0.4–0.8s ⇒ **~3–4s process/import overhead**, rest is upstream model
  latency. Same answer class as all 19 prior runs (model-bound).
- Fresh install 75s end to end (clone+install+smoke pre-deliberation).
- **No PERF row**: nothing user-felt is code-fixable — the slow parts are
  upstream models and queue wait (the latter filed as UX, DF-77).

## Board rows filed

- DF-CHIMERA-V2-75 (P2): chat surface hides hard worker failures.
- DF-CHIMERA-V2-76 (P2): CHIMERA_API_KEY without auth.enabled = silently
  unauthenticated server, no warning, no doc line.
- DF-CHIMERA-V2-77 (P3): concurrent queue wait is silent (18.9–49.4s spread).

## Lessons for the next dogfood

- `boardctl create` succeeded where hand-written JSONL was refused before —
  use it; `--evidence-run-id` dedupes re-detections (exit 2 on repeat).
- `boardctl validate` reports PRE-EXISTING events.jsonl id-descent errors
  (4 errors at HEAD, foreman-numbered event ids not monotone across lane
  restarts) — do not attribute them to your own append; diff your changed
  lines instead.
- On a lane-shared checkout, `git stash` of ONE file can still conflict on
  OTHER paths (.gitreins/tasks.yaml) — avoid stash mid-tick; use git show
  HEAD:<path> snapshots and pathspec checkout to restore.
