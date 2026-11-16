# Chimera — Operations

The deploy, supervision and observability path for the Chimera API. If you are
reading this because the service is down, jump to [Incident path](#incident-path).

Chimera is a single service: one process (`chimera serve`) serving the REST API,
the OpenAI-compatible surface and the web UI on one HTTP listener
(`CHIMERA_PORT`, default `8765`).

## Deploy

### Container (default)

```bash
cd <checkout>
export DEEPSEEK_KEY=...            # plus any other provider keys the config uses
docker compose up -d --build
docker compose ps                   # State=healthy once the container healthcheck passes
curl -fsS localhost:8765/health     # {"status":"alive", ...}
```

What the shipped files already give you:

| file | provides |
|---|---|
| `Dockerfile` | builds the wheel, `EXPOSE 8765`, `ENTRYPOINT ["chimera"] CMD ["serve"]`, and a `HEALTHCHECK` (`--interval=30s --timeout=5s --start-period=10s --retries=3`) that probes the liveness route |
| `docker-compose.yml` | port binding, config/key env, `restart: unless-stopped`, and the container `healthcheck` |

`restart: unless-stopped` is the restart policy: Docker restarts the container
after a crash and after a host reboot, and does not restart it after an operator
`docker compose stop`. That is the whole supervision story for a containerised
deploy — there is no separate systemd unit, and none is wanted.

### Bare host (no Docker)

```bash
uv sync --all-extras
uv run chimera serve                # binds CHIMERA_PORT
```

A bare-host process has **no supervisor** unless you supply one; that is a
deliberate gap, tracked on the project board rather than papered over here. Use
`systemd` (`Restart=always`) or `tmux`/`supervisord` and point the monitor at
`/health`, below.

### Configuration

`chimera.yaml` is local-only and gitignored; a fresh checkout ships
`chimera.yaml.example`. `chimera config init` copies it. Model defaults, provider
credentials and server tuning all live there — see `docs/CONFIG.md`.

The process reads its config **once at boot**: adding a formation or flipping
`auth.enabled` takes effect only after a restart of whatever supervises the
service (`docker compose restart`, or `systemctl restart chimera` on a bare host).

## Internal service lane (fleet agents)

Chimera also runs as the fleet's zero-shot answer service: one shared instance,
reached by agents over the tailnet directly or through 9router.

### Formations meant for fleet traffic

| preset | shape | when |
|---|---|---|
| `quick-panel` | 3 flash-tier workers (`deepseek-v4-flash`, `openrouter/qwen/qwen3-coder`, `hermes/glm-5.3-flash`) → one `deepseek-v4-flash` aggregator | default agent lane: a merged answer at flash-tier prices |
| `panel` | 3 pro-tier workers (`deepseek-v4-pro`, `claude-sonnet-4.6`, `gpt-5.6-sol`) → 2 aggregators, `best_of_n` merge | escalation, when the answer is load-bearing |
| `quick` | alias of `quick-panel` | 9router strips its prefix, so the upstream model name is the bare formation name |

There is no separate budget knob: the budget cap for `quick-panel` **is** the
model tier. Every lane in it is a flash model, so one deliberation costs cents
and cannot be routed onto a quota-limited or pro lane.

Measured 2026-11-16 against the live config through the engine CLI:

```bash
$ chimera -c chimera.yaml run --formation quick-panel --json '<prompt>'
formation=quick-panel  workers=3  duration_ms=23793  tokens=74847  cost_usd=0.0121
```

3 workers across 3 providers plus the aggregator, 23.8 s wall clock, ~$0.012.

### Exposure (tailnet, not public)

The service binds loopback (`127.0.0.1:8765`). Publish it to the tailnet with
`tailscale serve` — no public ingress, no port-forward, TLS terminated by
Tailscale:

```bash
tailscale serve --bg --https=8443 http://127.0.0.1:8765
tailscale serve status
#   https://<host>.<tailnet>.ts.net (tailnet only)
#   |-- / proxy http://127.0.0.1:8765
```

`serve` (not `funnel`) keeps it reachable only to tailnet members. Revoke with
`tailscale serve reset`.

### Auth

`auth.enabled: true` with `mode: env` puts a key in front of every route except
the ones a monitor or catalog needs keylessly: `/health`, `/v1/health`,
`/v1/health/live`, `/v1/health/ready`, `/v1/models`, `/v1/formations` and
`/.well-known/agent-card.json`.

The key is `CHIMERA_API_KEY` in `.secrets/chimera.env` (never committed); either
header is accepted:

```bash
curl -s https://<host>.<tailnet>.ts.net:8443/v1/models -H "Authorization: Bearer $CHIMERA_API_KEY"
curl -s https://<host>.<tailnet>.ts.net:8443/v1/models -H "X-API-Key: $CHIMERA_API_KEY"
```

Clients that already carry it: the Hermes provider block (`api_key_env:
CHIMERA_API_KEY`) and `scripts/smoke_live.py` (`--api-key`, defaulting to
`$CHIMERA_API_KEY`). A protected route without the key answers `401`; a keyless
route answers `200` either way. A wrong or stale key is a client-side problem —
`/v1/health` stays `degraded`-free because health does not authenticate.

### 9router upstream lane

9router carries chimera as one more upstream, so any fleet agent that already
talks to 9router can name `chim/quick` or `chim/panel` instead of holding a
chimera-specific base URL:

| field | value |
|---|---|
| node type | `openai-compatible` |
| prefix | `chim` |
| base URL | `https://<host>.<tailnet>.ts.net:8443/v1` |
| api key | the same `CHIMERA_API_KEY` |
| models | `chim/quick` → formation `quick`, `chim/panel` → formation `panel` |

9router strips the prefix before forwarding, so the upstream model name is the
bare formation name — that is why `quick` exists as an alias of `quick-panel`.
Liveness: `GET /v1/models` from an agent through 9router must list both ids, and
a `POST /v1/chat/completions` with `{"model":"chim/quick"}` returns a single
merged answer (not one worker's).

## Health

Three probes, all on the API listener, all cheap to scrape:

| route | meaning |
|---|---|
| `GET /health`, `GET /v1/health/live` | process alive — always `200` when the server answers at all |
| `GET /v1/health/ready` | readiness — provider connectivity |
| `GET /v1/health` | detailed health: `status` (`healthy`/`degraded`/`unhealthy`), plus `details.providers` with per-provider latency, `unhealthy_providers` and `slow_providers` |

`/health` is what the container healthcheck uses; use `/v1/health/ready` in a
load-balancer or k8s readiness gate.

## Metrics

`GET /metrics` serves the Prometheus text exposition format (0.0.4) from the
same listener. It needs no extra port and no extra auth scheme: whatever
credential your monitor already uses for `/v1/health` works here.

| family | type | labels | meaning |
|---|---|---|---|
| `chimera_requests_total` | counter | `method`, `route`, `status` | every HTTP request served, `status` is the class (`2xx`/`3xx`/`4xx`/`5xx`) |
| `chimera_request_errors_total` | counter | `method`, `route`, `reason` | failed requests by cause: `client_error`, `server_error`, `exception` (an unhandled crash, counted separately from a deliberate 5xx) |
| `chimera_request_duration_seconds` | histogram | `method`, `route` | request latency; buckets `0.005 … 60`s |

Two properties worth knowing when you read them:

* `route` is the **route template** (`/v1/deliberate`), not the raw path, and an
  unmatched request collapses to `<unmatched>` — bounded cardinality, so a
  scanner hitting random paths cannot mint a time series per hit.
* the scrape endpoint itself is **not** counted, so monitoring traffic never
  shows up as user traffic.

### Scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: chimera
    metrics_path: /metrics
    static_configs:
      - targets: ["chimera-host:8765"]
```

If the API key requirement is enabled (`auth.enabled`), front the scrape with the
same bearer credential the health probe uses.

### The three signals that matter

1. `rate(chimera_requests_total{status="5xx"}[5m])` — a rising 5xx rate is the
   only early warning that upstream providers are failing.
2. `histogram_quantile(0.95, rate(chimera_request_duration_seconds_bucket[5m]))`
   — deliberation latency; a step change with a flat 5xx rate means provider
   slowness, not an outage.
3. `rate(chimera_request_errors_total{reason="exception"}[5m])` — anything above
   zero is a code defect: an exception escaped a handler.

## Logs

`chimera serve` emits structured JSON on stdout (docker: `docker compose logs -f`);
the MCP stdio transport forces every sink to stderr so JSON-RPC is never
corrupted. `observability.use_stdout` and `observability.level` in
`chimera.yaml` control the sink and verbosity. Langfuse tracing is opt-in and off
by default — enable it in config only when configured.

## Data and backup

Chimera owns no database of record: the deliberation state is in-process, the
board is git-tracked JSONL, and the model catalog is a committed YAML file. There
is nothing to dump. The only local state is the blocked-model registry
(`.chimera/blocked-models.json`), which is regenerable from traffic, and the
sessions directory for the web UI, which is scratch.

## Incident path

1. `docker compose ps` — is the container `Up`/`healthy`? If it restarted, the
   exit code and the last 200 log lines name the cause.
2. `curl -s localhost:8765/health` — `degraded`/`unhealthy` with a provider named
   in `unhealthy_providers` is an upstream credential/quota problem, not a
   Chimera problem; check that provider's key and balance.
3. `curl -s localhost:8765/metrics` — a 5xx rate with `reason="server_error"`
   points at a handler defect; `reason="exception"` points at a traceback in the
   logs.
4. A container that will not start: `docker compose logs --tail=100` — the most
   common cause is a missing config (`chimera.yaml` absent) or a missing provider
   key, both of which fail fast at startup by design.
