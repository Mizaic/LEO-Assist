# Opus Training Label Audit Report

**Date:** 2026-03-05 23:19 UTC  
**Mode:** DRY-RUN  
**Records audited:** 10  
**Elapsed:** 963s (96.3s/record)  

## Summary

| Metric | Count |
|--------|-------|
| Records passed | 0 |
| Records with issues | 10 |
| Errors (parse/LLM) | 0 |
| Total auto-fixes | 3 |
| Total proposals (human review) | 38 |
| Total agentic tool calls | 115 |
| Second opinions requested | 27 |

## Entity Verdict Breakdown

| Verdict | Count |
|---------|-------|
| correct | 2 |
| fixable | 6 |
| needs_review | 38 |
| remove | 2 |

## Auto-Fix Field Breakdown

| Field | Count |
|-------|-------|
| text | 3 |

## Proposal Type Breakdown

| Type | Count |
|------|-------|
| missing | 26 |
| fixable | 7 |
| needs_review | 3 |
| remove | 2 |

## Token Usage & Cost

| Metric | Value |
|--------|-------|
| Total input tokens | 60,103 |
| Total output tokens | 18,196 |
| Cached input tokens | 0 |
| Guardrail total tokens | 786,070 |
| Estimated cost | $14.53 |

## Sample Auto-Fixes (up to 10)

- **1684fc9cac9c...** entity[0] `text`: `grade 1 endometrioid adenocarcinoma` -> `grade 1 endometrioid adenocarcinoma` (conf=0.99) -- Text value is correct but start/end span (17–74) covers entire sentence including 'Hysteroscopy biopsy:' and trailing period. Script will recompute offsets from corrected text.
- **1684fc9cac9c...** entity[2] `text`: `cancer` -> `cancer` (conf=0.99) -- Text value correct but start/end span (209–256) covers entire sentence s3. Script will recompute offsets.
- **5ecd02417b2a...** entity[2] `text`: `4.5 cm right renal mass` -> `4.5 cm right renal mass` (conf=0.95) -- Text correct but span (start:60, end:176) covers entire sentence s2; over-captured.

## Sample Proposals for Human Review (up to 10)

- **f1c2f877e4e1...** entity[4] `assertion`: `hypothetical` -> `cancelled` (conf=0.78) -- 'Deferred' means a planned procedure was postponed/not proceeding — 'cancelled' better fits than 'hypothetical'
- **f1c2f877e4e1...** MISSING: `TURBT` (procedure, present) conf=0.90 -- TURBT pathology referenced in s1 — the procedure was performed and yielded pathology results
- **f1c2f877e4e1...** MISSING: `restaging TURBT` (procedure, present) conf=0.93 -- Restaging TURBT explicitly mentioned in s2 as the investigation that excluded muscle invasive disease
- **f1c2f877e4e1...** MISSING: `T1` (finding, present) conf=0.85 -- T1 tumour staging explicitly stated in s1; represents pathological stage finding
- **1684fc9cac9c...** entity[0] `snomed_score`: `1.1` -> `None` (conf=0.99) -- snomed_score >1.0 is a data quality bug — flagging for review (read-only field).
- **1684fc9cac9c...** entity[2] `normalized`: `None` -> `malignant neoplastic disease` (conf=0.90) -- Normalized field should not be null; 'malignant neoplastic disease' matches the SNOMED term.
- **1684fc9cac9c...** entity[2] `snomed_score`: `1.3` -> `None` (conf=0.99) -- snomed_score >1.0 is a data quality bug — flagging for review (read-only field).
- **1684fc9cac9c...** MISSING: `Hysteroscopy biopsy` (procedure, present) conf=0.95 -- Clinically significant procedure in s1 not extracted; biopsy result follows.
- **1684fc9cac9c...** MISSING: `MRI pelvis` (procedure, present) conf=0.93 -- Imaging procedure in s2 with reported findings not extracted.
- **1684fc9cac9c...** MISSING: `disease confined to uterine corpus` (finding, present) conf=0.88 -- MRI finding describing disease extent in s2 not extracted.

## Sample Needs-Review (up to 10)

- **f1c2f877e4e1...** entity[0] -- text: Text is correct but start/end span (21-137) covers entire sentence; needs recomputation to match actual surface form; normalized: Text in parentheses provides the modern equivalent term; normalized should reflect this
- **f1c2f877e4e1...** entity[1] -- text: Text is correct but start/end span (21-137) covers entire sentence; needs recomputation to match actual surface form
- **f1c2f877e4e1...** entity[2] -- assertion: 'Excluded on restaging TURBT' implies active investigation ruled it out — 'refuted' may be more precise than 'absent'; needs human review
- **1684fc9cac9c...** entity[1] -- text: Text string is correct but start/end offsets (75–208) are wrong; they span unrelated text. Script will recompute offsets from the corrected text.; snomed_score: snomed_score >1.0 is a data quality bug. Read-only field — flagging for human review.; snomed_term: Encounter says open 'Total abdominal hysterectomy', coded concept specifies 'Laparoscopic'. Clinically distinct approaches — wrong concept. Read-only field, needs human review.
- **484b053ba771...** entity[0] -- text: Text value is correct but start/end span (20–83) covers 'Colposcopy biopsy: squamous cell carcinoma of cervix stage IB1'. Span must be narrowed to match the 18-char surface form.; snomed_score: snomed_score >1.0 is a data quality bug — flag for review.; snomed_term: SNOMED 'Colposcopy' omits the biopsy component. A more specific concept (e.g. 'Colposcopic biopsy of cervix') likely exists. Terminology tools unavailable; needs human review.
- **484b053ba771...** entity[1] -- text: Text value is correct but start/end span (20–83) over-captures 'Colposcopy biopsy: ' prefix. Script should recompute offsets from corrected text match.; normalized: Normalized should not be null; standard clinical term for SNOMED lookup should be provided.; snomed_score: snomed_score >1.0 is a data quality bug — flagging for review (read-only field, no fix suggested).
- **484b053ba771...** entity[2] -- text: Text value is correct but span 84-133 over-captures 'MRI pelvis confirming disease confined to cervix'. Script should recompute offsets from corrected text.; snomed_score: snomed_score >1.0 is a data quality bug; cannot suggest replacement — flag for review.
- **484b053ba771...** entity[3] -- text: Text string is correct but span end=209 over-captures beyond the 55-char entity. Script should recompute offsets from corrected text.; snomed_score: snomed_score >1.0 is a data quality bug — flag for review. Read-only field, cannot suggest fix.
- **fe7213b12833...** entity[0] -- text: Text surface form is correct but start/end span (22–118) massively over-captures, covering 'Core biopsy histology:' through receptor results. Offsets are read-only; needs human correction.; snomed_score: snomed_score > 1.0 is a data quality bug. Read-only field — flagging for review.; label: Coded SNOMED 82711006 has semantic tag '(morphologic abnormality)', not '(disorder)'. Either the code should be a disorder-level concept or the label should reflect morphology. Needs human review.
- **fe7213b12833...** entity[1] -- text: Text string is correct but start/end span (22–118) massively over-captures; covers 'Core biopsy histology:...HER2 negative'. Script should recompute offsets to match exact substring.; label: ER positive is a biomarker/IHC result (finding), but coded SNOMED 416053008 is semantic tag (disorder). Label 'finding' fits clinical usage; SNOMED concept may need review for alignment.; snomed_score: snomed_score > 1.0 is a data quality bug — read-only field, flagging for human review.

## Sample Agentic Tool Calls (up to 5)

- **1684fc9cac9c...** `resolve_term` input={"text": "total abdominal hysterectomy and bilateral salpingo-oophorectomy", "label": "procedure"}
- **1684fc9cac9c...** `get_related_concepts` input={"concept_id": "414575003"}
- **1684fc9cac9c...** `resolve_term` input={"label": "procedure", "text": "total abdominal hysterectomy bilateral salpingo-oophorectomy"}
- **1684fc9cac9c...** `get_descendants` input={"concept_id": "414575003", "depth": 1}
- **1684fc9cac9c...** `get_second_opinion` input={"entity_index": 1, "question": "Does the entity text \"Total abdominal hysterectomy and bilateral salpingo-oophorectomy\" appear as a verbatim substring in the encounter text, and do the start/end offsets (75\u2013208) correctly correspond to this text in the encounter?"}
