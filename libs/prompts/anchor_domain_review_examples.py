"""Few-shot example library for the anchor_domain_review prompt.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Each example has:
  input       -- a JSON array of JSONL lines (the batch to review)
  output      -- expected JSON array (one object per input line)
  category    -- domain pattern demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy (extends extraction_examples.py):
  anchor:2ww-referral              -- active 2WW referral action
  anchor:2ww-clinic-seen           -- patient attended fast track clinic
  anchor:cancer-diagnosis          -- confirmed cancer finding
  anchor:cancer-excluded           -- cancer explicitly ruled out
  anchor:cancer-treatment          -- active cancer treatment
  anchor:cancer-treatment-hist     -- past completed cancer treatment
  anchor:investigation             -- diagnostic investigation for cancer workup
  anchor:metastatic                -- secondary / metastatic disease
  anchor:non-cancer                -- clearly not a cancer pathway event
  anchor:ambiguous                 -- cannot determine from evidence alone
  anchor:family-history            -- family history context (assertion=family_history)
  anchor:negated                   -- explicitly denied cancer event
"""

from __future__ import annotations

ANCHOR_DOMAIN_REVIEW_EXAMPLES: list[dict] = [
    # -- 2WW Referral ----------------------------------------------------------
    {
        "category": "anchor:2ww-referral",
        "model_scope": "any",
        "description": "Fast track referral for suspected skin cancer",
        "input": '[{"line_number": 1, "concept_id": "276401000000108", "concept_name": "Fast track referral for suspected skin cancer (procedure)", "text": "Fast track referral for suspected skin cancer", "confidence": 0.95, "detection_method": "concept", "milestone_type": "referral", "label": 1}]',
        "output": "[{\"line_number\": 1, \"original_concept_id\": \"276401000000108\", \"domain\": \"2WW_REFERRAL\", \"concept_correct\": true, \"suggested_concept_id\": null, \"suggested_concept_name\": null, \"assertion\": \"present\", \"rationale\": \"Fast track referral for suspected skin cancer is an active 2WW referral action, not an attendance or diagnosis.\", \"target_rule\": \"TargetRule('Fast track referral for suspected skin cancer (procedure)', '2WW_REFERRAL', pattern=[{'LOWER': 'fast'}, {'LOWER': 'track'}, {'LOWER': 'referral'}, {'OP': '?'}, {'LOWER': 'suspected'}, {'LOWER': 'skin'}, {'LOWER': 'cancer'}])\"}]",
    },
    {
        "category": "anchor:2ww-referral",
        "model_scope": "any",
        "description": "2WW referral lower GI for change in bowel habit",
        "input": '[{"line_number": 1, "concept_id": "276436000", "concept_name": "Referral to lower gastrointestinal surgery (procedure)", "text": "2WW referral to lower GI surgery - change in bowel habit", "confidence": 0.88, "detection_method": "hybrid", "milestone_type": "referral", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "276436000", "domain": "2WW_REFERRAL", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "2WW referral text with cancer-specific context confirms an active fast-track referral action.", "target_rule": "TargetRule(\'Referral to lower gastrointestinal surgery (procedure)\', \'2WW_REFERRAL\', pattern=[{\'LOWER\': \'2ww\'}, {\'LOWER\': \'referral\'}, {\'OP\': \'?\'}, {\'LOWER\': \'lower\'}, {\'LOWER\': \'gi\'}])"}]',
    },
    # -- 2WW Clinic Seen -------------------------------------------------------
    {
        "category": "anchor:2ww-clinic-seen",
        "model_scope": "any",
        "description": "Patient seen at fast track prostate clinic",
        "input": '[{"line_number": 1, "concept_id": "266753000", "concept_name": "Seen in urology clinic (finding)", "text": "Seen in fast track suspected prostate cancer clinic", "confidence": 0.82, "detection_method": "hybrid", "milestone_type": "specialist_visit", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "266753000", "domain": "2WW_CLINIC_SEEN", "concept_correct": false, "suggested_concept_id": null, "suggested_concept_name": "Attendance at fast track suspected prostate cancer clinic", "assertion": "present", "rationale": "Text records clinic attendance, not just a referral; 2WW_CLINIC_SEEN is correct. SNOMED concept is generic urology clinic which is imprecise.", "target_rule": "TargetRule(\'Seen in fast track suspected prostate cancer clinic\', \'2WW_CLINIC_SEEN\', pattern=[{\'LOWER\': \'seen\'}, {\'LOWER\': \'in\'}, {\'LOWER\': \'fast\'}, {\'LOWER\': \'track\'}, {\'LOWER\': \'suspected\'}, {\'LOWER\': \'prostate\'}])"}]',
    },
    # -- Cancer Diagnosis ------------------------------------------------------
    {
        "category": "anchor:cancer-diagnosis",
        "model_scope": "any",
        "description": "Histology confirms adenocarcinoma of sigmoid colon",
        "input": '[{"line_number": 1, "concept_id": "363414004", "concept_name": "Malignant neoplasm of sigmoid colon (disorder)", "text": "Histology: moderately differentiated adenocarcinoma of sigmoid colon", "confidence": 0.97, "detection_method": "concept", "milestone_type": "diagnosis", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "363414004", "domain": "CANCER_DIAGNOSIS", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Histology text explicitly states confirmed adenocarcinoma; this is a present positive cancer diagnosis.", "target_rule": "TargetRule(\'Malignant neoplasm of sigmoid colon (disorder)\', \'CANCER_DIAGNOSIS\', pattern=[{\'LOWER\': \'adenocarcinoma\'}, {\'LOWER\': \'of\'}, {\'LOWER\': \'sigmoid\'}, {\'LOWER\': \'colon\'}])"}]',
    },
    # -- Cancer Diagnosis Excluded ---------------------------------------------
    {
        "category": "anchor:cancer-excluded",
        "model_scope": "any",
        "description": "Biopsy benign - cancer excluded",
        "input": '[{"line_number": 1, "concept_id": "415068004", "concept_name": "No evidence of malignancy (finding)", "text": "Biopsy result: benign intradermal naevus. No malignancy.", "confidence": 0.91, "detection_method": "concept", "milestone_type": "diagnosis", "label": 0}]',
        "output": '[{"line_number": 1, "original_concept_id": "415068004", "domain": "CANCER_DIAGNOSIS_EXCLUDED", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Biopsy confirms benign lesion with explicit no malignancy; this is a cancer-excluded outcome.", "target_rule": "TargetRule(\'No evidence of malignancy (finding)\', \'CANCER_DIAGNOSIS_EXCLUDED\', pattern=[{\'LOWER\': \'no\'}, {\'LOWER\': \'malignancy\'}])"}]',
    },
    {
        "category": "anchor:cancer-excluded",
        "model_scope": "any",
        "description": "Family history of cancer - assertion family_history",
        "input": '[{"line_number": 1, "concept_id": "160303001", "concept_name": "Family history of malignant neoplasm (situation)", "text": "No fam hx of cancer", "confidence": 0.74, "detection_method": "hybrid", "milestone_type": "referral", "label": 0}]',
        "output": '[{"line_number": 1, "original_concept_id": "160303001", "domain": "CANCER_DIAGNOSIS_EXCLUDED", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "family_history", "rationale": "Text states no family history of cancer; domain is CANCER_DIAGNOSIS_EXCLUDED with assertion family_history as per rules.", "target_rule": "TargetRule(\'Family history of malignant neoplasm (situation)\', \'CANCER_DIAGNOSIS_EXCLUDED\', pattern=[{\'LOWER\': \'no\'}, {\'LOWER\': \'fam\'}, {\'LOWER\': \'hx\'}, {\'LOWER\': \'of\'}, {\'LOWER\': \'cancer\'}])"}]',
    },
    # -- Cancer Treatment ------------------------------------------------------
    {
        "category": "anchor:cancer-treatment",
        "model_scope": "any",
        "description": "First cycle CHOP chemotherapy commenced",
        "input": '[{"line_number": 1, "concept_id": "367336001", "concept_name": "Chemotherapy (procedure)", "text": "First cycle CHOP chemotherapy commenced", "confidence": 0.93, "detection_method": "hybrid", "milestone_type": "treatment", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "367336001", "domain": "CANCER_TREATMENT", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "CHOP is a cancer-specific chemotherapy regimen; first cycle commenced confirms active treatment.", "target_rule": "TargetRule(\'Chemotherapy (procedure)\', \'CANCER_TREATMENT\', pattern=[{\'LOWER\': \'chop\'}, {\'LOWER\': \'chemotherapy\'}, {\'LOWER\': \'commenced\'}])"}]',
    },
    {
        "category": "anchor:cancer-treatment-hist",
        "model_scope": "any",
        "description": "Completed radiotherapy course - historical treatment",
        "input": '[{"line_number": 1, "concept_id": "33195004", "concept_name": "Radiotherapy (procedure)", "text": "Completed radiotherapy to left breast 2020", "confidence": 0.87, "detection_method": "concept", "milestone_type": "treatment", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "33195004", "domain": "CANCER_TREATMENT_HISTORICAL", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "historical", "rationale": "Completed radiotherapy with explicit past year (2020) indicates historical treatment, not active.", "target_rule": "TargetRule(\'Radiotherapy (procedure)\', \'CANCER_TREATMENT_HISTORICAL\', pattern=[{\'LOWER\': \'completed\'}, {\'LOWER\': \'radiotherapy\'}])"}]',
    },
    # -- Investigation ---------------------------------------------------------
    {
        "category": "anchor:investigation",
        "model_scope": "any",
        "description": "CT abdomen for cancer staging",
        "input": '[{"line_number": 1, "concept_id": "169069000", "concept_name": "CT of abdomen (procedure)", "text": "CT abdomen chest pelvis for staging", "confidence": 0.85, "detection_method": "concept", "milestone_type": "investigation", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "169069000", "domain": "INVESTIGATION", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "CT scan for staging is a diagnostic investigation in the cancer workup pathway.", "target_rule": "TargetRule(\'CT of abdomen (procedure)\', \'INVESTIGATION\', pattern=[{\'LOWER\': \'ct\'}, {\'LOWER\': \'abdomen\'}, {\'OP\': \'?\'}, {\'LOWER\': \'staging\'}])"}]',
    },
    # -- Metastatic Disease ----------------------------------------------------
    {
        "category": "anchor:metastatic",
        "model_scope": "any",
        "description": "Liver metastases from colorectal primary",
        "input": '[{"line_number": 1, "concept_id": "94225005", "concept_name": "Secondary malignant neoplasm of liver (disorder)", "text": "CT: liver metastases from colorectal primary", "confidence": 0.95, "detection_method": "concept", "milestone_type": "diagnosis", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "94225005", "domain": "METASTATIC_DISEASE", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Liver metastases from a known colorectal primary is confirmed metastatic disease.", "target_rule": "TargetRule(\'Secondary malignant neoplasm of liver (disorder)\', \'METASTATIC_DISEASE\', pattern=[{\'LOWER\': \'liver\'}, {\'IN\': [\'metastases\', \'mets\', \'metastasis\']}])"}]',
    },
    # -- Non-Cancer ------------------------------------------------------------
    {
        "category": "anchor:non-cancer",
        "model_scope": "any",
        "description": "Blood pressure reading - not a cancer pathway event",
        "input": '[{"line_number": 1, "concept_id": "163020007", "concept_name": "Blood pressure reading (observable entity)", "text": "BP 148/92 mmHg", "confidence": 0.99, "detection_method": "concept", "milestone_type": "referral", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "163020007", "domain": "NON_CANCER", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Blood pressure measurement has no cancer pathway relevance; label=1 is incorrect for this event.", "target_rule": "TargetRule(\'Blood pressure reading (observable entity)\', \'NON_CANCER\', pattern=[{\'LOWER\': \'bp\'}, {\'IS_DIGIT\': true}])"}]',
    },
    {
        "category": "anchor:non-cancer",
        "model_scope": "any",
        "description": "Bowel cancer screening invitation with no result - non-cancer",
        "input": '[{"line_number": 1, "concept_id": "413810007", "concept_name": "Bowel cancer screening programme screening invitation (record artifact)", "text": "Bowel cancer screening programme - no response", "confidence": 0.61, "detection_method": "hybrid", "milestone_type": "referral", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "413810007", "domain": "NON_CANCER", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Screening invitation with no response recorded is an administrative screening event, not a cancer pathway outcome.", "target_rule": "TargetRule(\'Bowel cancer screening programme screening invitation (record artifact)\', \'NON_CANCER\', pattern=[{\'LOWER\': \'bowel\'}, {\'LOWER\': \'cancer\'}, {\'LOWER\': \'screening\'}, {\'LOWER\': \'programme\'}, {\'OP\': \'?\'}])"}]',
    },
    # -- Ambiguous -------------------------------------------------------------
    {
        "category": "anchor:ambiguous",
        "model_scope": "any",
        "description": "Vague letter reference - cannot determine pathway outcome",
        "input": '[{"line_number": 1, "concept_id": "229059009", "concept_name": "Clinic letter (record artifact)", "text": "Letter received from oncology", "confidence": 0.52, "detection_method": "concept", "milestone_type": "diagnosis", "label": 1}]',
        "output": '[{"line_number": 1, "original_concept_id": "229059009", "domain": "AMBIGUOUS", "concept_correct": true, "suggested_concept_id": null, "suggested_concept_name": null, "assertion": "present", "rationale": "Clinic letter from oncology suggests cancer relevance but content is unknown; cannot determine outcome from evidence text alone.", "target_rule": "TargetRule(\'Clinic letter (record artifact)\', \'AMBIGUOUS\', pattern=[{\'LOWER\': \'letter\'}, {\'LOWER\': \'received\'}, {\'LOWER\': \'from\'}, {\'LOWER\': \'oncology\'}])"}]',
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
    ANCHOR_DOMAIN_REVIEW_EXAMPLES,
    {
        "anchor:2ww-referral",
        "anchor:2ww-clinic-seen",
        "anchor:cancer-diagnosis",
        "anchor:cancer-excluded",
        "anchor:cancer-treatment",
        "anchor:metastatic",
        "anchor:non-cancer",
        "anchor:ambiguous",
    },
)
