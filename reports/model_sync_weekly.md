# Chimera Model Sync — 2026-10-07

## Summary

The sync identified 4 core candidates. Three Ministral 3 instruction models (3B, 8B, 14B) pass availability, provider-announcement, and pricing checks and are reasonable additions to consider. Leanstral 1.5.1 is not recommended: no OpenRouter listing or pricing was found for that exact candidate, and available Mistral material identifies the Leanstral 1.5 family as a specialized Lean 4 theorem-proving model, not a general chat model. A secondary release-notes listing says Leanstral 1.5 was retired September 30, 2026; confirm retirement with Mistral before considering any replacement ID.

No catalog files were modified. The sync's automatic scoring failed with HTTP 402 (Payment Required), so the scores below are conservative, provisional capability estimates, not model-sync LLM scores or benchmark-derived measurements. The requested `references/category-paths.md` was not present; category names below are taken from `src/chimera/selector.py`'s canonical `PATH_PATTERNS` tree. Only paths estimated at 60 or higher are listed.

## Candidates and verification

| Candidate | Availability / provider evidence | Pricing evidence | Recommendation |
|---|---|---|---|
| `ministral-14b-2512` | Verified OpenRouter listing: [mistralai/ministral-14b-2512](https://openrouter.ai/mistralai/ministral-14b-2512). Mistral announced Ministral 3 (3B/8B/14B) and maintains an official [14B model card](https://docs.mistral.ai/models/ministral-3-14b-25-12). | OpenRouter lists $0.20/M input and output (= $0.000200 per 1K each), matching the sync report. | Recommend; best capability of the three and useful small-model/edge option. |
| `ministral-8b-2512` | Verified OpenRouter listing: [mistralai/ministral-8b-2512](https://openrouter.ai/mistralai/ministral-8b-2512). Mistral announcement and official [8B model card](https://docs.mistral.ai/models/ministral-3-8b-25-12). | OpenRouter lists $0.15/M input and output (= $0.000150 per 1K each), matching the sync report. | Recommend; balanced budget/latency option. |
| `ministral-3b-2512` | Verified OpenRouter listing: [mistralai/ministral-3b-2512](https://openrouter.ai/mistralai/ministral-3b-2512). Mistral announcement and official [3B model card](https://docs.mistral.ai/models/ministral-3-3b-25-12). | OpenRouter lists $0.10/M input and output (= $0.000100 per 1K each), matching the sync report. | Recommend for lightweight/low-cost tasks; expect lower capability ceiling. |
| `labs-leanstral-1-5-1` | Mistral's [Leanstral 1.5 announcement](https://mistral.ai/news/leanstral-1-5/) confirms the specialized Lean 4 theorem-proving family, but not this exact `.1` candidate ID. No exact OpenRouter model page was found. A third-party release-note index reports retirement of Leanstral 1.5 on 2026-09-30; this was not independently confirmed on an official retirement notice. | Sync report has N/A; no OpenRouter pricing found. | Do not add. Exact ID, current availability, and retirement status are unresolved; specialized use case also falls outside ordinary chat coverage. |

Official Mistral release announcement for the Ministral 3 family: [Introducing Mistral 3](https://mistral.ai/news/mistral-3/). It describes the 3B/8B/14B family and vision capabilities. Pricing above is listed by OpenRouter; it does not establish native Mistral API pricing.

## Provisional category scores

Integer scores on the canonical 0–100 scale. These are deliberately limited to plausible strengths; omitted paths should remain unscored until evaluated. The scores are initial recommendations only and should be validated with real task evals before catalog admission.

### `ministral-14b-2512`

```yaml
categories:
  technology_code/code_generation/python: 65
  technology_code/code_generation/javascript: 65
  technology_code/data_interaction/file_based/json: 70
  complex_reasoning_agency/multi_step_planning/task_decomposition: 70
  complex_reasoning_agency/tool_use/code_execution: 65
  academic_scientific/mathematics/statistics: 65
  general_knowledge/reasoning/explanation: 75
  general_knowledge/fact_retrieval/definitions: 70
  language_translation/translation/language_to_language: 70
  language_translation/summarization/abstractive: 70
  multimedia_processing/image/analysis: 70
cost_tier: budget
provider: mistral
cost_per_1k_input: 0.000200
cost_per_1k_output: 0.000200
```

### `ministral-8b-2512`

```yaml
categories:
  technology_code/code_generation/python: 60
  technology_code/data_interaction/file_based/json: 65
  complex_reasoning_agency/multi_step_planning/task_decomposition: 65
  general_knowledge/reasoning/explanation: 70
  general_knowledge/fact_retrieval/definitions: 65
  language_translation/translation/language_to_language: 65
  language_translation/summarization/abstractive: 65
  multimedia_processing/image/analysis: 65
cost_tier: budget
provider: mistral
cost_per_1k_input: 0.000150
cost_per_1k_output: 0.000150
```

### `ministral-3b-2512`

```yaml
categories:
  technology_code/data_interaction/file_based/json: 60
  general_knowledge/reasoning/explanation: 60
  general_knowledge/fact_retrieval/definitions: 60
  language_translation/translation/language_to_language: 60
  language_translation/summarization/abstractive: 60
  multimedia_processing/image/analysis: 60
cost_tier: budget
provider: mistral
cost_per_1k_input: 0.000100
cost_per_1k_output: 0.000100
```

## Provider/model-ID mapping notes

- For the verified OpenRouter listings, use catalog IDs `openrouter/mistralai/ministral-14b-2512`, `openrouter/mistralai/ministral-8b-2512`, and `openrouter/mistralai/ministral-3b-2512`, with provider `openrouter`. Confirm exact provider config naming and wire IDs against the local `chimera.yaml` conventions before admission.
- For direct Mistral API routing, use provider `mistral` and the corresponding Mistral model IDs `ministral-14b-2512`, `ministral-8b-2512`, and `ministral-3b-2512` (catalog ID convention would be `mistral/<id>`). The OpenRouter prices above should not be assumed to be Mistral-native API prices.
- Do not add the Leanstral `.1` candidate under an OpenRouter prefix without a verified OpenRouter listing.

## Action items

1. Seek approval before editing `chimera.yaml`; no catalog files were changed in this run.
2. If approved, prefer evaluating 14B and 8B first; compare native Mistral and OpenRouter routes for real pricing/latency and validate actual wire IDs.
3. Retry the sync's LLM scoring after resolving the DeepSeek API 402/payment issue. Keep these provisional scores labeled as estimates until then.
4. Exclude Leanstral 1.5.1 unless Mistral confirms the exact ID remains available and an acceptable supported route/pricing is verified.
