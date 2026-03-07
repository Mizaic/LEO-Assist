# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-06 23:58 UTC  
**Mode:** APPLY  
**Records audited:** 5281  
**Elapsed:** 14813s (2.8s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 784 |
| Records with issues | 4487 |
| Errors (parse/LLM) | 10 |
| Total auto-fixes | 4824 |
| Total proposals (human review) | 1054 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 5271 |
| Small models agreed (no escalation) | 4003 (75.9%) |
| Escalated to big model | 1268 (24.1%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 1797 |
| fixable | 852 |
| needs_review | 3649 |
| remove | 1153 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 1452 |
| None | 1116 |
| unknown | 943 |
| assertion | 671 |
| label | 423 |
| normalized | 116 |
| reference_range | 55 |
| value | 28 |
| unit | 20 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 582 |
| missing | 274 |
| fixable | 161 |
| remove | 37 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 58,271,279 |
| Total output tokens | 16,912,026 |
| Cached input tokens | 20,406,144 |
| Guardrail total tokens | 76,695,631 |
| Estimated cost | $133.57 |

## Sample Auto-Fixes (up to 10)

- **a62ccbaf106b...** entity[1] `None`: `None` -> `None` (conf=0.99) -- The numeric value '22 iu/L' is already captured in Entity 0 (observable_entity) as value/unit fields. Extracting it as a separate entity is over-capture and redundant. Per rules, do not extract bare numeric values as standalone entities.; Entity 2 is missing the assertion field entirely. All clinical entities require an assertion value. This indicates the entity should not exist in this form.
- **65493f79d162...** entity[0] `text`: `Schizoaffective disorder` -> `Schizoaffective disorder` (conf=0.98) -- Entity span (0-36) over-captures section label '[Diagnosis] '. Correct span starts at position 12. Text itself is correct but span is wrong.
- **a9254b263d29...** entity[0] `label`: `procedure` -> `observable_entity` (conf=0.95) -- SNOMED term explicitly states 'observable entity', not procedure. FOB test is a measurable parameter, not an action performed.
- **d3d3c266e704...** entity[0] `text`: `Body weight normal` -> `Body weight normal` (conf=0.98) -- Entity text is correct but start/end offsets are over-captured. Text 'Body weight normal' begins at position 16 (after 'The result was: '), not 0. Span 0–34 includes entire sentence including preamble.
- **d3d3c266e704...** entity[0] `label`: `finding` -> `observable entity` (conf=0.95) -- Body weight is a measurable clinical parameter; per decision ladder it should be 'observable entity' not 'finding'.
- **c3b0140ffe2d...** entity[0] `text`: `Calculated Globulin:` -> `Calculated Globulin` (conf=0.98) -- Trailing colon is punctuation separating label from value, not part of the clinical concept. Extract test name only.
- **c3b0140ffe2d...** entity[1] `None`: `None` -> `None` (conf=0.95) -- Redundant extraction. Value and unit already captured in Entity 0 (observable_entity). Duplicate qualifier_value should not be extracted.
- **eb27b3d09077...** entity[1] `None`: `None` -> `None` (conf=1.00) -- Observable entity values (value + unit + reference_range) are fields of the observable entity, not standalone entities. '93 fL' is redundantly captured. Per rules: 'Bare numeric values without a clinical parameter' should not be extracted.
- **660ff58660f6...** entity[1] `None`: `None` -> `None` (conf=0.98) -- Bare numeric measurement value already captured in entity 0 (value='4.8', unit='%'). Extracting it as a separate qualifier_value is redundant and violates the 'do not extract bare numeric values without a clinical parameter' rule.
- **a281af4444f3...** entity[0] `text`: `Abdominal pain` -> `Abdominal pain` (conf=1.00) -- Text is correct but span is over-captured (end=93 covers entire sentence). Correct span is ~2–16. Script will recompute offsets from text.

## Sample Proposals for Human Review (up to 10)

- **a9254b263d29...** entity[0] `assertion`: `absent` -> `present` (conf=0.90) -- Sentence does not start with negation; line documents a screening report/communication rather than negating the test.
- **60f0b7265b67...** entity[0] `start/end`: `0/44` -> `None` (conf=1.00) -- Span mismatch: entity.text 'Body Mass Index 25.11' does not correspond to substring at offsets 0-44 (which is 'Examination: Body Mass Index 25.11 (20 - 25)'). Correct offsets should begin after 'Examination: ' prefix. This is a read-only field — requires script correction.
- **660ff58660f6...** entity[0] `reference_range`: `4-5.9` -> `4 - 5.9` (conf=0.90) -- Source text reads '[4 - 5.9]'; brackets stripped correctly but internal whitespace around dash should be preserved as written.
- **a2ee564ebe2f...** entity[1] `label`: `qualifier_value` -> `qualifier_value` (conf=0.55) -- Decision ladder permits qualifier_value for value/unit tokens, but the 'Do Not Extract' rule covers bare numeric values without an embedded clinical parameter name. Value and unit are already fully captured in entity 0's structured value/unit fields, making this entity redundant. Human should decide whether the pipeline requires a separate qualifier_value entity or whether entity 0's fields suffice.
- **b4b49448ef4c...** entity[0] `reference_range`: `30-130` -> `30 - 130` (conf=0.92) -- Source text reads '[30 - 130]' with spaces around the hyphen. After stripping brackets, the exact value is '30 - 130', not '30-130'.
- **889c2fe27894...** MISSING: `Lives alone` (situation, present) conf=0.72 -- 'Lives alone' is a clinically relevant social circumstance (isolation risk factor) mappable to a SNOMED situation concept. '(XM0Ct)' is a Read code parenthetical and must not be extracted.
- **cfb6b569e2f8...** entity[0] `start, end (read-only span)`: `0, 38` -> `None` (conf=0.99) -- Span 0:38 covers entire sentence; text='fevers' should match only the word 'fevers' (~3–9). Data quality issue in offset computation.
- **cfb6b569e2f8...** entity[0] `snomed_score (read-only)`: `1.3` -> `None` (conf=0.99) -- snomed_score > 1.0 is invalid; confidence range is [0.0–1.0]. Data quality bug in terminology lookup.
- **211bc9231381...** entity[0] `start/end offsets`: `start: 0, end: 68` -> `None` (conf=1.00) -- Entity text 'Platelet disorder' is 16 chars, but span covers entire sentence (68 chars). Offsets are read-only, but this suggests pipeline span calculation error — verify against original text extraction.
- **b2e3e1966dc1...** MISSING: `2ww referral to urology` (procedure, hypothetical) conf=0.92 -- Conditional action: 'consider 2ww referral' — hypothetical procedure based on UTI exclusion.

## Sample Needs-Review (up to 10)

- **65493f79d162...** entity[0] -- text: Entity span (0-36) over-captures section label '[Diagnosis] '. Correct span starts at position 12. Text itself is correct but span is wrong.; snomed_score: Score exceeds maximum valid range (0.0–1.0). Data quality bug. Read-only field — cannot suggest fix, requires human review.; snomed_term: snomed_term is generic and does not match the extracted text 'Schizoaffective disorder'
- **19c38f8077a3...** entity[0] -- snomed_score: Score exceeds valid range (0.0–1.0). Data quality bug on read-only field — human review required to correct the underlying score.
- **4779fcc12cf9...** entity[0] -- start: Offset span (0–115) covers entire sentence; should span only 'Serum ferritin level' (~0–19). Read-only field; pipeline span computation error.; end: Offset span (0–115) covers entire sentence; should span only 'Serum ferritin level' (~0–19). Read-only field; pipeline span computation error.
- **4779fcc12cf9...** entity[1] -- start: Offset span (0–115) covers entire sentence; should span only 'Borderline' (~29–39). Read-only field; pipeline span computation error.; end: Offset span (0–115) covers entire sentence; should span only 'Borderline' (~29–39). Read-only field; pipeline span computation error.
- **a9254b263d29...** entity[0] -- label: SNOMED term explicitly states 'observable entity', not procedure. FOB test is a measurable parameter, not an action performed.; assertion: Sentence does not start with negation; line documents a screening report/communication rather than negating the test.
- **60f0b7265b67...** entity[0] -- start/end: Span mismatch: entity.text 'Body Mass Index 25.11' does not correspond to substring at offsets 0-44 (which is 'Examination: Body Mass Index 25.11 (20 - 25)'). Correct offsets should begin after 'Examination: ' prefix. This is a read-only field — requires script correction.
- **a281af4444f3...** entity[0] -- text: Text is correct but span is over-captured (end=93 covers entire sentence). Correct span is ~2–16. Script will recompute offsets from text.; snomed_score: Score > 1.0 is invalid (max 1.0). Read-only field — flag for review only.
- **a281af4444f3...** entity[1] -- text: Text is correct but span is over-captured (end=93 covers entire sentence). Correct span is ~45–64. Script will recompute offsets from text.; snomed_score: Score > 1.0 is invalid (max 1.0). Read-only field — flag for review only.
- **a2ee564ebe2f...** entity[1] -- label: Decision ladder permits qualifier_value for value/unit tokens, but the 'Do Not Extract' rule covers bare numeric values without an embedded clinical parameter name. Value and unit are already fully captured in entity 0's structured value/unit fields, making this entity redundant. Human should decide whether the pipeline requires a separate qualifier_value entity or whether entity 0's fields suffice.; assertion: Entity is missing the assertion field entirely; no negation cues in s0, so assertion should be 'present' if this entity is retained.
- **794b6e4ba3a1...** entity[0] -- snomed_score: snomed_score > 1.0 is a data quality bug; cannot suggest replacement here; start: Entity text is 'dysuria' but offsets span entire sentence (0-57). Read-only field; script will recompute.
