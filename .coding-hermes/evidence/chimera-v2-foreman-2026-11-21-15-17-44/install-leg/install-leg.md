# Install leg — SKIPPED-INSTALL-CHIMERA-V2-21, rework attempt 2

Built from HEAD 06dc8d6; fresh agent iskipchimera21r2 on bunker-mvp. Cell timestamps are evidence-recording time, not command start time. Raw attempt 1 files are retained in raw/attempt1; current run stdout, stderr and exit codes are in raw/. The OpenRouter error contains a key management URL: its key identifier is redacted, with the error otherwise preserved.

| Cell | Status | Evidence | rc |
|---|---|---|---|
| install | OK | OS Python; sdist installed in fresh venv (raw/install.*) | 0 |
| version | OK | chimera 0.3.0 | 0 |
| config | OK | config init and file existence assertion | 0 |
| formations | OK | six shipped presets displayed | 0 |
| deliberation | OK | Fireworks glm-5p3-flash returned a real answer; request 9614d2b2732d438d | 0 |
| teardown | OK | destroy 0; subsequent bunker-mvp list 0, agent absent | 0 |

## Distribution

- sdist SHA256 af7cc0b3d602abd687ce8f7c2c9f3a50a0a1f3fda4434ad20cde84fa04277857
- wheel SHA256 a20c69aa0112252901b2db476ca0dfc99ec2f387267ac63e1c1a25cb94b14069

## Provider attempts

1. OpenRouter mistralai/mistral-nemo: rc 2, HTTP 403, key spending limit exceeded. See raw/deliberation.*.
2. Router9 cx/gpt-6.1-terra: rc 2, LiteLLM rejected temperature parameters before provider completion. See raw/router9.*.
3. Fireworks llama-v3p1-8b-instruct: rc 2, model not found/inaccessible/not deployed. See raw/fireworks.*. The authenticated models listing is in raw/fireworks-models.*.
4. Fireworks accounts/fireworks/models/glm-5p3-flash: rc 0, actual answer returned. See raw/fireworks-retry.*. Request ID 9614d2b2732d438d; trace total cost 0.000124 USD (Chimera estimate); worker input/output 57/75 tokens. Full answer, complete trace, stage tokens and costs are captured in the raw output.

The successful answer: Testing a fresh install matters because it verifies that all dependencies, configurations, and setup steps work correctly from scratch, catching issues that would only appear for new users or on clean systems rather than being masked by an already-configured environment.

## Procedure

Artifacts built using `uv build --out-dir /home/kara/.hermes/cache/scratch/iskip-r2/dist /home/kara/chimera-v2`; copied both distributions with `bunker cp`. The agent-side scripts are retained in raw/ (they contain no credentials). The provider keys were transferred via stdin to a private temporary agent file, read by the script and removed before running the CLI. Battery used the shipped sdist, `python3 -m venv`, `chimera --version`, `chimera config init`, `chimera -c chimera.yaml formations`, and `chimera -c <provider config> -f simple run --json` with the prompt shown in the scripts. Logs were harvested before `bunker destroy iskipchimera21r2 --server bunker-mvp --purge`; raw/list.out is the post-destroy listing.
