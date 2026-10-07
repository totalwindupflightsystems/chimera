# Chimera Model Sync — Weekly Report

**Date:** 2026-10-06  
**Run:** 2026-10-06 17:00 UTC  
**Source:** `reports/latest.md` and `reports/model_scores_20261006_1201.yaml`

## Results

- **New core candidates:** 1 (`mistral/mistral-large-4`); 0 task-router lane finds.
- **Verification:** Verified as a real, announced model. Mistral's official announcement says the public preview is available through the Mistral Studio API. OpenRouter lists the corresponding route as `mistralai/mistral-large-4-0`; its page reports $0.68/M input and $2.09/M output. Pricing matches the sync report after conversion ($0.000680/$0.002090 per 1K tokens). The synced price is the public-preview rate; recheck before catalog admission because pricing can change.
- **Sources:** [Mistral launch announcement](https://mistral.ai/news/mistral-large-4/), [Mistral model documentation](https://docs.mistral.ai/models/mistral-large-4-0), [OpenRouter model and pricing page](https://openrouter.ai/mistralai/mistral-large-4-0).
- **Scoring:** The generated score artifact assigns `premium` and scores these 17 category paths (0–100):
  - `complex_reasoning_agency/multi_step_planning/task_decomposition`: 90
  - `complex_reasoning_agency/self_correction/debugging`: 90
  - `complex_reasoning_agency/tool_use/code_execution`: 90
  - `general_knowledge/reasoning/explanation`: 90
  - `general_knowledge/reasoning/logic_puzzle`: 90
  - `multimedia_processing/image/analysis`: 85
  - `technology_code/code_generation/javascript`: 90
  - `technology_code/code_generation/python`: 95
  - `technology_code/code_generation/shell`: 85
  - `technology_code/code_generation/sql`: 85
  - `technology_code/data_interaction/database/sql`: 85
  - `technology_code/data_interaction/file_based/json`: 85
  - `technology_code/data_science/analysis`: 85
  - `technology_code/data_science/modeling`: 85
  - `technology_code/system_design/architecture`: 80
  - `technology_code/system_design/devops`: 80
  - `technology_code/testing_debugging/error_analysis`: 90
  - `technology_code/testing_debugging/unit_tests`: 85

  **Scoring limitation:** The requested `references/category-paths.md` file is absent from this checkout, and the generated YAML scores the 18 paths listed in this section. Therefore a full validation/scoring against the canonical 32-path taxonomy could not be completed. Scores are model-generated estimates, not independent benchmark results; retain them as provisional pending taxonomy review. (The generated file's description cites provider claims.)
- **Catalog recommendation (approval required):** Consider adding native provider ID `mistral/mistral-large-4` with `cost_tier: premium`, `cost_per_1k_input: 0.000680`, and `cost_per_1k_output: 0.002090`, using the provisional scores above. For OpenRouter routing, the provider's route/model identifier is `mistralai/mistral-large-4-0`; use the Chimera OpenRouter prefix form `openrouter/mistralai/mistral-large-4-0` only if that endpoint is intended. Confirm the exact provider/model mapping against the configured gateway before catalog entry. **No catalog files were modified.**

## Scope notes

The sync output's separate Reseller Watch and Blind Spot tables are informational, not additional core candidates. The “Pending — seen, not catalogued” list is not treated as a recommendation or approval to add those models.

## Action items

1. Restore or locate the canonical 32-path taxonomy and rerun/validate the candidate scoring against it.
2. Confirm whether the intended catalog route is native Mistral API or OpenRouter, then obtain user approval before changing `chimera.yaml` or its shipped templates.
3. Recheck preview pricing at admission time.
