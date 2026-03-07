# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 01:06 UTC  
**Mode:** APPLY  
**Records audited:** 6730  
**Elapsed:** 23370s (3.5s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 839 |
| Records with issues | 5891 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 5171 |
| Total proposals (human review) | 6719 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 6730 |
| Small models agreed (no escalation) | 5587 (83.0%) |
| Escalated to big model | 1091 (16.2%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 2159 |
| fixable | 906 |
| needs_review | 4561 |
| remove | 1803 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 1863 |
| None | 1793 |
| assertion | 727 |
| label | 467 |
| value | 172 |
| unit | 62 |
| normalized | 56 |
| reference_range | 31 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 5254 |
| missing | 1398 |
| fixable | 52 |
| remove | 15 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 66,365,501 |
| Total output tokens | 17,448,939 |
| Cached input tokens | 29,654,272 |
| Guardrail total tokens | 83,814,440 |
| Estimated cost | $460.83 |

## Sample Auto-Fixes (up to 10)

- **d876570adf7a...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Duplicate extraction. Entity 0 already captures the complete observable entity (Weight: 98 Kg). Entity 1 is the value/unit component of entity 0, not a separate entity. Qualifier_value should not be extracted as a standalone entity when the parent observable entity already includes value and unit fields.
- **923dcbcb3fd0...** entity[0] `label`: `finding` -> `situation` (conf=0.99) -- Smoking status is a social history/risk factor; semantic tag should be 'situation' not 'finding'. Also snomed_score=1.3 (>1.0) is a data-quality issue requiring review.
- **d82145a70c09...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Duplicate extraction. The value and unit are already captured in entity 0 (observable_entity) as value='42' and unit='mmol/mol'. Extracting them again as a separate qualifier_value entity creates redundancy and violates the rule: 'One distinct concept per sentence only.'
- **58db80f265a6...** entity[0] `value`: `3` -> `3` (conf=1.00) -- Value is correct but text span is misaligned. Entity text 'Non-HDL Cholesterol' (start:40, end:59) does not include the value '3 mmol/L' which precedes it in the source. The observable entity should capture the complete measured parameter.
- **58db80f265a6...** entity[1] `None`: `None` -> `None` (conf=0.95) -- Separate 'qualifier_value' label is not in the semantic tag set and duplicates value/unit already captured on the observable entity.
- **fbda4c032543...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Redundant extraction. The value and unit are already captured in entity 0 (observable_entity) as value='53' and unit='iu/L'. Extracting them again as a separate qualifier_value entity duplicates the measurement and violates the rule: 'One distinct concept per sentence only.'
- **213292134458...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Duplicate extraction. Value and unit are already captured in entity 0 (observable_entity) as value='104', unit='fL'. Separate qualifier_value entity is redundant and violates one-concept-per-sentence rule.
- **2336468ec2c2...** entity[0] `text`: `tickly cough` -> `Ongoing tickly cough after eating.` (conf=0.95) -- Text must match the exact sentence substring and capture the full concept; current text does not match the entity offsets. Also snomed_score=1.3>1.0 (data quality bug) — read-only field, requires human review.
- **6962a6d8294e...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Redundant extraction. The value and unit are already captured in entity 0 (observable entity) as value='3.69' and unit='10^12/L'. Extracting the combined value+unit string as a separate qualifier_value entity duplicates information and violates the rule that observable entities should contain their measured values inline.
- **cb7a9089f130...** entity[0] `assertion`: `absent` -> `present` (conf=1.00) -- Text reads 'Clips in situ' — this affirms presence of clips. SNOMED mapping (snomed_term) appears unrelated and requires review.

## Sample Proposals for Human Review (up to 10)

- **05bb082c1658...** MISSING: `biopsy` (procedure, declined) conf=0.95 -- Patient explicitly declined biopsy. Clinically significant refusal not extracted.
- **923dcbcb3fd0...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score exceeds maximum valid range (1.0). Data quality bug — requires human verification of coded concept.
- **509a2bf4ae69...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **509a2bf4ae69...** entity[1] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **4c6029cc6ef0...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- Read-only field: snomed_score > 1.0 is invalid (must be 0.0–1.0). Data quality bug.
- **4c6029cc6ef0...** entity[1] `snomed_score`: `0.5` -> `None` (conf=1.00) -- Read-only field: low score (0.5) conflicts with decision_tier 3 routing. Semantic match of 'Not detected by smear of cervix' to 'negative' is reasonable but score is borderline.
- **ed5545f4c91f...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review and correction.
- **ecf56f0167bd...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **ecf56f0167bd...** entity[1] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **c006043a17c6...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.

## Sample Needs-Review (up to 10)

- **923dcbcb3fd0...** entity[0] -- snomed_score: snomed_score exceeds maximum valid range (1.0). Data quality bug — requires human verification of coded concept.; label: Smoking status is a social history/risk factor; semantic tag should be 'situation' not 'finding'. Also snomed_score=1.3 (>1.0) is a data-quality issue requiring review.
- **509a2bf4ae69...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **509a2bf4ae69...** entity[1] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **4c6029cc6ef0...** entity[0] -- snomed_score: Read-only field: snomed_score > 1.0 is invalid (must be 0.0–1.0). Data quality bug.
- **4c6029cc6ef0...** entity[1] -- snomed_score: Read-only field: low score (0.5) conflicts with decision_tier 3 routing. Semantic match of 'Not detected by smear of cervix' to 'negative' is reasonable but score is borderline.
- **ed5545f4c91f...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review and correction.
- **ecf56f0167bd...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **ecf56f0167bd...** entity[1] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **c006043a17c6...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **c6aed9080985...** entity[0] -- start: Entity text 'shoulder pain' ends at position 13, but end offset is 72 (entire sentence). Span over-captured.; end: Entity text 'shoulder pain' ends at position 13, but end offset is 72 (entire sentence). Span over-captured.; snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring human review.
