# Dogfood run 19 — 2026-10-09 — fresh-machine surface + CLI honest-path probe

## Promise under test

"A fresh user on a clean machine can `pip install chimera-deliberation[full]`
from the public mirror, `chimera config init`, and run a real deliberation —
and the CLI's machine-readable paths (`--quiet`, `--json`) behave as the
README promises, including how they fail."

Runs 1–18 covered docker, PyPI wheel, MCP, OpenAI-SDK drop-in, custom
providers and the web UI. This run targeted the one surface no prior run
exercised: **the CLI on a fresh box with NO credentials configured** — the
default state of the documented quickstart for a user who hasn't yet added
`DEEPSEEK_API_KEY` — plus the machine-readable output contract.

## Install leg (ephemeral bunker)

Host: las-03 offline (ssh timeout ×1 probe; not retried further — sibling rule
applies). las-02 answered, `bunkerd` active. First `bunker spawn` failed with
the known transient `slice-limits: containment landing did not converge`
(swapon bar); retry ONCE per the skill → **agent 994784e5** spawned (TTL 2h,
destroyed and verified gone at the end).

- clone PUBLIC mirror `github.com/totalwindupflightsystems/chimera` → HEAD `0e5de41`, 5.2s
- `python3 -m venv ~/venv` + `pip install "chimera-deliberation[full]"` → **54s**
- `chimera config init` → "Created chimera.yaml from …/chimera.yaml.example" (wheel template found — force-includes load-bearing, confirmed again)
- `chimera --version` → 0.2.7

Documented install path holds end-to-end with zero friction. No compose
plugin, no sudo, no toolchain beyond python3-venv needed.

## What a fresh user actually gets (no API key)

`chimera "Name one HTTP status code for not found"` on the fresh box **exits
0 and prints to stdout**:

> [stage aggregator (deepseek/deepseek-v4-flash) unavailable: … provider
> 'deepseek' rejected the credentials or none were found: set DEEPSEEK_API_KEY …]

That is an error string delivered as the ANSWER, with exit code 0. Stderr
does warn (`dispatch degraded — source=fallback`), but a scripted consumer
(`ANSWER=$(chimera --quiet "…")`, exactly the README pattern) captures the
error text as the answer and sees success. The same box through the REST
surface correctly returns **HTTP 502** with a structured error, and
`scripts/smoke_live.py` correctly exits 1 (`SMOKE FAIL … 502`). So the REST
error contract is exact and the CLI failure contract is wrong.

This is a new finding (filed DF-CHIMERA-V2-71): run 15 found fresh-auth
silent-fail on the *server* (DF-CHIMERA-V2-56, since addressed); the CLI's
fallback-answering-with-the-error path is a different defect.

Second CLI defect found on the same box: `chimera --dag '{}' "hi"` without
`--allow-custom-dag` prints `error: Custom DAG requires allow_custom_dag=True`
to stderr, produces no answer, and **exits 0** (the documented convention is
exit 2 for usage errors — unknown formation exits 2 correctly, and the
README's own help text says "an unknown name exits 2"). Filed
DF-CHIMERA-V2-73.

## Machine-readable contract (credentialed box, live :8765 config)

- `chimera --quiet "…"` → stdout is exactly the answer + `\n` (verified: "404 Not Found is the HTTP status code…")
- `chimera --json "…"` → one JSON object; `jq .answer` → "Paris";
  `trace.total_duration_ms`=11438, `trace.total_tokens`=21307 — README's
  documented jq paths all resolve
- `--formation nosuchform` → exit 2 with available-formation list (docs hold)
- `--quiet`/`--json` before the implicit prompt work as documented

## CLI with real credentials (control host)

- warm `--formation simple`: 18s / 20s (two runs)
- `--json` one-shot: 12s wall vs 11.4s trace — shell overhead ~1s
- `--formation debate "Say ok"`: 27s, 5 stages, merged answer correct

## REST surface (local deployment, CODE-CURRENT 18bb00d)

`python scripts/smoke_live.py` → SMOKE PASS, exit 0, merged answer
("The capital of France is Paris."), deployment classified CODE-CURRENT
(zero material diff vs origin/main). Endpoint battery on the bunker serve
instance: `/web/` 200, `/v1/formations` 200, `/v1/models` 200, `/docs` 200,
unknown path 404, `/health` alive with `commit:"unknown"` on the wheel-only
machine (known container shape, DF-CHIMERA-V2-48 class).

Web sessions workflow (live box): create → `{"session_id":"36ac77f2ded0"}`;
turn 1 ("remember chartreuse") 11s → "OK"; turn 2 ("what is my favorite
color?") 6s → "chartreuse" — multi-turn memory works; `DELETE` → 204,
`GET` after delete → 404. **Run 18's finding DF-CHIMERA-V2-69 (no DELETE
route) is now FIXED in deployed code** — the row's premise is false as of
this run; filed the correction as DF-CHIMERA-V2-72's sibling context rather
than editing the old row (a new correction row, DF-CHIMERA-V2-74, names the
change, per the skill's never-edit-someone-else's-row rule).

## Docs gap

`POST /web/sessions/{id}/chat` request body field is **`prompt`**. Neither
INTEGRATION.md's endpoint table nor USAGE.md names the field; I first sent
`{"message": …}` (the natural guess) and got a 422 `Field required` naming
`prompt`. Small, but it is the exact kind of thing the error hides from a
casual reader ("Field required" without the doc anchor). Filed
DF-CHIMERA-V2-72 (P3).

## Verdict

**SHIPPABLE** (10th consecutive). Install path proven on fresh hardware
(54s, zero friction), documented output contracts hold where credentials
exist, error contracts exact on REST, session lifecycle works end to end,
and one previously-filed finding is verified fixed. The fresh-install
no-credentials CLI path answers errors as successful answers — that is the
one place the product lies to its user today.

## Perf (Step 2b)

Warm simple CLI 18–20s, debate 27s, JSON one-shot 12s, session turns 6–11s,
fresh install 54s — all model-bound (trace ≈ wall − 1s), consistent with
runs 11–18's 25–35s band. Nothing a user would feel as a project defect.
**No PERF row.**
