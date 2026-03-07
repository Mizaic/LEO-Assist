# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 01:04 UTC  
**Mode:** APPLY  
**Records audited:** 6628  
**Elapsed:** 22900s (3.5s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 834 |
| Records with issues | 5794 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 5082 |
| Total proposals (human review) | 6683 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 6628 |
| Small models agreed (no escalation) | 5501 (83.0%) |
| Escalated to big model | 1079 (16.3%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 2143 |
| fixable | 896 |
| needs_review | 4495 |
| remove | 1755 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 1834 |
| None | 1742 |
| assertion | 721 |
| label | 461 |
| value | 173 |
| unit | 58 |
| normalized | 50 |
| reference_range | 43 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 5203 |
| missing | 1393 |
| fixable | 67 |
| remove | 20 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 65,379,754 |
| Total output tokens | 17,160,768 |
| Cached input tokens | 28,881,664 |
| Guardrail total tokens | 83,881,146 |
| Estimated cost | $117.35 |

## Sample Auto-Fixes (up to 10)

- **882312c1dbdd...** entity[0] `label`: `disorder` -> `finding` (conf=0.95) -- Chest pain is a symptom/sign; 'musculoskeletal chest pain' should be labelled as a finding per semantic tag rules.
- **14c59115aaba...** entity[2] `None`: `None` -> `None` (conf=0.98) -- Result descriptors ('Outside reference range') are qualifier_value, not finding. This duplicates entity 1 and should not be extracted as a separate entity.
- **6d1d57c00056...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Redundant extraction. The observable entity (entity 0) already captures the complete measured value (value='13', unit='miu/L'). Extracting the value+unit as a separate qualifier_value entity duplicates information and violates the rule: 'For observable entities with measured value, capture test name + value/unit in single entity, not separately.'
- **763f6376c53f...** entity[0] `assertion`: `hypothetical` -> `present` (conf=0.99) -- Symptom is described as currently experienced under conditions (if he has not taken med/eats too much); not a hypothetical. Also snomed_score=1.3>1.0 (read-only) so coding needs review.
- **4a7a908d8ff6...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Bare numeric value duplicate of observable entity value; do not extract standalone numeric values.
- **4a7a908d8ff6...** entity[2] `None`: `None` -> `None` (conf=0.98) -- Result descriptor 'Outside reference range' is a qualifier, not a clinical finding. It should not be extracted as a separate entity — it is metadata about entity 0.
- **8f5aff5f9b11...** entity[1] `assertion`: `hypothetical` -> `present` (conf=0.95) -- Text states an existing 'Fast track referral ... updated: Waiting For Information' — referral is present/recorded, not hypothetical.
- **ea11708784d2...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Qualifier_value is a redundant duplicate of the observable entity's value/unit fields. The value and unit are already captured in entity 0. Extracting them as a separate entity creates data duplication and violates the rule: 'One distinct concept per sentence only.'
- **de91256ee173...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Value/unit are already present on the observable_entity (entity 0); this separate qualifier_value duplicates that info.
- **de91256ee173...** entity[2] `None`: `None` -> `None` (conf=0.98) -- Result descriptor 'Outside reference range' is a qualifier, not a clinical finding. It should not be extracted as a separate entity — it is metadata about the observable entity value.

## Sample Proposals for Human Review (up to 10)

- **7602710ad220...** MISSING: `Advice given about breast screening programme` (procedure, present) conf=0.94 -- Clinical action performed (advice given) should be extracted as a procedure; Read code in brackets should be excluded.
- **649496dc6953...** entity[0] `snomed_score`: `1.3` -> `review` (conf=1.00) -- snomed_score > 1.0 (data quality bug). SNOMED-related read-only field must be reviewed by human.
- **882312c1dbdd...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score is 1.1, which exceeds the valid range [0.0, 1.0]. This is a data quality bug. Cannot suggest a replacement — requires human review of the scoring mechanism.
- **763f6376c53f...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring review.
- **763f6376c53f...** entity[1] `assertion`: `hypothetical` -> `present` (conf=0.90) -- Medication is described as being taken/omitted in practice (if he has not taken Trimbow) implying current use rather than purely hypothetical. Also snomed_term appears mismatched and snomed_score=1.2748>1.0 (read-only).
- **763f6376c53f...** entity[1] `snomed_score`: `1.2748` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring review.
- **e4b804cbf719...** entity[0] `start`: `0` -> `offsets appear to cover entire sentence rather than the exact span 'Full blood count' — read-only field flagged for review` (conf=0.95) -- Entity text is 'Full blood count' but start/end cover full sentence; offsets are read-only so flag for human review
- **e4b804cbf719...** entity[0] `end`: `93` -> `offsets appear to cover entire sentence rather than the exact span 'Full blood count' — read-only field flagged for review` (conf=0.95) -- Entity text is shorter than the provided span; end offset appears incorrect
- **e4b804cbf719...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring human review.
- **e4b804cbf719...** entity[1] `start`: `0` -> `offsets appear to cover entire sentence rather than the exact span 'eGFR low for age' — read-only field flagged for review` (conf=0.95) -- Entity text is a substring but provided offsets cover whole sentence; read-only offsets require human review

## Sample Needs-Review (up to 10)

- **649496dc6953...** entity[0] -- snomed_score: snomed_score > 1.0 (data quality bug). SNOMED-related read-only field must be reviewed by human.
- **882312c1dbdd...** entity[0] -- snomed_score: snomed_score is 1.1, which exceeds the valid range [0.0, 1.0]. This is a data quality bug. Cannot suggest a replacement — requires human review of the scoring mechanism.; label: Chest pain is a symptom/sign; 'musculoskeletal chest pain' should be labelled as a finding per semantic tag rules.
- **763f6376c53f...** entity[0] -- assertion: Symptom is described as currently experienced under conditions (if he has not taken med/eats too much); not a hypothetical. Also snomed_score=1.3>1.0 (read-only) so coding needs review.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring review.
- **763f6376c53f...** entity[1] -- assertion: Medication is described as being taken/omitted in practice (if he has not taken Trimbow) implying current use rather than purely hypothetical. Also snomed_term appears mismatched and snomed_score=1.2748>1.0 (read-only).; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring review.
- **e4b804cbf719...** entity[0] -- start: Entity text is 'Full blood count' but start/end cover full sentence; offsets are read-only so flag for human review; end: Entity text is shorter than the provided span; end offset appears incorrect; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug requiring human review.
- **e4b804cbf719...** entity[1] -- start: Entity text is a substring but provided offsets cover whole sentence; read-only offsets require human review; end: Entity text is a substring but provided offsets cover whole sentence; read-only offsets require human review; snomed_score: snomed_score = 1.0 is at boundary; acceptable but entity lacks measured value required for observable_entity classification.
- **8f5aff5f9b11...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **8f5aff5f9b11...** entity[1] -- assertion: Text states an existing 'Fast track referral ... updated: Waiting For Information' — referral is present/recorded, not hypothetical.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **cc2a489f7e50...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring human review.
- **83ef3d0414fa...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — human review required.; snomed_term: 'Low mood' is a symptom/finding (eg depressed mood); SNOMED term is too broad/incorrect. Read-only SNOMED issue.
