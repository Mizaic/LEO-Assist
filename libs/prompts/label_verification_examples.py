"""Few-shot example library for the label_verification prompt (v2).

Each example has:
  input       -- encounter snippet + JSON entity list to classify
  output      -- expected JSON {"entities": [...]}
  category    -- label type / boundary rule demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy (extends extraction_examples.py):
  label-verify:finding            -- symptom / sign / clinical observation
  label-verify:disorder           -- confirmed diagnosis or condition
  label-verify:observable         -- structured test name (value/unit split off)
  label-verify:qualifier          -- value/unit, result descriptor, severity, staging value
  label-verify:procedure          -- clinical action performed
  label-verify:substance          -- bare drug ingredient
  label-verify:situation          -- risk/pending/pathway status
  label-verify:regime-therapy     -- treatment regimen shorthand
  label-verify:record-artifact    -- document heading or administrative artifact
  label-verify:x-dosage           -- medication dose token (NOT lab values)
  label-verify:x-temporal         -- temporal expression
  label-verify:boundary:find-dis  -- finding vs disorder boundary
  label-verify:boundary:obs-qual  -- observable_entity vs qualifier_value boundary
  label-verify:boundary:sub-proc  -- substance vs procedure boundary
  label-verify:boundary:multi-label -- preserve intentional dual-labelled spans
  label-verify:negation           -- negated concept keeps its base type
  label-verify:new-span           -- missing span suggested as a new entity
"""

from __future__ import annotations

LABEL_VERIFICATION_EXAMPLES: list[dict] = [
    # ── Finding ───────────────────────────────────────────────────────────────
    {
        "category": "label-verify:finding",
        "model_scope": "any",
        "description": "Rectal bleeding - symptom is finding",
        "input": (
            'Encounter: "Patient presents with 6-week history of rectal bleeding and change in bowel habit."\n'
            'Entities: [{"entity_index": 0, "text": "rectal bleeding", "current_label": "disorder"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "finding", "confidence": 0.95, "rule_triggered": "symptom_observation", "rationale": "Rectal bleeding is a symptom/sign not yet a formal diagnosis; finding is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:finding",
        "model_scope": "any",
        "description": "Narrative observation - finding NOT observable_entity",
        "input": (
            'Encounter: "Drop in eGFR from 24 to 19 - rpt for monitoring."\n'
            'Entities: [{"entity_index": 0, "text": "drop in egfr from 24 to 19", "current_label": "observable_entity"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "finding", "confidence": 0.91, "rule_triggered": "narrative_observation", "rationale": "Narrative description of trend is a clinical observation (finding); observable_entity requires a structured test-name + value.", "is_new": false, "new_text": ""}]}',
    },
    # ── Disorder ──────────────────────────────────────────────────────────────
    {
        "category": "label-verify:disorder",
        "model_scope": "any",
        "description": "Adenocarcinoma confirmed on histology - disorder",
        "input": (
            'Encounter: "Histology: moderately differentiated adenocarcinoma of sigmoid colon."\n'
            'Entities: [{"entity_index": 0, "text": "adenocarcinoma of sigmoid colon", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "disorder", "confidence": 0.97, "rule_triggered": "confirmed_diagnosis", "rationale": "Histology confirms a specific cancer diagnosis; disorder is the correct label.", "is_new": false, "new_text": ""}]}',
    },
    # ── Observable entity vs qualifier value ──────────────────────────────────
    {
        "category": "label-verify:observable",
        "model_scope": "any",
        "description": "PSA - test name only is observable_entity",
        "input": (
            'Encounter: "Fast track referral to urology for raised PSA. PSA 12.4 ng/mL."\n'
            'Entities: [{"entity_index": 0, "text": "PSA", "current_label": "finding"}, {"entity_index": 1, "text": "12.4 ng/mL", "current_label": "X_DOSAGE"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "observable_entity", "confidence": 0.96, "rule_triggered": "lab_result_test_name", "rationale": "PSA is a measurable clinical parameter name; test name alone is observable_entity.", "is_new": false, "new_text": ""}, {"entity_index": 1, "suggested_label": "qualifier_value", "confidence": 0.97, "rule_triggered": "lab_result_value", "rationale": "12.4 ng/mL is a lab result value, not a medication dose; qualifier_value is correct, never X_DOSAGE.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:boundary:obs-qual",
        "model_scope": "any",
        "description": "Serum sodium - span boundary: test name vs value",
        "input": (
            'Encounter: "Serum sodium level (XE2q0) 142 mmol/L [135-145]"\n'
            'Entities: [{"entity_index": 0, "text": "Serum sodium level", "current_label": "observable_entity"}, {"entity_index": 1, "text": "142 mmol/L", "current_label": "X_DOSAGE"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "observable_entity", "confidence": 0.97, "rule_triggered": "lab_test_name_span", "rationale": "Serum sodium level is the test name; Read code (XE2q0) and value/range excluded from span.", "is_new": false, "new_text": ""}, {"entity_index": 1, "suggested_label": "qualifier_value", "confidence": 0.98, "rule_triggered": "lab_result_value", "rationale": "142 mmol/L is a lab measurement value, not a medication dose; qualifier_value is correct.", "is_new": false, "new_text": ""}]}',
    },
    # ── Qualifier value variants ──────────────────────────────────────────────
    {
        "category": "label-verify:qualifier",
        "model_scope": "any",
        "description": "Outside reference range - result descriptor is qualifier_value",
        "input": (
            'Encounter: "Haemoglobin concentration 112 g/L [115-165] - Outside reference range"\n'
            'Entities: [{"entity_index": 0, "text": "Outside reference range", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "qualifier_value", "confidence": 0.95, "rule_triggered": "result_descriptor", "rationale": "Result status descriptors (Outside reference range, Abnormal, NAD) are qualifier_value, not clinical findings.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:qualifier",
        "model_scope": "any",
        "description": "Abnormal flag on HbA1c - qualifier_value",
        "input": (
            'Encounter: "Haemoglobin A1c level Report, Abnormal, Make an appointment to see nurse."\n'
            'Entities: [{"entity_index": 0, "text": "Abnormal", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "qualifier_value", "confidence": 0.94, "rule_triggered": "result_descriptor", "rationale": "Abnormal describes measurement status, not a clinical symptom; qualifier_value is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:qualifier",
        "model_scope": "any",
        "description": "New Episode marker - qualifier_value not X_TEMPORAL",
        "input": (
            'Encounter: "Minor: Constipation (XE0rD) (New Episode)"\n'
            'Entities: [{"entity_index": 0, "text": "New Episode", "current_label": "X_TEMPORAL"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "qualifier_value", "confidence": 0.93, "rule_triggered": "episode_context_marker", "rationale": "New Episode is an episode context marker, not a temporal expression; qualifier_value is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:qualifier",
        "model_scope": "any",
        "description": "Severity modifier - qualifier_value",
        "input": (
            'Encounter: "Severe cough - more than 25 days."\n'
            'Entities: [{"entity_index": 0, "text": "Severe", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "qualifier_value", "confidence": 0.91, "rule_triggered": "severity_modifier", "rationale": "Severe qualifies the cough (finding); severity descriptors are qualifier_value, not standalone findings.", "is_new": false, "new_text": ""}]}',
    },
    # ── Procedure ─────────────────────────────────────────────────────────────
    {
        "category": "label-verify:procedure",
        "model_scope": "any",
        "description": "Colonoscopy performed - procedure",
        "input": (
            'Encounter: "Colonoscopy performed today under sedation. Multiple biopsies taken."\n'
            'Entities: [{"entity_index": 0, "text": "Colonoscopy", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "procedure", "confidence": 0.97, "rule_triggered": "clinical_action_performed", "rationale": "Colonoscopy is a clinical action performed on the patient; procedure is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:procedure",
        "model_scope": "any",
        "description": "MDT - clinical governance procedure",
        "input": (
            'Encounter: "Discussed in MDT by Rachel."\n'
            'Entities: [{"entity_index": 0, "text": "MDT", "current_label": "record_artifact"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "procedure", "confidence": 0.92, "rule_triggered": "clinical_governance_activity", "rationale": "MDT (multidisciplinary team meeting) is a clinical governance procedure; record_artifact would apply to an MDT outcome heading.", "is_new": false, "new_text": ""}]}',
    },
    # ── Substance vs procedure boundary ──────────────────────────────────────
    {
        "category": "label-verify:boundary:sub-proc",
        "model_scope": "any",
        "description": "Drug name alone - substance; full administration phrase - procedure",
        "input": (
            'Encounter: "Degarelix 240 mg SC injection administered today."\n'
            'Entities: [{"entity_index": 0, "text": "Degarelix", "current_label": "procedure"}, {"entity_index": 1, "text": "Degarelix 240 mg SC injection administered today", "current_label": "substance"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "substance", "confidence": 0.96, "rule_triggered": "bare_drug_ingredient", "rationale": "Degarelix alone is a drug name (substance); the full administration phrase including administered is the procedure.", "is_new": false, "new_text": ""}, {"entity_index": 1, "suggested_label": "procedure", "confidence": 0.95, "rule_triggered": "drug_administration_phrase", "rationale": "The full span including administered today describes a treatment action performed (procedure).", "is_new": false, "new_text": ""}]}',
    },
    # ── X_DOSAGE — medication dose only ──────────────────────────────────────
    {
        "category": "label-verify:x-dosage",
        "model_scope": "any",
        "description": "240 mg next to drug name - X_DOSAGE; lab value - qualifier_value",
        "input": (
            'Encounter: "Degarelix 240 mg SC injection administered today."\n'
            'Entities: [{"entity_index": 0, "text": "240 mg", "current_label": "qualifier_value"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "X_DOSAGE", "confidence": 0.95, "rule_triggered": "medication_dose", "rationale": "240 mg appears next to a drug name (Degarelix) — this is a medication dose, so X_DOSAGE is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:x-dosage",
        "model_scope": "any",
        "description": "eGFR value - qualifier_value NOT X_DOSAGE",
        "input": (
            'Encounter: "eGFR using creatinine (CKD-EPI) per 1.73 square metres 43 mL/min"\n'
            'Entities: [{"entity_index": 0, "text": "43 mL/min", "current_label": "X_DOSAGE"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "qualifier_value", "confidence": 0.97, "rule_triggered": "lab_result_value", "rationale": "43 mL/min is a lab measurement result (eGFR), not a medication dose; qualifier_value is correct, never X_DOSAGE.", "is_new": false, "new_text": ""}]}',
    },
    # ── Regime therapy ────────────────────────────────────────────────────────
    {
        "category": "label-verify:regime-therapy",
        "model_scope": "any",
        "description": "Named regimen stays regime_therapy",
        "input": (
            'Encounter: "Discussed CHOP regimen with oncology team."\n'
            'Entities: [{"entity_index": 0, "text": "CHOP regimen", "current_label": "procedure"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "regime_therapy", "confidence": 0.92, "rule_triggered": "named_regimen", "rationale": "CHOP regimen names a treatment regimen/course rather than the act of treatment, so regime_therapy is correct.", "is_new": false, "new_text": ""}]}',
    },
    # ── Situation / procedure status boundary ────────────────────────────────
    {
        "category": "label-verify:situation",
        "model_scope": "any",
        "description": "Cancer ruled out - situation",
        "input": (
            'Encounter: "Seen post-referral. Discharged from 2WW pathway. Cancer ruled out."\n'
            'Entities: [{"entity_index": 0, "text": "Cancer ruled out", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "situation", "confidence": 0.93, "rule_triggered": "diagnostic_conclusion_status", "rationale": "Cancer ruled out is a clinical status statement (diagnostic conclusion); situation is correct.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:procedure",
        "model_scope": "any",
        "description": "Planned colonoscopy keeps procedure label",
        "input": (
            'Encounter: "Plan: colonoscopy planned next week."\n'
            'Entities: [{"entity_index": 0, "text": "colonoscopy", "current_label": "situation"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "procedure", "confidence": 0.94, "rule_triggered": "procedure_status_preserved", "rationale": "Colonoscopy is the clinical action itself; planned timing should not change the semantic type from procedure.", "is_new": false, "new_text": ""}]}',
    },
    {
        "category": "label-verify:boundary:multi-label",
        "model_scope": "any",
        "description": "2WW referral preserves intentional dual labels",
        "input": (
            'Encounter: "Happy to continue with 2WW referral under NHS."\n'
            'Entities: [{"entity_index": 0, "text": "2WW referral", "current_label": "procedure"}, {"entity_index": 1, "text": "2WW referral", "current_label": "situation"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "procedure", "confidence": 0.95, "rule_triggered": "preserve_existing_multilabel", "rationale": "This gold-annotated referral phrase can legitimately carry a procedure label; keep it rather than collapsing to a single type.", "is_new": false, "new_text": ""}, {"entity_index": 1, "suggested_label": "situation", "confidence": 0.95, "rule_triggered": "preserve_existing_multilabel", "rationale": "This gold-annotated referral phrase can also carry a pathway/status meaning; preserve both labels when the span is intentionally dual-labelled.", "is_new": false, "new_text": ""}]}',
    },
    # ── Negation: base type preserved ─────────────────────────────────────────
    {
        "category": "label-verify:negation",
        "model_scope": "any",
        "description": "Negated finding keeps base type - no jaundice stays finding",
        "input": (
            'Encounter: "No jaundice noted on examination."\n'
            'Entities: [{"entity_index": 0, "text": "jaundice", "current_label": "situation"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "finding", "confidence": 0.95, "rule_triggered": "negated_base_type", "rationale": "Negated concepts keep their base clinical type (finding); negation is stored as assertion=absent by post-processing.", "is_new": false, "new_text": ""}]}',
    },
    # ── Record artifact ───────────────────────────────────────────────────────
    {
        "category": "label-verify:record-artifact",
        "model_scope": "any",
        "description": "MDT outcome document heading - record_artifact",
        "input": (
            'Encounter: "Colorectal Cancer MDT Meet Outcome: proceed with surgery."\n'
            'Entities: [{"entity_index": 0, "text": "Colorectal Cancer MDT Meet Outcome", "current_label": "procedure"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "record_artifact", "confidence": 0.91, "rule_triggered": "document_heading", "rationale": "MDT Meet Outcome is a document heading / correspondence phrase, not a procedure action itself.", "is_new": false, "new_text": ""}]}',
    },
    # ── Temporal expression ───────────────────────────────────────────────────
    {
        "category": "label-verify:x-temporal",
        "model_scope": "any",
        "description": "28 days - temporal expression",
        "input": (
            'Encounter: "Next dose in 28 days."\n'
            'Entities: [{"entity_index": 0, "text": "28 days", "current_label": "qualifier_value"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "X_TEMPORAL", "confidence": 0.93, "rule_triggered": "temporal_expression", "rationale": "28 days is a temporal duration for scheduling, not a measurement qualifier.", "is_new": false, "new_text": ""}]}',
    },
    # ── New span suggested ────────────────────────────────────────────────────
    {
        "category": "label-verify:new-span",
        "model_scope": "any",
        "description": "Missing disorder span - suggest new entity",
        "input": (
            'Encounter: "Started capecitabine for colorectal cancer today."\n'
            'Entities: [{"entity_index": 0, "text": "capecitabine", "current_label": "substance"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "substance", "confidence": 0.97, "rule_triggered": "bare_drug_ingredient", "rationale": "Capecitabine is a drug name in medication context; substance is correct.", "is_new": false, "new_text": ""}, {"entity_index": -1, "suggested_label": "disorder", "confidence": 0.94, "rule_triggered": "confirmed_diagnosis", "rationale": "Colorectal cancer is a confirmed diagnosis present in the text but missing from entity list.", "is_new": true, "new_text": "colorectal cancer"}]}',
    },
    {
        "category": "label-verify:boundary:find-dis",
        "model_scope": "any",
        "description": "Suggestive of melanoma - finding; malignant melanoma - disorder",
        "input": (
            'Encounter: "Lesion suggestive of melanoma. Biopsy confirmed malignant melanoma."\n'
            'Entities: [{"entity_index": 0, "text": "suggestive of melanoma", "current_label": "disorder"}, {"entity_index": 1, "text": "malignant melanoma", "current_label": "finding"}]'
        ),
        "output": '{"entities": [{"entity_index": 0, "suggested_label": "finding", "confidence": 0.95, "rule_triggered": "uncertain_impression", "rationale": "Suggestive of is an uncertain impression, not a confirmed diagnosis; finding is correct.", "is_new": false, "new_text": ""}, {"entity_index": 1, "suggested_label": "disorder", "confidence": 0.97, "rule_triggered": "confirmed_diagnosis", "rationale": "Biopsy confirmed malignant melanoma is a definitive diagnosis; disorder is correct.", "is_new": false, "new_text": ""}]}',
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
    LABEL_VERIFICATION_EXAMPLES,
    {
        "label-verify:finding",
        "label-verify:disorder",
        "label-verify:observable",
        "label-verify:qualifier",
        "label-verify:procedure",
        "label-verify:substance",
        "label-verify:boundary:find-dis",
        "label-verify:boundary:obs-qual",
    },
)
