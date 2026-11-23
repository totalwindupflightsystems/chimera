# Evidence — run 35 (tick chimera-v2-dogfood-2026-11-23-14-28-25)

Provenance: captured 2026-11-23 on the controller (host `kara`), driving the LIVE deployed
Chimera instance on 127.0.0.1:8765 (serving commit `0eb9232`, which contains the DF-CHIMERA-V2-130
fallback fix) and the PATH-installed CLI v0.3.0. The graded tree is HEAD
`925af817064c55c26951ef1ad12ded0103ab0b00` (manifest `manifest-controller.txt`: 619 files,
sha256 20ce853d1ad44fb5834ff46b6dd7cdbdf0eb23fa1ef826135a338ee3cf349140). Files copied verbatim
from `~/.hermes/cache/scratch/dogfood-cv2-run35/` — no transformation, no rename.

The auth header file is deliberately NOT here: the deployed key was read from the server process
environ into a shell variable and staged at mode 600 in scratch; it is never echoed and never
committed. Leak scan over this directory (`Bearer <token>` / `sk-…` patterns) returned zero hits.

## Files

- `cli-cold.out/.err/.time` — CLI from `~` (no config): RC=2, 0.39 s, refusal text. The P5 row's evidence.
- `cli-c2.out/.time` — CLI from repo dir, default `auto` formation: RC=0, 79.01 s, JSON answer. DF-137's baseline arm.
- `cli-speed.out/.err/.time` — same prompt, `--formation speed`: RC=0, 5.77 s. DF-137's remedy arm.
- `api-cold.json/.time`, `api-warm.json/.time` — REST `/v1/deliberate`, `speed`, idle-cold 3.75 s / warm 4.61 s; full traces.
- `api-quick.json/.time` — `quick` formation (hermes provider, recovered by call time): 9.14 s, all 3 workers answered.
- `api-dead.json/.http/.time`, `api-dead-resp.json` — the DF-130 live re-verification arm: `allowed_models` forced onto the credential-dead cliproxy; both workers fail after 3 attempts, HTTP 200 + real answer in 3.63 s; `trace.worker_failures` full text; `degraded_reasons=[]` (DF-CHIMERA-V2-111-R2's evidence).
- `oai-req.json/oai-resp.json/.http/.time` — OpenAI-compatible `/v1/chat/completions`, `model=speed`: 200, 3.54 s, `chimera_degraded_reasons` present.
- `err-formation-resp.json`, `err-t-resp.json`, `err-empty-resp.json` — error-contract arms: 422 unknown formation, 400 malformed X-Chimera-Timeout, 422 missing prompt.
- `head.txt`, `manifest-controller.txt` — tree binding for the graded commit.

## Re-run hints

CLI arms need the repo cwd (or `CHIMERA_CONFIG`). REST arms need the bearer header (see above —
staged, not committed) and the live instance; `api-dead.json` is byte-reusable as the request body.
Numbers quoted in docs/dogfood/2026-11-23-run35-fallback-auth-integration.md come from the `.time`
files and the trace `total_duration_ms` fields in the `.json` artifacts.
