# Full Pipeline Rollout and VT Evidence Plan

## Rollout Strategy

This rollout applies to:

- encounter reset and recode
- patient full rebuild
- admin run patient/cohort
- training re-extraction and coding review assists

### Phase 1 - Shadow Validation (internal)

- Enable new telemetry fields and prompt metadata capture.
- Compare output parity between:
  - runtime extraction path
  - training re-extraction path
  - coding worker fallback path
- Exit criteria:
  - no prompt-source drift
  - no post-processing drift
  - balanced F1 non-regression on regression slices

### Phase 2 - Canary (limited cohort)

- Enable for a bounded patient cohort and one org scope.
- Monitor:
  - extraction quality slices
  - lab-value false disorder rate
  - assertion mismatch rate
  - partial-run failure rate
- Exit criteria:
  - no critical safety regression
  - telemetry completeness for 100% of canary runs

### Phase 3 - Full rollout

- Promote to all supported run actions.
- Continue weekly quality review for first month.

## Rollback Triggers

Rollback immediately if any condition is met:

1. prompt metadata missing for critical runs (`prompt_hash` empty).
2. few-shot metadata missing for extraction run with dynamic selector enabled.
3. balanced F1 drops by >2 points on safety-critical slices.
4. lab-only text produces disorder writebacks above baseline threshold.
5. mismatch between runtime and training post-processing outputs for same input.

## Verification Test Evidence Mapping

| Area | Existing artefact(s) | This cycle evidence |
| --- | --- | --- |
| Coding mode safety | `DI-LEO-AI-040`, `VT-LEO-AI-025` | backend parity changes preserve mode routing |
| Consensus verification | `DI-LEO-AI-041`, `VT-LEO-AI-026` | unchanged gate; telemetry enrichment added |
| Assertion lifecycle safety | `DI-LEO-AI-042`, `VT-LEO-AI-028` | post-processing parity retained across paths |
| Prompt source governance | PromptConfig runtime controls | PromptConfig now used in runtime/training/worker extraction |
| Few-shot retrieval quality | prompt examples and selector | domain-routed selector tests added |

## Automated Evidence Collected in This Change

- `pytest tests/test_llm_extractor.py tests/test_extractor_fallback.py tests/test_prompt_registry_config.py tests/test_few_shot_selector_routing.py -q`
- Result: 31 passed.

## Follow-up VT Additions (next increment)

- add integration test asserting telemetry completeness for pipeline run records.
- add parity fixture test for runtime vs training post-processing outputs.
- add failure-propagation test for partial-success-as-failure orchestration.
