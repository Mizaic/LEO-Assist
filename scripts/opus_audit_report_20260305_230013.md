# Opus Training Label Audit Report

**Date:** 2026-03-05 23:01 UTC  
**Mode:** DRY-RUN  
**Records audited:** 10  
**Elapsed:** 60s (6.0s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 0 |
| Records with issues | 10 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 5 |
| Total proposals (human review) | 41 |
| Total agentic tool calls | 0 |
| Second opinions requested | 0 |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 2 |
| fixable | 7 |
| needs_review | 37 |
| remove | 2 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 4 |
| label | 1 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| missing | 29 |
| fixable | 8 |
| needs_review | 2 |
| remove | 2 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 60,103 |
| Total output tokens | 18,770 |
| Cached input tokens | 0 |
| Guardrail total tokens | 78,873 |
| Estimated cost | $2.31 |

## Sample Auto-Fixes (up to 10)

- **1684fc9cac9c...** entity[0] `text`: `grade 1 endometrioid adenocarcinoma` -> `grade 1 endometrioid adenocarcinoma` (conf=0.98) -- Text string is correct but start/end span (17–74) covers entire sentence incl 'Hysteroscopy biopsy:' and period — span over-captured
- **d65d99b22add...** entity[1] `text`: `T3 N1 M0` -> `T3 N1 M0` (conf=0.95) -- Text correct but span 101–122 includes 'Staging CT: ' prefix and period; span over-captured
- **738f83295edf...** entity[1] `label`: `substance` -> `regime/therapy` (conf=0.95) -- R-CHOP is a named chemotherapy regimen, not a single substance. SNOMED term itself is tagged (regime/therapy).
- **5ecd02417b2a...** entity[2] `text`: `4.5 cm right renal mass` -> `4.5 cm right renal mass` (conf=0.98) -- Text correct but start/end span (60-176) covers entire sentence s2; needs recomputation
- **b0d44e28d9f8...** entity[1] `text`: `Gleason 4+3=7` -> `Gleason 4+3=7` (conf=0.95) -- Text is correct but start/end (16-69) covers entire s1. Script will recompute offsets from text match.

## Sample Proposals for Human Review (up to 10)

- **1684fc9cac9c...** entity[0] `snomed_score`: `1.1` -> `None` (conf=0.99) -- snomed_score > 1.0 is a data quality bug — flagging for review
- **1684fc9cac9c...** MISSING: `Hysteroscopy biopsy` (procedure, present) conf=0.95 -- Diagnostic procedure explicitly mentioned in s1 but not extracted as a separate entity
- **1684fc9cac9c...** MISSING: `MRI pelvis` (procedure, present) conf=0.94 -- Imaging procedure in s2 with reported findings; not extracted
- **1684fc9cac9c...** MISSING: `disease confined to uterine corpus` (finding, present) conf=0.82 -- MRI finding describing disease extent in s2; clinically significant, not extracted
- **1684fc9cac9c...** MISSING: `stage 1A` (finding, present) conf=0.88 -- Tumour staging in s2 not extracted; clinically significant qualifier
- **1684fc9cac9c...** MISSING: `pT1a N0 M0` (finding, present) conf=0.88 -- Pathological TNM staging in s3 not extracted; clinically significant
- **1684fc9cac9c...** MISSING: `Gynaecology MDT` (procedure, present) conf=0.80 -- Multidisciplinary team discussion is a clinical procedure in s0; not extracted
- **484b053ba771...** MISSING: `stage IB1` (qualifier_value, present) conf=0.78 -- Tumour staging value IB1 (FIGO) is a distinct qualifier concept not captured separately.
- **484b053ba771...** MISSING: `disease confined to cervix` (finding, present) conf=0.82 -- MRI finding confirming disease confinement is a clinically significant finding not extracted.
- **f1c2f877e4e1...** entity[4] `assertion`: `hypothetical` -> `cancelled` (conf=0.78) -- 'Deferred' means a planned procedure was postponed/not proceeding — 'cancelled' is closer than 'hypothetical'

## Sample Needs-Review (up to 10)

- **1684fc9cac9c...** entity[1] -- text: Text string correct but start/end (75–208) covers entire sentence incl MRI result — span over-captured; snomed_score: snomed_score > 1.0 is a data quality bug
- **1684fc9cac9c...** entity[2] -- text: Text correct but start/end (209–256) covers entire sentence — span over-captured; normalized: Normalized field should not be null; generic cancer term should have a normalized form; snomed_score: snomed_score > 1.0 is a data quality bug
- **484b053ba771...** entity[0] -- text: Text field is correct but start/end span (20-83) covers entire sentence including the disorder. Span is over-captured.; snomed_score: snomed_score > 1.0 is a data quality bug. Read-only field — flagging for review.
- **484b053ba771...** entity[1] -- text: Text field is correct but start/end span (20-83) covers entire sentence including 'Colposcopy biopsy:'. Span is over-captured.; normalized: Normalized should provide a standard clinical term for SNOMED lookup.; snomed_score: snomed_score > 1.0 is a data quality bug. Read-only field — flagging for review.
- **484b053ba771...** entity[2] -- text: Text field is correct but start/end span (84-133) covers entire sentence. Span is over-captured.; snomed_score: snomed_score > 1.0 is a data quality bug. Read-only field — flagging for review.
- **484b053ba771...** entity[3] -- text: Text field is correct but start/end span (134-209) covers 'MDT recommendation:' prefix. Span is over-captured.; snomed_score: snomed_score > 1.0 is a data quality bug. Read-only field — flagging for review.
- **f1c2f877e4e1...** entity[0] -- text: Text is correct but start/end span (21–137) covers entire sentence; needs recomputation to match surface form only; normalized: Text in parentheses clarifies: 'high grade urothelial carcinoma' is the standard clinical term
- **f1c2f877e4e1...** entity[1] -- text: Text correct but start/end span (21–137) covers entire sentence; needs recomputation to match surface form
- **f1c2f877e4e1...** entity[2] -- assertion: 'excluded on restaging TURBT' implies active investigation ruled it out — 'refuted' is more precise than 'absent'
- **fe7213b12833...** entity[0] -- text: Text is correct but start/end span (22–118) covers entire sentence including 'Core biopsy histology:' and receptor results — over-captured offsets; snomed_score: snomed_score > 1.0 is a data quality bug — read-only field, flagging for review
