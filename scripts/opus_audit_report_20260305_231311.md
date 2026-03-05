# Opus Training Label Audit Report

**Date:** 2026-03-05 23:29 UTC  
**Mode:** DRY-RUN  
**Records audited:** 10  
**Elapsed:** 984s (98.4s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 0 |
| Records with issues | 10 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 1 |
| Total proposals (human review) | 39 |
| Total agentic tool calls | 102 |
| Second opinions requested | 30 |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 3 |
| fixable | 5 |
| needs_review | 38 |
| remove | 2 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| normalized | 1 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| missing | 30 |
| fixable | 6 |
| remove | 2 |
| needs_review | 1 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 60,103 |
| Total output tokens | 17,351 |
| Cached input tokens | 0 |
| Guardrail total tokens | 811,645 |
| Estimated cost | $15.17 |

## Sample Auto-Fixes (up to 10)

- **5ecd02417b2a...** entity[0] `normalized`: `None` -> `renal mass` (conf=0.95) -- Normalized should be populated with standard clinical term

## Sample Proposals for Human Review (up to 10)

- **f1c2f877e4e1...** entity[4] `assertion`: `hypothetical` -> `declined` (conf=0.72) -- 'Deferred' means a planned procedure was postponed/not pursued — closer to 'declined' or 'cancelled' than 'hypothetical'
- **f1c2f877e4e1...** MISSING: `TURBT` (procedure, present) conf=0.88 -- TURBT pathology referenced in s1 — the procedure that produced the pathology result was not extracted
- **f1c2f877e4e1...** MISSING: `restaging TURBT` (procedure, present) conf=0.92 -- Restaging TURBT in s2 is a distinct procedure that was performed to exclude muscle invasion
- **f1c2f877e4e1...** MISSING: `T1` (finding, present) conf=0.82 -- T1 tumour staging explicitly stated in s1; represents pathological stage finding
- **1684fc9cac9c...** MISSING: `Hysteroscopy biopsy` (procedure, present) conf=0.95 -- Clinically significant diagnostic procedure mentioned in s1 but not extracted as a separate entity
- **1684fc9cac9c...** MISSING: `MRI pelvis` (procedure, present) conf=0.95 -- Imaging procedure in s2 with reported findings; not extracted
- **1684fc9cac9c...** MISSING: `disease confined to uterine corpus` (finding, present) conf=0.82 -- MRI finding describing disease extent in s2; clinically significant staging information
- **1684fc9cac9c...** MISSING: `stage 1A` (finding, present) conf=0.88 -- FIGO staging in s2 — clinically significant tumour staging not extracted
- **1684fc9cac9c...** MISSING: `pT1a N0 M0` (finding, present) conf=0.88 -- TNM pathological staging in s3 — clinically significant tumour staging not extracted
- **1684fc9cac9c...** MISSING: `Gynaecology MDT` (procedure, present) conf=0.80 -- Multidisciplinary team discussion is a clinical procedure mentioned in s0

## Sample Needs-Review (up to 10)

- **f1c2f877e4e1...** entity[0] -- text: Text is correct but start/end span (21-137) covers entire sentence; needs recomputation to match actual surface form; normalized: Text in parentheses provides the modern equivalent term; normalized should reflect this
- **f1c2f877e4e1...** entity[1] -- text: Text correct but start/end span (21-137) covers entire sentence; needs recomputation to match surface form
- **f1c2f877e4e1...** entity[2] -- assertion: 'Excluded on restaging TURBT' implies active investigation ruled it out — 'refuted' may be more precise than 'absent'
- **1684fc9cac9c...** entity[0] -- text: Text surface form is correct but start offset 17 over-captures 'Hysteroscopy biopsy: '; correct start is ~40. Script should recompute offsets from text.; snomed_score: snomed_score > 1.0 is a data quality bug — read-only field, flagging for human review.; label: Label 'disorder' is correct, but coded SNOMED concept 30289006 is semantic tag 'morphologic abnormality', not 'disorder'. Concept 1260086007 (Endometrioid carcinoma of endometrium) is a true disorder. Needs human SNOMED review.
- **1684fc9cac9c...** entity[1] -- text: Text string is correct but offsets 75–208 are massively over-captured, spanning from MRI pelvis through 'performed'. Script should recompute offsets from corrected text.; snomed_score: snomed_score > 1.0 is a data quality bug — flag for review.; snomed_term (read-only): SNOMED 414575003 specifies 'Laparoscopic' but text describes open abdominal approach. 116144002 'Total abdominal hysterectomy with bilateral salpingo-oophorectomy' is the correct match.
- **1684fc9cac9c...** entity[2] -- text: Offsets 209-256 span 'cancer confirmed' or wider; text field says 'cancer' but offsets are inconsistent — over-captured span; normalized: Normalized should not be null; 'cancer' maps to 'malignant neoplastic disease' as a standard clinical term; snomed_score: snomed_score > 1.0 is a data quality bug — read-only field, flagging for human review
- **484b053ba771...** entity[0] -- text: Text surface form is correct but start/end span (20-83) covers the entire phrase including the disorder. Span must be narrowed to match the 18-char text only.; snomed_score: snomed_score > 1.0 is a data quality bug; scores must be 0.0-1.0.; normalized: Context specifies cervix; normalized should reflect full concept. SNOMED 'Colposcopy (procedure)' misses biopsy; 50796003 'Cervical biopsy' or similar combined concept may be more appropriate.
- **484b053ba771...** entity[1] -- text: Start/end span (20–83) over-captures 'Colposcopy biopsy: ' prefix. Also, 'stage IB1' is a staging qualifier that may warrant a separate qualifier_value entity. The disorder text should be 'squamous cell carcinoma of cervix'.; normalized: Normalized is null; should provide a standard clinical term for SNOMED lookup.; snomed_score: snomed_score > 1.0 is a data quality bug — scores must be 0.0–1.0.
- **484b053ba771...** entity[2] -- text: Text value is correct but start/end span (84-133) is grossly over-captured, covering ~50 chars instead of 10. Script should recompute offsets from text.; snomed_score: snomed_score 1.3 exceeds valid range 0.0-1.0; data quality bug. SNOMED concept 2690005 is semantically correct but score is invalid.
- **484b053ba771...** entity[3] -- snomed_score: snomed_score > 1.0 is a data quality bug; scores must be 0.0–1.0.; normalized: Normalized is null; should contain standard clinical term for SNOMED lookup.

## Sample Agentic Tool Calls (up to 5)

- **1684fc9cac9c...** `resolve_term` input={"text": "grade 1 endometrioid adenocarcinoma", "label": "disorder"}
- **1684fc9cac9c...** `get_related_concepts` input={"concept_id": "30289006"}
- **1684fc9cac9c...** `get_second_opinion` input={"entity_index": 0, "question": "What are the exact character positions (start and end) of the substring \"grade 1 endometrioid adenocarcinoma\" in the encounter text? Does the entity's current start offset of 17 correctly point to the beginning of this text?"}
- **1684fc9cac9c...** `resolve_term` input={"text": "total abdominal hysterectomy and bilateral salpingo-oophorectomy", "label": "procedure"}
- **1684fc9cac9c...** `get_related_concepts` input={"concept_id": "414575003"}
