#!/usr/bin/env bash
# File dogfood run 34 findings as board rows. No repo code is touched.
set -eu
cd /home/kara/chimera-v2
B=.coding-hermes/board/tasks.jsonl
EV=.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume
RUN=chimera-v2-dogfood-2026-11-20-06-01-48
E1=$EV/run34-results.txt
E2=$EV/stub-arrivals.jsonl
E3=$EV/probe_abandon.sh
E4=$EV/fixture.yaml
E5=$EV/stub_slow.py
E6=$EV/metrics-final.txt

boardctl -C . create --id DF-CHIMERA-V2-130 --priority P1 --type bug --complexity 4 \
  --status pending --capability-tags dogfood,reliability,failover,health \
  --evidence-run-id "$RUN" --evidence-artifact "$E1" --evidence-artifact "$E6" \
  --title "[P1] The live deployment cannot answer a single deliberation: deepseek balance is empty, /v1/health knows it (error_class=quota), yet every formation still picks deepseek - 8 providers and 48 models configured, zero fallback" \
  --reasoning "Real-use arm against the deployed service on 127.0.0.1:8765 (not a test): POST /v1/deliberate with formations speed, simple and auto each returned HTTP 502 in 2.1-9.1s. Body: 'no usable answer produced. Upstream error: deepseek/deepseek-v4-flash call failed: ... Insufficient Balance'. /v1/health already reports status=degraded, unhealthy_providers=[cliproxy,deepseek], providers_configured=8, models_configured=48, details.providers.deepseek.error_class=quota.
Escalation measured on the same live service: adding allowed_models=[z-ai/glm-5] still 502 (2 calls, 9.05s / 8.89s); adding dispatcher_model=z-ai/glm-5 AND aggregator_model=z-ai/glm-5 still 502 (2 calls, 8.31s / 7.06s) - the failure message still names deepseek-v4-flash, a model the caller never asked for.
Mechanism: the engine's model selection treats a provider as usable when a credential RESOLVES, not when the provider answers. src/chimera/engine.py:431 chooses 'fallback = default_worker if default_worker in usable else next(iter(usable))', and deepseek is 'usable' because credential_sources.deepseek=hermes_dotenv_fallback. DF-CHIMERA-V2-6 closed the presence-vs-validity hole at the credential gate; the selection path still only tests presence, so a billing-empty provider is picked every time and nothing consults the health snapshot the same process just produced.
User-felt: a person who opens the documented quickstart today gets no answer at all, in any formation, and the 502 suggests they fix a model they did not choose." \
  --acceptance-criteria "1. When a provider used by a formation reports a quota/auth error in /v1/health, a deliberation on that formation still produces an answer from a healthy configured model, OR fails with a machine-readable reason that names every fallback attempted. 2. The selection path consults provider health (not only credential presence); cite the exact code changed and prove the old behaviour red with the recorded health snapshot. 3. A test drives the live failure shape: provider A quota-dead, provider B healthy, formation whose defaults name A, assert HTTP 200 with stages served by B. 4. /v1/health keeps reporting the quota condition rather than masking it once failover works." \
  --foreman-note "Filed by dogfood run 34 against the deployed instance (commit f0a34a2, see DF-CHIMERA-V2-134). Reproduce with the four curl calls recorded in run34-results and the live-*.json bodies in the same evidence dir. This is the run's headline: the product is 100% unavailable for real use while its own health endpoint is honest about why."

boardctl -C . create --id DF-CHIMERA-V2-131 --priority P2 --type bug --complexity 3 \
  --status pending --capability-tags dogfood,api,config,usability \
  --evidence-run-id "$RUN" --evidence-artifact "$E1" \
  --title "[P2] lock_aggregator=true makes a request's aggregator_model override vanish silently: the field validates, no 400, no warning, and the failure message names the locked model - so a user cannot escape a dead aggregator through the API" \
  --reasoning "Two live POSTs to /v1/deliberate on 127.0.0.1:8765 carried aggregator_model=z-ai/glm-5 together with allowed_models and dispatcher_model overrides; both returned 502 in 8.31s and 7.06s with 'deepseek/deepseek-v4-flash call failed ... Insufficient Balance'. chimera.yaml:14 sets defaults.lock_aggregator: true, and src/chimera/engine.py:598-604 discards the override when the lock is set, recording it only in dispatch.dispatch_note - which exists on the success path. On a failure there is no note, no header, no warning: the caller's explicit model choice is dropped and the error blames a model they never named.
The schema advertises the field (src/chimera/api/server.py:402 'aggregator_model: str | None = None  # Override aggregator'), so the API promises a control it does not honour under the shipped config. During a provider outage this is the difference between 'one request fixes my problem' and 'edit chimera.yaml and restart'." \
  --acceptance-criteria "1. Under lock_aggregator=true, a request carrying aggregator_model gets one of: HTTP 400 naming the lock, a documented precedence in which the request wins, or a 2xx whose body states the discard. Silent discard is gone in all three cases. 2. The failure path carries the same information as the success path (dispatch_note or an error field), so a 502 never names only the locked model. 3. Tests cover both lock settings and both outcomes (success and upstream failure). 4. Docs state which per-request model overrides a locked config absorbs." \
  --foreman-note "Pairs with DF-CHIMERA-V2-130: the lock is why the outage could not be worked around in-band. Decide the product question (lock wins vs request wins) before coding; if lock wins, the 400 must be explicit."

boardctl -C . create --id DF-CHIMERA-V2-132 --priority P2 --type bug --complexity 3 \
  --status pending --capability-tags dogfood,cancellation,cost,concurrency \
  --evidence-run-id "$RUN" --evidence-artifact "$E1" --evidence-artifact "$E2" --evidence-artifact "$E3" --evidence-artifact "$E4" --evidence-artifact "$E5" \
  --title "[P2] A client that walks away is not noticed: the abandoned deliberation keeps the only concurrency slot and keeps billing upstream - next request waits 6.16s behind the corpse (14.18s vs 8.54s control) and 2 upstream calls are paid for an answer nobody received" \
  --reasoning "Fixture-served instance (queue.max_concurrent: 1, max_queue_depth: 4, 4s-per-call stub that logs every upstream arrival with a monotonic timestamp): control request wall 8.54s, X-Chimera-Queue-Position 1. Second request abandoned at 2.02s (curl rc=28). Immediately retried as a user would: wall 14.18s, queue position 2 - 66% slower than control.
Upstream clock: abandoned request's worker arrived t=11.66 and was served t=15.67; its aggregator then arrived t=15.69 and was served t=19.69. The client left at t=13.58. So the abandoned request's second stage was not only completed after the client was gone - it was DISPATCHED 2.11s after abandonment, and finished 6.11s after it. Four upstream calls were bought for one delivered answer (2 wasted), and the retry spent 6.16s of its 14.18s waiting for a slot the corpse still held.
Mechanism: the deliberation path never observes the disconnection. It awaits the engine, not the request stream, so nothing in src/chimera/api/server.py calls request.receive()/is_disconnected() before or during a non-streaming run (grep for 499/client_disconnect/task.cancel finds no disconnect handling outside the queue's own wait path; a Ctrl-C'd CLI that is still queued IS cancelled cleanly - the gap is a run already in flight).
User-felt: closing the tab costs money, delays the retry, and on a small deployment (max_concurrent 1-2) blocks other users until the abandoned run finishes." \
  --acceptance-criteria "1. On client disconnect during a non-streaming deliberation, in-flight stages are cancelled, the concurrency slot is released immediately and no further upstream calls are issued for that request; proven with the run-34 fixture (abort at 2s: stub arrivals for the aborted prompt stop after the stage in flight, and the next request's wall is within ~1 stage of control instead of waiting for the orphan). 2. The cancellation is logged once per request (reason=client_disconnect) so the spend is attributable. 3. A test drives disconnect->cancel and asserts both the arrival count and the slot release; red-prove it against today's tree. 4. Streaming and non-streaming paths behave consistently, or the difference is documented." \
  --foreman-note "Reproduce: bash .coding-hermes/evidence/<run>/run34-abandon-resume/probe_abandon.sh (takes ~75s, needs a free port on 18091/18791). Stub is stdlib-only, no deps installed. Numbers above come from run34-results.txt + stub-arrivals.jsonl, not from inference."

boardctl -C . create --id DF-CHIMERA-V2-133 --priority P2 --type bug --complexity 2 \
  --status pending --capability-tags dogfood,observability,metrics,trust \
  --evidence-run-id "$RUN" --evidence-artifact "$E1" --evidence-artifact "$E6" --evidence-artifact "$E2" \
  --title "[P2] Metrics book an abandoned request as a delivered 2xx success: 3 of 3 POST /v1/deliberate requests counted status=2xx with a full duration, including the one whose client left at 2s and never saw a body" \
  --reasoning "Same run-34 fixture. /metrics after the arm reports chimera_requests_total{method=POST,route=/v1/deliberate,status=2xx} 3 and chimera_request_duration_seconds_sum 30.7469 over _count 3. Only three requests reached the endpoint in that window and one of them (ABORT1, curl rc=28 at 2.02s) was received by nobody; a fourth (CLI Ctrl-C while queued) was cancelled before dispatch and never appears at all. There is no aborted/disconnected status label, no counter, and no bucket that separates 'answered' from 'computed into the void' - so an operator reading request rate and error rate during an outage, or a user retrying a timeout, sees a healthy 100% success rate.
This is the observability half of DF-CHIMERA-V2-132: even after cancellation is implemented, the accounting has to stop calling an unreceived result a success, or the metric will keep flattering the deployment." \
  --acceptance_criteria "1. A request whose client disconnected before the response was sent is observable as such (dedicated status label, separate counter, or equivalent) and is not counted as a delivered 2xx with a normal duration. 2. The metric family is documented (docs) with the meaning of each status so an operator can compute delivered-vs-computed. 3. A test asserts the label/counter for the run-34 shape (disconnect at 2s mid-stage); red-prove against today's tree. 4. Existing dashboards/health consumers that read the 2xx counter keep working or are updated in the same change." \
  --foreman-note "Filed by dogfood run 34. Do this together with DF-CHIMERA-V2-132 (detection) or after it; the detection is the prerequisite for any honest label. metrics-final.txt is the raw scrape."

boardctl -C . create --id DF-CHIMERA-V2-134 --priority P3 --type bug --complexity 2 \
  --status pending --capability-tags dogfood,deploy,freshness,trust \
  --evidence-run-id "$RUN" --evidence-artifact "$E1" \
  --title "[P3] The live instance a user reaches on :8765 runs commit f0a34a2, six commits behind HEAD 20e7598 - the run-32 and run-33 fixes are not in the build being used, and nothing in /v1/health says the build is stale" \
  --reasoning "GET /v1/health from the deployed service returns details.commit=f0a34a2, version=0.3.0. The repo is at 20e7598 and 'git rev-list --count f0a34a2..HEAD' = 6, with f0a34a2 an ancestor of HEAD. The six commits behind include e613e75 (run 32 container/PyPI finding) and 20e7598 (run 33 retry/Retry-After fix), so a person evaluating the product right now is exercising code that predates two rounds of dogfood fixes - and the health payload reports the short SHA but nothing that compares it to origin/main, so staleness is invisible unless you go and check the repo yourself.
Effect on this run: the scratch instance served from HEAD 20e7598 for the abandon/resume arm, while the :8765 arms ran on f0a34a2; the two must not be conflated when judging fixes." \
  --acceptance_criteria "1. /v1/health (or /v1/health/ready) exposes the build commit AND whether it matches the branch it was deployed from, so a stale deployment is visible without shell access to the repo. 2. The documented deploy/upgrade path names the exact command, and docs state what 'stale' looks like in the health payload. 3. A test covers the stale case (build SHA != expected SHA) and the fresh case. 4. Restarting the deployed instance stays an owner action: the row adds detection and documentation, not an unattended auto-redeploy." \
  --foreman-note "Filed by dogfood run 34. The commit is already reported; what is missing is the comparison and the docs. Do not wire an unattended redeploy of the live service."

echo "--- tail"
tail -5 "$B" | jq -r '[.id,.status,.priority,(.title[0:70])]|@tsv'
echo "--- validate"
boardctl -C . validate && echo VALIDATE-OK
