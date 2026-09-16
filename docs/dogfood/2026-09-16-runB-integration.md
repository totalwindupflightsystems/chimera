# Chimera Dogfood — Run 9B Integration Report (2026-09-16)

Ninth dogfood run; cron re-picked chimera-v2 the same day as run 9 (16:21
tick), so this run took an **additive angle** (the 2026-09-04 "run B"
precedent): everything here was either never tested before or tested against
a *different artifact* than before. Artifacts under test:

| Artifact | Version / commit | How obtained |
|---|---|---|
| PyPI wheel | 0.2.5 (published 2026-09-12) | fresh venv `pip install chimera-deliberation[full]` (26s) |
| Repo tree | 77a1b9d (= deployed `/health` commit — full parity) | fresh `git clone` in ephemeral bunker |
| Live server | :8765, commit 77a1b9d | systemd `chimera.service` |

New ground this run: (a) MCP driven on the **published wheel** with a
real-client harness, (b) the **official OpenAI python SDK** against the
OpenAI-compat endpoint (9 prior runs used curl only), (c) the **ephemeral
bunker install leg** — SKIPPED 7 consecutive times — executed and passed.

## Time-to-first-success

~25s: `pip install` (26s) overlapped probes; first real answer (SDK
chat.completions → "Paris") at 27.4s of call time. On the fresh bunker box:
clone→install 68s, first answer 11s.

## 1. MCP on the published 0.2.5 wheel — real-client verdict: CLEAN

Prior runs proved stdout purity at HEAD only; run 8 (09-11) showed 0.2.3's
published wheel polluted lazily (only under real tools/call). Re-test on
0.2.5's published artifact, `formation=speed` (the formation that triggered
the 0.2.4 pollution), real deliberation:

- initialize → serverInfo (mcp SDK 1.30.0)
- tools/list → `chimera_deliberate`, `chimera_formations`, `chimera_models`
- tools/call("Reply with exactly the word: ok", speed) → answer `ok`,
  26.2s, full trace (dispatch deepseek-v4-flash → 2 workers → aggregator)
- **0 polluted stdout lines**; 21 log lines, all on stderr

**DF-CHIMERA-0911-1 is verified FIXED on the released artifact.**

### The harness lesson (cost us one false failure)

A `printf ... | chimera-mcp` probe *closes stdin after sending*. The server
hits EOF and shuts down **before the ~25s deliberation responds**, so the
tools/call reply never arrives and the probe reports a truncated session.
This looks exactly like "server broken" and is nothing of the sort — real
MCP clients keep the pipe open. Working driver (used for the numbers above):

```python
p = subprocess.Popen([BIN], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)
def feed():                     # background thread: write requests, DON'T close stdin
    for r in requests: p.stdin.write(json.dumps(r) + "\n"); p.stdin.flush()
threading.Thread(target=feed, daemon=True).start()
while ...:                      # main thread: readline until YOUR request id answers
    line = p.stdout.readline()  # JSON-RPC lines; anything unparseable = pollution
```

Any future purity gate must use this pattern (or mcp SDK's client), never a
piped one-shot.

## 2. Official OpenAI SDK vs the OpenAI-compatible endpoint

`pip install openai` (v1.x), `OpenAI(base_url="http://localhost:8765/v1")`:

| Call | Result |
|---|---|
| `client.models.list()` | 💥 `TypeError: object of type 'NoneType' has no len()` — GET /v1/models returns a bare `{model_id: {scores...}}` dict, not `{"object":"list","data":[...]}`. Verified raw via httpx. **First real-SDK run in 9 dogfoods breaks on the first catalog call.** → DF-CHIMERA-0916B-2 |
| `client.chat.completions.create(model="simple", ...)` | ✅ works: "Paris", 27.4s. Usage block parses: 17,291 prompt / 4,976 completion tokens for an 8-word prompt — the prompt_tokens inflation (dispatch+worker prompts, DF-CHIMERA-V2-10) is visible to any SDK client doing cost accounting |
| model=`deepseek/deepseek-v4-flash` (valid catalog id) | 404 — but the message now *teaches*: "model selects a FORMATION, not a catalog model ID — use GET /v1/models" (improved since 09-11; DF-CHIMERA-0911-3 fix verified live) |

**Practical rule until 0916B-2 lands:** use the SDK for chat, plain GET for
the catalog; don't call `models.list()`.

## 3. Ephemeral bunker install (las-bunker-03) — PASSED, streak closed

7 consecutive runs recorded SKIPPED-install-bunker (port-pool exhaustion,
then gRPC :10001 + ssh :22 firewall). This cycle the host was healthy
(`systemctl is-active bunkerd` = active, Docker 26.1.5, bunker CLI 0.1.3):

```
bunker spawn --server bunker-las-03 --ttl 2h     # 1st try: deadline_exceeded (transient); 2nd: OK
agent 62a41be8 — bare Debian, x86_64, python3.13.5, non-root, no toolchains
git clone https://github.com/totalwindupflightsystems/chimera.git ~/app   → 77a1b9d ✔
python3 -m venv .venv && .venv/bin/pip install -e ".[full]"               → 68s ✔
chimera --version → 0.2.5 ✔          chimera config init → refused* ✔
env DEEPSEEK_API_KEY set → chimera --quiet 'Reply with exactly: ok' → "ok", exit 0, 11s ✔
bunker destroy 62a41be8 → destroyed, `bunker list` empty
```

*refusal is a finding, not an install failure (below). No repo visibility or
permission was touched; the public origin URL cloned as-is.

## 4. Fresh-clone config gotcha — DF-CHIMERA-0916B-4

The live internal config is **tracked in the public repo as `chimera.yaml`**
(77KB: SIMON SAYS section-spec prompts, category weights, fleet tuning;
`git ls-tree github/HEAD` confirms it's on the remote). API keys are all
`${VAR}` refs — no secret leak (checked). Two user-facing consequences:

1. `chimera config init` on a fresh clone refuses: "chimera.yaml already
   exists. Use --force to overwrite it" — the documented first-run step
   dead-ends for repo installs (works fine for pip installs, where the
   template ships inside the wheel).
2. Internal ops/prompt-engineering content is published.

A fresh clone still works as-is (the shipped config + one env var → answer
in 11s, proven in the bunker). Fix belongs to the foreman: untrack the live
config / rename to a gitignored name, keep `chimera.yaml.example` as the
only shipped template.

## 5. Release-lag recurrence #4 — DF-CHIMERA-0916B-3

README Quickstart documents `chimera --version`; published 0.2.5 exits 2
("No such option"). The flag exists at HEAD (`@click.version_option`,
d6f144c, 2026-09-14) but 0.2.4/0.2.5 shipped 2026-09-12. The pattern is the
same as DF-CHIMERA-0911-2 (marked complete): gates exist but run against
repo HEAD, never the published artifact. Remedy: cut 0.2.6 + wire the
quickstart battery (config init, --version, --quiet run) as a post-publish
canary on the PyPI wheel.

## Verdict bookkeeping

- 5 board rows filed (2 complete = prior-fix verifications, 3 pending =
  new findings), verified by read-back: DF-CHIMERA-0916B-1…5.
- Skill updated: `skills/chimera-usage/SKILL.md` v1.1.0 (lessons 27–31).
- Board IDs to reference in future runs: 0916B-2 (SDK models.list),
  0916B-3 (0.2.6 + artifact canary), 0916B-4 (untrack live config).
