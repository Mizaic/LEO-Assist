# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 01:44 UTC  
**Mode:** APPLY  
**Records audited:** 6350  
**Elapsed:** 24255s (3.8s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 721 |
| Records with issues | 5629 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 4823 |
| Total proposals (human review) | 6726 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 6350 |
| Small models agreed (no escalation) | 5262 (82.9%) |
| Escalated to big model | 1039 (16.4%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 1899 |
| fixable | 917 |
| needs_review | 4373 |
| remove | 1699 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 1747 |
| None | 1670 |
| assertion | 729 |
| label | 355 |
| value | 165 |
| normalized | 58 |
| reference_range | 50 |
| unit | 49 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 5231 |
| missing | 1356 |
| fixable | 101 |
| remove | 38 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 63,274,729 |
| Total output tokens | 17,508,481 |
| Cached input tokens | 24,058,880 |
| Guardrail total tokens | 82,072,932 |
| Estimated cost | $131.04 |

## Sample Auto-Fixes (up to 10)

- **bd07c4e41175...** entity[0] `text`: `High risk HPV detected` -> `High risk HPV detected.` (conf=1.00) -- Surface form must match sentence exactly (sentence includes final period).
- **c3d36a2310f8...** entity[0] `text`: `Suspected asthma (XaInC)` -> `Suspected asthma` (conf=0.98) -- Text over-captured: includes Read code '(XaInC)' which should not be part of the clinical entity surface form
- **34a012014571...** entity[1] `assertion`: `hypothetical` -> `present` (conf=0.95) -- Sentence states 'Fast track referral for ...' with no conditional language; reads as an executed/present referral.
- **017b86f1e073...** entity[0] `text`: `Serum free T` -> `Serum free T4 level` (conf=0.99) -- Text is over-captured; should include complete test name. Normalized field correctly shows 'serum free T4 level'.
- **017b86f1e073...** entity[0] `assertion`: `absent` -> `present` (conf=0.99) -- No negation cues in sentence. Test result is reported with a measured value (19.3 pmol/L), indicating present/confirmed status.
- **017b86f1e073...** entity[1] `None`: `None` -> `None` (conf=0.99) -- Spurious fragment. '4 level' is not a distinct clinical concept; it is part of 'Serum free T4 level' already captured by entity 0. Should be removed.
- **017b86f1e073...** entity[2] `None`: `None` -> `None` (conf=0.99) -- Redundant extraction. The value and unit are already correctly captured in entity 0's 'value' and 'unit' fields. Extracting them as a separate qualifier_value entity duplicates information and fragments the observable entity.
- **9a2f0ef50e55...** entity[0] `text`: `Systolic BP reading:` -> `Systolic BP reading` (conf=0.98) -- Text span includes trailing colon which is punctuation, not part of the clinical term. Should be 'Systolic BP reading' (chars 7–26).
- **9a2f0ef50e55...** entity[1] `None`: `None` -> `None` (conf=0.99) -- Duplicate extraction. The value and unit are already captured in entity 0 (value='135', unit='mmHg'). Extracting them as a separate 'qualifier_value' entity is redundant and violates the rule: 'One distinct concept per sentence only.'
- **a28069789877...** entity[0] `text`: `PR bleeding` -> `no PR bleeding` (conf=0.95) -- Negation marker 'no' is part of the clinical assertion and should be included in the surface form to preserve negation scope.

## Sample Proposals for Human Review (up to 10)

- **bd07c4e41175...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
- **ed9fad61aa69...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — human review required.
- **ed9fad61aa69...** MISSING: `cough` (finding, present) conf=0.99 -- Explicit clinical finding in sentence s0 ('has a cough as well') — should be extracted as separate entity
- **c3d36a2310f8...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring review
- **34a012014571...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score exceeds maximum valid range (1.0). Data quality bug — cannot verify correct score without terminology API.
- **34a012014571...** entity[1] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score exceeds maximum valid range (1.0). Data quality bug — cannot verify correct score without terminology API.
- **a28069789877...** entity[0] `snomed_score`: `1.1` -> `None` (conf=1.00) -- snomed_score exceeds maximum valid range (1.0). Data quality bug — requires human verification of SNOMED coding.
- **e1431a425a1d...** entity[0] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **e1431a425a1d...** MISSING: `chest xray` (procedure, present) conf=0.95 -- Chest X-ray is a diagnostic procedure performed. Should be extracted as a separate entity with assertion 'present' (result was 'ok').
- **ad0efbd0b546...** entity[1] `snomed_score`: `1.3` -> `None` (conf=1.00) -- snomed_score > 1.0 is invalid (max 1.0). Data quality bug — flag for review.

## Sample Needs-Review (up to 10)

- **bd07c4e41175...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.; text: Surface form must match sentence exactly (sentence includes final period).
- **ed9fad61aa69...** entity[0] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — human review required.
- **c3d36a2310f8...** entity[0] -- text: Text over-captured: includes Read code '(XaInC)' which should not be part of the clinical entity surface form; snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug requiring review
- **34a012014571...** entity[0] -- snomed_score: snomed_score exceeds maximum valid range (1.0). Data quality bug — cannot verify correct score without terminology API.
- **34a012014571...** entity[1] -- snomed_score: snomed_score exceeds maximum valid range (1.0). Data quality bug — cannot verify correct score without terminology API.; assertion: Sentence states 'Fast track referral for ...' with no conditional language; reads as an executed/present referral.
- **a28069789877...** entity[0] -- snomed_score: snomed_score exceeds maximum valid range (1.0). Data quality bug — requires human verification of SNOMED coding.; text: Negation marker 'no' is part of the clinical assertion and should be included in the surface form to preserve negation scope.
- **e1431a425a1d...** entity[0] -- text: Text span over-captured. Should be 'no hemptysis' (negation + finding), not just 'hemptysis'. Current span (0–31) includes entire sentence.; snomed_score: snomed_score > 1.0 is invalid (scores must be 0.0–1.0). Data quality bug — requires human review.
- **ad0efbd0b546...** entity[1] -- snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — flag for review.
- **97da082fc6ef...** entity[0] -- text: Text span end=90 exceeds actual text length. Correct span is 0–19. Over-capture includes 'Report', 'Abnormal', and entire sentence.; value: Observable entity has no measured value in text. Value should remain null; this is a test name only, not a result.
- **97da082fc6ef...** entity[1] -- text: Text span end=90 over-captures entire sentence. Correct span is 32–40. Abnormal is a result descriptor, not a clinical finding.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug — requires human review.
