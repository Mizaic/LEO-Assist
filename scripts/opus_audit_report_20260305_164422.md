# Opus Training Label Audit Report

**Date:** 2026-03-05 16:44 UTC  
**Mode:** DRY-RUN  
**Records audited:** 5  
**Elapsed:** 33s (6.5s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 0 |
| Records with issues | 5 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 38 |
| Total proposals (human review) | 70 |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 0 |
| fixable | 22 |
| needs_review | 0 |
| remove | 1 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| end | 20 |
| start | 18 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| fixable | 49 |
| missing | 19 |
| remove | 2 |

## Token Usage

| Metric | Tokens |
|--------|--------|
| Total input | 22,992 |
| Total output | 9,532 |
| Cached input | 0 |

## Sample Auto-Fixes (up to 10)

- **484b053ba771...** entity[0] `end`: `83` -> `38` (conf=0.97) — Span [20,83) covers entire sentence including diagnosis. 'Colposcopy biopsy' is chars 20-38.
- **484b053ba771...** entity[1] `start`: `20` -> `39` (conf=0.97) — 'squamous cell carcinoma of cervix stage IB1' starts at char 39, not 20. Current span includes 'Colposcopy biopsy: '.
- **484b053ba771...** entity[2] `end`: `133` -> `94` (conf=0.97) — Span [84,133) covers entire sentence. 'MRI pelvis' is chars 84-94.
- **484b053ba771...** entity[3] `start`: `134` -> `154` (conf=0.97) — 'radical hysterectomy with pelvic lymph node dissection' starts at char 154, not 134. Current span includes 'MDT recommendation: '.
- **484b053ba771...** entity[3] `end`: `209` -> `208` (conf=0.95) — Span should exclude trailing period. Text ends at char 208.
- **1684fc9cac9c...** entity[0] `start`: `17` -> `38` (conf=0.98) — Span [17,74) covers entire sentence including 'Hysteroscopy biopsy: ' and trailing period. Should be [38,73) for exact surface form.
- **1684fc9cac9c...** entity[0] `end`: `74` -> `73` (conf=0.98) — End offset 74 includes the period. The text 'grade 1 endometrioid adenocarcinoma' ends at 73.
- **1684fc9cac9c...** entity[1] `start`: `75` -> `133` (conf=0.99) — Span [75,208) starts at sentence s2 (MRI pelvis). Actual text begins at offset 133 in sentence s3.
- **1684fc9cac9c...** entity[1] `end`: `208` -> `197` (conf=0.99) — End 208 includes ' performed.' — surface form ends at 197 ('...oophorectomy').
- **1684fc9cac9c...** entity[2] `start`: `209` -> `244` (conf=0.98) — Span [209,256) covers entire sentence s4. 'cancer' starts at offset 244.

## Sample Proposals for Human Review (up to 10)

- **484b053ba771...** entity[0] `snomed_term`: `Colposcopy (procedure)` -> `None` (conf=0.85) — needs_review: SNOMED maps to 'Colposcopy' but text is 'Colposcopy biopsy' — a biopsy via colposcopy is a more specific concept.
- **484b053ba771...** entity[0] `snomed_score`: `1.3` -> `None` (conf=0.95) — Score 1.3 exceeds valid 0-1 range; likely a pipeline bug.
- **484b053ba771...** entity[0] `normalized`: `colposcopy biopsy` -> `biopsy of cervix using colposcope` (conf=0.75) — Normalized should be a standard clinical term suitable for SNOMED lookup.
- **484b053ba771...** entity[1] `normalized`: `None` -> `squamous cell carcinoma of cervix stage IB1` (conf=0.95) — Normalized should not be null; should be a standard clinical term for SNOMED lookup.
- **484b053ba771...** entity[1] `snomed_score`: `1.3` -> `None` (conf=0.95) — Score 1.3 exceeds valid 0-1 range; likely a pipeline bug.
- **484b053ba771...** entity[2] `snomed_score`: `1.3` -> `None` (conf=0.95) — Score 1.3 exceeds valid 0-1 range; likely a pipeline bug.
- **484b053ba771...** entity[3] `normalized`: `None` -> `radical hysterectomy with pelvic lymph node dissection` (conf=0.90) — Normalized should not be null; should be a standard clinical term for SNOMED lookup.
- **484b053ba771...** entity[3] `snomed_score`: `1.3` -> `None` (conf=0.95) — Score 1.3 exceeds valid 0-1 range; likely a pipeline bug.
- **484b053ba771...** entity[3] `snomed_term`: `Radical excision with lymph node dissection (procedure)` -> `None` (conf=0.80) — needs_review: snomed_term is generic 'radical excision'; a more specific concept for radical hysterectomy + pelvic LND may exist.
- **484b053ba771...** MISSING: `stage IB1` (qualifier_value, present) conf=0.82 — Tumour staging 'IB1' is a distinct qualifier_value concept per decision ladder step 10; not separately extracted.
