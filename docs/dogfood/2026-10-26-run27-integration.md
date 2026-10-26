# Chimera-v2 dogfood run 27 — 2026-10-26 — MCP formation selection and live delivery parity

Surface: an external MCP client using the shipped `chimera-mcp` entry point, with the `simple` and `speed` formations, plus the supervised REST deployment and the fresh-machine QA leg. Run 26 covered the delivery chain and published artifact; this run re-proved the newly restored `speed` release-gate formation on the current build and checked the live service against the canonical branch.

Verdict: SHIPPABLE for the exercised MCP and live REST paths. No new product defect was found. The bunker battery completed, but its fresh-install cell is a harness classification failure: install rc=0 successfully installed chimera-deliberation 0.2.8, then bunker-qa searched for an unrelated toolsd artifact. This corroborates the existing harness-owned QA-CHIMERA-V2-44 row; it is not a new Chimera install defect.

No product source, board state, scheduler state, visibility, permission, or credential was changed by this lane.

## Promise and real use

Promise: an AI-agent client can start `chimera-mcp` over stdio, initialize JSON-RPC, discover the tools, select a named formation, and receive a non-empty merged answer without non-JSON stdout pollution.

The independent probe drove `initialize`, `notifications/initialized`, `tools/list`, and `tools/call` with the real `chimera-mcp` binary from the repository venv. Both formations completed:

- `simple`: rc=0, `PROBE OK`, answer marker `17 * 23 = 391`, wall 17,322 ms.
- `speed`: rc=0, `PROBE OK`, answer marker `17 * 23 = 391`, wall 19,623 ms.
- stdout logs were 1,058 and 1,182 bytes; neither contained a token-shaped `sk-` value.

A repeat simple measurement was also successful: cold 25,532 ms and warm 20,727 ms. The difference is upstream/provider variance, not a Chimera-owned hot path. No PERF row is warranted: MCP startup/tool discovery is fast and the 17–26 second real deliberations are model/provider-bound.

The live supervised service also completed the documented smoke workflow: `/health` reported commit `9bdb753`, `scripts/smoke_live.py --base-url http://127.0.0.1:8765 --formation simple` returned rc=0, `SMOKE PASS`, and the merged answer `Paris is the capital of France.` The service is `CODE-CURRENT` against `origin/main` because the path-scoped diff over `src/`, `scripts/`, `tests/`, and `pyproject.toml` is empty; the commit gap is board/docs bookkeeping only.

CLI negative contract: `chimera --formation definitely-not-real run '2+2'` returned rc=2 and a clear stderr error listing the available formations. The live formation inventory exposed `audit`, `auto`, `debate`, `simple`, `speed`, and `spec-writer`; REST `/v1/formations` exposed the same named presets.

## Install leg

`bunker-qa.sh launch /home/kara/chimera-v2` ran on `bunker-mvp` with agent `5d53db3f`, testing HEAD `ab4bf7c986bf4d898bd3f4a6d2725627afbd1485`. The battery completed on agent `5d53db3f`. Its evidence says `fresh-install` FAIL because install rc=0 produced no `toolsd` artifact, while the same row records `chimera-deliberation-0.2.8` successfully installed. This is the known external harness mismatch already owned by QA-CHIMERA-V2-44, not a Chimera packaging failure. The battery also reports native suite PASS (2167 tests), clean missing-config rc=2, and `ci-act` UNVERIFIED because the agent lacked the `catthehacker/ubuntu:act-24.04` image. The collector recorded teardown recovery and a fresh `bunker list --server bunker-mvp` census no longer lists agent `5d53db3f`; the agent is gone.

The agent-side log also reported `HARNESS_COMPOSE=ok` and `HARNESS_NODE=missing`; these are harness/environment facts, not product verdicts. Installability is therefore verified by the successful package installation recorded in the evidence, while the battery's aggregate fresh-install status remains harness-red and must not be called a clean PASS.

## Reproduction commands

```text
python scripts/probe_mcp_stdio.py --formation=simple .venv/bin/chimera-mcp
python scripts/probe_mcp_stdio.py --formation=speed .venv/bin/chimera-mcp
python scripts/smoke_live.py --base-url http://127.0.0.1:8765 --formation simple
chimera --formation definitely-not-real run '2+2'   # expected rc=2
```

Evidence captured outside the repository: `/tmp/chimera-df-20261026-122906/`, including the MCP logs, summaries, CLI negative-path output, formation response, and smoke output. Install evidence: `/tmp/bunker-qa-evidence-20261026T123952Z-1330600.jsonl` and its `.meta` file.

## Run 27 addendum — fresh-install artifact identity, same tick

A second delivery of this tick independently re-checked the install battery and live HTTP surface; the earlier MCP evidence above was not repeated. The live REST path held: `GET /.well-known/agent-card.json` returned HTTP 200 with version `0.2.8`, three skills, and `streaming=false`; `/v1/formations` returned six formations; `/v1/models` returned 43 entries; `POST /v1/deliberate` with formation `simple` returned `DOGFOOD27`. `python3 scripts/smoke_live.py` exited 0 with `CODE-CURRENT` and `SMOKE PASS`. Hyperfine over ten warm agent-card requests measured `6.0 ms ± 0.5 ms` (5.5–6.9 ms). A simple deliberation measured 58.08s cold with trace duration 58070ms and a second captured run measured 98257ms; provider-bound variance, no PERF row.

The fresh-machine battery on `bunker-mvp`, agent `5d53db3f`, recorded HEAD `ab4bf7c...`, installed `chimera-deliberation-0.2.8` with rc=0, and passed the native suite (2167 tests). Its `fresh-install` cell nevertheless failed with the exact message `install rc=0 but no artifact found (toolsd not in PATH, PREFIX/bin/toolsd missing, or zero-size)`. Chimera is a Python package whose relevant console scripts are `chimera` and `chimera-mcp`; the battery is checking an unrelated artifact. The agent teardown recovered after an initial destroy failure and a final census no longer listed it. This is current-HEAD corroboration of closed `QA-CHIMERA-V2-44`, row-ready as recurrence candidate `QA-CHIMERA-V2-44-R2`; this read-only lane did not append a board row. `ci-act` remained UNVERIFIED because `catthehacker/ubuntu:act-24.04` was absent. Full evidence: `/tmp/bunker-qa-evidence-20261026T123952Z-1330600.jsonl`.

`ch:trace row=QA-CHIMERA-V2-44-R2 spec=docs/dogfood/2026-10-26-run27-integration.md#run-27-addendum wave=chimera-v2-dogfood-2026-10-26-12-29-06 test=none doc=docs/dogfood/2026-10-26-run27-integration.md prompt=none evidence=/tmp/bunker-qa-evidence-20261026T123952Z-1330600.jsonl witness=live:bunker-mvp-agent-5d53db3f+smoke-live+agent-card+deliberate verdict=none:read-only-dogfood commit=ab4bf7c986bf4d898bd3f4a6d2725627afbd1485 memory=none:foreman-writes`
