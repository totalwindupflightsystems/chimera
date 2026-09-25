# Run 16 — Custom OpenAI-Compatible Provider Seam (2026-09-25)

**Surface:** the README's "Custom OpenAI-compatible endpoints" — pointing
Chimera at an external OpenAI-compatible gateway instead of a first-party
provider. The one documented surface runs 1–15 never drove. Two real
gateways were used, both already declared in the live config:
`hermes` (local Hermes gateway `http://127.0.0.1:8642/v1`, key via
`API_SERVER_KEY`) and `router9` (fleet 9router `http://master001:20128/v1`,
key via `ROUTER9_API_KEY`).

**Promise under test:** "Any provider Chimera does not route natively is
called through its own `base_url`, over the OpenAI-compatible SDK, using the
provider's resolved key. Exactly one leading `<provider>/` segment is
stripped before the request goes out" — and the model-id rule for
namespaced gateways: "the catalog id `router9/ds/deepseek-v4-flash` reaches
9router as `ds/deepseek-v4-flash`".

## Setup (what a user does)

Scratch instance, independent of the live service: fresh venv in /tmp,
`pip install 'chimera-deliberation[full]==0.2.7'` from PyPI (43s), a minimal
config written fresh per docs/CONFIG.md declaring both custom providers and
three catalog models (`hermes/glm-5.3-flash`,
`router9/ds/deepseek-v4-flash`, `router9/ollama/gpt-oss:20b`). Keys came
from the process environment only.

## What worked (credit)

1. **Live REST, custom worker** — `POST /v1/chat/completions` on :8765 with
   `model: simple, worker_model: router9/ds/deepseek-v4-flash`:
   "The capital of France is Paris." in 10.9s, finish stop, no worker
   failures. One leading provider segment stripped correctly.
2. **Scratch CLI, mixed custom workers** — `chimera --formation simple
   --stage-models '{"worker_1":"router9/ds/deepseek-v4-flash",
   "worker_2":"hermes/glm-5.3-flash"}'`: full 3-stage deliberation, merged
   answer, 14.6s cold / 25.6–31.1s warm, $0.0205, trace shows per-stage
   model + latency, zero worker failures.
3. **Client-defined DAG entirely on custom providers** — `--allow-custom-dag
   --dag` with 4 stages (router9 worker → hermes aggregator → router9
   worker → hermes aggregator): 61.0s sequential, correct structured answer
   ("two pros and one con of remote work"), source=custom.
4. **/v1/deliberate with custom stage_models** — 9.5s, "Pacific",
   zero failures (note: takes `prompt`, not `messages`).
5. **Resilience against malformed upstreams** (control probes first, then
   through the seam):
   - `router9/ollama/gpt-oss:20b` returns SSE chunks even when `stream` is
     not requested → Chimera consumed it cleanly (worker 17.4s, full run
     27.8s, no failures).
   - 9router's `ds/` lane appends a literal `data: [DONE]` after the
     non-stream JSON body → Chimera's lenient parse tolerates it (strict
     JSON clients would not; see DF-CHIMERA-V2-63).
6. **Trace honesty** — every run carried the real stage models and the
   merged answers were genuine merges (not pass-through of one worker).

## What broke (findings; full evidence on the board rows)

- **DF-CHIMERA-V2-58 (P1):** a credential-class block recorded without a
  fingerprint (the missing-key case) persists 7 days in the SHARED
  `~/.chimera/blocked-models.json` and can never self-clear, while the CLI
  remedy text promises "the block self-clears when the key changes". Hit
  live: my scratch instance with a valid key inherited a block written by
  another chimera process hours earlier. Escape: delete the state file
  (verified live) or use only non-default models. 4-phase repro with the
  wheel's own registry on a temp state file proves the gap and the working
  control case.
- **DF-CHIMERA-V2-59 (P2):** malformed formation yaml (`stages: 2` instead
  of `workers: 2`) silently becomes an auto preset, then fails 0.3s later
  with the misleading "Cannot build a structural DAG from an auto preset".
- **DF-CHIMERA-V2-60 (P1):** `smoke_live.py` exits 0 on a STALE deployment
  and its parity check is checkout-relative (on this shared workdir it
  printed CURRENT while origin/main was 7 material files ahead).
- **DF-CHIMERA-V2-61 (P2):** out-of-catalog custom-provider models are
  rejected with "unknown model" even though the gateway serves them; no doc
  states the catalog entry is required for dispatchability.
- **DF-CHIMERA-V2-62 (P2):** install leg SKIPPED — las-03 offline, las-02
  bunkerd stuck activating.
- **DF-CHIMERA-V2-63 (P3):** upstream (9router) defect — trailing
  `data: [DONE]` after non-stream JSON.

## Fresh-user quickstart for this seam (field-tested)

```bash
python3 -m venv venv && venv/bin/pip install 'chimera-deliberation[full]'
cat > chimera.yaml <<'YAML'
defaults:
  dispatcher: hermes/glm-5.3-flash          # point defaults AT the custom models
  default_worker: router9/ds/deepseek-v4-flash
  default_aggregator: hermes/glm-5.3-flash
formations:
  simple: {workers: 2}                      # workers:, NOT stages:
providers:
  hermes:  {base_url: http://127.0.0.1:8642/v1, api_key_env: API_SERVER_KEY}
  router9: {base_url: http://myhost:20128/v1, api_key_env: ROUTER9_API_KEY}
models:
  hermes/glm-5.3-flash: {provider: hermes, cost_tier: budget}
  router9/ds/deepseek-v4-flash: {provider: router9, cost_tier: budget}
YAML
export API_SERVER_KEY=... ROUTER9_API_KEY=...
venv/bin/chimera --formation simple "Your real question"
```

Traps learned the hard way: (a) the `models.<id>` catalog entry is REQUIRED
— a gateway model without one is "unknown"; (b) formation scalar is
`workers:` — `stages:` silently turns the preset into an auto preset; (c)
if you ever saw a credential block on the default provider, the state file
`~/.chimera/blocked-models.json` is shared by every chimera process on the
machine — deleting it is the verified escape; (d) `/v1/deliberate` takes
`prompt`, `/v1/chat/completions` takes `messages`.

## Perf

No PERF row: warm 25.6–31.1s, cold 14.6s, install 43s — all model-bound,
consistent with runs 11–15. Nothing a user would feel as a defect.

## Environment

All work in /tmp/dogfood-chimera-v2 (scratch venv + config + captures);
no repo code touched; live `~/.chimera/blocked-models.json` backed up,
temporarily removed, restored byte-identical. No credentials committed.
