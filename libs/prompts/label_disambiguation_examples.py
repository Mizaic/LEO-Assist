"""Few-shot example library for the label_disambiguation prompt (v1).

Each example has:
  input       -- model A label + rationale, model B label + rationale, entity text, encounter context
  output      -- expected JSON: {"resolved_label": "...", "confidence": ..., "reason": "..."}
  category    -- boundary case demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy (extends label_verification_examples.py):
  label-disambig:find-dis      -- finding vs disorder boundary
  label-disambig:obs-qual      -- observable_entity vs qualifier_value boundary
  label-disambig:sub-proc      -- substance vs procedure boundary
  label-disambig:dosage-qual   -- X_DOSAGE (drug dose) vs qualifier_value (lab value)
  label-disambig:sit-dis       -- situation vs disorder boundary
  label-disambig:regime-sub    -- regime_therapy vs substance boundary
  label-disambig:artifact-proc -- record_artifact vs procedure boundary
  label-disambig:temporal-qual -- X_TEMPORAL vs qualifier_value boundary
  label-disambig:negation      -- negated concept keeps base clinical type
"""

from __future__ import annotations

LABEL_DISAMBIGUATION_EXAMPLES: list[dict] = [
    # ── Finding vs Disorder ────────────────────────────────────────────────────
    {
        "category": "label-disambig:find-dis",
        "model_scope": "any",
        "description": "Suggestive of melanoma - finding not disorder",
        "input": (
            'Model A: "finding" — rationale: "Suggestive of is uncertain, not confirmed."\n'
            'Model B: "disorder" — rationale: "Melanoma is a serious cancer diagnosis."\n'
            'Entity text: "suggestive of melanoma"\n'
            'Encounter context: "Irregular pigmented lesion on back, suggestive of melanoma. Biopsy arranged."'
        ),
        "output": '{"resolved_label": "finding", "confidence": 0.94, "reason": "Suggestive of indicates uncertainty; a diagnosis is not yet confirmed. Finding is correct per the finding-vs-disorder boundary rule."}',
    },
    {
        "category": "label-disambig:find-dis",
        "model_scope": "any",
        "description": "Malignant melanoma confirmed on biopsy - disorder",
        "input": (
            'Model A: "disorder" — rationale: "Biopsy confirmed malignant melanoma is a definitive diagnosis."\n'
            'Model B: "finding" — rationale: "Melanoma is described as a clinical observation."\n'
            'Entity text: "malignant melanoma"\n'
            'Encounter context: "Biopsy confirmed malignant melanoma. Wide local excision planned."'
        ),
        "output": '{"resolved_label": "disorder", "confidence": 0.97, "reason": "Biopsy confirmed malignant melanoma is a definitive diagnosis statement; disorder is correct per the finding-vs-disorder boundary."}',
    },
    # ── Observable entity vs qualifier value ─────────────────────────────────
    {
        "category": "label-disambig:obs-qual",
        "model_scope": "any",
        "description": "PSA - test name is observable_entity",
        "input": (
            'Model A: "observable_entity" — rationale: "PSA is a measurable clinical parameter."\n'
            'Model B: "finding" — rationale: "PSA result was raised, suggesting a clinical finding."\n'
            'Entity text: "PSA"\n'
            'Encounter context: "PSA 12.4 ng/mL. Fast track referral to urology."'
        ),
        "output": '{"resolved_label": "observable_entity", "confidence": 0.96, "reason": "PSA is a structured test name; the test name alone is observable_entity. The numeric value 12.4 ng/mL is a separate qualifier_value."}',
    },
    {
        "category": "label-disambig:obs-qual",
        "model_scope": "any",
        "description": "Lab result value - qualifier_value not observable_entity",
        "input": (
            'Model A: "qualifier_value" — rationale: "142 mmol/L is the measurement result value."\n'
            'Model B: "observable_entity" — rationale: "It describes a lab measurement."\n'
            'Entity text: "142 mmol/L"\n'
            'Encounter context: "Serum sodium level (XE2q0) 142 mmol/L [135-145]"'
        ),
        "output": '{"resolved_label": "qualifier_value", "confidence": 0.97, "reason": "142 mmol/L is the value+unit component of a lab result; the test name Serum sodium level is the observable_entity. qualifier_value is correct."}',
    },
    # ── X_DOSAGE vs qualifier_value ──────────────────────────────────────────
    {
        "category": "label-disambig:dosage-qual",
        "model_scope": "any",
        "description": "240 mg next to drug - X_DOSAGE not qualifier_value",
        "input": (
            'Model A: "X_DOSAGE" — rationale: "240 mg is the dose of Degarelix (a drug)."\n'
            'Model B: "qualifier_value" — rationale: "mg values are generally qualifier_value."\n'
            'Entity text: "240 mg"\n'
            'Encounter context: "Degarelix 240 mg SC injection administered today."'
        ),
        "output": '{"resolved_label": "X_DOSAGE", "confidence": 0.95, "reason": "240 mg immediately follows a drug name (Degarelix) and describes a medication dose; X_DOSAGE is correct. qualifier_value is for lab values."}',
    },
    {
        "category": "label-disambig:dosage-qual",
        "model_scope": "any",
        "description": "eGFR value - qualifier_value never X_DOSAGE",
        "input": (
            'Model A: "qualifier_value" — rationale: "43 mL/min is a lab result value."\n'
            'Model B: "X_DOSAGE" — rationale: "mL/min with a number could be a dosage."\n'
            'Entity text: "43 mL/min"\n'
            'Encounter context: "eGFR using creatinine (CKD-EPI) per 1.73 square metres 43 mL/min"'
        ),
        "output": '{"resolved_label": "qualifier_value", "confidence": 0.98, "reason": "43 mL/min is a lab measurement result (eGFR), not a medication dose. X_DOSAGE is strictly for drug doses; qualifier_value is correct."}',
    },
    {
        "category": "label-disambig:dosage-qual",
        "model_scope": "any",
        "description": "Smoking consumption - qualifier_value not X_DOSAGE",
        "input": (
            'Model A: "qualifier_value" — rationale: "Smoking amount qualifies the smoking status."\n'
            'Model B: "X_DOSAGE" — rationale: "Quantity could be interpreted as a dose."\n'
            'Entity text: "1-9 cigs/day"\n'
            'Encounter context: "Current smoker, 1-9 cigs/day."'
        ),
        "output": '{"resolved_label": "qualifier_value", "confidence": 0.93, "reason": "Smoking consumption is a qualifying amount for a lifestyle factor, not a medication dose; qualifier_value is correct."}',
    },
    # ── Substance vs procedure ────────────────────────────────────────────────
    {
        "category": "label-disambig:sub-proc",
        "model_scope": "any",
        "description": "Drug name alone - substance not procedure",
        "input": (
            'Model A: "substance" — rationale: "Degarelix is a drug name (bare ingredient)."\n'
            'Model B: "procedure" — rationale: "It is part of a treatment action."\n'
            'Entity text: "Degarelix"\n'
            'Encounter context: "Degarelix 240 mg SC injection administered today."'
        ),
        "output": '{"resolved_label": "substance", "confidence": 0.96, "reason": "Degarelix is a bare drug ingredient name; the full administration phrase including administered is the procedure. Drug name alone = substance."}',
    },
    {
        "category": "label-disambig:sub-proc",
        "model_scope": "any",
        "description": "Full drug administration phrase - procedure",
        "input": (
            'Model A: "procedure" — rationale: "Administered today describes a treatment action performed."\n'
            'Model B: "substance" — rationale: "Degarelix is a drug."\n'
            'Entity text: "Degarelix 240 mg SC injection administered today"\n'
            'Encounter context: "Degarelix 240 mg SC injection administered today."'
        ),
        "output": '{"resolved_label": "procedure", "confidence": 0.95, "reason": "The full phrase including administered today is a treatment action performed on the patient; procedure is correct. Drug name alone would be substance."}',
    },
    # ── Situation vs Disorder ─────────────────────────────────────────────────
    {
        "category": "label-disambig:sit-dis",
        "model_scope": "any",
        "description": "DVT risk - situation not disorder",
        "input": (
            'Model A: "situation" — rationale: "DVT risk is a risk/pending status, not a confirmed diagnosis."\n'
            'Model B: "disorder" — rationale: "DVT is a clinical disorder."\n'
            'Entity text: "DVT risk"\n'
            'Encounter context: "High DVT risk - prescribe LMWH prophylaxis."'
        ),
        "output": '{"resolved_label": "situation", "confidence": 0.93, "reason": "DVT risk is a contextualised risk statement, not a confirmed diagnosis. Confirmed DVT would be disorder; DVT risk is situation."}',
    },
    {
        "category": "label-disambig:sit-dis",
        "model_scope": "any",
        "description": "Cancer ruled out - situation",
        "input": (
            'Model A: "situation" — rationale: "Cancer ruled out is a diagnostic conclusion status."\n'
            'Model B: "finding" — rationale: "It describes a clinical outcome finding."\n'
            'Entity text: "Cancer ruled out"\n'
            'Encounter context: "Discharged from 2WW pathway. Cancer ruled out."'
        ),
        "output": '{"resolved_label": "situation", "confidence": 0.94, "reason": "Cancer ruled out is a clinical status statement (diagnostic conclusion); situation is correct per boundary rules."}',
    },
    # ── Regime therapy vs Substance ───────────────────────────────────────────
    {
        "category": "label-disambig:regime-sub",
        "model_scope": "any",
        "description": "Chemo shorthand - regime_therapy not substance",
        "input": (
            'Model A: "regime_therapy" — rationale: "Chemo is shorthand for a treatment regimen."\n'
            'Model B: "substance" — rationale: "Chemo refers to a chemical treatment agent."\n'
            'Entity text: "chemo"\n'
            'Encounter context: "Discussed pros and cons of chemo with oncologist."'
        ),
        "output": '{"resolved_label": "regime_therapy", "confidence": 0.91, "reason": "Chemo is a shorthand for a treatment regimen programme, not a bare substance name; regime_therapy is correct."}',
    },
    {
        "category": "label-disambig:regime-sub",
        "model_scope": "any",
        "description": "HRT as treatment regime shorthand",
        "input": (
            'Model A: "regime_therapy" — rationale: "HRT is a named treatment programme."\n'
            'Model B: "substance" — rationale: "HRT is a hormonal drug."\n'
            'Entity text: "HRT"\n'
            'Encounter context: "Started HRT for menopausal symptoms."'
        ),
        "output": '{"resolved_label": "regime_therapy", "confidence": 0.89, "reason": "HRT in treatment context is a treatment regimen shorthand; regime_therapy is correct per boundary rules."}',
    },
    # ── Record artifact vs Procedure ─────────────────────────────────────────
    {
        "category": "label-disambig:artifact-proc",
        "model_scope": "any",
        "description": "MDT outcome heading - record_artifact not procedure",
        "input": (
            'Model A: "record_artifact" — rationale: "MDT Meet Outcome is a document heading."\n'
            'Model B: "procedure" — rationale: "MDT is a clinical governance activity."\n'
            'Entity text: "Colorectal Cancer MDT Meet Outcome"\n'
            'Encounter context: "Colorectal Cancer MDT Meet Outcome: proceed with sigmoid colectomy."'
        ),
        "output": '{"resolved_label": "record_artifact", "confidence": 0.90, "reason": "MDT Meet Outcome in this form is a document/correspondence heading (record_artifact). MDT as a standalone action is procedure; the outcome heading is record_artifact."}',
    },
    # ── Temporal vs qualifier value ───────────────────────────────────────────
    {
        "category": "label-disambig:temporal-qual",
        "model_scope": "any",
        "description": "New Episode - qualifier_value not X_TEMPORAL",
        "input": (
            'Model A: "qualifier_value" — rationale: "New Episode is an episode context marker."\n'
            'Model B: "X_TEMPORAL" — rationale: "It relates to time/episode tracking."\n'
            'Entity text: "New Episode"\n'
            'Encounter context: "Minor: Constipation (XE0rD) (New Episode)"'
        ),
        "output": '{"resolved_label": "qualifier_value", "confidence": 0.93, "reason": "New Episode is an episode context marker qualifying the clinical entry, not a temporal expression; qualifier_value is correct."}',
    },
    # ── Negation: base type preserved ─────────────────────────────────────────
    {
        "category": "label-disambig:negation",
        "model_scope": "any",
        "description": "Negated finding keeps finding label - no jaundice",
        "input": (
            'Model A: "finding" — rationale: "Jaundice is a symptom/sign; negation handled by post-processing."\n'
            'Model B: "situation" — rationale: "Negated jaundice describes a clinical status."\n'
            'Entity text: "jaundice"\n'
            'Encounter context: "No jaundice noted on examination."'
        ),
        "output": '{"resolved_label": "finding", "confidence": 0.95, "reason": "Negated concepts keep their base clinical type; jaundice is a finding. Negation is stored as assertion=absent by post-processing, not by changing the label."}',
    },
    {
        "category": "label-disambig:negation",
        "model_scope": "any",
        "description": "Negated disorder keeps disorder label",
        "input": (
            'Model A: "disorder" — rationale: "Infection is a disorder; negation is handled separately."\n'
            'Model B: "situation" — rationale: "No evidence of infection is a clinical status."\n'
            'Entity text: "infection"\n'
            'Encounter context: "No evidence of infection identified."'
        ),
        "output": '{"resolved_label": "disorder", "confidence": 0.92, "reason": "Infection as a negated concept retains its base type (disorder); X_NEGATION_CUE is not a valid label. assertion=absent is set by post-processing."}',
    },
    # ── Planned procedure - situation ─────────────────────────────────────────
    {
        "category": "label-disambig:sit-dis",
        "model_scope": "any",
        "description": "Colonoscopy planned - situation not procedure",
        "input": (
            'Model A: "situation" — rationale: "Colonoscopy planned/booked is pending; SNOMED 405613005."\n'
            'Model B: "procedure" — rationale: "Colonoscopy is a clinical procedure."\n'
            'Entity text: "colonoscopy planned"\n'
            'Encounter context: "Colonoscopy planned. Referred to endoscopy unit."'
        ),
        "output": '{"resolved_label": "situation", "confidence": 0.94, "reason": "Planned/booked procedures not yet performed are situation (SNOMED 405613005 Planned procedure); procedure = performed. situation is correct."}',
    },
    # ── Formal staging ────────────────────────────────────────────────────────
    {
        "category": "label-disambig:obs-qual",
        "model_scope": "any",
        "description": "Formal staging FIGO IB1 - tumor_staging not qualifier_value",
        "input": (
            'Model A: "tumor_staging" — rationale: "FIGO IB1 is a formal cancer staging classification."\n'
            'Model B: "qualifier_value" — rationale: "Staging values qualify the cancer diagnosis."\n'
            'Entity text: "FIGO IB1"\n'
            'Encounter context: "Cervical carcinoma FIGO IB1. Referred to gynaecological oncology."'
        ),
        "output": '{"resolved_label": "tumor_staging", "confidence": 0.93, "reason": "FIGO IB1 is a formal cancer staging classification; tumor_staging is correct. Informal staging qualifiers use qualifier_value but formal FIGO/Dukes/Clark are tumor_staging."}',
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
    LABEL_DISAMBIGUATION_EXAMPLES,
    {
        "label-disambig:find-dis",
        "label-disambig:obs-qual",
        "label-disambig:sub-proc",
        "label-disambig:dosage-qual",
        "label-disambig:sit-dis",
        "label-disambig:regime-sub",
        "label-disambig:artifact-proc",
        "label-disambig:negation",
    },
)
