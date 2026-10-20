# Chimera-v2 dogfood run 25 — 2026-10-20 — the task-router registry source

**Surface:** the documented model-catalog source override — `CHIMERA_TASK_ROUTER_MODELS_PATH`
and `TASK_ROUTER_HOME` (docs/CONFIG.md §"Model catalog source: the task-router registry
(env overrides)") — plus what the resolved pricing does to the number a user reads in a
deliberation trace. Runs 1–24 covered CLI, REST, MCP, web UI, docker compose, custom
formations, custom DAG, idempotency, SSE, concurrency, custom providers, PyPI wheel and
install; the registry seam was the untouched surface.

**Verdict: 🟡 PROMISING-BUT-ROUGH.** The env contract itself is solid — 11 of 12 legs
behaved exactly as documented, including every failure arm. The value chain behind it is
not: the price a catalog model is billed at in the trace comes from an unrelated gateway
(row DF-CHIMERA-V2-93), and the published artifact currently ships the operator config the
repo forbids shipping (row DF-CHIMERA-V2-92).

Everything below was executed for real; nothing in the repo was modified except the
artifacts this run left behind. No repo visibility, permission or credential change was
made.

---

## 1. What the surface promises (docs/CONFIG.md:418-435)

> "`chimera models`, provider discovery and `scripts/model_sync.py` read the model catalog
> from task-router's generated JSONL registry."
> "**`CHIMERA_TASK_ROUTER_MODELS_PATH`** — Explicit path to a `models.jsonl` table.
> Authoritative — it wins even when it points at a missing file, so a wrong path produces a
> clear diagnostic instead of silently reading a different checkout."
> "**`TASK_ROUTER_HOME`** — Path to a task-router checkout. The registry is read from
> `<home>/data/tables/models.jsonl`."
> "Default discovery order when neither is set: `~/task-router/data/tables/models.jsonl`
> (the home checkout), then a `task-router` checkout sibling to the installed package."
> "Registry selection is logged at startup (`registry_source_selected`)."

Null hypothesis: *a user can point Chimera at their own task-router-generated model registry,
see it selected, get a diagnostic when the path is wrong, and have the registry's prices
(not some other checkout's) reflected in what the tool reports.*

## 2. Working recipe (verified)

```bash
# point at a specific registry (authoritative)
CHIMERA_TASK_ROUTER_MODELS_PATH=/home/kara/task-router/data/tables/models.jsonl \
  chimera models            # stderr: registry_source_selected path=... providers=25
# or name a checkout (the registry is read from <home>/data/tables/models.jsonl)
TASK_ROUTER_HOME=/srv/task-router chimera models
```
Real registry used: 1992 rows, **838 live rows / 25 provider blocks** (37 archived, 805
disabled, 464 with `valid_to`). The adapter read it faithfully — 838/838 live rows and
25/25 provider blocks, no silent drops (checked against an independent parse).

## 3. Contract legs (exact results)

Harness: `CHIMERA_CONFIG=<scratch>/chimera.yaml` (copy of the shipped 120-line example),
repo venv, `README`-documented CLI. Every leg below is reproducible with the commands in §7.

| leg | invocation | rc | observed |
|---|---|---|---|
| L0 | default discovery, real HOME | 0 | `registry_source_selected path=~/task-router/data/tables/models.jsonl providers=25` ✅ |
| L1 | explicit real registry | 0 | `registry_source_selected` ✅ |
| L2 | explicit **missing** path | 0 | `registry_source_fallback` **warning**, reason `configured table does not exist: <path>` ✅ authoritative as documented |
| L3 | malformed JSONL (torn line 51) | 0 | `registry_source_fallback` warning, reason names **line 51** ✅ |
| L4 | duplicate live row | 0 | warning, reason `unsupported duplicate live row ... line 6: aws-bedrock/amazon.nova-2-lite-v1:0` ✅ |
| L5 | every row archived/disabled/expired | 0 | `task-router table has no live supported rows: <path>` ✅ |
| L6 | empty file | 0 | same as L5 ✅ |
| L7 | row with `provider: null` | 0 | `provider must be a string` (line named) ✅ |
| L8 | non-object row (`[1,2,3]`) | 0 | `expected an object` (line named) ✅ |
| L9 | `TASK_ROUTER_HOME` valid | 0 | registry selected ✅ |
| L10 | `TASK_ROUTER_HOME` **bogus** | 0 | selects `~/task-router` instead — **silent substitution** ❌ (DF-CHIMERA-V2-94) |
| L11 | both set | 0 | explicit file wins ✅ |

Container-level behaviour is right: a bad registry never crashes a run (rc=0, models.dev
fallback in every failure case), and an *unset* file variable stays quiet at info level.

## 4. Value leg — does the registry price reach the user?

Two real deliberations, same prompt (`Reply with exactly: PONG`), same `simple` formation,
same catalog (`deepseek/deepseek-v4-flash`, `provider: deepseek` → `https://api.deepseek.com/v1`):

| source | stage | tokens in/out | trace cost | implied rate per 1k |
|---|---|---|---|---|
| task-router registry reachable | `deepseek/deepseek-v4-flash` | 861 / 78 | 0.0004818 | **0.00044 / 0.00132** (= 0.44/1.32 per M) |
| registry NOT reachable (models.dev) | `deepseek/deepseek-v4-flash` | 1108 / 140 | 0.000155456 | **0.000112 / 0.000224** (= 0.112/0.224 per M) |
| what the lab publishes / the gateway actually billed | — | — | — | **0.00015 / 0.0006** (0.15/0.60 per M) |

Both implied rates reproduce their stage cost **exactly** (`tin*r_in + tout*r_out`), so these
are the rates the engine used (`_stage_cost`, src/chimera/engine.py:242-247).

Provenance dig (replica of the discovery pricing loop with the writer recorded):
25 live providers write the **same resolved key** `deepseek/deepseek-v4-flash`; the last
positive write wins. The lab's own row is written 2nd of 25 and overwritten 23 times.

- task-router path winner: `clinepass/deepseek-v4-flash` (0.44/1.32 per M)
- models.dev path winner: `routing-run/deepseek-v4-flash` (0.112/0.224 per M)

Contributing data shape: the live lab rows are `deepseek-flash` and `deepseek-v4-pro`; the
exact id `deepseek-v4-flash` is dead (`valid_to: 2026-09-10`), so the lab's price never
reaches that key — and `MODEL_ID_MAP` (src/chimera/provider_discovery.py:443) collapses
**every** provider's same-named row onto the lab key regardless of provider.

Net effect for a user: the `total_cost` the README tells them to read is 2.9× too high on
one machine and 0.75× on another, for the same workload, neither matching the gateway that
was billed. Filed as **DF-CHIMERA-V2-93**.

## 5. Install leg — fresh machine

Designated ephemeral host was down (see §6), so the leg ran on the substitute that answered:

- `bunker-mvp` agent `f78bf274` (ttl 2h, destroyed + verified gone: list total 4 → 2, id absent).
- Fresh user, documented path: `python3 -m venv ~/venv` → `pip install "chimera-deliberation[full]"`
  **rc=0 in 31s** (Python 3.12.3) → `chimera 0.2.7` → `chimera config init` → `chimera models` rc=0.
- No task-router checkout on the box: default discovery falls back to models.dev as designed
  (and, on 0.2.7, `CHIMERA_TASK_ROUTER_MODELS_PATH` is inert — the registry feature is in HEAD only).

**Published-artifact defect found on this leg (DF-CHIMERA-V2-92, P1):** the wheel's
`chimera/chimera.yaml.example` is **83,677 bytes / 1671 lines**, sha256
`b50ba51dc3438f491c76ddc17cac71a00eb089af316119abb22bcbbc3d34f635` — byte-identical to the
repo's `chimera.yaml.fleet`, the file `pyproject.toml:310-315` says must NEVER ship (it carries
tailnet hostnames and internal gateway ports; the shipped copy contains the exact guard tokens
`master001`, `8642`, `20128`, `3456`). The tracked `chimera.yaml.example` is 3,973 bytes / 120
lines. So `chimera config init` on a fresh machine hands the user the operator config instead of
the minimal starter, and `tests/test_yaml_example_sanitized.py` cannot catch it because it only
reads the repo file. The split that fixes it (`4e9d59f`) is in HEAD but unreleased
(`RELEASE-CUT-2026-09-28` still pending authorization).

## 6. Step 2b — what it costs (PERF)

| measurement | command shape | result |
|---|---|---|
| warm `chimera models`, registry source | `hyperfine --warmup 2 --runs 10 -N` | **308 ms ± 16 ms** |
| warm `chimera models`, models.dev source | same | **267 ms ± 8 ms** |
| cold first run, empty cache (fetches models.dev api.json, 10 MB) | `time -p`, one-shot | **1.06 s** |
| real deliberation, warm | `chimera run ... -f simple --json` | 40.1 s wall / 2.33 s user (model-bound) |

Registry parsing of 1992 rows costs ~41 ms against the models.dev path — imperceptible; the
cold path is one whole network fetch on the first ever run. **No PERF row is filed: nothing
here is slow enough for a user to feel.** No profiling was run because no number justified it.

## 7. Repro commands (all read-only)

```bash
REPO=/home/kara/chimera-v2; S=/tmp/chv2-df25       # scratch config + fixtures
# contract legs (L0-L11): see /tmp/chv2-df25/probe_source.sh
CHIMERA_CONFIG=$S/chimera.yaml CHIMERA_LOG_LEVEL=info PYTHONPATH=$REPO/src \
  $REPO/.venv/bin/python -m chimera models 2>&1 | grep registry_source
# explicit-missing arm
CHIMERA_TASK_ROUTER_MODELS_PATH=$S/reg/nope.jsonl ... chimera models       # warning + reason
# price provenance
PYTHONPATH=$REPO/src $REPO/.venv/bin/python /tmp/chv2-df25/pricing_provenance.py
# trace cost source
CHIMERA_CONFIG=$S/chimera.yaml ... chimera run "Reply with exactly: PONG" -f simple --json
```

## 8. What holds (credit)

- The env-var contract: authority of the explicit path, line-numbered diagnostics for every
  malformed-input class, quiet fallback when nothing is configured, rc=0 throughout.
- The adapter itself: 1992-row registry → 838 live rows, 25 provider blocks, zero silent drops.
- Fresh install on a bare box: 31 s, no sudo, no toolchain, `config init` + `models` both work.
- Deliberation correctness is unaffected — both D-legs answered `PONG` with clean traces
  (`finish_reason: stop`, no worker failures); only the reported price differs.

## 9. Deploy parity

`/health` reports `635d282`, HEAD is `3338e10` (resolves, ancestor). Material diff
(`src/ scripts/ tests/ pyproject.toml`) is **`pyproject.toml` only, and it is comment-only**
(a dependency-census comment block; every changed line starts with `#`). Per the documented
rule this is a STALE classification with an explicit deferral: **no reload performed from a
read-only dogfood lane** — the supervising foreman owns the restart decision.
