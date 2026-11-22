# GitReins Judge Lane — sanctioned triple + coherence validator (CH-MAINT-015)

Status: landed. Validator shipped in the gitreins worktree branch
`wt/chimera-v2-CH-MAINT-015` and refreshed into the live `pipx` CLI
(`gitreins --version` → gitreins 0.21.1). Measured 2026-11-22.

## The sanctioned judge-lane triple

The judge lane resolves from `GITREINS_LLM_*` env ONLY — INT-CI-021
deliberately keeps provider/base_url/model out of the config schema keys
(`engine/config.py` defaults block, repo note INT-CI-021), so the coherence
responsibility lives on the env triple itself:

| Variable | Sanctioned value |
|---|---|
| `GITREINS_LLM_BASE_URL` | `https://api.z.ai/api/coding/paas/v4` |
| `GITREINS_LLM_MODEL` | `glm-5.3-flash` |
| `GITREINS_LLM_API_KEY` | resolved at runtime from env variable `ZAI_API_KEY`. The variable NAME only is recorded here — never the value, and commit the name without an `=`-shaped token (the repo's secret guard refuses that pattern; source the value in a live shell by indirection instead) |

Key indirection only: the key must never be echoed, committed, or stored.
This doc records the VARIABLE NAME, nothing else.

Measured (2026-11-22, live): `GET https://api.z.ai/api/coding/paas/v4/models`
with the `ZAI_API_KEY` credential → HTTP 200, OpenAI shape `{"object":"list","data":[{"id":...}]}`,
12 model ids including `glm-5.3-flash` (glm-4.5 … glm-5.3-flashx-legal). No
`kimi` ids are served, which is what makes the kimi-k3 triple incoherent on
this endpoint.

## The incoherence defect (measured, pre-fix)

With an incoherent triple the judge did not refuse — it burned every tier-2
LLM iteration on an unusable lane and came back with a hollow verdict:

- `GITREINS_LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4` +
  `GITREINS_LLM_MODEL=moonshotai/kimi-k3` → **HTTP 400 on every tier-2
  iteration** (the coding endpoint does not serve that model id) → verdict
  **FAIL [DEGRADED] INCOMPLETE**.
- `GITREINS_LLM_BASE_URL=https://openrouter.ai/api/v1` + same model + a
  stale key → **HTTP 403** on every iteration → same **FAIL [DEGRADED]
  INCOMPLETE**.
- The coherent triple (z.ai base_url + `glm-5.3-flash` + `ZAI_API_KEY`)
  grades tier-2 PASS in ~40s on a trivial criterion; a full-row verdict
  took 10–18m.

Nothing validated that the model id is served by the configured base_url —
the lane fails only where iterations spend money.

## The validator (what changed in gitreins)

Code path (gitreins worktree `wt/chimera-v2-CH-MAINT-015`, based on main
f9aa97ef):

- `engine/llm.py:89` — `JudgeLaneIncoherent(RuntimeError)`: the named
  refusal exception.
- `engine/llm.py:107` — `_served_models_cache: dict[str, frozenset[str]]`:
  process-lifetime `/models` probe results keyed by base_url. Tier-2 runs
  many iterations against one endpoint; the probe happens once per process,
  never once per iteration. Failures are deliberately NOT cached (a
  transient failure must not poison a long-lived MCP server; failures exit
  anyway).
- `engine/llm.py:329` — `LLMClient.validate_lane()`: one GET
  `{base_url}/models` with the resolved credential (OpenAI-compatible list
  endpoint; z.ai's coding endpoint and OpenRouter serve it; the Anthropic
  path sends x-api-key + anthropic-version headers), then a set-membership
  check on `data[].id`.
- `engine/llm.py:374` — `_probe_served_models()`: the probe itself,
  timeout-capped at `min(GITREINS_LLM_TIMEOUT, 30)`, refusing FAST before
  tier-1 work starts.
- `engine/llm.py:361-364` — success-only cache write.
- `gitreins/cli.py:3614` — `_validate_judge_lane_or_exit()`: turns the
  exception into a non-zero exit with the refusal on stderr and the line
  "No tier-1 guard work was started and no verdict was produced (exit
  code 1)." (`--json` keeps stderr-only, stdout stays a clean document
  channel.)
- Hook sites (each BEFORE tier-1 / any tier-2 iteration):
  - `gitreins/cli.py:3714` — `gitreins judge <id>` (sync; only when
    `--skip-tier2` is not set, preserving that flag's "no LLM at all"
    contract);
  - `gitreins/cli.py:3832` — `gitreins judge --ephemeral` (same
    skip-tier2 condition);
  - `gitreins/cli.py:3962` — `judge --async` dispatch gate (refuses
    up front, instead of spawning a detached child that dies far away);
  - `gitreins/cli.py:4073` — the detached `judge --run-job` worker child,
    which records the refusal as a terminal job error via its existing
    `except Exception` handler;
  - `gitreins/cli.py:2554` — `gitreins task complete` (the closeout
    re-judge burns tier-2 the same way; the gate sits inside the
    not-`skip_tier2` block, after the credential refusal).
  There is NO new config schema key (INT-CI-021 respected) and no provider
  registry — the check lives entirely inside `LLMClient`.

### Refusal message shapes

Every refusal starts with `judge lane incoherent:` and names base_url,
model id, and the reason:

- Model absent from a 200 `/models` list (the measured PROBE A case):

  ```
  judge lane incoherent: base_url https://api.z.ai/api/coding/paas/v4 does not serve model moonshotai/kimi-k3 (model absent from /models list: 12 models); fix GITREINS_LLM_MODEL or GITREINS_LLM_BASE_URL (or set GITREINS_LLM_SKIP_MODEL_CHECK=1 to skip this check)
  ```

- Non-200 from `/models` (e.g. an endpoint that 400s the list call):

  ```
  judge lane incoherent: base_url <url> does not serve model <model> (HTTP 400 from /models); fix GITREINS_LLM_MODEL or GITREINS_LLM_BASE_URL (or set GITREINS_LLM_SKIP_MODEL_CHECK=1 to skip this check)
  ```

- Credential rejected (401/403) — names the key variable, never the key:

  ```
  judge lane incoherent: base_url <url> rejected the credential (HTTP 401 from /models); cannot verify it serves model <model>. Fix GITREINS_LLM_API_KEY (or set GITREINS_LLM_SKIP_MODEL_CHECK=1 to skip this check)
  ```

- Unreachable endpoint / non-JSON body / unexpected shape — names
  `GITREINS_LLM_BASE_URL`.

### Escape hatch

`GITREINS_LLM_SKIP_MODEL_CHECK=1` skips the probe entirely, for endpoints
without an OpenAI-compatible `/models`. Also documented in the
`validate_lane` docstring: the probe likewise auto-skips when
`GITREINS_MOCK_LLM_RESPONSE` is set (a mocked lane makes no real HTTP call;
demanding a live /models listing would break every subprocess-based test
out of proportion to the check's value), and the pytest suite defaults the
probe OFF via the `skip_judge_lane_model_check` autouse fixture in
`tests/conftest.py` (mirroring `skip_worker_llm_probe`), with the gate's
own tests opting back in by deleting the env var.

## Measured live evidence (scratch clone of chimera-v2 @ 2c676fb)

Task: `gitreins task create PROBE-LANE-015 "trivial lane probe" "the number
one is odd"` + `gitreins task start PROBE-LANE-015` in
`/tmp/lane-probe-ch-maint-015` (throwaway clone; cleaned up after capture).
Key always sourced by indirection; value never echoed.

### PROBE A — incoherent triple → fast named refusal

Command shape (key redacted):

```bash
export GITREINS_LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
export GITREINS_LLM_MODEL=moonshotai/kimi-k3
# GITREINS_LLM_API_KEY is also exported at this point, sourced from the
# named env variable by indirection — value never echoed.
time gitreins judge PROBE-LANE-015
```

Result: named refusal in **2.06 s** wall (exit 1), NO tier-1 work, NO
tier-2 iteration:

```
judge lane incoherent: base_url https://api.z.ai/api/coding/paas/v4 does not serve model moonshotai/kimi-k3 (model absent from /models list: 12 models); fix GITREINS_LLM_MODEL or GITREINS_LLM_BASE_URL (or set GITREINS_LLM_SKIP_MODEL_CHECK=1 to skip this check)
No tier-1 guard work was started and no verdict was produced (exit code 1).

real	0m2.055s   user	0m0.539s   sys	0m0.144s
```

Compare: pre-fix, the same env burned HTTP 400 on every tier-2 iteration.

### PROBE B — sanctioned triple → PASS

Same clone, same command with `GITREINS_LLM_MODEL=glm-5.3-flash`:

```
Stage tier1: PASS (DEGRADED - skipped checks)   # guard: DEGRADED PASS — no staged files (test mode: diff)
Stage tier2: PASS
  COMPLETE
  ✓ the number one is odd: Mathematical fact verified by direct execution ... exit_code 0
Overall: PASS ✓ [DEGRADED — skipped: tier1(guard)=...]
  📋 Verdict saved: 7ad7c770

real	0m51.067s   user	0m19.594s   sys	0m1.868s
EXIT=0
```

PASS grading in **51.07 s** wall — far below the row's measured 10–18m
full-row verdict (that figure includes real change-set grading; a trivial
criterion on a clean tree is bounded by the guard + one cheap lane).

## Prior art (carry-lessons)

- **off-by-one class 2798** (`gitreins-tier2-time-cap-queue-contention`):
  a tier-2 time-cap INCOMPLETE with token burn far under fleet norm is lane
  WAIT, not work — check the burn rate before blaming budgets. The same
  discipline applies to 400-burn: a hollow INCOMPLETE can mean "lane never
  served the model", which this validator now refuses at t≈2s instead of
  after a full cap.
- **off-by-one class 2265**: `gitreins judge` can detach a main checkout's
  HEAD — always run judges in worktrees or throwaway clones (PROBE A/B were
  run in `/tmp/lane-probe-ch-maint-015` for exactly this reason).

## Test coverage (gitreins worktree)

`tests/test_llm_lane_validation.py` (12 tests, all HTTP mocked):
mismatch → refusal naming base_url + model + `GITREINS_LLM_MODEL/BASE_URL`
and never the key; matching model → proceeds and returns the served set;
`/models` 401 → refusal names credential + `GITREINS_LLM_API_KEY`;
`/models` 400 → the measured message shape; unreachable → refusal; skip
flag → probe bypassed (`requests.get` never called); cache → one probe per
base_url across two clients; failure not cached; mocked lane
(`GITREINS_MOCK_LLM_RESPONSE`) skips the probe; plus two end-to-end CLI
tests (refusal before tier-1 narration; skip-flag + mock proceeds to
grading).

Targeted run: `pytest tests/test_llm_lane_validation.py tests/test_llm.py
tests/test_judge.py tests/test_llm_gap074.py
tests/test_poc78_llm_probe_and_cap.py tests/test_judge_tier2_grading.py -q`
→ 188 passed. Full suite run recorded in the CH-MAINT-015 worker report.
