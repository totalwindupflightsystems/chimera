# Chimera Model Sync — 2026-10-13

## Summary

The sync found **2 new core candidates** (Google Gemini 4 Argon and Meta Muse Wonder 1.0) plus **1 task-router lane find** (Kimi K2.8 Preview Agent). The sync report treats the latter separately from core-lab candidates. No catalog changes were made.

## Candidate review

### Google Gemini 4 Argon — recommend for approval, subject to access check

- **Registry candidate:** `google/gemini-4-argon`; `google` native provider.
- **OpenRouter:** page found and available: https://openrouter.ai/google/gemini-4-argon
- **Provider announcement:** Google announcement found: https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/
- **Availability caveat:** Google's announcement describes rollout to trusted cyber defenders through its Fairwind Program. Confirm intended account/API access before treating it as generally usable.
- **Pricing:** OpenRouter lists $2/M input and $10/M output, equal to **$0.002/$0.010 per 1k**. This agrees with `reports/latest.md`.
- **Auto-score artifact:** `reports/model_scores_20261013_1201.yaml` assigns premium tier and scores >=60 on: research-paper writing 85; algebra 90, calculus 90, statistics 88; task decomposition 92, debugging 90, code execution/tool use 90; definitions 82, historical events 82, explanation 88, logic puzzles 88; abstractive summarization 85, translation 82; image analysis 82; JavaScript 85, Python 88, shell 85, SQL generation 84, SQL/database interaction 84, JSON/file interaction 82, data-science analysis 85 and modeling 82, architecture 85, DevOps 82, error analysis 90, unit tests 88.
- **Recommendation:** if access is confirmed, use the native `google/gemini-4-argon` catalog ID/provider, not an `openrouter/`-prefixed ID. The sync's automatic scores are provisional, not benchmark-validated.

### Meta Muse Wonder — recommend for approval after ID/pricing reconciliation

- **Sync/score candidate:** `meta/muse-wonder-1.0`; the task-router/model-sync record says pricing unavailable.
- **OpenRouter:** a live model page was found under the distinct ID `meta/muse-wonder`: https://openrouter.ai/meta/muse-wonder
- **Provider announcement:** Meta announcement found: https://about.fb.com/news/2026/10/introducing-muse-wonder-models/
- **Pricing:** OpenRouter lists $4/M input and $20/M output, or **$0.004/$0.020 per 1k**. This conflicts with the sync's N/A pricing and should be reconciled against the intended provider route before adding.
- **Auto-score artifact:** `reports/model_scores_20261013_1201.yaml` assigns premium tier and scores >=60 on: algebra/calculus/statistics 78; task decomposition 88, debugging 86, code execution/tool use 87; definitions 80, historical events 78, explanation 84, logic puzzles 82; summarization 82, translation 78; image analysis 88; JavaScript 84, Python 86, shell 80, SQL generation 80, SQL/database interaction 78, JSON/file interaction 80, data-science analysis 80 and modeling 78, architecture 80, DevOps 76, error analysis 86, unit tests 84.
- **Recommendation:** favor the exact OpenRouter ID `meta/muse-wonder` with provider `openrouter` if that is the desired route. Do not add `meta/muse-wonder-1.0` without confirming the native model identifier and price; reconcile scoring artifact ID and route first. Scores are provisional.

### Moonshot Kimi K2.8 Preview Agent — do not recommend for core catalog yet

- **Task-router lane candidate:** routable ID `xkiro/moonshotai/kimi-k2.8-preview-agent`; lane-resolved ID `moonshot/moonshotai/kimi-k2.8-preview-agent`.
- **OpenRouter:** no matching OpenRouter page was found in searches for the exact candidate/model name.
- **Provider release announcement:** search results surfaced secondary reports about a Kimi K2.8 Preview rollout, but no Moonshot primary announcement or changelog was verified in this review. Those sources also say the API ID remains `kimi-for-coding`, which does not match the discovered candidate ID.
- **Pricing:** the sync report lists $1/M input and $4/M output for the xkiro lane, but this is lane pricing and does not establish Moonshot's native price.
- **Auto-score artifact:** score output maps it to `moonshot/moonshotai/kimi-k2.8-preview-agent`, standard tier; scored categories >=60: algebra 76, calculus/statistics 75; task decomposition 86, debugging 84, code execution/tool use 88; definitions 78, historical events 76, explanation 82, logic puzzles 80; sentiment 76, summarization 86, translation 80; JavaScript 82, Python 86, shell 82, SQL generation 80, SQL/database interaction 80, JSON/file interaction 84, data-science analysis 80 and modeling 78, architecture 80, DevOps 76, error analysis 86, unit tests 84.
- **Recommendation:** keep this as a task-router lane observation, not a core catalog addition. Verify the exact model ID, official availability, and independent pricing before reconsidering.

## Scoring validation note

The score artifact contains hierarchical category paths and whole-number scores, with only paths scoring >=60 included. The expected `references/category-paths.md` file was not present in the repository path checked, so the category names/scores above are transcribed from the generated artifact and were **not independently checked against the canonical 32-path list**. Treat all LLM-generated scores as provisional pending that validation.

## Action items

1. Confirm whether Google Gemini 4 Argon is enabled for the intended provider account; if yes, review its score artifact and consider native-provider admission.
2. Resolve Muse Wonder's model ID (`meta/muse-wonder` vs `meta/muse-wonder-1.0`) and pricing discrepancy before any addition.
3. Leave Kimi K2.8 Preview Agent out of the core catalog pending exact-ID, primary-source, OpenRouter, and pricing confirmation.
4. Validate candidate score paths against the canonical 32-path reference when its current location is available.

**No models were added to `chimera.yaml` or its templates.**
