import json, pathlib

B = pathlib.Path("/home/kara/chimera-v2/.coding-hermes/board/tasks.jsonl")
EV = ".coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume"

TITLE = ("[P1] The live deployment cannot answer a single deliberation: deepseek balance is empty, "
         "/v1/health knows it (error_class=quota), yet every formation still picks deepseek - "
         "8 providers and 48 models configured, zero fallback")

REASONING = (
"Real-use arm against the deployed service on 127.0.0.1:8765 (not a test): POST /v1/deliberate with "
"formations speed, simple and auto each returned HTTP 502 in 2.1-9.1s. Body: 'no usable answer produced. "
"Upstream error: deepseek/deepseek-v4-flash call failed: ... Insufficient Balance'. /v1/health already "
"reports status=degraded, unhealthy_providers=[cliproxy,deepseek], providers_configured=8, "
"models_configured=48, details.providers.deepseek.error_class=quota.\n"
"Escalation measured on the same live service: adding allowed_models=[z-ai/glm-5] still 502 (2 calls, "
"9.05s / 8.89s); adding dispatcher_model=z-ai/glm-5 AND aggregator_model=z-ai/glm-5 still 502 "
"(2 calls, 8.31s / 7.06s) - the failure message still names deepseek-v4-flash, a model the caller "
"never asked for.\n"
"Mechanism: the engine treats a provider as usable when a credential RESOLVES, not when the provider "
"answers. src/chimera/engine.py:431 chooses 'fallback = default_worker if default_worker in usable "
"else next(iter(usable)))', and deepseek is 'usable' because credential_sources.deepseek="
"hermes_dotenv_fallback. DF-CHIMERA-V2-6 closed the presence-vs-validity hole at the credential gate; "
"the selection path still only tests presence, so a billing-empty provider is picked every time and "
"nothing consults the health snapshot the same process just produced.\n"
"User-felt: a person who opens the documented quickstart today gets no answer at all, in any "
"formation, and the 502 suggests they fix a model they did not choose."
)

AC = ("1. When a provider used by a formation reports a quota/auth error in /v1/health, a deliberation on "
"that formation still produces an answer from a healthy configured model, OR fails with a machine-readable "
"reason that names every fallback attempted. 2. The selection path consults provider health (not only "
"credential presence); cite the exact code changed and prove the old behaviour red with the recorded health "
"snapshot. 3. A test drives the live failure shape: provider A quota-dead, provider B healthy, formation "
"whose defaults name A, assert HTTP 200 with stages served by B. 4. /v1/health keeps reporting the quota "
"condition rather than masking it once failover works.")

NOTE = ("Filed by dogfood run 34 against the deployed instance (commit f0a34a2, see DF-CHIMERA-V2-134). "
"Reproduce with the four curl calls recorded in run34-results.txt and the live-*.json bodies in the same "
"evidence dir. This is the run's headline: the product is 100% unavailable for real use while its own "
"health endpoint is honest about why.")

lines = B.read_text().splitlines(True)
out, hits = [], 0
for line in lines:
    row = json.loads(line)
    if row.get("id") == "DF-CHIMERA-V2-130":
        hits += 1
        row["title"] = TITLE
        row["reasoning"] = REASONING
        row["acceptance_criteria"] = AC
        row["foreman_note"] = NOTE
        row["capability_tags"] = ["dogfood", "reliability", "failover", "health"]
        row["detail"]["evidence"][0]["artifacts"] = [
            f"{EV}/run34-results.txt",
            f"{EV}/metrics-final.txt",
        ]
        out.append(json.dumps(row) + "\n")
    else:
        out.append(line if line.endswith("\n") else line + "\n")
assert hits == 1, f"expected 1 row, edited {hits}"
B.write_text("".join(out))
print("edited rows:", hits, "total lines:", len(out))
