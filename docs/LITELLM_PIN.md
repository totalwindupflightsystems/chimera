# The `litellm<1.100` pin and its freshness check

Chimera depends on `litellm>=1.50.0,<1.100` (pyproject.toml:43). The upper
bound is **load-bearing**: a newer litellm silently corrupts Chimera's stdout,
and stdout is the MCP stdio transport's JSON-RPC wire. This page explains why
the cap exists, what it does *not* protect, how the freshness check decides
whether the cap can be lifted, and the exact update procedure.

| Item | Where |
|------|-------|
| The requirement and its rationale | pyproject.toml:30-43 |
| The same specifier in the lock file | uv.lock:620 (metadata) and uv.lock:1499 (resolved `1.99.4`) |
| Freshness check | `scripts/litellm_pin_check.py` |
| Cron-shaped wrapper | `scripts/litellm_pin_check_cron.py` |
| Runtime guard (independent of the pin) | `chimera.gateway.ensure_litellm_quiet()` — src/chimera/gateway.py:52 |
| Stdout-purity gate for a release | `scripts/probe_mcp_stdio.py` |
| Offline unit tests for the check | tests/test_litellm_pin_check.py |

## 1. Why the pin exists

### 1.1 The regression the upper bound encodes

litellm **1.100.0** replaced its plain stderr `logging.StreamHandler()` with
`LevelRoutingStreamHandler`, which routes every log record **below WARNING** to
`sys.stdout`. Chimera's own logging hygiene cannot compensate: the records are
emitted by litellm's logger, not Chimera's, and `force_stderr`-style pinning of
Chimera's sinks does not touch them.

Why that is fatal rather than noisy:

- **MCP stdio transport.** `chimera-mcp` speaks JSON-RPC 2.0 over stdout. One
  non-JSON line — an INFO record, a banner — and the client's parser receives
  garbage mid-session. The failure appears on the *first real* completion
  (a `tools/list` handshake never triggers the lazy litellm import), so a
  models-only probe passes while a real deliberation breaks.
- **Piped CLI output.** `chimera ... | jq` and any machine-readable mode read
  stdout; stray diagnostics break them the same way.

Measured evidence: `de355aa` (DEPS-008) refreshed the venv to **1.99.4**, the
maximum the cap allows, and CH-MAINT-007 measured **1.103.2** in a scratch venv
producing non-JSON-RPC stdout lines — the cap is still load-bearing today.

The lower bound (`>=1.50.0`) is ordinary floor hygiene: the code uses the
modern provider-lookup / `suppress_debug_info` surface that older releases do
not have.

### 1.2 What the pin does NOT protect

Every release in the pinned range — 1.99.4 included — still has always-on bare
`print()` paths gated by the process-global `litellm.suppress_debug_info`
(`False` by default):

- the ANSI **`Provider List: https://docs.litellm.ai/docs/providers`** banner
  in `litellm_core_utils/get_llm_provider_logic.py`, emitted even on a
  *successful* call (litellm calls the provider lookup from its own provider
  transformations, e.g. OpenRouter → `utils.supports_reasoning`);
- the **`Give Feedback / Get Help`** block in
  `litellm_core_utils/exception_mapping_utils.exception_type`, printed for
  every mapped provider error.

These are handled **at runtime, not by the pin**:
`chimera.gateway.ensure_litellm_quiet()` sets
`litellm.suppress_debug_info = True` (and `set_verbose = False`) immediately
before every completion — async path, sync fallback, and therefore the
exception-mapping path that runs inside `litellm.completion` /
`acompletion`. It is idempotent and cheap, and tests/test_litellm_stdout_suppression.py
pins the ordering.

**Both guards are required and neither is redundant.** Lifting the cap without
a green stdout probe re-opens the handler regression; removing
`ensure_litellm_quiet()` re-opens the banner/feedback leaks on *any* version.
A change that removes one must prove the other still covers the surface.

### 1.3 What a local install actually looks like today

Reproduced on this checkout (litellm 1.99.4, the max in range):

```
$ python scripts/litellm_pin_check.py --target .venv/bin/python
...
litellm: 1.99.4 | pin litellm>=1.50.0,<1.100 (cap 1.100.0)
VERDICT: INCONCLUSIVE — target litellm 1.99.4 is INSIDE the pinned range ...
banner print fired (default flag): True
banner silenced by suppress_debug_info=True: True
log routing: handler=StreamHandler info->stdout=False
```

That is the expected shape of a healthy in-range install: the **stderr**
handler is in place (so the cap is doing its job), and both bare-print paths
fire at the default flag and are silenced by the flag — which is why
`ensure_litellm_quiet()` exists.

## 2. The freshness check — `scripts/litellm_pin_check.py`

Purpose: notice when upstream litellm **fixes** the stdout pollution, so the
pin can be lifted with evidence instead of aging silently. It is entirely
offline in its default modes — no API calls, no provider keys, no network.

### 2.1 What it probes

The probe runs as a child process in the **target** interpreter (`python -c`,
stdlib only) and reports one JSON line. Each step is individually fault
isolated, so a litellm whose internals moved still yields a parsable partial
report:

| Probe key | What it does | Defect if |
|-----------|--------------|-----------|
| `banner` | calls the provider lookup with an unknown model, capturing stdout, with `suppress_debug_info` at its default (`False`) | the ANSI `Provider List` banner appears on stdout |
| `banner_suppressed` | reruns `banner` with `suppress_debug_info = True` | the banner still appears — `ensure_litellm_quiet()` can no longer save us (a defect on **any** version) |
| `feedback` | calls `litellm.utils.exception_type(...)` with a fake connection error, capturing stdout | the `Give Feedback / Get Help` block appears on stdout |
| `log_routing` | at **fd level** (`dup2` stdout/stderr to temp files) emits an INFO and a DEBUG record on the `LiteLLM` logger and reports where each landed, plus the handler class names | records land on stdout, or the handler is `LevelRoutingStreamHandler` — the exact `<1.100` regression |

### 2.2 Modes

| Mode | Invocation | Probes | Network | Use |
|------|------------|--------|---------|-----|
| installed (default) | `python scripts/litellm_pin_check.py` | the repo venv (`.venv/bin/python`), else the running interpreter | no | routine/CI-safe sanity; **always `INCONCLUSIVE` while the cap holds** |
| target | `--target /path/to/python` | any interpreter's environment | no | audit a deployment's venv, a docker image, a colleague's box |
| scratch | `--scratch` | creates a temporary venv, `pip install litellm>=1.100.0`, probes it, deletes it | **yes** | cap-boundary evidence; the only mode that can return `SAFE_TO_TEST` / `STAY_PINNED` |

`--scratch` never touches the repo venv. Without network (or when pip fails) it
degrades to `INCONCLUSIVE` with the pip error tail as the reason.

### 2.3 Verdicts and what to do

| Verdict | Meaning | Action |
|---------|---------|--------|
| `SAFE_TO_TEST` | a litellm **>= 1.100.0** was probed and showed no stdout defect on any probe that answered | evidence says the cap can be lifted — **confirm** with `scripts/probe_mcp_stdio.py` (both formations) and a real deliberation before editing pyproject.toml |
| `STAY_PINNED` | a litellm >= the cap was probed and showed at least one stdout defect | keep the cap; the reason names each defect. Re-check later (the check tracks upstream's latest) |
| `INCONCLUSIVE` | no cap-boundary evidence | typical causes: target inside the pinned range (the default run — rerun with `--scratch`), litellm not importable, unparseable version, every probe errored, scratch install failed |

`SAFE_TO_TEST` is a *permission to test*, not a release verdict: the probe
answers "does litellm print to stdout on these paths", not "does Chimera's MCP
server keep the wire clean". The second question is
`scripts/probe_mcp_stdio.py`'s job.

### 2.4 Output contract

- **stdout carries exactly one JSON line** — `"schema": "litellm-pin-check/1"`,
  sorted keys. Every other line, including human-readable progress and the
  summary, goes to **stderr**.
- Exit code is **0 for every completed check**, whatever the verdict — the
  verdict, not the exit status, carries the finding. Exit **2** only on a
  harness error (the script itself crashed, e.g. unterminated subprocess).

Parse it as:

```bash
python scripts/litellm_pin_check.py --scratch 2>/dev/null | tail -1 | jq -r .verdict
```

The report also carries `reason`, `probe_mode`, `pin_spec`, `version_cap`,
`litellm_version`, `target_python` and the full child `detail` block, so a
reader can reconstruct the finding without re-running anything.

## 3. Updating the pin safely

Treat a pin lift as a **dependency + transport** change, not a version bump.
The `pip list --outdated` row for litellm must **never** be actioned on its
own — that is precisely how the 1.100.0 regression would land.

### 3.1 Checklist

1. **Get boundary evidence.**

   ```bash
   python scripts/litellm_pin_check.py --scratch
   ```

   Requires `SAFE_TO_TEST`. Re-run it at the moment you start the lift: it
   installs upstream's *current* latest, so a verdict from weeks ago is stale.

2. **Start the change on a branch/worktree**, not the live checkout, and edit
   the requirement everywhere it is written:

   - pyproject.toml:43 — the requirement, plus the comment block at
     pyproject.toml:30-43 (rewrite it to say what is now true; do not leave a
     stale rationale above a new cap);
   - the "Deferred majors" census block in pyproject.toml, whose `litellm
     1.100+` entry states the cap is deliberate. Also re-derive the neighbours
     it pins: litellm carries the `openai<3` and `importlib-metadata<9` caps,
     so a litellm move can unblock or move those entries;
   - uv.lock — re-lock (`uv lock`) rather than hand-editing. The specifier
     appears at uv.lock:620 and the resolved version at uv.lock:1499; both
     must move together.

3. **Prove the transport on the candidate stack, from a clean environment.**
   A gate verified only in the repo venv is not a gate — the repo venv holds
   the old pin and will happily pass while a fresh install resolves something
   else:

   ```bash
   python3.11 -m venv /tmp/pin-lift-venv
   /tmp/pin-lift-venv/bin/pip install -e ".[full]"    # or install the built wheel
   /tmp/pin-lift-venv/bin/python -m pip show litellm | head -2   # confirm the candidate

   /tmp/pin-lift-venv/bin/python scripts/probe_mcp_stdio.py /tmp/pin-lift-venv/bin/chimera-mcp
   /tmp/pin-lift-venv/bin/python scripts/probe_mcp_stdio.py --formation=speed /tmp/pin-lift-venv/bin/chimera-mcp
   ```

   Both formations must print **0** non-JSON-RPC stdout lines. Drive both on
   purpose: the leak was formation-dependent (a `simple` run was clean while
   `speed`'s OpenRouter leg printed the ANSI banner), so one formation is not
   evidence.

4. **Run a real deliberation** — not just the handshake. The probe's own depth
   call (`chimera_deliberate` on a small arithmetic prompt) is the minimum;
   for a release, also run `scripts/smoke_live.py` against a deployed/served
   build of the candidate.

5. **Update the check to the new boundary.** The pin is encoded in four places
   in the harness, and all must move together:

   | Constant / assertion | File |
   |----------------------|------|
   | `PIN_SPEC = "litellm>=1.50.0,<1.100"` | scripts/litellm_pin_check.py:93 |
   | `VERSION_CAP = "1.100.0"` (first release with the regression) | scripts/litellm_pin_check.py:98 |
   | `SCRATCH_REQUIREMENT = "litellm>=1.100.0"` | scripts/litellm_pin_check.py:101 |
   | `test_constants_match_the_pin` asserts all three | tests/test_litellm_pin_check.py:87-91 |

   Point `VERSION_CAP` at the new **upper bound** and `SCRATCH_REQUIREMENT` at
   the first release above it. If a *new* upstream stdout defect appears later,
   `VERSION_CAP` moves to that release, not to the newest version. Nothing in
   the verdict logic needs editing — `derive_verdict` compares against
   `VERSION_CAP` and the probe list is version-agnostic.

6. **Re-run the gates on the repo venv** after upgrading it: full test suite,
   `ruff check .`, and the pin check in default mode. Default mode will report
   `INCONCLUSIVE` *again* — the installed version is once more inside the
   (new) pinned range. That is expected, not a failure; boundary evidence only
   comes from `--scratch`.

7. **Record it.** Add a CHANGELOG entry naming the old and new cap and the
   measured evidence (which litellm versions were probed, which formations were
   driven), and note the change in the dependency record
   (docs/DEPS_REFRESH_2026-10-01.md is a dated artifact — write a new record,
   don't rewrite history).

### 3.2 Do not

- Do not lift the cap because a scanner reports a newer litellm exists.
- Do not delete `ensure_litellm_quiet()` "because litellm is fixed now" — it
  guards the banner/feedback paths, which the pin never covered.
- Do not run `--scratch` expecting it to alter the repo venv; it cannot, by
  design. Upgrade the venv separately.
- Do not hand-edit uv.lock's resolved version to match pyproject.toml; re-lock.

### 3.3 If it fails

`STAY_PINNED` after a candidate install is a **successful** check, not a
problem to work around: leave the requirement as it is, delete the branch's
pyproject/uv.lock edits, and keep the recorded reason (which defect, which
version) so the next check starts from evidence. On a deployed box that was
already upgraded, reinstall the pinned range (`pip install -e ".[full]"` with
the cap restored) and re-run `scripts/smoke_live.py`.

## 4. The cron wrapper — `scripts/litellm_pin_check_cron.py`

A thin, idempotent, cron-shaped wrapper that runs the check with the current
interpreter, from the repository root, and forwards every argument:

```bash
python scripts/litellm_pin_check_cron.py              # installed mode
python scripts/litellm_pin_check_cron.py --scratch    # boundary evidence
```

- **Exit code** is the check's exit code (0 completed, 2 harness error).
- **The last stdout line** is the single JSON report (`schema:
  litellm-pin-check/1`), so a cron reader can parse the verdict
  unambiguously; human-readable detail is on stderr.
- The wrapper's own interpreter does **not** need litellm: the check probes the
  repo venv (`.venv/bin/python`) by default and spawns the probe there. If the
  checkout has no `.venv`, it falls back to the wrapper's interpreter.

### 4.1 Cadence and registration

No system cron or scheduler entry is registered by this repository — the
wrapper is **ad-hoc by design**, the same precedent as
`scripts/model_sync_cron.py` (see AGENTS.md "Operations — model catalog
refresh"). The intended cadence is **monthly**: upstream litellm moves faster
than that, but the cost of the check (a venv probe, or one pip install in
`--scratch`) is only worth paying when someone is ready to act on a
`SAFE_TO_TEST`.

**Important trap:** the default (installed) mode is `INCONCLUSIVE` by
construction while the cap holds — the installed litellm is inside the pinned
range, so it cannot produce boundary evidence. A monthly cron that only runs
the default mode will emit `INCONCLUSIVE` forever and tell you nothing. Schedule
it with `--scratch` (needs network) or point `--target` at an environment that
holds a cap-boundary litellm.

Example user crontab entry (monthly, 1st at 04:17, log appended outside the
repo):

```
17 4 1 * * cd /home/kara/chimera-v2 && .venv/bin/python scripts/litellm_pin_check_cron.py --scratch >> /var/log/chimera-litellm-pin.log 2>&1
```

A reader of that log takes the last line and reads `.verdict`: `STAY_PINNED`
means "still needed", `SAFE_TO_TEST` means "start the lift checklist in
§3", `INCONCLUSIVE` usually means the run had no network or pip failed (the
`reason` field says which).

## 5. Related surfaces

- `scripts/probe_mcp_stdio.py` — the release gate that proves the real
  `chimera-mcp` server keeps stdout pure end-to-end (initialize →
  initialized → tools/list → `tools/call chimera_deliberate`), with a
  selectable formation. This is what turns a `SAFE_TO_TEST` verdict into a
  release decision.
- `src/chimera/gateway.py` — `ensure_litellm_quiet()` and every completion call
  site that must run it first.
- tests/test_litellm_pin_check.py — offline tests of the verdict logic (no
  network, no installed litellm required).
- tests/test_litellm_stdout_suppression.py — pins the `suppress_debug_info`
  ordering and the banner/feedback suppression contract.
- pyproject.toml:30-43 — the authoritative rationale comment. If this page and
  that block disagree, the block wins; update both in the same commit.
- CHANGELOG.md — the 0.2.4 entry records the cap's discovery (found by the
  strengthened fresh-venv probe) and the 0.2.5 entry corrects the record: the
  cap and `ensure_litellm_quiet()` guard two different regressions.
