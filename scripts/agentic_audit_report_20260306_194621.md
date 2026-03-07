# Agentic Auditor — Training Label Audit Report

**Date:** 2026-03-07 00:01 UTC  
**Mode:** APPLY  
**Records audited:** 5429  
**Elapsed:** 15295s (2.8s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 869 |
| Records with issues | 4551 |
| Errors (parse/LLM) | 9 |
| Total auto-fixes | 3616 |
| Total proposals (human review) | 1747 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Consensus Mode

| Metric | Value |
|--------|-------|
| Records via consensus (small models) | 5420 |
| Small models agreed (no escalation) | 4114 (75.9%) |
| Escalated to big model | 1304 (24.1%) |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 1946 |
| fixable | 869 |
| needs_review | 3764 |
| remove | 1067 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 1385 |
| None | 1011 |
| assertion | 664 |
| label | 431 |
| reference_range | 51 |
| normalized | 29 |
| value | 25 |
| unit | 20 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| missing | 856 |
| needs_review | 669 |
| fixable | 165 |
| remove | 57 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 55,822,193 |
| Total output tokens | 17,418,561 |
| Cached input tokens | 19,764,736 |
| Guardrail total tokens | 75,100,857 |
| Estimated cost | $135.07 |

## Sample Auto-Fixes (up to 10)

- **45e260dc97da...** entity[1] `None`: `None` -> `None` (conf=0.95) -- Bare numeric value without clinical parameter violates extraction rules. Value and unit already captured in Entity 0.
- **8278266d0336...** entity[0] `None`: `None` -> `None` (conf=1.00) -- Span over-captured: text='Serum TSH level' (≈15 chars) but start=0, end=79 covers entire 79-char sentence. Span must match text length.; Observable entity rule: must have measured value (value/unit fields). Entity has value=null, unit=null. Per rules: 'Do not extract observable entity mentions with no actual measured value'.
- **71a35e6f6e5e...** entity[2] `label`: `finding` -> `qualifier_value` (conf=0.98) -- Result descriptors (e.g., 'Outside reference range', 'Abnormal') are qualifier_value, not findings. Per extraction rules: descriptors → qualifier_value.
- **5606d64a83b6...** entity[0] `text`: `Liver function tests` -> `Liver function tests` (conf=0.99) -- Text span grossly over-captured: end=123 covers entire encounter. Correct text 'Liver function tests' appears at start 0, end ~19 only.
- **5606d64a83b6...** entity[0] `label`: `procedure` -> `observable entity` (conf=0.95) -- Test name (Liver function tests) is an observable entity (lab test), not a procedure.
- **5606d64a83b6...** entity[1] `text`: `Abnormal` -> `Abnormal` (conf=0.99) -- Text span over-captured: end=123 is entire encounter. 'Abnormal' appears much earlier (approx chars 37–45). Correct span needed.
- **5606d64a83b6...** entity[2] `text`: `high TGs` -> `high TGs` (conf=0.99) -- Text span over-captured: end=123 is entire encounter. 'high TGs' appears around chars 100–108. Correct span needed.
- **5a3e4a7776d7...** entity[0] `text`: `Serum vitamin B` -> `Serum vitamin B12 level` (conf=1.00) -- Text is truncated and split across entities; full surface form in sentence is 'Serum vitamin B12 level'.
- **5a3e4a7776d7...** entity[1] `None`: `None` -> `None` (conf=1.00) -- Fragment of the observable entity; should be merged into 'Serum vitamin B12 level' not extracted separately.
- **5a3e4a7776d7...** entity[2] `None`: `None` -> `None` (conf=0.99) -- Value and unit should not be separate entity. They are correctly captured in entity 0's value/unit fields. Extracting them as qualifier_value duplicates information.

## Sample Proposals for Human Review (up to 10)

- **f843aa9693b6...** entity[0] `text`: `Platelet count - observation` -> `Platelet count` (conf=0.92) -- "- observation" is a Read-code label annotation artifact, not part of the clinical concept. Over-capture. Normalized correctly uses "platelet count" already.
- **c1322e10dd65...** MISSING: `nil pallor` (finding, absent) conf=0.98 -- Compound negation sentence with two findings. Both 'jaundice' and 'pallor' are clinically significant and both negated by 'Nil'. Pallor extraction missed.
- **c1322e10dd65...** MISSING: `pallor` (finding, absent) conf=0.98 -- Sentence 'Nil jaundice nil pallor' contains a second negated finding 'pallor' that was not extracted.
- **1a4dfa1e638c...** entity[0] `reference_range`: `130-180` -> `130 - 180` (conf=0.88) -- Rule says 'strip brackets' only. Source text is '[130 - 180]'; after stripping brackets the correct value preserves internal spaces: '130 - 180', not '130-180'.
- **1aa0e5b62eaa...** MISSING: `diarrhoea` (finding, present) conf=0.98 -- Clinical finding explicitly mentioned in same sentence ('with diarrhoea') but not extracted as separate entity. Should be extracted as distinct finding.
- **9b611ae9c5c2...** MISSING: `Urea and electrolytes` (procedure, present) conf=0.75 -- U&E report is confirmed as performed (report exists, result 'Satisfactory'). Qualifies as a completed diagnostic procedure per extraction rules.
- **63072dc66a11...** entity[0] `start/end offsets`: `start: 0, end: 52` -> `None` (conf=0.98) -- Offsets span entire sentence including headers. Should match only 'Low WCC' text. Read-only field — human review required.
- **cb74a7fd8970...** entity[0] `text`: `Tired all the time` -> `Tired all the time` (conf=0.90) -- Entity text is correct but the provided span (0-30) over-captures the sentence which also contains 'Sweats' — offsets need correction by pipeline.
- **cb74a7fd8970...** MISSING: `Sweats` (finding, present) conf=0.98 -- Second clinical symptom in the same sentence, not extracted. Should be tagged as finding with assertion present (no negation).
- **e56b04e14c8d...** MISSING: `abnormal thought content` (finding, absent) conf=0.98 -- Sentence 's0' opens with 'No evidence of' — negation covers all clinical entities. 'abnormal thought content' is a distinct psychiatric finding that should be extracted separately.

## Sample Needs-Review (up to 10)

- **b2f5dcacea71...** entity[0] -- snomed_score: Score exceeds 1.0 — impossible for a probability metric. Data quality bug requiring human verification of the SNOMED coding.
- **71a35e6f6e5e...** entity[0] -- snomed_term: snomed_term indicates a 'procedure' but entity is labelled 'observable entity' (measured test). Read-only SNOMED mismatch requires review.
- **5606d64a83b6...** entity[0] -- text: Text span grossly over-captured: end=123 covers entire encounter. Correct text 'Liver function tests' appears at start 0, end ~19 only.; label: Test name (Liver function tests) is an observable entity (lab test), not a procedure.
- **5606d64a83b6...** entity[1] -- text: Text span over-captured: end=123 is entire encounter. 'Abnormal' appears much earlier (approx chars 37–45). Correct span needed.
- **5606d64a83b6...** entity[2] -- text: Text span over-captured: end=123 is entire encounter. 'high TGs' appears around chars 100–108. Correct span needed.
- **7e3c74fd7766...** entity[0] -- snomed_term: Entity labeled 'observable entity' but snomed_term is a 'measurement (procedure)' — read-only coding mismatch requires human review
- **c1322e10dd65...** entity[0] -- text: Span end=23 over-captures entire sentence including 'pallor'. Text field is correct but span should be 0–12, not 0–23.; snomed_score: snomed_score > 1.0 is invalid (max 1.0). Data quality bug in terminology layer — human review required.
- **1a4dfa1e638c...** entity[0] -- reference_range: Rule says 'strip brackets' only. Source text is '[130 - 180]'; after stripping brackets the correct value preserves internal spaces: '130 - 180', not '130-180'.; snomed_term: Coded concept describes MCHC (Hb concentration inside erythrocytes), not total blood haemoglobin concentration. Likely incorrect SNOMED mapping; requires human terminology review.
- **b85ade054265...** entity[0] -- text: Entity span 0-102 over-captures entire line. Correct span should be 0-20, covering only the test name.; assertion: Sentence indicates the test/result is present with 'Normal - No Action' so the procedure was performed; assertion should be present.
- **1aa0e5b62eaa...** entity[0] -- snomed_score: snomed_score exceeds maximum valid range (0.0–1.0). Data quality bug in read-only field; human review required.; start: Span (0–65) encompasses entire sentence. Text 'altered bowel habit' begins ~9 chars in. Span mismatch — flagged as read-only field issue.; end: Span end should correspond to end of 'altered bowel habit', not entire sentence. Mismatch with text field.
