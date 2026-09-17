# Local CLI proxies as a provider (`claude-code-router`, `one-api`, `new-api`)

A **local CLI proxy** is a process on the operator's own machine that fronts one
or more upstream LLM providers behind a single, stable, OpenAI-compatible
endpoint — the tool you install so that editors, CLIs and scripts all talk to
`http://127.0.0.1:3456` instead of each vendor's SDK. `claude-code-router` is
the popular one for coding agents; `one-api` / `new-api` are the common
multi-tenant alternates.

Using one as a Chimera provider needs **no adapter code**: Chimera already has
every shape required — a generic `base_url` provider branch
(`resolve_litellm_model`), a loopback/keyless convention
(`_is_local_base_url`, `provider_api_key_env`) and a catalog id → wire id rule.
This page is the class recipe: what the proxy must expose, how to wire it, how
the model id travels, and the measured behaviour of the reference proxy.

The ready-to-edit entry lives in `chimera.yaml.example`:

```yaml
providers:
  cliproxy:
    base_url: http://127.0.0.1:3456/v1
    # api_key_env: CLIPROXY_API_KEY   # only for a proxy that enforces a token

models:
  cliproxy/deepseek,deepseek-v4-flash:
    categories: { ... }
    cost_tier: budget
    provider: cliproxy
    enabled: true
```

## What a supported proxy must expose

| Surface | Required | Notes |
| --- | --- | --- |
| `POST /v1/chat/completions` | **yes** | OpenAI-shaped request (`model`, `messages`, optional `temperature` / `max_tokens` / `stream`) and OpenAI-shaped response (`choices[0].message.content`). Extra vendor fields in the response are ignored by Chimera. |
| `GET /v1/models` | no | Nice for discovery, never required — Chimera routes by the **configured** catalog id, not by a listing. `claude-code-router` 1.x answers this route with `404 Route GET:/v1/models not found`. |
| Auth on the endpoint | no | Keyless loopback is normal and supported. A token-enforcing proxy is wired through `api_key_env` instead (below). |
| Reachability from the Chimera process | **yes** | The process must be running and reachable at the configured `base_url`. |

Anything that speaks that surface can be a provider, which is the whole point:
the integration is configuration, not code.

## Wiring it into Chimera

1. **`providers.cliproxy.base_url`** — the proxy's OpenAI base, i.e. the URL
   *before* `/chat/completions` (`http://127.0.0.1:3456/v1`). Because
   `cliproxy` is not a LiteLLM-native prefix, the configured `base_url` is what
   routes the call: no gateway fallback, no LiteLLM default host.
2. **The catalog id is the proxy's id, prefixed once.** Chimera strips exactly
   one leading `cliproxy/` and sends the remainder verbatim as the wire model:

   | Catalog id (`models:`) | Wire model sent to the proxy | Upstream model in the request |
   | --- | --- | --- |
   | `cliproxy/deepseek,deepseek-v4-flash` | `deepseek,deepseek-v4-flash` | `deepseek-v4-flash` (rewritten by the proxy) |

   The wire model is what the trace prints as `wire_model`
   (`openai/deepseek,deepseek-v4-flash` — the `openai/` prefix is LiteLLM's, not
   the proxy's). Ids that do **not** carry the provider prefix fall back to the
   innermost `/`-segment, so **always** write the catalog id as
   `cliproxy/<the proxy's own id>`.
3. **Scores describe the upstream model, not the proxy.** The `categories:`
   block is what the selector uses to schedule work; copy the scores of the
   model the proxy actually fronts, and move the entry (id + scores) when you
   repoint the proxy.
4. **A keyless provider is not auto-selectable by default.** With the default
   `auto_formation.restrict_to_credentialed_providers: true`, a loopback
   provider with no key resolves no credential (measured:
   `provider_credential_resolved(cfg, "cliproxy") == False`), so the `auto`
   formation will not assign it to a stage. Either pin the stage
   (`--stage-models '{"worker_1":"cliproxy/<id>"}'`, or a formation's
   `worker_models`), or set `auto_formation.restrict_to_credentialed_providers:
   false` to let the full catalog — keyless proxies included — take part. A
   **keyed** proxy (`api_key_env` + the variable exported) resolves a
   credential and needs none of this.

## Credentials: keyless loopback vs keyed

Chimera treats **loopback `base_url` + no `api_key` / `api_key_env`** as a
keyless local endpoint — `provider_api_key_env` returns `None` ("no env var can
be named honestly") instead of inventing `CLIPROXY_API_KEY`. That is the shape
shipped in `chimera.yaml.example`.

Two measured caveats, both worth knowing before you debug:

- **A keyless proxy still needs a placeholder in the environment for the run.**
  The generic branch pins `custom_llm_provider="openai"`, and LiteLLM's OpenAI
  SDK path refuses to start a call with no credential at all — keyless proxy,
  no env credential, and the stage fails with
  `Missing credentials. Please pass an api_key ... or set the OPENAI_API_KEY
  environment variable.` (measured). Pass a throwaway value that the proxy
  ignores: `OPENAI_API_KEY=local chimera ...`.
- **A token-enforcing proxy names its variable.** `claude-code-router` **3.x**
  always requires a client token (measured below), and `one-api` / `new-api`
  normally do too. Set `api_key_env:` on the provider and export the token:

  ```yaml
  cliproxy:
    base_url: http://127.0.0.1:3456/v1
    api_key_env: CLIPROXY_API_KEY
  ```

  Keys stay in the environment: never inline a real token in `chimera.yaml`.

## Worked example — `claude-code-router` 1.0.73 (measured)

Measured 2026-09-17 on this host. Install **outside** the repo — the proxy must
not hold the checkout as its working directory (it writes SQLite/log files next
to its cwd):

```bash
mkdir -p /tmp/ccr-lab && cd /tmp/ccr-lab
npm init -y && npm i @musistudio/claude-code-router@1.0.73     # 1.0.73 = last 1.x
# global install works too: npm i -g @musistudio/claude-code-router@1.0.73
```

Configure it at `~/.claude-code-router/config.json` (1.x schema — the router
target is written `provider,model`):

```json
{
  "LOG": false,
  "HOST": "127.0.0.1",
  "PORT": 3456,
  "Providers": [
    {
      "name": "deepseek",
      "api_base_url": "https://api.deepseek.com/v1/chat/completions",
      "api_key": "<the upstream provider key>",
      "models": ["deepseek-v4-flash"]
    }
  ],
  "Router": {
    "default": "deepseek,deepseek-v4-flash",
    "background": "deepseek,deepseek-v4-flash",
    "think": "deepseek,deepseek-v4-flash",
    "longContext": "deepseek,deepseek-v4-flash"
  }
}
```

> ⚠️ **`"LOG": true` writes the upstream credential to disk.** Measured on
> 1.0.73: with logging on, every forwarded request is logged with its headers
> intact — `"msg":"final request"` records
> `headers.authorization: "Bearer <the upstream provider key>"` in clear text
> under `~/.claude-code-router/logs/ccr-<date>.log`. Treat that switch as
> "hand the provider key to anything that can read this host", which is why the
> example above ships `false`; the log excerpt further down was captured with it
> turned on for diagnosis. If you do enable it, keep the log directory out of
> backups, syncs and shared paths (mode `700`/`600`) and rotate it after
> debugging. The same question applies to any proxy you point at a paid
> upstream — check its request-logging switch before wiring it in.

Start it (the cwd stays outside the repo) and probe:

```bash
cd /tmp/ccr-lab
node node_modules/@musistudio/claude-code-router/dist/cli.js start
# ⚠️ API key is not set. HOST is forced to 127.0.0.1.
# Loaded JSON config from: ~/.claude-code-router/config.json
# 🚀 LLMs API server listening on http://127.0.0.1:3456
```

Measured probe output (raw):

```text
$ curl -s http://127.0.0.1:3456/v1/models
{"message":"Route GET:/v1/models not found","error":"Not Found","statusCode":404}

$ curl -s -X POST http://127.0.0.1:3456/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"deepseek,deepseek-v4-flash","messages":[{"role":"user","content":"Reply with the single word: PROXY-OK"}],"max_tokens":300}'
{"id":"649d1608-...","object":"chat.completion","model":"deepseek-flash",
 "choices":[{"index":0,"message":{"role":"assistant","content":"PROXY-OK",
 "reasoning_content":"We need answer single word PROXY-OK. ..."},"finish_reason":"stop"}],
 "usage":{"prompt_tokens":40,"completion_tokens":21,"total_tokens":61}, ...}
HTTP 200
```

Note the two things that shape the recipe: the proxy serves **no**
`/v1/models`, and the id it accepts is its own `provider,model` router target —
the bare upstream id is a hard 404:

```text
$ curl -s -X POST ... -d '{"model":"deepseek-v4-flash", ...}'
{"error":{"message":"Provider 'deepseek-v4-flash' not found ..."}}   HTTP 404
```

Then a real Chimera run through it (config copied out of the repo first, per the
local-config rule):

```bash
cp chimera.yaml /tmp/cliproxy-chimera.yaml     # add the cliproxy provider + model
OPENAI_API_KEY=local .venv/bin/chimera -f simple -c /tmp/cliproxy-chimera.yaml --json \
  --stage-models '{"worker_1":"cliproxy/deepseek,deepseek-v4-flash","worker_2":"deepseek/deepseek-v4-flash","aggregator":"deepseek/deepseek-v4-flash"}' \
  "In two sentences, explain why a local CLI proxy in front of LLM providers is useful."
```

The trace attributes the proxied stage (measured):

```text
worker_1   model=cliproxy/deepseek,deepseek-v4-flash  provider='cliproxy'
           wire_model='openai/deepseek,deepseek-v4-flash'
           api_base='http://127.0.0.1:3456/v1'   tokens_in=334 tokens_out=1558
aggregator model=deepseek/deepseek-v4-flash           provider='deepseek'   (merged answer)
worker_failures: []
```

and the proxy's own log shows the request it forwarded upstream — the
independent half of the proof:

```text
req-1: IN  POST /v1/chat/completions
req-1: FWD -> https://api.deepseek.com/v1/chat/completions  model=deepseek-v4-flash msgs=1
req-1: DONE status=200 in 5463ms
```

Negative control: stop the proxy, re-run the same command, and the proxied
stage fails immediately with `Connection error` / `tokens_in=0` while the rest
of the formation still runs — i.e. the passing run really did depend on the
proxy and was not served by a fallback provider.

## Class alternates

| Proxy | Why you would pick it | Wiring notes |
| --- | --- | --- |
| `claude-code-router` | Coding-agent oriented; per-task router rules (`default` / `background` / `think` / `longContext`); one upstream key per provider entry. | 1.x: JSON config at `~/.claude-code-router/config.json`, keyless by default, id is `provider,model`. 3.x: configuration moves into `~/.claude-code-router/config.sqlite` (a legacy `config.json` is adopted once, then archived), and the gateway **always** requires a client token — the spawned gateway process is started with `AUTH_ENABLED=true`, `AUTH_MODE=static_api_key`, `AUTH_REQUIRED=true` hardcoded, and a keyless call answers `{"error":{"message":"Missing auth token header: authorization"}}`. Use `api_key_env` there. |
| `one-api` / `new-api` | Multi-provider, multi-user gateways: channel pooling, quotas, token management, a web console. | Same contract: point `base_url` at `/v1`, create a token in the console, and set `api_key_env` to the variable holding it. Catalog ids use the upstream model name the gateway is configured to expose. |
| LiteLLM proxy, vLLM, `llama.cpp` server, Hermes gateway | Same class: an OpenAI-compatible endpoint on a port you control. | Identical shape — `base_url` + optional `api_key_env`; only the served model ids differ. |

## Verifying an integration

```bash
# 1. the proxy answers, and with which ids
curl -s http://127.0.0.1:3456/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"<candidate id>","messages":[{"role":"user","content":"ok"}],"max_tokens":8}'

# 2. Chimera reaches it, and the trace says so
chimera -c /tmp/cliproxy-chimera.yaml --json --stage-models '{"worker_1":"cliproxy/<id>"}' "<prompt>" \
  | python3 -c 'import json,sys; [print(s["stage_id"], s["provider"], s["wire_model"], s["api_base"]) for s in json.load(sys.stdin)["trace"]["stages"]]'
```

A stage is only proven to have traversed the proxy when its trace line shows
`provider='cliproxy'` with a non-empty `wire_model` / `api_base` **and** the
proxy's own log records the forwarded request. A degraded stage prints empty
`provider` / `wire_model` / `api_base` values and a `worker_failures` entry
quoting the upstream error — read that error before assuming the wiring is wrong:
`Provider 'x' not found` is an id mismatch, `Missing credentials` is the LiteLLM
placeholder above, `Missing auth token header` is a keyed proxy.

## Measured limitations

- `claude-code-router` 1.x implements no `GET /v1/models`; take served ids from
  its config/UI. Nothing in Chimera needs the listing, but tooling that
  auto-discovers against `base_url` will see the 404.
- The npm package version (`1.0.73`, `ccr -v`) and the HTTP banner
  (`{"message":"LLMs API","version":"1.0.51"}`) disagree — the banner constant
  lags the release. Record the npm version when you report a measurement.
- `claude-code-router` 3.x's gateway is not keyless-capable by configuration:
  the hardcoded auth above is set by the launcher, so plan for `api_key_env`.
- A keyless proxy still needs the environment placeholder described under
  *Credentials*; that requirement comes from Chimera's LiteLLM path, not from
  the proxy.
- `"LOG": true` captures the upstream `authorization` header — i.e. the
  provider key itself — in plain text under `~/.claude-code-router/logs/`
  (measured on 1.0.73, where the files were also group/other-readable). Keep
  logging off by default and that directory out of any backed-up or shared
  path.
