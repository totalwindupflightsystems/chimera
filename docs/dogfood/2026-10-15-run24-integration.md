# Dogfood run 24 — chimera-mcp (MCP stdio surface) as a real client

2026-10-15 · lane `chimera-v2-dogfood` · HEAD 12011c7 · deployed process 3c394ec (CODE-CURRENT, material diff empty)

## What this run proved

Runs 1-22 covered the CLI, REST, chat, SSE and concurrency surfaces. This run
drove the third shipped entry point — `chimera-mcp`, the stdio MCP server —
as a real MCP client would: raw newline-delimited JSON-RPC 2.0 over the
process's stdin/stdout, no SDK.

## Working client recipe (verified verbatim)

```python
import json, subprocess
p = subprocess.Popen(["chimera-mcp"], cwd=<repo-or-anywhere>,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     text=True, bufsize=0)          # unbuffered matters
def req(payload, timeout=120):
    p.stdin.write(json.dumps(payload)+"\n"); p.stdin.flush()
    # read lines until the response with the matching id arrives;
    # notifications produce NO response — never block waiting for one
    ...
def notify(payload):
    p.stdin.write(json.dumps(payload)+"\n"); p.stdin.flush()

req({"jsonrpc":"2.0","id":1,"method":"initialize",
     "params":{"protocolVersion":"2024-11-05","capabilities":{},
               "clientInfo":{"name":"my-client","version":"0"}}})
notify({"jsonrpc":"2.0","method":"notifications/initialized"})
req({"jsonrpc":"2.0","id":2,"method":"tools/list"})
req({"jsonrpc":"2.0","id":3,"method":"tools/call",
     "params":{"name":"chimera_deliberate",
               "arguments":{"prompt":"...","formation":"simple"}}})
```

Measured (cold server process, formation=simple, 3 stages):

| Operation | Time |
|---|---|
| initialize handshake | 0.73s |
| tools/list, chimera_formations, chimera_models | <0.05s each |
| chimera_deliberate (cold server) | 25.2s |
| chimera_deliberate (warm server, same prompt) | 43.1s / 47.1s |

Deliberation latency is provider-bound (the identical REST surface measured
the same range in runs 20-21); nothing here justifies a PERF row.

## Error arms (all exact on live 0.2.7)

- Unknown formation → payload `{"error":"unknown_formation","available":[6 names],"hint":...}` (DF-CHIMERA-V2-7 contract holds on MCP).
- Bare install, no config → `{"error":"config_missing","hint":"Run chimera config init..."}` (DF-CHIMERA-0917-5 contract holds).
- **Total provider failure → `isError:false`, no error field, answer = failure text; only `trace.worker_failures` carries the machine signal.** Finding DF-CHIMERA-V2-89 (P1). The CLI on the identical keyless state exits 2.
- Progressive prompting (`wait_messages`) works over MCP: 2 context messages → 3 stages, 0 failures. Params beyond prompt+formation are undocumented — DF-CHIMERA-V2-91 (P3).

## stdio purity

Zero non-JSON bytes on stdout across every leg, including the config-load
logging that previously corrupted the stream (DF-CHIMERA-0906-2). Logs go to
stderr only. Structural (force_stderr before load_config), not incidental.

## Credential-acquisition trap (DF-CHIMERA-V2-90, P2)

With `env -i`, no repo `.env`, and the untouched `chimera.yaml.example`,
deliberations SUCCEED on this host — `config.py:415` falls back to
`~/.hermes/.env` for `${VAR}` substitution. On a host without that file the
same config fails. A healthy-looking run gives no clue which source satisfied
the key. Fix direction: name the source (env / repo .env / hermes fallback)
at load time and surface it in health/trace.

## Fresh-install leg (bunker-mvp, agent chv2-df23, destroyed + residue rechecked)

- `python3 -m venv` + `pip install chimera-deliberation[full]`: rc=0, 34s (41s total with config init).
- `chimera --version` / `chimera-mcp --version` → 0.2.7 (wheel-shipped entry points both present).
- `chimera config init` works from the wheel's shipped example (no repo checkout needed).
- MCP handshake + tools/list smoke on the fresh box: exact.
- Fresh-box no-key deliberate fails with `set DEEPSEEK_API_KEY` — honest, but shaped like finding 89 (answer-text, isError:false).

## Driver scripts used (session scratch, /tmp)

`chv2-mcp-dogfood.py` (main drive), `chv2-nokey*.py`/`chv2-nohome*.py`
(failure-ladder probes), `chv2-install.sh` (bunker leg), `chv2-bunker-mcp-smoke.py`.
Board rows: DF-CHIMERA-V2-89/87/88. Log: `.coding-hermes/dogfood-log.md` run 24.
