# Opus Training Label Audit Report

**Date:** 2026-03-05 16:52 UTC  
**Mode:** DRY-RUN  
**Records audited:** 5  
**Elapsed:** 26s (5.2s/record)  

## Summary


| Metric                         | Count |
| ------------------------------ | ----- |
| Records passed                 | 0     |
| Records with issues            | 5     |
| Errors (parse/LLM)             | 0     |
| Total auto-fixes               | 0     |
| Total proposals (human review) | 20    |


## Entity Verdict Breakdown


| Verdict      | Count |
| ------------ | ----- |
| correct      | 0     |
| fixable      | 1     |
| needs_review | 21    |
| remove       | 1     |


## Proposal Type Breakdown


| Type    | Count |
| ------- | ----- |
| missing | 18    |
| remove  | 1     |
| fixable | 1     |


## Token Usage


| Metric       | Tokens |
| ------------ | ------ |
| Total input  | 25,057 |
| Total output | 6,032  |
| Cached input | 0      |


## Sample Proposals for Human Review (up to 10)

- **484b053ba771...** MISSING: `stage IB1` (qualifier_value, present) conf=0.82 — FIGO staging IB1 is a distinct qualifier/staging concept that should be extracted separately from the disorder
- **484b053ba771...** MISSING: `disease confined to cervix` (finding, present) conf=0.78 — MRI finding confirming disease confined to cervix is a clinically significant imaging result not extracted
- **1684fc9cac9c...** MISSING: `Hysteroscopy biopsy` (procedure, present) conf=0.95 — Hysteroscopy biopsy is a distinct procedure mentioned in s1, not extracted.
- **1684fc9cac9c...** MISSING: `MRI pelvis` (procedure, present) conf=0.95 — MRI pelvis is a diagnostic imaging procedure mentioned in s2, not extracted.
- **1684fc9cac9c...** MISSING: `disease confined to uterine corpus` (finding, present) conf=0.85 — MRI finding describing disease extent in s2, clinically significant, not extracted.
- **1684fc9cac9c...** MISSING: `stage 1A` (finding, present) conf=0.88 — Tumour staging qualifier in s2, clinically significant, not extracted.
- **1684fc9cac9c...** MISSING: `pT1a N0 M0` (finding, present) conf=0.90 — Pathological TNM staging in s4, clinically significant, not extracted.
- **1684fc9cac9c...** MISSING: `Gynaecology MDT` (procedure, present) conf=0.80 — Multidisciplinary team discussion is a clinical procedure/event in s0, not extracted.
- **d65d99b22add...** entity[4] `text`: `Cancer diagnosis confirmed` -> `None` (conf=0.90) — Duplicate of entity 0. 'Cancer diagnosis confirmed' is an administrative confirmation statement, not a separate clinical concept. The specific diagnosis is already captured in entity 0.
- **d65d99b22add...** MISSING: `Staging CT` (procedure, present) conf=0.85 — CT staging scan was performed (results reported). Should be extracted as a procedure entity.

## Sample Needs-Review (up to 10)

- **484b053ba771...** entity[0] — text: Text field says 'Colposcopy biopsy' but start/end (20-83) spans entire sentence including the carcinoma diagnosis. Offsets are wrong but read-only; text is correct.; normalized: Normalized should reflect the full procedure concept including biopsy, not just colposcopy
- **484b053ba771...** entity[1] — normalized: Normalized should not be null; should be a standard clinical term for SNOMED lookup
- **484b053ba771...** entity[2] — text: Text is correct but start/end (84-133) spans entire sentence. Offsets are read-only; flagging for review.
- **484b053ba771...** entity[3] — text: Text is correct but start/end (134-209) spans entire sentence including 'MDT recommendation:'. Offsets are read-only; flagging.; normalized: Normalized should not be null; should provide a standard clinical term for SNOMED lookup
- **1684fc9cac9c...** entity[0] — text: Text span (17-74) covers entire sentence including 'Hysteroscopy biopsy: ' prefix and period. Correct text starts at offset 38, ends at 73.; snomed_score: snomed_score > 1.0 is a data quality bug — flag for review.
- **1684fc9cac9c...** entity[1] — text: Span 75-208 covers sentences s2 and s3 entirely. Correct text is in s3 starting at offset 133, ending at 197. Offsets are grossly wrong.; snomed_score: snomed_score > 1.0 is a data quality bug — flag for review.
- **1684fc9cac9c...** entity[2] — text: Span 209-256 covers entire sentence s4 but text is only 'cancer'. Offsets are wrong; script should recompute from surface form.; normalized: Normalized field is null; should provide a standard clinical term for SNOMED lookup.; snomed_score: snomed_score > 1.0 is a data quality bug — flag for review.
- **d65d99b22add...** entity[0] — text: Span end 100 includes trailing period and 'Histology:' prefix area. Actual text at 31-100 is 'Histology: moderately differentiated adenocarcinoma of sigmoid colon.' — over-captured.; None: snomed_score is 1.3 (>1.0) — data quality bug. snomed_term 'Malignant neoplasm of intestine' is too broad for sigmoid colon adenocarcinoma. Read-only fields — needs human review.
- **d65d99b22add...** entity[1] — text: Span 101-122 covers 'Staging CT: T3 N1 M0.' — over-captured with 'Staging CT:' prefix and period. Correct text is 'T3 N1 M0' starting at char 113.; label: T3 N1 M0 is a composite of three staging qualifier values. Could be split into individual staging components. Flagging for review.
- **d65d99b22add...** entity[2] — text: Span 157-224 covers 'Plan: laparoscopic anterior resection with defunctioning ileostomy.' — over-captured with 'Plan:' prefix and period.; None: snomed_score 1.3 (>1.0) — data quality bug. snomed_term refers to rectum but text says sigmoid colon. Read-only — needs human review.

