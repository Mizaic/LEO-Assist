"""Few-shot example library for the disambiguation prompt.

Each example has:
  input       -- the clinical term in context plus a JSON list of candidate concepts
  output      -- expected JSON: {"conceptId": "...", "confidence": ..., "reason": "..."}
  category    -- linguistic / semantic pattern demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy (extends extraction_examples.py):
  disambiguation:exact-match     -- candidate FSN directly matches the term
  disambiguation:abbreviation    -- GP abbreviation matched to expanded SNOMED concept
  disambiguation:specificity     -- most specific concept selected from broad candidates
  disambiguation:no-match        -- no candidate is clinically correct; return NONE
  disambiguation:context-driven  -- surface form is ambiguous; context text resolves it
  disambiguation:negated         -- negated term; best concept still selected
"""

from __future__ import annotations

DISAMBIGUATION_EXAMPLES: list[dict] = [
    # ── Exact match ───────────────────────────────────────────────────────────
    {
        "category": "disambiguation:exact-match",
        "model_scope": "any",
        "description": "FSN matches term exactly - high confidence",
        "input": (
            'Term: "type 2 diabetes mellitus"\n'
            'Context: "Known T2DM, HbA1c 58 mmol/mol."\n'
            'Candidates: [{"conceptId": "44054006", "name": "Diabetes mellitus type 2"}, '
            '{"conceptId": "73211009", "name": "Diabetes mellitus"}]'
        ),
        "output": '{"conceptId": "44054006", "confidence": 0.98, "reason": "Diabetes mellitus type 2 directly corresponds to type 2 diabetes mellitus."}',
    },
    {
        "category": "disambiguation:exact-match",
        "model_scope": "any",
        "description": "Hypertension - unambiguous match",
        "input": (
            'Term: "hypertension"\n'
            'Context: "Longstanding hypertension, on ramipril."\n'
            'Candidates: [{"conceptId": "38341003", "name": "Hypertension"}, '
            '{"conceptId": "59621000", "name": "Essential hypertension"}]'
        ),
        "output": '{"conceptId": "38341003", "confidence": 0.95, "reason": "Hypertension is the preferred top-level SNOMED concept matching the extracted term."}',
    },

    # ── Abbreviation expansion ────────────────────────────────────────────────
    {
        "category": "disambiguation:abbreviation",
        "model_scope": "any",
        "description": "GP abbreviation AF matched to atrial fibrillation",
        "input": (
            'Term: "atrial fibrillation"\n'
            'Context: "AF on anticoagulation."\n'
            'Candidates: [{"conceptId": "49436004", "name": "Atrial fibrillation"}, '
            '{"conceptId": "195080001", "name": "Atrial flutter"}]'
        ),
        "output": '{"conceptId": "49436004", "confidence": 0.97, "reason": "Atrial fibrillation is the exact expanded form of the abbreviation AF."}',
    },

    # ── Specificity selection ─────────────────────────────────────────────────
    {
        "category": "disambiguation:specificity",
        "model_scope": "any",
        "description": "Choose most specific - community-acquired pneumonia over generic",
        "input": (
            'Term: "community-acquired pneumonia"\n'
            'Context: "Chest X-ray confirms community-acquired pneumonia."\n'
            'Candidates: [{"conceptId": "385093006", "name": "Community acquired pneumonia"}, '
            '{"conceptId": "233604007", "name": "Pneumonia"}]'
        ),
        "output": '{"conceptId": "385093006", "confidence": 0.97, "reason": "Community acquired pneumonia is the precise concept; the generic pneumonia concept is too broad."}',
    },
    {
        "category": "disambiguation:specificity",
        "model_scope": "any",
        "description": "CKD stage specified in context - select stage-specific concept",
        "input": (
            'Term: "chronic kidney disease"\n'
            'Context: "CKD stage 3b, eGFR 43."\n'
            'Candidates: [{"conceptId": "709044004", "name": "Chronic kidney disease stage 3b"}, '
            '{"conceptId": "709044004", "name": "Chronic kidney disease"}, '
            '{"conceptId": "46177005", "name": "Renal insufficiency"}]'
        ),
        "output": '{"conceptId": "709044004", "confidence": 0.96, "reason": "Context explicitly states stage 3b; the stage-specific concept is the most precise match."}',
    },

    # ── Context-driven disambiguation ─────────────────────────────────────────
    {
        "category": "disambiguation:context-driven",
        "model_scope": "any",
        "description": "Mass - prostate context resolves ambiguity",
        "input": (
            'Term: "mass"\n'
            'Context: "DRE: hard irregular prostate mass. PSA 18.4. 2WW referral to urology."\n'
            'Candidates: [{"conceptId": "300848003", "name": "Mass of body region"}, '
            '{"conceptId": "190432002", "name": "Prostate mass"}]'
        ),
        "output": '{"conceptId": "190432002", "confidence": 0.88, "reason": "Context confirms the mass is prostatic; prostate mass is the more precise concept."}',
    },
    {
        "category": "disambiguation:context-driven",
        "model_scope": "any",
        "description": "Discharge - gynaecological context resolves to vaginal discharge",
        "input": (
            'Term: "discharge"\n'
            'Context: "Patient presenting with vaginal discharge and pelvic pain."\n'
            'Candidates: [{"conceptId": "267132006", "name": "Vaginal discharge"}, '
            '{"conceptId": "300843003", "name": "Ear discharge"}]'
        ),
        "output": '{"conceptId": "267132006", "confidence": 0.96, "reason": "Context specifies vaginal discharge in a gynaecological presentation."}',
    },

    # ── No suitable match ─────────────────────────────────────────────────────
    {
        "category": "disambiguation:no-match",
        "model_scope": "any",
        "description": "No candidate matches - return NONE",
        "input": (
            'Term: "nephrostomy irrigation"\n'
            'Context: "Nephrostomy flush performed by district nurse."\n'
            'Candidates: [{"conceptId": "60051002", "name": "Nephrectomy"}, '
            '{"conceptId": "16545000", "name": "Nephrolithotomy"}]'
        ),
        "output": '{"conceptId": "NONE", "confidence": 0.0, "reason": "Neither candidate matches nephrostomy irrigation; nephrectomy and nephrolithotomy are unrelated procedures."}',
    },
    {
        "category": "disambiguation:no-match",
        "model_scope": "any",
        "description": "Candidate list contains only unrelated concepts",
        "input": (
            'Term: "allergy to penicillin"\n'
            'Context: "NKDA except penicillin allergy documented."\n'
            'Candidates: [{"conceptId": "57386000", "name": "Allergy to peanuts"}, '
            '{"conceptId": "372687004", "name": "Amoxicillin"}]'
        ),
        "output": '{"conceptId": "NONE", "confidence": 0.0, "reason": "Neither candidate represents allergy to penicillin; peanut allergy and amoxicillin are not equivalent concepts."}',
    },

    # ── Negated term - concept still selected ────────────────────────────────
    {
        "category": "disambiguation:negated",
        "model_scope": "any",
        "description": "Negated term - select best concept regardless (assertion handled upstream)",
        "input": (
            'Term: "jaundice"\n'
            'Context: "No jaundice noted on examination."\n'
            'Candidates: [{"conceptId": "18165001", "name": "Jaundice"}, '
            '{"conceptId": "37151006", "name": "Icterus"}]'
        ),
        "output": '{"conceptId": "18165001", "confidence": 0.97, "reason": "Jaundice directly matches the extracted term; negation is handled by the assertion field upstream."}',
    },

    # ── Drug / substance ─────────────────────────────────────────────────────
    {
        "category": "disambiguation:exact-match",
        "model_scope": "any",
        "description": "Generic drug name - select substance concept",
        "input": (
            'Term: "metformin"\n'
            'Context: "Metformin 500mg twice daily for T2DM."\n'
            'Candidates: [{"conceptId": "372664007", "name": "Metformin"}, '
            '{"conceptId": "109081006", "name": "Metformin hydrochloride"}]'
        ),
        "output": '{"conceptId": "372664007", "confidence": 0.96, "reason": "Metformin is the standard SNOMED substance concept matching the generic drug name."}',
    },

    # ── Observable entity ─────────────────────────────────────────────────────
    {
        "category": "disambiguation:exact-match",
        "model_scope": "any",
        "description": "Lab parameter - estimated glomerular filtration rate",
        "input": (
            'Term: "estimated glomerular filtration rate"\n'
            'Context: "eGFR 43 mL/min (CKD-EPI)."\n'
            'Candidates: [{"conceptId": "1011481000000105", "name": "Estimated glomerular filtration rate"}, '
            '{"conceptId": "80274001", "name": "Glomerular filtration rate"}]'
        ),
        "output": '{"conceptId": "1011481000000105", "confidence": 0.95, "reason": "Estimated glomerular filtration rate matches the lookup term for eGFR exactly."}',
    },
]
