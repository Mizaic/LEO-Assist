"""Few-shot example library for the exclusion_detect prompt.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Each example has:
  input       -- encounter text (post-referral, de-identified)
  output      -- expected JSON outcome classification
  category    -- outcome type demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy:
  exclusion:cancer-excluded      -- cancer definitively ruled out
  exclusion:cancer-confirmed     -- positive cancer diagnosis made
  exclusion:still-investigating  -- investigations ongoing, no conclusion
  exclusion:pending-letter       -- clinic letter received, content unknown
  exclusion:not-relevant         -- encounter unrelated to cancer referral
  exclusion:conservative         -- borderline cases where still_investigating preferred
"""

from __future__ import annotations

EXCLUSION_DETECT_EXAMPLES: list[dict] = [
    # -- Cancer excluded -------------------------------------------------------
    {
        "category": "exclusion:cancer-excluded",
        "model_scope": "any",
        "description": "Biopsy result benign - cancer excluded",
        "input": (
            "Referral context: fast track referral for suspected skin cancer.\n"
            "Encounter: Biopsy result reviewed. Intradermal naevus -- benign. "
            "No malignancy identified. Patient reassured. Discharged from 2WW pathway."
        ),
        "output": '{"outcome": "cancer_excluded", "confidence": 0.97, "evidence_text": "Intradermal naevus - benign. No malignancy identified. Discharged from 2WW pathway.", "reasoning": "Biopsy confirms benign intradermal naevus with explicit no malignancy; patient discharged from 2WW pathway."}',
    },
    {
        "category": "exclusion:cancer-excluded",
        "model_scope": "any",
        "description": "Colonoscopy NAD after positive FIT",
        "input": (
            "Referral context: 2WW referral lower GI for positive FIT.\n"
            "Encounter: Colonoscopy result: no polyps detected, no cancer, NAD. "
            "No evidence of colorectal cancer. Patient discharged from surveillance."
        ),
        "output": '{"outcome": "cancer_excluded", "confidence": 0.95, "evidence_text": "No polyps detected, no cancer, NAD. No evidence of colorectal cancer.", "reasoning": "Colonoscopy found no pathology; explicit no evidence of colorectal cancer statement confirms exclusion."}',
    },
    {
        "category": "exclusion:cancer-excluded",
        "model_scope": "any",
        "description": "PSA result normalised - prostate cancer excluded",
        "input": (
            "Referral context: 2WW referral urology for raised PSA 18.4.\n"
            "Encounter: Repeat PSA 2.1. TRUS biopsy: all cores benign. "
            "No malignancy. Reassured - no further investigation needed."
        ),
        "output": '{"outcome": "cancer_excluded", "confidence": 0.96, "evidence_text": "TRUS biopsy: all cores benign. No malignancy.", "reasoning": "TRUS biopsy confirmed all cores benign with explicit no malignancy; prostate cancer excluded."}',
    },
    # -- Cancer confirmed ------------------------------------------------------
    {
        "category": "exclusion:cancer-confirmed",
        "model_scope": "any",
        "description": "Histology confirms breast cancer",
        "input": (
            "Referral context: fast track referral for breast lump.\n"
            "Encounter: Letter from breast unit. Histology result: invasive ductal carcinoma, ER+. "
            "Diagnosis confirmed. Discussed with patient. Referred to oncology."
        ),
        "output": '{"outcome": "cancer_confirmed", "confidence": 0.98, "evidence_text": "Histology result: invasive ductal carcinoma, ER+. Diagnosis confirmed.", "reasoning": "Histology confirms invasive ductal carcinoma; positive cancer diagnosis made with referral to oncology."}',
    },
    {
        "category": "exclusion:cancer-confirmed",
        "model_scope": "any",
        "description": "MDT outcome confirms lung cancer with staging",
        "input": (
            "Referral context: 2WW referral chest for haemoptysis and right upper lobe mass.\n"
            "Encounter: MDT outcome letter received and filed. NSCLC right upper lobe, T3 N2 M0. "
            "Referred for radical radiotherapy. "
        ),
        "output": '{"outcome": "cancer_confirmed", "confidence": 0.97, "evidence_text": "NSCLC right upper lobe, T3 N2 M0. Referred for radical radiotherapy.", "reasoning": "MDT confirms non-small cell lung cancer with staging; referral for radical radiotherapy confirms active cancer management."}',
    },
    # -- Still investigating ---------------------------------------------------
    {
        "category": "exclusion:still-investigating",
        "model_scope": "any",
        "description": "Awaiting biopsy results after MRI",
        "input": (
            "Referral context: 2WW referral urology for raised PSA 18.4.\n"
            "Encounter: Seen in prostate cancer clinic. MRI prostate: suspicious lesion PI-RADS 4. "
            "TRUS biopsy booked. Awaiting histology results."
        ),
        "output": '{"outcome": "still_investigating", "confidence": 0.88, "evidence_text": "MRI prostate: suspicious lesion PI-RADS 4. TRUS biopsy booked. Awaiting histology results.", "reasoning": "Suspicious MRI finding with biopsy planned but results not yet available; investigations ongoing."}',
    },
    {
        "category": "exclusion:still-investigating",
        "model_scope": "any",
        "description": "Clinic visit recorded with no outcome documented",
        "input": (
            "Referral context: fast track referral for suspected colorectal cancer.\n"
            "Encounter: Seen in fast track suspected colorectal cancer clinic. "
            "CT colonoscopy performed today. Results to follow."
        ),
        "output": '{"outcome": "still_investigating", "confidence": 0.82, "evidence_text": "Seen in fast track clinic. CT colonoscopy performed today. Results to follow.", "reasoning": "Clinic attendance documented and investigation performed but no result yet; still awaiting outcome."}',
    },
    # -- Pending letter --------------------------------------------------------
    {
        "category": "exclusion:pending-letter",
        "model_scope": "any",
        "description": "Clinic letter received but content not quoted",
        "input": (
            "Referral context: 2WW referral dermatology for suspicious pigmented lesion.\n"
            "Encounter: Outpatient letter from dermatology received and filed."
        ),
        "output": '{"outcome": "pending_letter", "confidence": 0.85, "evidence_text": "Outpatient letter from dermatology received and filed.", "reasoning": "A dermatology letter was received but no clinical content is quoted; outcome cannot be determined without reading the letter."}',
    },
    {
        "category": "exclusion:pending-letter",
        "model_scope": "any",
        "description": "Hospital discharge letter filed without clinical annotation",
        "input": (
            "Referral context: 2WW referral haematology for lymphadenopathy.\n"
            "Encounter: Discharge summary received from City Hospital haematology. Filed to record."
        ),
        "output": '{"outcome": "pending_letter", "confidence": 0.80, "evidence_text": "Discharge summary received from City Hospital haematology. Filed to record.", "reasoning": "Haematology discharge summary filed without quoted content; outcome determination requires reading the document."}',
    },
    # -- Not relevant ----------------------------------------------------------
    {
        "category": "exclusion:not-relevant",
        "model_scope": "any",
        "description": "Flu vaccination - no cancer pathway relevance",
        "input": (
            "Referral context: 2WW referral urology for haematuria.\n"
            "Encounter: Annual flu vaccination given. Patient otherwise well."
        ),
        "output": '{"outcome": "not_relevant", "confidence": 0.95, "evidence_text": "Annual flu vaccination given.", "reasoning": "Flu vaccination has no bearing on the urology 2WW pathway; unrelated clinical encounter."}',
    },
    {
        "category": "exclusion:not-relevant",
        "model_scope": "any",
        "description": "Diabetes review - unrelated to cancer referral",
        "input": (
            "Referral context: fast track referral for suspected breast cancer.\n"
            "Encounter: Routine diabetes review. HbA1c 58 mmol/mol. Metformin continued. No breast symptoms discussed."
        ),
        "output": '{"outcome": "not_relevant", "confidence": 0.93, "evidence_text": "Routine diabetes review. HbA1c 58 mmol/mol.", "reasoning": "Encounter is a routine diabetes review with no mention of breast symptoms or referral outcome."}',
    },
    {
        "category": "exclusion:not-relevant",
        "model_scope": "any",
        "description": "Screening invitation with no result - not_relevant",
        "input": (
            "Referral context: 2WW referral lower GI for positive FIT.\n"
            "Encounter: Bowel cancer screening programme -- invitation sent. No response recorded."
        ),
        "output": '{"outcome": "not_relevant", "confidence": 0.88, "evidence_text": "Bowel cancer screening programme - invitation sent. No response recorded.", "reasoning": "Screening invitation without results does not represent a post-referral pathway outcome."}',
    },
    # -- Conservative: borderline ----------------------------------------------
    {
        "category": "exclusion:conservative",
        "model_scope": "any",
        "description": "Benign finding at unrelated site - not cancer_excluded",
        "input": (
            "Referral context: 2WW referral urology for haematuria.\n"
            "Encounter: Blood results: eGFR 61, MSU clear. INR 2.3 -- within range. "
            "Continue warfarin. Review in 6 weeks."
        ),
        "output": '{"outcome": "still_investigating", "confidence": 0.55, "evidence_text": "MSU clear. eGFR 61.", "reasoning": "MSU clear suggests one negative test but does not confirm exclusion of urological malignancy; insufficient evidence to classify as excluded."}',
    },
]


def _apply_core_by_first_category(
    examples: list[dict], core_categories: set[str]
) -> None:
    seen: set[str] = set()
    for example in examples:
        category = str(example.get("category", ""))
        is_core = category in core_categories and category not in seen
        if is_core:
            seen.add(category)
        example["core"] = is_core


_apply_core_by_first_category(
    EXCLUSION_DETECT_EXAMPLES,
    {
        "exclusion:cancer-excluded",
        "exclusion:cancer-confirmed",
        "exclusion:still-investigating",
        "exclusion:pending-letter",
        "exclusion:not-relevant",
        "exclusion:conservative",
    },
)
