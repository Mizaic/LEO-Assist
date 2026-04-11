"""Few-shot example library for the encounter_classify prompt.

Each example has:
  input       -- raw encounter text (de-identified)
  output      -- expected JSON classification
  category    -- pattern demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy:
  classify:admin_only         -- administrative entry with no clinical content
  classify:document_transfer  -- document filed without GP annotation
  classify:clinical-acute     -- clinical encounter with active / urgent findings
  classify:clinical-chronic   -- routine chronic disease monitoring or medication review
  classify:clinical-oncology  -- cancer pathway encounter
  classify:clinical-multi     -- multiple domains in one encounter
"""

from __future__ import annotations

ENCOUNTER_CLASSIFY_EXAMPLES: list[dict] = [
    # ── Admin only ────────────────────────────────────────────────────────────
    {
        "category": "classify:admin_only",
        "model_scope": "any",
        "description": "SMS appointment reminder - no clinical content",
        "input": "SMS sent: Reminder for appointment on 14/03/2023 at 09:30 with Dr Smith.",
        "output": '{"content_type": "admin_only", "domains": [], "encounter_purpose": ["admin"], "key_clinical_signals": [], "expected_semantic_tags": [], "clinical_significance": "low"}',
    },
    {
        "category": "classify:admin_only",
        "model_scope": "any",
        "description": "SCR data sharing consent entry",
        "input": "Implied consent for Summary Care Record. Patient agreed to share record with other NHS organisations.",
        "output": '{"content_type": "admin_only", "domains": [], "encounter_purpose": ["admin"], "key_clinical_signals": [], "expected_semantic_tags": [], "clinical_significance": "low"}',
    },
    {
        "category": "classify:admin_only",
        "model_scope": "any",
        "description": "Record visibility note",
        "input": "Event has been made private by another organisation.",
        "output": '{"content_type": "admin_only", "domains": [], "encounter_purpose": ["admin"], "key_clinical_signals": [], "expected_semantic_tags": [], "clinical_significance": "low"}',
    },
    # ── Document transfer ─────────────────────────────────────────────────────
    {
        "category": "classify:document_transfer",
        "model_scope": "any",
        "description": "Hospital discharge letter filed without GP annotation",
        "input": "Discharge summary received from City Hospital, dated 12/02/2023. Filed.",
        "output": '{"content_type": "document_transfer", "domains": [], "encounter_purpose": ["discharge_summary"], "key_clinical_signals": [], "expected_semantic_tags": [], "clinical_significance": "low"}',
    },
    {
        "category": "classify:document_transfer",
        "model_scope": "any",
        "description": "Outpatient clinic letter received from oncology",
        "input": "Outpatient letter received from oncology department. Filed to record.",
        "output": '{"content_type": "document_transfer", "domains": ["oncology"], "encounter_purpose": ["clinic_letter"], "key_clinical_signals": [], "expected_semantic_tags": [], "clinical_significance": "low"}',
    },
    # ── Clinical: acute ───────────────────────────────────────────────────────
    {
        "category": "classify:clinical-acute",
        "model_scope": "any",
        "description": "Acute chest pain with ECG and urgent referral",
        "input": (
            "60M presents with central chest pain radiating to left arm, onset 2 hours ago. "
            "BP 155/95 mmHg. ECG: ST elevation in leads II, III, aVF. "
            "999 called — urgent transfer to cardiac centre."
        ),
        "output": '{"content_type": "clinical", "domains": ["cardiovascular"], "encounter_purpose": ["consultation", "referral"], "key_clinical_signals": ["chest pain", "ST elevation", "urgent transfer to cardiac centre"], "expected_semantic_tags": ["finding", "observable entity", "procedure"], "clinical_significance": "high"}',
    },
    {
        "category": "classify:clinical-acute",
        "model_scope": "any",
        "description": "2WW referral for suspected colorectal cancer",
        "input": (
            "72F. 8-week history of change in bowel habit and PR bleeding. "
            "Weight loss 4 kg. FIT positive 180 mcg/g. "
            "2WW referral to lower GI surgery for suspected colorectal cancer."
        ),
        "output": '{"content_type": "clinical", "domains": ["oncology", "gastroenterology"], "encounter_purpose": ["consultation", "referral"], "key_clinical_signals": ["change in bowel habit", "rectal bleeding", "weight loss", "positive FIT", "2WW referral"], "expected_semantic_tags": ["finding", "observable entity", "situation"], "clinical_significance": "high"}',
    },
    # ── Clinical: chronic disease monitoring ──────────────────────────────────
    {
        "category": "classify:clinical-chronic",
        "model_scope": "any",
        "description": "Routine diabetes review with HbA1c result",
        "input": (
            "Annual diabetes review. T2DM stable. HbA1c 58 mmol/mol — up from 52. "
            "Weight 96 kg, BMI 32.1. Continue metformin 1g BD. Discussed diet. "
            "Refer to dietitian. Review in 6 months."
        ),
        "output": '{"content_type": "clinical", "domains": ["metabolic"], "encounter_purpose": ["follow_up", "medication_review"], "key_clinical_signals": ["HbA1c 58 mmol/mol", "T2DM stable", "BMI 32.1"], "expected_semantic_tags": ["disorder", "observable entity", "substance", "procedure"], "clinical_significance": "medium"}',
    },
    {
        "category": "classify:clinical-chronic",
        "model_scope": "any",
        "description": "Hypertension and CKD medication review - telephone",
        "input": (
            "Tel consultation. Hypertension and CKD stage 3b. BP diary reviewed — average 138/82. "
            "eGFR stable at 43. Ramipril 5mg OD continued. No new symptoms. Review bloods in 3 months."
        ),
        "output": '{"content_type": "clinical", "domains": ["cardiovascular", "renal"], "encounter_purpose": ["telephone", "medication_review", "follow_up"], "key_clinical_signals": ["hypertension", "CKD stage 3b", "eGFR 43", "BP 138/82"], "expected_semantic_tags": ["disorder", "observable entity", "substance"], "clinical_significance": "medium"}',
    },
    # ── Clinical: oncology ────────────────────────────────────────────────────
    {
        "category": "classify:clinical-oncology",
        "model_scope": "any",
        "description": "Cancer treatment follow-up - letrozole and bone density",
        "input": (
            "Post-op follow-up. Breast cancer - T2N1M0. On letrozole 2.5mg OD. "
            "DEXA scan: osteopenia. Starting alendronic acid. Next oncology appointment booked."
        ),
        "output": '{"content_type": "clinical", "domains": ["oncology"], "encounter_purpose": ["follow_up", "medication_review"], "key_clinical_signals": ["breast cancer T2N1M0", "letrozole", "osteopenia", "DEXA scan"], "expected_semantic_tags": ["disorder", "staging scale", "substance", "observable entity", "finding"], "clinical_significance": "high"}',
    },
    # ── Clinical: multi-domain ────────────────────────────────────────────────
    {
        "category": "classify:clinical-multi",
        "model_scope": "any",
        "description": "Annual review covering multiple chronic conditions",
        "input": (
            "Annual review. PMH: COPD, T2DM, HTN, AF. "
            "Spirometry FEV1/FVC 0.62. Salbutamol PRN. "
            "HbA1c 66 mmol/mol — increased metformin dose. "
            "BP 148/88 — add amlodipine. INR 2.3, on warfarin. Flu jab given."
        ),
        "output": '{"content_type": "clinical", "domains": ["respiratory", "metabolic", "cardiovascular", "haematology"], "encounter_purpose": ["follow_up", "medication_review", "immunisation"], "key_clinical_signals": ["COPD", "T2DM", "hypertension", "atrial fibrillation", "HbA1c 66 mmol/mol", "BP 148/88", "INR 2.3"], "expected_semantic_tags": ["disorder", "observable entity", "substance", "procedure"], "clinical_significance": "high"}',
    },
    # ── Clinical: investigation result ────────────────────────────────────────
    {
        "category": "classify:clinical-chronic",
        "model_scope": "any",
        "description": "Blood test results reviewed - no action needed",
        "input": (
            "Blood results reviewed. Renal profile: Na 139, K 4.1, Cr 88, eGFR 76. "
            "LFTs normal. HbA1c 49 mmol/mol. All satisfactory. No action required."
        ),
        "output": '{"content_type": "clinical", "domains": ["renal", "metabolic"], "encounter_purpose": ["investigation_result"], "key_clinical_signals": ["eGFR 76", "HbA1c 49 mmol/mol", "renal profile normal"], "expected_semantic_tags": ["observable entity", "finding"], "clinical_significance": "medium"}',
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
    ENCOUNTER_CLASSIFY_EXAMPLES,
    {
        "classify:admin_only",
        "classify:document_transfer",
        "classify:clinical-acute",
        "classify:clinical-chronic",
        "classify:clinical-oncology",
        "classify:clinical-multi",
    },
)
