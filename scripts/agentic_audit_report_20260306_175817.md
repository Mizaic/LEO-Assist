# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 01:07 UTC  
**Mode:** APPLY  
**Records audited:** 7387  
**Elapsed:** 25736s (3.5s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 951 |
| Records with issues | 6436 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 4085 |
| Total proposals (human review) | 8921 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 7387 |
| Small models agreed (no escalation) | 6098 (82.6%) |
| Escalated to big model | 1241 (16.8%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 2386 |
| fixable | 990 |
| needs_review | 4957 |
| remove | 1962 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 2189 |
| assertion | 795 |
| label | 716 |
| value | 217 |
| unit | 69 |
| normalized | 58 |
| reference_range | 41 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 5754 |
| missing | 1559 |
| remove | 1541 |
| fixable | 67 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 73,068,194 |
| Total output tokens | 19,154,124 |
| Cached input tokens | 32,697,344 |
| Guardrail total tokens | 92,222,318 |
| Estimated cost | $506.52 |

## Sample Auto-Fixes (up to 10)

- **ca501e92aa9f...** entity[0] `text`: `Serum lipid levels` -> `Serum lipid levels` (conf=0.95) -- Text span is over-captured: ends at 85 but should end at 18. Current span includes Read code, person name, result descriptor, and action text. Correct span is 0–18.
- **ca501e92aa9f...** entity[0] `assertion`: `absent` -> `present` (conf=1.00) -- Sentence states 'Normal - No Action' (result present and normal); not a negation.
- **8f5c9aa622b1...** entity[0] `label`: `observable entity` -> `observable entity` (conf=0.95) -- SNOMED term is 'Serum urea measurement (procedure)' which is a procedure concept, inconsistent with observable entity label.
- **e0ff08f4c9b6...** entity[0] `text`: `Acute upper respiratory infection` -> `Acute upper respiratory infection (X1002) (New Episode)` (conf=0.95) -- Entity start/end span covers the entire sentence; text should match full sentence to avoid span mismatch.
- **c781a6a7beec...** entity[0] `assertion`: `possible` -> `possible` (conf=0.98) -- Sentence opens with 'Consider' — hedging cue. Assertion 'possible' is correct.
- **8e665db467e8...** entity[0] `text`: `change in bowel habit` -> `No change in bowel habit` (conf=0.98) -- Text span excludes negation marker 'No' at sentence start. Negation is integral to the clinical meaning and should be included in the surface form.
- **d996f7860d2e...** entity[1] `label`: `observable entity` -> `substance` (conf=0.95) -- Vitamin B12 is a substance/medication, not an observable entity. Observable entity requires a measured value (value/unit). This entity has no value/unit, so label should be 'substance'.
- **dfedd09be52e...** entity[1] `assertion`: `absent` -> `present` (conf=0.99) -- Sentence reads 'BMI 27 checked January this year' — measured BMI present, not negated
- **a629962e2bd1...** entity[1] `text`: `5.77 10^9/L` -> `5.77` (conf=0.95) -- qualifier_value should capture only the numeric value, not the unit. Unit is already encoded separately in observable entity.
- **8210479dc416...** entity[0] `text`: `Monocyte count - observation` -> `Monocyte count` (conf=0.98) -- Text over-captured: includes '- observation' label and Read code marker '(42N..)'. Surface form should be the clinical parameter name only.

## Sample Proposals for Human Review (up to 10)

- **2f9a67014f88...** entity[1] `text`: `5.09 10^9/L` -> `None` (conf=0.98) -- Qualifier_value should not be extracted as a separate entity. The value and unit are already captured in the observable_entity (entity 0) as 'value' and 'unit' fields. Extracting them again as a distinct entity creates redundancy and violates the rule that observable entities should have value/unit/reference_range in their own fields, not as separate entities.
- **ab68f91ec969...** entity[0] `snomed_score`: `1.2157` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review of SNOMED coding.
- **e0ff08f4c9b6...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring human review.
- **c781a6a7beec...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **c781a6a7beec...** entity[1] `assertion`: `present` -> `possible` (conf=0.92) -- Sentence context: 'given suggestions of emotional instability' — hedging language ('suggestions of') indicates uncertainty, not confirmed presence.
- **c781a6a7beec...** entity[1] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **c781a6a7beec...** entity[1] `decision_tier`: `1` -> `None` (conf=0.98) -- Tier 1 requires assertion 'present' + score ≥ 0.95. Assertion should be 'possible' (hedged), so tier should be 3, not 1.
- **c781a6a7beec...** MISSING: `suicidal ideation` (finding, historical) conf=0.94 -- Clinically significant symptom explicitly mentioned ('first suicidal ideation was after...') — past-tense context indicates historical assertion.
- **e8bb120123f5...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.
- **e8bb120123f5...** entity[1] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.

## Sample Needs-Review (up to 10)

- **ab68f91ec969...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review of SNOMED coding.
- **8f5c9aa622b1...** entity[0] -- label: SNOMED term is 'Serum urea measurement (procedure)' which is a procedure concept, inconsistent with observable entity label.
- **e0ff08f4c9b6...** entity[0] -- text: Entity start/end span covers the entire sentence; text should match full sentence to avoid span mismatch.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring human review.
- **c781a6a7beec...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.; assertion: Sentence opens with 'Consider' — hedging cue. Assertion 'possible' is correct.
- **c781a6a7beec...** entity[1] -- assertion: Sentence context: 'given suggestions of emotional instability' — hedging language ('suggestions of') indicates uncertainty, not confirmed presence.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.; decision_tier: Tier 1 requires assertion 'present' + score ≥ 0.95. Assertion should be 'possible' (hedged), so tier should be 3, not 1.
- **e8bb120123f5...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.
- **e8bb120123f5...** entity[1] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.
- **e8bb120123f5...** entity[2] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.
- **e8bb120123f5...** entity[3] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring investigation.; snomed_concept_id: SNOMED code 6077001 'Foot-drop' is semantically incorrect for 'Hb drop' (haemoglobin drop). Requires terminology review.
- **8e665db467e8...** entity[0] -- text: Text span excludes negation marker 'No' at sentence start. Negation is integral to the clinical meaning and should be included in the surface form.; snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring human review.
