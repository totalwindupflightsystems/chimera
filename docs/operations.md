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
