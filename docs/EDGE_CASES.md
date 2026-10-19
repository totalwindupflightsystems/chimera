# Edge Case Handling — Chimera v2

> Based on GPT-5.5 external audit, June 2026.
> Status: ✅ = implemented and tested, 📋 = documented for future

## C1 — Concurrent Request Safety ✅

**Risk:** Multiple simultaneous deliberations on one Engine instance could leak state (stage results, traces, budget tracking).

**Resolution:**
- `Engine` now validates unique `request_id` per deliberation
- Stage results are keyed by `stage_id` within each deliberation dict — no cross-request leakage
- `test_concurrency.py` covers: 2, 10, 20, and 50 concurrent deliberations with state isolation assertions

**Reproduction:**
```python
results = await asyncio.gather(*[engine.deliberate(p, "auto") for p in prompts])
assert all(r.answer for r in results)  # all complete independently
```

## C2 — Partial Worker Failure Recovery ✅

**Risk:** If 1 of 3 workers fails, the aggregator receives incomplete inputs and may produce silently corrupted output.

**Resolution:**
- `StageResult.degraded` flag marks failed worker outputs
- Aggregator `build_merge_prompt()` labels degraded workers with `[DEGRADED]` prefix
- WARNING `aggregator_partial_inputs` logged with counts (total_deps, degraded, healthy)
- Tests: 1-of-3 fails → completes with valid output; 2-of-3 → appropriate degraded response; 3-of-3 → clear error

## C3 — Token Limit Exceeded Mid-DAG ✅

**Risk:** A model hits its `max_tokens` limit mid-response, producing truncated dispatcher plans or partial worker reasoning without error indication.

**Resolution:**
- `GatewayResponse.finish_reason` field captures provider's finish reason
- `_build_response()` logs WARNING `token_limit_reached` with model + token counts when `finish_reason == "length"`
- `GatewayResponse.is_empty` flag helps downstream code detect truncation

## C4 — Empty/Null Model Responses ✅

**Risk:** Models may return empty strings, null content, missing `choices`, or `finish_reason="stop"` with zero-length output — crashing response extraction.

**Resolution:**
- `_extract_text()` handles all variants: empty choices, null content, missing message, whitespace-only
- Sets `is_empty=True` on `GatewayResponse` instead of raising exceptions
- Tests cover: empty content, null content, missing choices, stop-with-empty, reasoning fallback

## C5 — Mixed Provider Availability ✅

**Risk:** One provider is down while others work. Entire deliberation fails when it could degrade gracefully.

**Resolution:** Availability is handled in three layers, each of which keeps the run alive instead of aborting it.

**1. Dispatch-time model remapping (before any provider call):**
- Auto formations: with `auto_formation.restrict_to_credentialed_providers` enabled, a worker stage whose model has no resolved provider credential is remapped to the configured default worker (or the first credentialed, enabled catalog model) — `_apply_credentialed_only_remap`, INFO `engine_auto_credentialed_remap`. When nothing at all is credentialed the remap is skipped and an actionable `engine_auto_no_credentialed_models` warning is logged rather than guessing a model.
- Known-bad keys: `_apply_unblocked_worker_models` replaces a worker whose credential is *blocked* (credential/guardrail class, with a stored fingerprint that still matches the resolved key) using `_unblocked_worker_fallback` — default worker → default aggregator → first enabled, credentialed, unblocked catalog model. It runs last, so a known-bad key outranks an explicit `stage_models` choice, and the block self-clears once the key is replaced (fingerprint no longer matches, `_credential_block_active`).

**2. Mid-DAG stage failure → degraded stage, DAG continues:**
- `Engine._execute_stage()` catches `TimeoutError`, `GatewayError` and `BudgetExhaustedError` and returns `_degraded_stage(...)` instead of raising: a `StageResult(degraded=True)` whose text is `[stage <id> (<model>) unavailable: <error>]` and whose `response.metadata` carries `{"degraded": True, "stage_id": ..., "error": ...}` with zero tokens and zero cost.
- The wave scheduler's readiness rule is "every `depends_on` id is present in `results`", so a degraded result still satisfies dependents: the remaining workers and the aggregator run on the partial panel. (How the aggregator consumes those partial inputs is C2.)
- Aggregator/merge/audit stages get two extra attempts in `_handle_stage_failure()` before degrading: (a) same stage re-run on `defaults.default_aggregator` (`engine_stage_retry_ok`), (b) same model with `output_schema=None` — plain text — which recovers providers that reject `json_schema`/`json_object` (`engine_stage_retry_plaintext`). Worker stages are not retried on a second model at runtime; their fallback is the dispatch-time remap above.
- Dispatcher unavailability: `Dispatcher._call_dispatcher()` swallows the `GatewayError`, logs `dispatcher_call_failed`, and returns an empty `{}` payload; `parse_dispatch_result()` then falls back to the preset/custom DAG (`fallback_dag`) or the built-in minimal formation, marking `DispatchResult.source="fallback"` with a `fallback_reason` (`malformed_json` or `invalid_dag: <error>`). The deliberation proceeds on a known-good structure — it does **not** pick a second dispatcher model.
- Transient upstream failures (429/5xx/network) are retried inside the gateway first (F7 exponential backoff, `retry.max_attempts`), and Anthropic models route through the OpenRouter fallback (F8), so a blip degrades far less often than a hard outage.

**3. Degradation is surfaced, never hidden:**
- Aggregator `build_merge_prompt()` labels each failed dependency `[DEGRADED]` and logs WARNING `aggregator_partial_inputs` with `total_deps`, `degraded` and `healthy` counts.
- Trace: `DeliberationResult.answer_degraded` / `answer_error`; `trace.worker_failures` lists every degraded stage with its upstream error, and `_collect_worker_failures()` also records guardrail/credential failures in the shared block registry so the dispatcher stops selecting that model for the cooldown window.
- If the ANSWER stage itself is degraded (no usable answer), REST returns HTTP 502 with a structured error (`_NoUsableAnswerError`) and the CLI prints `deliberation produced no usable answer ...` on stderr and exits 2 rather than shipping the placeholder as the answer. In `--json`, the top-level `answer_degraded`/`answer_error` markers carry the same fact machine-readably.

**Tests:** `tests/test_engine.py` — `test_worker_failure_degrades_instead_of_crashing`, `test_aggregator_failure_retries_with_default_aggregator`, `test_stage_timeout_produces_degraded_result`, `test_one_of_three_workers_fails_deliberation_completes`, `test_two_of_three_workers_fail_degraded_answer`, `test_three_of_three_workers_fail_clear_error`, `test_worker_failures_populated_on_degraded_worker`; `tests/test_dispatcher.py` — `test_dispatcher_gateway_failure_falls_back`; plus `tests/test_cli_degraded_dispatch_warnings.py` and `tests/test_aggregator.py`.

## C6 — Deeply Nested DAG Cycles ✅

**Risk:** Self-referencing nodes, indirect cycles through aggregators, depth > 10 causing stack overflow.

**Resolution:** Cycles are detected before a single stage executes, and detection is not limited to self-references.

- `FormationDAG.topo_order()` — depth-first traversal that keeps an on-stack set; revisiting a node still on the stack raises `ValueError("Cycle detected at <id>")`. On a clean DAG it returns the dependency-first order that `Engine._run_dag()` uses as its schedule.
- `_has_cycle(dag)` — three-colour DFS (`0` = on stack, `1` = done) walking `depends_on` from every stage. A back edge into a node in state `0` is a cycle. Because it walks the whole dependency graph rather than just direct self-references, indirect cycles of any length are caught — including cycles routed through multi-level aggregator/merge/audit chains, which is exactly the case the original plan flagged as a possible gap.
- Detection runs at build time for every DAG source, before any provider call: `build_preset_dag()` (presets and config-defined formations) and `build_dag_from_dict()` (client `dag=` payloads) both end in `_validate_dag()`. That validation rejects duplicate stage ids, dependencies on unknown stages, unknown or disabled models, a formation with no worker stage or no aggregator/merge/audit stage (`DagShapeError`), and any cycle (`ValueError("Formation DAG contains a cycle")`). The REST layer maps these to HTTP 400.
- Dispatcher-authored (`auto`) plans are repaired first (`_repair_formation`: phantom edge targets injected, a missing aggregator appended over terminal workers) and then scheduled through `topo_order()` — so a cyclic plan aborts with `Cycle detected at <id>` at scheduling time, before any worker is called. `_run_dag()` additionally raises `RuntimeError("DAG has unresolvable dependencies")` if a wave produces no ready stage, which is the guard against dangling dependencies surviving validation.
- Depth: there is no fixed depth cap, and execution is iterative — `_run_dag()` loops over `remaining` and launches every stage whose dependencies are already resolved as one wave of `asyncio.create_task`. A deep chain costs scheduling rounds, not stack. The only recursion is inside the DFS used for ordering and cycle detection, whose depth equals the longest dependency path, so the practical ceiling is Python's recursion limit (thousands of stages), not 10. Chains deeper than 10 are covered by the same wave scheduler.

**Tests:** `tests/test_dispatcher.py` — `test_client_dag_cycle_rejected` (a two-stage `a → b → a` cycle is rejected by `build_dag_from_dict`), `test_topo_order_respects_dependencies`, `test_preset_simple_dag`, `test_client_dag_no_worker_stages_rejected`, `test_client_dag_no_aggregator_stages_rejected`, `test_client_dag_dangling_dependency_rejected`, `test_validate_dag_rejects_disabled_model`.

## C7 — Budget Exhaustion Errors ✅

**Risk:** Provider returns quota/billing errors that are not surfaced clearly to the user or operator.

**Resolution:**
- `BudgetExhaustedError` exception class in `src/chimera/exceptions.py`
- Gateway detects keywords: `insufficient_quota`, `billing`, `payment required`, `quota exceeded`
- Logs CRITICAL with model, provider, and error details
- Engine catches and propagates to API layer

## C8 — Config Immutability During Requests ✅

**Risk:** Config file modified while requests are in-flight → model catalog changes mid-DAG, causing stale references or inconsistent scoring.

**Resolution:**
- `Engine.__init__()` deep-copies config via `model_copy(deep=True)`
- Frozen snapshot stored as `_config` for all in-flight requests
- `_check_config_mutation()` called at start of each `deliberate()` — hashes original object against stored checksum
- WARNING `config_mutated_after_snapshot` logged if external mutation detected
- Tests: modify config after Engine init → snapshot unchanged; delete model from live config → snapshot intact; mutation triggers warning
