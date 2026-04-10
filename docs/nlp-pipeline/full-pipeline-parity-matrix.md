# Full Pipeline Parity Matrix

## Scope

This matrix defines the enforced parity contract across:

- Runtime canonical workflow (`libs/pipeline_graph/*`)
- Training verification and re-extraction (`services/api/app/services/label_verifier.py`)
- Ask LEO review endpoints (`services/api/app/routers/_training_askleo.py`)
- Legacy coding worker fallback (`services/coding_worker/app/pipeline/*`)

## Path-by-Path Matrix

| Capability | Runtime canonical | Training/review | Ask LEO | Legacy coding worker |
| --- | --- | --- | --- | --- |
| Prompt source | PromptConfig (Neo4j) | PromptConfig (Neo4j) for re-extraction | Escalation prompts + safety prompts | PromptConfig (Neo4j) |
| Few-shot selection | Core + dynamic selector | PromptConfig few-shots | N/A (candidate-ranking prompts) | PromptConfig few-shots |
| Shared post-processing | `run_post_processing()` required | `run_post_processing()` required | N/A (review-only reasoning) | `run_post_processing()` now required |
| Lab-value safety guard | Yes (Layer 2) | Yes (Layer 2) | Explicit guard in rank/smart routes | Yes via shared pipeline |
| Assertion normalization | Yes (Layer 7 + layer mapping) | Yes | Context notes, no auto-write | Yes |
| Disorder gate | Optional by config | Enabled for verification path | No direct write path | Disabled by default |
| Write-back semantics | Pipeline subgraphs + persistence stage | Training label/coding-review writes | Read-only unless apply action | Encounter payload persistence only |
| Telemetry | Per-step + run-level metadata | Job-level counters | Endpoint-level responses | Prompt hash + few-shot IDs in extractor context |

## Mandatory Unifications Implemented

1. Prompt single-source now enforced for extraction paths:
   - Runtime extraction adapter uses PromptConfig metadata.
   - Training re-extraction now assembles from PromptConfig system+schema+few-shots.
   - Legacy coding worker extractor now reads PromptConfig.
2. Shared post-processing is now applied in legacy coding worker before terminology resolution.
3. Model backend policy is explicit:
   - `ModelExtractorProvider` is disabled by default (`CODING_MODEL_PROVIDER_ENABLED=false`).
   - A model backend cannot silently run as a no-op extractor.
4. Workflow telemetry now includes:
   - `prompt_name`, `prompt_version`, `prompt_hash`
   - selected `few_shot_example_ids`
   - `provider`, `model_tier`
   - per-step token/cost metrics and step status.

## Remaining Hardening Work

- Enforce identical assertion allow-lists in every Ask LEO apply write path.
- Add backend integration tests that fail on partial-success write outcomes.
- Add run-level fail-fast gate when critical telemetry keys are missing.
