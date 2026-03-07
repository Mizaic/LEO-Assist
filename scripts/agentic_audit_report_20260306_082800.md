# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 08:30 UTC  
**Mode:** APPLY  
**Records audited:** 11602  
**Elapsed:** 86521s (7.5s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 2628 |
| Records with issues | 8973 |
| Errors (parse/LLM) | 1 |
| Total auto-fixes | 7987 |
| Total proposals (human review) | 9856 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 5520 |
| fixable | 1954 |
| needs_review | 7570 |
| remove | 1953 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 3703 |
| label | 2652 |
| assertion | 1064 |
| normalized | 217 |
| reference_range | 156 |
| unit | 112 |
| value | 83 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| needs_review | 6693 |
| missing | 2499 |
| remove | 365 |
| fixable | 299 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 50,823,981 |
| Total output tokens | 4,462,899 |
| Cached input tokens | 44,623,488 |
| Guardrail total tokens | 55,286,880 |
| Estimated cost | $108.16 |

## Sample Auto-Fixes (up to 10)

- **7264900b17fc...** entity[0] `text`: `Urea and electrolytes` -> `Urea and electrolytes` (conf=0.99) -- Span over-captured (start=0, end=138 covers entire sentence) and entity is an observable without a measured value, which should not be extracted.
- **1cd71720d11c...** entity[2] `text`: `- Outside reference range` -> `Outside reference range` (conf=0.99) -- Leading hyphen and space are over-captured; not part of clinical concept
- **1cd71720d11c...** entity[2] `label`: `finding` -> `qualifier_value` (conf=0.95) -- Result descriptor should be qualifier_value, not finding, per observable entity rules
- **f5816ec692ed...** entity[0] `assertion`: `absent` -> `present` (conf=0.99) -- Lab result with measured value 13.8 mg/mmol; no negation present. Assertion should be present.
- **049d2bd9908a...** entity[0] `text`: `Haematocrit ([POSTCODE]) 0.439  [0.4 - 0.54]` -> `Haematocrit` (conf=0.99) -- Text span is over-captured; should include only the clinical parameter name, not postcode placeholder, value, or reference range.
- **201545baf271...** entity[0] `normalized`: `None` -> `Cervical lymphadenopathy` (conf=0.95) -- Normalized term should contain a standard clinical term for SNOMED lookup
- **b4000bbb2855...** entity[1] `label`: `qualifier_value` -> `REMOVE_ENTITY` (conf=0.99) -- Value is already captured within the observable entity; standalone qualifier_value is not an allowed semantic tag and duplicates information.
- **50f9a4313da9...** entity[0] `text`: `FIT test` -> `FIT test` (conf=0.99) -- Text span offsets (0–116) cover entire sentence, not the exact substring 'FIT test'. Offsets are read-only so require review.
- **3cb1f7b68137...** entity[0] `text`: `high psa` -> `high psa` (conf=0.99) -- Entity start/end (0–87) span entire sentence; text field does not match that substring, indicating offset/span inconsistency.
- **e47b571dd1a8...** entity[0] `text`: `Smoker` -> `Smoker` (conf=0.95) -- Start/end offsets (0–15) cover 'History: Smoker'; text span should match exact surface form 'Smoker' only.

## Sample Proposals for Human Review (up to 10)

- **e0477e1874bf...** entity[0] `snomed_score`: `1.3` -> `1.0` (conf=0.99) -- SNOMED score exceeds 1.0, which is a data quality bug per specification
- **7264900b17fc...** entity[0] `assertion`: `absent` -> `present` (conf=0.90) -- No negation in sentence; 'Normal - No action' does not indicate absence of the test.
- **956ac14c2ccc...** entity[0] `snomed_score`: `1.1` -> `1.0` (conf=0.99) -- snomed_score exceeds 1.0 which is a data quality bug per specification
- **1cd71720d11c...** entity[0] `normalized`: `haemoglobin concentration` -> `haemoglobin concentration in blood` (conf=0.71) -- SNOMED term refers to erythrocyte concentration; text implies general blood haemoglobin concentration
- **1e285b8fdcd0...** entity[0] `normalized`: `haemoglobin concentration` -> `Haemoglobin concentration in blood` (conf=0.75) -- SNOMED term refers to erythrocyte haemoglobin concentration, not general blood haemoglobin concentration stated in text
- **201545baf271...** entity[0] `snomed_score`: `1.1` -> `needs_review` (conf=1.00) -- SNOMED score > 1.0 indicates data quality bug; read-only field requires human review
- **48bdf0f6665b...** entity[0] `snomed_score`: `1.3` -> `needs_review` (conf=1.00) -- SNOMED score > 1.0 indicates a data quality bug; scores should not exceed 1.0.
- **48bdf0f6665b...** MISSING: `night sweats` (finding, absent) conf=0.98 -- Negated symptom in same sentence beginning with 'denies' not extracted.
- **48bdf0f6665b...** MISSING: `recurrent infections` (finding, absent) conf=0.95 -- Negated clinical finding in 'denies' sentence not extracted.
- **48bdf0f6665b...** MISSING: `lumps/bumps` (finding, absent) conf=0.90 -- Negated symptom in 'denies' sentence not extracted.

## Sample Needs-Review (up to 10)

- **e0477e1874bf...** entity[0] -- snomed_score: SNOMED score exceeds 1.0, which is a data quality bug per specification
- **956ac14c2ccc...** entity[0] -- snomed_score: snomed_score exceeds 1.0 which is a data quality bug per specification
- **1cd71720d11c...** entity[0] -- normalized: SNOMED term refers to erythrocyte concentration; text implies general blood haemoglobin concentration
- **f5816ec692ed...** entity[0] -- assertion: Lab result with measured value 13.8 mg/mmol; no negation present. Assertion should be present.
- **1e285b8fdcd0...** entity[0] -- normalized: SNOMED term refers to erythrocyte haemoglobin concentration, not general blood haemoglobin concentration stated in text
- **201545baf271...** entity[0] -- normalized: Normalized term should contain a standard clinical term for SNOMED lookup; snomed_score: SNOMED score > 1.0 indicates data quality bug; read-only field requires human review
- **48bdf0f6665b...** entity[0] -- snomed_score: SNOMED score > 1.0 indicates a data quality bug; scores should not exceed 1.0.
- **50f9a4313da9...** entity[0] -- text: Text span offsets (0–116) cover entire sentence, not the exact substring 'FIT test'. Offsets are read-only so require review.; snomed_score: SNOMED score is >1.0, which is a data quality bug per rules and requires review.
- **3cb1f7b68137...** entity[0] -- text: Entity start/end (0–87) span entire sentence; text field does not match that substring, indicating offset/span inconsistency.
- **e47b571dd1a8...** entity[0] -- text: Start/end offsets (0–15) cover 'History: Smoker'; text span should match exact surface form 'Smoker' only.; label: Smoking status is a risk/status statement and should be tagged as 'situation', not 'finding'. Also snomed_score >1.0 indicates a data quality issue requiring review.
