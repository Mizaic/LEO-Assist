# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 02:27 UTC  
**Mode:** APPLY  
**Records audited:** 7498  
**Elapsed:** 31101s (4.1s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 1656 |
| Records with issues | 5842 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 5166 |
| Total proposals (human review) | 7090 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 7498 |
| Small models agreed (no escalation) | 1509 (20.1%) |
| Escalated to big model | 5956 (79.4%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 3461 |
| fixable | 1322 |
| needs_review | 4948 |
| remove | 1239 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 2613 |
| label | 1470 |
| assertion | 702 |
| normalized | 141 |
| reference_range | 93 |
| value | 79 |
| unit | 68 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 4845 |
| missing | 1628 |
| remove | 421 |
| fixable | 196 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 94,885,800 |
| Total output tokens | 21,500,277 |
| Cached input tokens | 51,145,472 |
| Guardrail total tokens | 116,386,077 |
| Estimated cost | $607.16 |

## Sample Auto-Fixes (up to 10)

- **482bf2b7c4e4...** entity[1] `text`: `4.87 10^12/L` -> `REMOVE_ENTITY` (conf=0.99) -- Bare numeric value already captured within observable entity; standalone value extraction not permitted
- **1a30e1e1d002...** entity[0] `text`: `colonoscopy` -> `colonoscopy` (conf=0.98) -- Span over-captured (0–93 covers whole sentence). Should capture only 'colonoscopy'. Also snomed_score >1.0 is invalid and requires human review.
- **61456802c06f...** entity[0] `text`: `back pain` -> `back pain` (conf=0.95) -- Start/end offsets (0–31) cover entire sentence, not exact span of 'back pain'; surface span should match substring only. Also snomed_score >1.0 is a data quality issue.
- **6dca5558921a...** entity[1] `label`: `qualifier_value` -> `remove` (conf=0.95) -- Value/unit already fully captured in the observable entity; standalone qualifier_value is redundant and unnecessary.
- **71c9916f3136...** entity[0] `reference_range`: `115-165` -> `115 - 165` (conf=0.95) -- Reference range should match source text with spaces, brackets removed. SNOMED term appears to describe erythrocyte concentration, not blood haemoglobin.
- **5b9571945059...** entity[0] `unit`: `mmHg` -> `mm Hg` (conf=0.95) -- Unit should match exact surface form in text, which is written as 'mm Hg'
- **3ddf327db77a...** entity[0] `text`: `smoking related lung damage` -> `smoking related lung damage` (conf=0.98) -- Entity start/end (0–50) over-capture entire sentence; text should align only to the phrase within the sentence.
- **3ddf327db77a...** entity[0] `normalized`: `smoking-related lung damage` -> `smoking-related lung damage` (conf=0.99) -- SNOMED term 'Mental disorder (disorder)' is grossly mismatched to lung damage and snomed_score 1.3 exceeds valid range; requires human review.
- **3325c45c7ffb...** entity[0] `text`: `Ex-smoker` -> `Ex-smoker (Ub1na)` (conf=0.95) -- Extracted span offsets cover whole sentence; surface form should match substring including parenthetical code.
- **3325c45c7ffb...** entity[0] `label`: `finding` -> `situation` (conf=1.00) -- This is a smoking status (risk/social history), which per rules should be tagged as 'situation', not 'finding'.

## Sample Proposals for Human Review (up to 10)

- **d8c67a38ddae...** entity[0] `label`: `disorder` -> `finding` (conf=0.90) -- SNOMED term is 'Prediabetes (finding)' and prediabetes is typically modelled as a finding rather than a disorder.
- **d8c67a38ddae...** entity[0] `text`: `Known pre diabetes` -> `Known pre diabetes` (conf=0.85) -- Start/end offsets (0–103) cover the entire sentence, indicating span over-capture; text should align only to this phrase.
- **cdbbe4cfd459...** entity[0] `label`: `observable entity` -> `observable entity` (conf=0.88) -- SNOMED term is a measurement (procedure) concept, which semantically conflicts with observable entity label; requires terminology review.
- **b0c3a94c3fc6...** entity[0] `snomed_score`: `1.3` -> `review_required` (conf=0.99) -- snomed_score is >1.0, which is a data quality bug per specification; requires manual review.
- **b0c3a94c3fc6...** MISSING: `constipation` (finding, present) conf=0.98 -- Symptom explicitly stated in same sentence but not extracted.
- **b0c3a94c3fc6...** MISSING: `smearing of stool` (finding, present) conf=0.95 -- Symptom described in sentence but not extracted.
- **dc410b0b4b8a...** entity[0] `snomed_score`: `1.3` -> `1.3` (conf=0.99) -- SNOMED score is >1.0, which is a data quality bug per audit rules; read-only field so requires human review.
- **69b7ab28da60...** entity[0] `normalized`: `haemoglobin concentration` -> `Haemoglobin concentration in blood` (conf=0.72) -- SNOMED term refers to erythrocyte haemoglobin concentration, but text implies blood haemoglobin concentration
- **5f0636e16793...** entity[0] `label`: `product` -> `product` (conf=0.61) -- Label is product but SNOMED term is a substance concept; semantic mismatch between label and coded concept.
- **790b636f5768...** entity[0] `snomed_score`: `1.3` -> `1.0` (conf=0.99) -- SNOMED score >1.0 is a data quality bug; scores should not exceed 1.0

## Sample Needs-Review (up to 10)

- **d8c67a38ddae...** entity[0] -- label: SNOMED term is 'Prediabetes (finding)' and prediabetes is typically modelled as a finding rather than a disorder.; text: Start/end offsets (0–103) cover the entire sentence, indicating span over-capture; text should align only to this phrase.
- **cdbbe4cfd459...** entity[0] -- label: SNOMED term is a measurement (procedure) concept, which semantically conflicts with observable entity label; requires terminology review.
- **1a30e1e1d002...** entity[0] -- text: Span over-captured (0–93 covers whole sentence). Should capture only 'colonoscopy'. Also snomed_score >1.0 is invalid and requires human review.
- **61456802c06f...** entity[0] -- text: Start/end offsets (0–31) cover entire sentence, not exact span of 'back pain'; surface span should match substring only. Also snomed_score >1.0 is a data quality issue.
- **b0c3a94c3fc6...** entity[0] -- snomed_score: snomed_score is >1.0, which is a data quality bug per specification; requires manual review.
- **dc410b0b4b8a...** entity[0] -- snomed_score: SNOMED score is >1.0, which is a data quality bug per audit rules; read-only field so requires human review.
- **71c9916f3136...** entity[0] -- reference_range: Reference range should match source text with spaces, brackets removed. SNOMED term appears to describe erythrocyte concentration, not blood haemoglobin.
- **3ddf327db77a...** entity[0] -- text: Entity start/end (0–50) over-capture entire sentence; text should align only to the phrase within the sentence.; normalized: SNOMED term 'Mental disorder (disorder)' is grossly mismatched to lung damage and snomed_score 1.3 exceeds valid range; requires human review.
- **69b7ab28da60...** entity[0] -- normalized: SNOMED term refers to erythrocyte haemoglobin concentration, but text implies blood haemoglobin concentration
- **5f0636e16793...** entity[0] -- label: Label is product but SNOMED term is a substance concept; semantic mismatch between label and coded concept.
