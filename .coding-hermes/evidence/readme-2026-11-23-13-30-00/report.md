# chimera-v2 README health sweep — 2026-11-23 (tick chimera-v2-readme-2026-11-23-13-30-00)

Identity, measured at probe time:
- canonical checkout /home/kara/chimera-v2, HEAD == origin/main == 0eb9232e9be888af5ef437425a925a96e18fe536
- remote origin = gitlab.readydedis.com:totalwindup/chimera (upstream origin/main), github = public mirror main; github HEAD symref -> main @ 0eb9232e (matches); origin gitlab HEAD symref -> refs/heads/master @ 81819dbb (stale 2026-09-24 branch, NOT the publication lane — the tracked upstream is origin/main)
- README.md sha256 at tip: 814b6396ab75bf80277db101ecde233e2938d59d85dac332ac3b40febd3064d6 (working file == origin/main blob)
- newest tag v0.3.0 (2026-11-21, 917969f); pyproject version 0.3.0; CHANGELOG 0.3.0 is the newest entry
- README last commit a99ede4 (2026-11-21 13:27, post-tag) — the README's own last change IS the post-tag DF-CHIMERA-V2-128 retries feature, and README:379-389 documents its chimera_retries_total family. Freshness: CURRENT (README ahead of the tag, not behind).

## Executed command matrix (fixture path — the README's own no-credential recipe, README:938-991)

All CLI/serve/probe arms ran with the audited tree's editable venv (.venv) = tip 0eb9232.
Stub + serve daemons were started, probed, and torn down by recorded PID inside single
invocations (raw logs attached). STUB-OK contract: README:976.

| Arm (command file / invocation) | rc | Verdict |
|---|---|---|
| Arms 1-2 `chimera --version` / `python -m chimera --version` | 0 | "chimera 0.3.0" printed. Both also emitted the blocked-models UserWarning (blocked_models.py:640) — DF-CHIMERA-V2-124 premise re-proven live. |
| Arm 3 `chimera serve --help` | 0 | README:343 "works either way" verified (no traceback). |
| Arm 4 `chimera config init` in scratch cwd | 0 | Created chimera.yaml from example; diff vs chimera.yaml.example = IDENTICAL (README:28 verified). |
| Arm 5 `--formation nosuchformation` | 2 | README:37 "an unknown name exits 2" verified; remedy line names available formations. |
| P1 `GET /health` | 200 | Body: {"status":"alive","uptime_models":1,"commit":"0eb9232","version":"0.3.0"} — README:353 verified. |
| P2 `GET /v1/health` | 200 | status=healthy, unhealthy_providers=[], slow_providers=[], providers map {mock: healthy} — README:396-447 semantics verified. |
| P3 `GET /v1/health/ready` | 200 | status=ready with 1 reachable provider — README:355 verified. |
| P4 `GET /v1/health/live` | 200 | README:356 verified. |
| P5 `GET /metrics` | 200 text/plain; version=0.0.4 | 68 chimera_ metric lines incl. chimera_requests_total; matches README:358-389 (families + text format 0.0.4 + the README:377 curl arm). |
| P6/P7 `GET /docs`, `GET /web/` | 200/200 | README:348-349 verified. |
| P8 `GET /.well-known/agent-card.json` | 200 | name=chimera version=0.3.0 skills=['chimera_deliberate','chimera_formations','chimera_models'] — README:390-394 verified exactly. |
| P9/P10 `GET /v1/formations`, `GET /v1/models` | 200 | /v1/models: data=['mock/m1'] + catalog map — README:868,111-112 verified. |
| P11 `POST /v1/deliberate` formation=simple | 200 | answer='STUB-OK', request_id top-level + trace.request_id, total_cost=1e-06, aggregator_model=mock/m1, worker_failures=[] — README:617-642 contract verified. |
| P12 `POST /v1/chat/completions` model=simple | 200 | id=chatcmpl-<request_id>, model echo, usage tokens; total_cost NOT in the chat body — README:655-659 claim verified exactly. |
| P13 `chimera --json` (fixture) success leg (e2e_cli3.sh, stub up) | 0 | answer=STUB-OK, answer_degraded=false, answer_error=null; ALL 12 trace keys claimed by README:60-83 present (missing subset printed as []); stdout exactly 1 line; operational warnings on stderr (README:107-109). |
| P13 `chimera --quiet` success leg | 0 | stdout exactly 'STUB-OK\n' (od -c) — README:52 verified. |
| `--json --quiet` both flags | 2 | README:109 usage error verified. |
| Degraded-path leg (accidental first control, no key exported): `chimera --json` / `--quiet` with fixture but unreachable provider | 2 / 2 | answer_degraded=true, answer_error carries the upstream reason, --quiet stdout EMPTY (od -c 0 bytes) — README:93-96 contract verified on the real failure path. Note: the first --json control also failed because the stub was down (connection error) — probe defect, not product. |
| P14 `pytest tests/test_credential_source.py -k documented_local_fixture -q` | 0 | 4 passed, 25 deselected — docs/CONFIG.md #minimal-local-fixture regression arm green. |
| SMOKE `python scripts/smoke_live.py --base-url http://127.0.0.1:18082 --formation simple` | 0 | SMOKE PASS; deployment parity CURRENT (running commit 0eb9232 == origin/main resolution); providers 1/1 healthy; deliberation returned STUB-OK — README:492-528 verified end-to-end. |
| PYRECIPE README:125-134 Python block run VERBATIM (CHIMERA_CONFIG=fixture per README:198, stub up) | 0 | recipe printed the answer (STUB-OK) AND 16 engine observability log lines on stdout (pyblock-recipe.out); result.trace.total_cost / request_id / worker_failures all resolved via attribute probe. README:125-134 mentions none of the three attributes (grep false on all three) — DF-CHIMERA-V2-115 premise still live; the stdout interleaving is the new doc finding (config.py:273 use_stdout: bool = True; DF-CHIMERA-V2-113 fixed honoring the setting, the default still serves stdout). |
| README:110 `chimera formations` / `chimera models` | 0/0 | Rich tables render (README:110 "tables are unchanged" — no regression). |
| README:610 line claim | — | quick-panel defined at chimera.yaml.example lines 55-62 exactly as cited. |
| README:923 (323 models / 16 prefixes, measured 2026-10-19) | — | Coherent with docs/CONFIG.md:898-899 (identical dated claim); dated historical class. |
| refire scripts: link check, anchor check, structure census | 0 | local_missing=0 external_non_200=0 (all 5 badges 200 incl. CoC 2.0 badge); anchors_checked=12 broken=0; H2 census: 15 H2 sections, no TOC by design (structure questions what/why/build/run/serve/test/install/limits all present after README-8/README-7 fixes). |

## Release boundary / freshness

- v0.3.0 = 917969f (2026-11-21 09:04 -05). 40 commits post-tag to origin/main: board/docs bookkeeping plus ONE product feature (a99ede4 DF-CHIMERA-V2-128 retry counters — documented in the README already) and merged test fixes. CHANGELOG [Unreleased] still reads "Nothing yet" at tip 0eb9232 while the tree carries the post-tag feat — covered by pending RELEASE-FINDING-2026-11-21-005 (names DF-116/DF-127; DF-128/a99ede4 is a third post-tag product commit — note left on that row).
- pyproject version 0.3.0 == tag == PyPI badge target. No version drift found in the README.

## Unverified this sweep (each with reason)

- pipx install / fresh `pip install chimera-deliberation[full]` from PyPI: not re-run (global side effect / network install). Covered by the closed install leg SKIPPED-INSTALL-CHIMERA-V2-21 (2026-11-21, .coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/).
- chimera-mcp execution (stdlib run): gate-blocked twice by the unattended surface (compound with `echo |` + inline python died in consent-timeout); the invocation never ran. UNVERIFIED, reason = api-server consent gate.
- Docker arms (README:719-733 docker build/run/compose + CHIMERA_PORT): not run — daemon + minutes-long network build; covered by completed README-13 fix verification range. UNVERIFIED this fire.
- Live quickstart curl example (README:138-141, model auto on a real deployment): not run against the live 127.0.0.1:8765 instance because it consumes real provider quota.
- Live-instance endpoints beyond /v1/health (e.g. the README:377 localhost metrics curl): gate-blocked compound call; UNVERIFIED.
- Ambient note: the probe shell inherited CHIMERA_API_KEY, which made `chimera serve` print its documented unauthenticated warning (README:147-150) — matched, not a defect.
