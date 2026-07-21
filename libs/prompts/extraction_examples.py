"""Few-shot example library for the extraction prompt.

Atlas trace:
  DO: DO-416BA91D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-416BA91D")

Each example has:
  input       — de-identified clinical text snippet
  output      — expected JSON output (as a string, will be parsed to validate)
  category    — what clinical/linguistic pattern this example demonstrates
  model_scope — which LLM provider this example is tuned for:
                  "any"   → works equally well with Claude (AWS Bedrock) and OpenAI (Azure)
                  "aws"   → tuned for Claude on AWS Bedrock (e.g. exploits Claude's XML/list
                            instruction following or extended thinking phrasing)
                  "azure" → tuned for OpenAI on Azure (e.g. GPT-specific JSON-mode phrasing
                            or system-prompt structure differences)
  description — short human-readable label for the Admin UI example library

Category taxonomy:
  assertion:absent        — negation patterns
  assertion:possible      — uncertainty / suspected
  assertion:historical    — past / resolved
  assertion:hypothetical  — conditional / planned / safety-netting
  assertion:family        — family history
  assertion:refuted       — initial impression overridden
  assertion:declined      — patient refusal
  assertion:cancelled     — procedure/appointment cancellation
  multi-entity            — sentence with more than one codable concept
  observable              — lab results with value/unit/reference_range
  staging                 — cancer staging / performance status
  abbreviation            — GP abbreviations expanded in lookup_term
  brand-name              — pharmaceutical brand → generic
  situation:allergy       — allergy status
  situation:referral      — referral to service / planned procedure
  finding:lifestyle       — smoking and lifestyle status (finding, not situation)
  observable:blood_panel  — Blood Results table row cells
  vital-signs             — bedside measurement with shorthand label
  negation:compound       — compound sentence where negation covers multiple entities
  disorder:imaging        — named pathologies described via imaging (pleural effusion,
                            pleural thickening etc.) tagged as disorder not finding
"""

from __future__ import annotations

EXTRACTION_EXAMPLES: list[dict] = [
    # ── Assertion: absent ────────────────────────────────────────────────────
    {
        "category": "assertion:absent",
        "model_scope": "any",
        "description": "Simple negation",
        "input": "[s0] No fever.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "fever", "lookup_term": "fever", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:absent",
        "model_scope": "any",
        "description": "Denial with explicit cue",
        "input": "[s0] Denies chest pain.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "chest pain", "lookup_term": "chest pain", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "negation:compound",
        "model_scope": "any",
        "description": "Opening negation applies to every entity in the sentence",
        "input": "[s0] No bloating, change in bowel habit, or rectal bleeding.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "bloating", "lookup_term": "bloating", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "change in bowel habit", "lookup_term": "change in bowel habit", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "rectal bleeding", "lookup_term": "rectal bleeding", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "negation:compound",
        "model_scope": "any",
        "description": "Reports no — all three entities absent",
        "input": "[s0] Reports no nausea, vomiting, or diarrhoea.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "nausea", "lookup_term": "nausea", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "vomiting", "lookup_term": "vomiting", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "diarrhoea", "lookup_term": "diarrhoea", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: possible ──────────────────────────────────────────────────
    {
        "category": "assertion:possible",
        "model_scope": "any",
        "description": "Question mark prefix",
        "input": "[s0] ? UTI",
        "output": '{"terms": [{"sentence_id": "s0", "text": "? UTI", "lookup_term": "suspected urinary tract infection", "semantic_tag": "disorder", "assertion": "possible", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:possible",
        "model_scope": "any",
        "description": "Concerning for — uncertain malignancy",
        "input": "[s0] Mass concerning for lymphoma.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "mass", "lookup_term": "mass", "semantic_tag": "finding", "assertion": "possible", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: historical ────────────────────────────────────────────────
    {
        "category": "assertion:historical",
        "model_scope": "any",
        "description": "Resolved in same sentence",
        "input": "[s0] Back pain on Friday, but this has since resolved.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Back pain", "lookup_term": "back pain", "semantic_tag": "finding", "assertion": "historical", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:historical",
        "model_scope": "any",
        "description": "Bleeding stopped — historical",
        "input": "[s0] Bleeding has stopped.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Bleeding", "lookup_term": "bleeding", "semantic_tag": "finding", "assertion": "historical", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:historical",
        "model_scope": "any",
        "description": "Past medical history with explicit cue",
        "input": "[s0] PMH: appendicectomy 2019.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "appendicectomy", "lookup_term": "appendicectomy", "semantic_tag": "procedure", "assertion": "historical", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: planned ───────────────────────────────────────────────────
    {
        "category": "assertion:planned",
        "model_scope": "any",
        "description": "Booked referral -- confirmed, not yet happened",
        "input": "[s0] Referred for physiotherapy.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "physiotherapy", "lookup_term": "physiotherapy", "semantic_tag": "procedure", "assertion": "planned", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:planned",
        "model_scope": "any",
        "description": "Awaiting investigation -- confirmed, not yet done",
        "input": "[s0] Awaiting MRI spine.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "MRI spine", "lookup_term": "MRI scan of spine", "semantic_tag": "procedure", "assertion": "planned", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: hypothetical ──────────────────────────────────────────────
    {
        "category": "assertion:hypothetical",
        "model_scope": "any",
        "description": "Safety-netting text -- do not extract as present",
        "input": "[s0] If associated with shortness of breath, seek urgent review.",
        "output": '{"terms": []}',
    },
    {
        "category": "assertion:hypothetical",
        "model_scope": "any",
        "description": "Conditional future action -- not yet arranged",
        "input": "[s0] Will refer to cardiology if no improvement.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "refer to cardiology", "lookup_term": "referral to cardiology", "semantic_tag": "procedure", "assertion": "hypothetical", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: family history as situation + present ─────────────────────
    {
        "category": "assertion:family",
        "model_scope": "any",
        "description": "Family history",
        "input": "[s0] Mother had breast cancer.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Mother had breast cancer", "lookup_term": "family history of malignant neoplasm of breast", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: refuted ───────────────────────────────────────────────────
    {
        "category": "assertion:refuted",
        "model_scope": "any",
        "description": "Initial impression overridden by biopsy",
        "input": "[s0] Thought to be eczema but biopsy confirmed psoriasis.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "eczema", "lookup_term": "eczema", "semantic_tag": "disorder", "assertion": "refuted", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "psoriasis", "lookup_term": "psoriasis", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: declined ──────────────────────────────────────────────────
    {
        "category": "assertion:declined",
        "model_scope": "any",
        "description": "Patient declined medication",
        "input": "[s0] Patient declined statins.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "statins", "lookup_term": "statin", "semantic_tag": "substance", "assertion": "declined", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:declined",
        "model_scope": "any",
        "description": "Patient refused investigation",
        "input": "[s0] Patient refused colonoscopy.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "colonoscopy", "lookup_term": "colonoscopy", "semantic_tag": "procedure", "assertion": "declined", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Assertion: cancelled ─────────────────────────────────────────────────
    {
        "category": "assertion:cancelled",
        "model_scope": "any",
        "description": "Procedure cancelled",
        "input": "[s0] MRI cancelled due to claustrophobia.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "MRI", "lookup_term": "magnetic resonance imaging", "semantic_tag": "procedure", "assertion": "cancelled", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:cancelled",
        "model_scope": "any",
        "description": "Did not attend",
        "input": "[s0] DNA — appointment cancelled.",
        "output": '{"terms": []}',
    },
    # ── Multi-entity ─────────────────────────────────────────────────────────
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Three comorbidities in problem list",
        "input": "[s0] HTN, T2DM and CKD.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "HTN", "lookup_term": "hypertension", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "T2DM", "lookup_term": "type 2 diabetes mellitus", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "CKD", "lookup_term": "chronic kidney disease", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Observable entity plus a disorder in the same sentence",
        "input": "[s0] eGFR 43 — CKD stage 3b.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "eGFR", "lookup_term": "estimated glomerular filtration rate", "semantic_tag": "observable entity", "assertion": "present", "value": "43", "unit": "mL/min", "reference_range": null}, {"sentence_id": "s0", "text": "CKD stage 3b", "lookup_term": "chronic kidney disease stage 3b", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Observable entity ────────────────────────────────────────────────────
    {
        "category": "observable",
        "model_scope": "any",
        "description": "Compound lab result — parameter name only in text, value/unit/range in fields",
        "input": "[s0] Haemoglobin concentration (Xa96v) 106 g/L [130-180] - Outside reference range.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Haemoglobin concentration", "lookup_term": "haemoglobin concentration", "semantic_tag": "observable entity", "assertion": "present", "value": "106", "unit": "g/L", "reference_range": "130-180"}]}',
    },
    {
        "category": "observable",
        "model_scope": "any",
        "description": "Lab result — do NOT infer a disorder from the value",
        "input": "[s0] eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 69 mL/min.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "eGFR", "lookup_term": "estimated glomerular filtration rate", "semantic_tag": "observable entity", "assertion": "present", "value": "69", "unit": "mL/min", "reference_range": null}]}',
    },
    {
        "category": "vital-signs",
        "model_scope": "any",
        "description": "Vital-signs shorthand with value",
        "input": "[s0] HR: 73 bpm",
        "output": '{"terms": [{"sentence_id": "s0", "text": "HR", "lookup_term": "pulse rate", "semantic_tag": "observable entity", "assertion": "present", "value": "73", "unit": "bpm", "reference_range": null}]}',
    },
    {
        "category": "vital-signs",
        "model_scope": "any",
        "description": "Blood pressure",
        "input": "[s0] BP: 142/92 mmHg",
        "output": '{"terms": [{"sentence_id": "s0", "text": "BP", "lookup_term": "blood pressure", "semantic_tag": "observable entity", "assertion": "present", "value": "142/92", "unit": "mmHg", "reference_range": null}]}',
    },
    # ── Staging scale ────────────────────────────────────────────────────────
    {
        "category": "staging",
        "model_scope": "any",
        "description": "TNM staging with primary tumour disorder",
        "input": "[s0] Breast cancer T2N1M0.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Breast cancer", "lookup_term": "breast cancer", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "T2N1M0", "lookup_term": "TNM staging", "semantic_tag": "staging scale", "assertion": "present", "value": "T2N1M0", "unit": null, "reference_range": null}]}',
    },
    {
        "category": "staging",
        "model_scope": "any",
        "description": "Gleason score",
        "input": "[s0] Prostate cancer Gleason 7 (3+4).",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Prostate cancer", "lookup_term": "prostate cancer", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "Gleason 7 (3+4)", "lookup_term": "Gleason score", "semantic_tag": "staging scale", "assertion": "present", "value": "7 (3+4)", "unit": null, "reference_range": null}]}',
    },
    {
        "category": "staging",
        "model_scope": "any",
        "description": "ECOG performance status",
        "input": "[s0] ECOG PS2.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "ECOG PS2", "lookup_term": "ECOG performance status", "semantic_tag": "staging scale", "assertion": "present", "value": "2", "unit": null, "reference_range": null}]}',
    },
    {
        "category": "staging",
        "model_scope": "any",
        "description": "FIGO staging",
        "input": "[s0] Cervical carcinoma Stage IIIA.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Cervical carcinoma", "lookup_term": "carcinoma of cervix", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "Stage IIIA", "lookup_term": "FIGO staging", "semantic_tag": "staging scale", "assertion": "present", "value": "IIIA", "unit": null, "reference_range": null}]}',
    },
    # ── Abbreviation expansion ───────────────────────────────────────────────
    {
        "category": "abbreviation",
        "model_scope": "any",
        "description": "Common GP abbreviation → standard lookup term",
        "input": "[s0] AF and IHD.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "AF", "lookup_term": "atrial fibrillation", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "IHD", "lookup_term": "ischaemic heart disease", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Brand name → generic ─────────────────────────────────────────────────
    {
        "category": "brand-name",
        "model_scope": "any",
        "description": "Brand name in text, generic in lookup_term",
        "input": "[s0] Amoxicillin 500mg capsules.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Amoxicillin 500mg capsules", "lookup_term": "amoxicillin", "semantic_tag": "substance", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Situation: allergy ───────────────────────────────────────────────────
    {
        "category": "situation:allergy",
        "model_scope": "any",
        "description": "Allergy status",
        "input": "[s0] Allergic to penicillin.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Allergic to penicillin", "lookup_term": "allergy to penicillin", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "situation:allergy",
        "model_scope": "any",
        "description": "No known drug allergies",
        "input": "[s0] NKDA.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "NKDA", "lookup_term": "no known drug allergies", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Referral template: symptoms and labs only (no pathway prose) ─────────
    {
        "category": "precision:referral_scope",
        "model_scope": "any",
        "description": "2WW email header with symptoms -- skip referral routing phrase",
        "input": "[s0] Urgent 2WW brain/CNS referral for personality change and new visual disturbance.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "personality change", "lookup_term": "personality change", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "visual disturbance", "lookup_term": "visual disturbance", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope",
        "model_scope": "any",
        "description": "Breast suspected pathway -- situation present",
        "input": "[s0] Refer this patient under the breast suspected cancer pathway.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "breast suspected cancer pathway", "lookup_term": "malignant neoplasm of breast suspected", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope:ng12_mri",
        "model_scope": "any",
        "description": "NG12 plan -- MRI arranged, skip 2WW pathway echo",
        "input": "[s0] An urgent MRI scan of the brain has been arranged as part of this 2WW brain/CNS referral.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "urgent MRI scan of the brain", "lookup_term": "magnetic resonance imaging of brain", "semantic_tag": "procedure", "assertion": "planned", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope:lower_gi_fit",
        "model_scope": "any",
        "description": "Lower GI -- suspected situation, FIT+, symptoms; skip referral placed",
        "input": "[s0] Problem: Suspected lower GI cancer -- FIT+ in lab feed; 2WW referral placed. History: fresh rectal bleeding and change in bowel habit.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Suspected lower GI cancer", "lookup_term": "malignant neoplasm of lower gastrointestinal tract suspected", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "FIT+", "lookup_term": "faecal immunochemical test positive", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "fresh rectal bleeding", "lookup_term": "rectal bleeding", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "change in bowel habit", "lookup_term": "change in bowel habit", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope:upper_gi_stomach",
        "model_scope": "any",
        "description": "Upper GI stomach pathway -- situation present",
        "input": "[s0] Refer under the suspected cancer pathway for stomach cancer.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "suspected cancer pathway for stomach cancer", "lookup_term": "malignant neoplasm of upper gastrointestinal tract suspected", "semantic_tag": "situation", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope:submitted",
        "model_scope": "any",
        "description": "Plan line referral submitted -- no entity",
        "input": "[s0] Plan: 2WW lower GI referral submitted via e-Referral Service today.",
        "output": '{"terms": []}',
    },
    {
        "category": "precision:referral_scope:short_span",
        "model_scope": "any",
        "description": "Long eye sentence -- short visual disturbance span only",
        "input": "[s0] She has also developed new onset visual disturbance in the right field over three weeks, described as flickering.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "visual disturbance", "lookup_term": "visual disturbance", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "precision:referral_scope:ers_reason",
        "model_scope": "any",
        "description": (
            "NHS eRS 2WW reason-for-referral table cell -- "
            "extract symptoms and investigation result, skip the label phrase"
        ),
        "input": (
            "[s0] | The reason I am concerned this patient has cancer is: "
            "significant loss of appetite with intermittent vomiting. "
            "Patient has difficulty swallowing. FIT neg, "
            "Date Symptoms Started: end of september | | --- |"
        ),
        "output": (
            '{"terms": ['
            '{"sentence_id": "s0", "text": "loss of appetite", '
            '"lookup_term": "loss of appetite", "semantic_tag": "finding", '
            '"assertion": "present", "value": null, "unit": null, "reference_range": null}, '
            '{"sentence_id": "s0", "text": "intermittent vomiting", '
            '"lookup_term": "vomiting", "semantic_tag": "finding", '
            '"assertion": "present", "value": null, "unit": null, "reference_range": null}, '
            '{"sentence_id": "s0", "text": "difficulty swallowing", '
            '"lookup_term": "dysphagia", "semantic_tag": "finding", '
            '"assertion": "present", "value": null, "unit": null, "reference_range": null}, '
            '{"sentence_id": "s0", "text": "FIT neg", '
            '"lookup_term": "faecal immunochemical test", "semantic_tag": "finding", '
            '"assertion": "present", "value": null, "unit": null, "reference_range": null}'
            "]}"
        ),
    },
    {
        "category": "situation:referral",
        "model_scope": "any",
        "description": "Referred to specialist - procedure planned",
        "input": "[s0] Referred to rheumatology.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Referred to rheumatology", "lookup_term": "referral to rheumatology", "semantic_tag": "procedure", "assertion": "planned", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "situation:referral",
        "model_scope": "any",
        "description": "Awaiting planned procedure",
        "input": "[s0] Awaiting knee replacement surgery.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "knee replacement surgery", "lookup_term": "knee replacement", "semantic_tag": "procedure", "assertion": "planned", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Finding: lifestyle (smoking per annotation guidelines rule 10) ───────
    {
        "category": "finding:lifestyle",
        "model_scope": "any",
        "description": "Smoking status as finding",
        "input": "[s0] Ex-smoker.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Ex-smoker", "lookup_term": "ex-smoker", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Implicit negation / normal finding ───────────────────────────────────
    {
        "category": "assertion:absent",
        "model_scope": "any",
        "description": "Positive statement of normality — NOT negated",
        "input": "[s0] Chest clear.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Chest clear", "lookup_term": "chest clear", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Multi-entity: mixed present + absent in one sentence ─────────────────
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Confirmed condition plus denied symptom in the same sentence",
        "input": "[s0] Hypertension confirmed, no chest pain.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Hypertension", "lookup_term": "hypertension", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "chest pain", "lookup_term": "chest pain", "semantic_tag": "finding", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Possible finding plus absent finding in same sentence",
        "input": "[s0] ? DVT, no cellulitis.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "? DVT", "lookup_term": "suspected deep vein thrombosis", "semantic_tag": "disorder", "assertion": "possible", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "cellulitis", "lookup_term": "cellulitis", "semantic_tag": "disorder", "assertion": "absent", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Multi-sentence — each entity stamped with its own sentence ID",
        "input": "[s0] PMH: T2DM, hypertension. [s1] On metformin and ramipril.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "T2DM", "lookup_term": "type 2 diabetes mellitus", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "hypertension", "lookup_term": "hypertension", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s1", "text": "metformin", "lookup_term": "metformin", "semantic_tag": "substance", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s1", "text": "ramipril", "lookup_term": "ramipril", "semantic_tag": "substance", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Regime / therapy ─────────────────────────────────────────────────────
    {
        "category": "regime/therapy",
        "model_scope": "any",
        "description": "Chemotherapy regimen",
        "input": "[s0] Commenced FOLFOX chemotherapy.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "FOLFOX chemotherapy", "lookup_term": "FOLFOX regimen", "semantic_tag": "regime/therapy", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "regime/therapy",
        "model_scope": "any",
        "description": "Radiation therapy course",
        "input": "[s0] Completed a course of radiotherapy to the left breast.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "radiotherapy to the left breast", "lookup_term": "radiotherapy", "semantic_tag": "regime/therapy", "assertion": "historical", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "regime/therapy",
        "model_scope": "any",
        "description": "Antibiotic course",
        "input": "[s0] Started 7-day course of amoxicillin for community-acquired pneumonia.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "community-acquired pneumonia", "lookup_term": "community-acquired pneumonia", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "7-day course of amoxicillin", "lookup_term": "amoxicillin", "semantic_tag": "regime/therapy", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Product (medical devices) ─────────────────────────────────────────────
    {
        "category": "product",
        "model_scope": "any",
        "description": "Continuous glucose monitor fitted",
        "input": "[s0] Freestyle Libre fitted today.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Freestyle Libre", "lookup_term": "continuous glucose monitoring system", "semantic_tag": "product", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "product",
        "model_scope": "any",
        "description": "Inhaler device prescribed",
        "input": "[s0] Prescribed Ventolin MDI 100mcg.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Ventolin MDI 100mcg", "lookup_term": "salbutamol inhaler", "semantic_tag": "product", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Medication with dose ─────────────────────────────────────────────────
    {
        "category": "brand-name",
        "model_scope": "any",
        "description": "Medication with dose and frequency — generic lookup, strip dose from text",
        "input": "[s0] Metformin 500mg twice daily.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Metformin 500mg twice daily", "lookup_term": "metformin", "semantic_tag": "substance", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "assertion:hypothetical",
        "model_scope": "any",
        "description": "Hypothetical with a specific planned drug",
        "input": "[s0] If no improvement, will start prednisolone.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "prednisolone", "lookup_term": "prednisolone", "semantic_tag": "substance", "assertion": "hypothetical", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "situation:referral",
        "model_scope": "any",
        "description": "Medication planned but not yet started",
        "input": "[s0] Plan to start atorvastatin once LFTs checked.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "atorvastatin", "lookup_term": "atorvastatin", "semantic_tag": "substance", "assertion": "hypothetical", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Observable: weight / BMI ─────────────────────────────────────────────
    {
        "category": "observable",
        "model_scope": "any",
        "description": "Weight and BMI as separate observable entities",
        "input": "[s0] Weight 92 kg, BMI 31.4 kg/m².",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Weight", "lookup_term": "body weight", "semantic_tag": "observable entity", "assertion": "present", "value": "92", "unit": "kg", "reference_range": null}, {"sentence_id": "s0", "text": "BMI", "lookup_term": "body mass index", "semantic_tag": "observable entity", "assertion": "present", "value": "31.4", "unit": "kg/m²", "reference_range": null}]}',
    },
    {
        "category": "observable",
        "model_scope": "any",
        "description": "HbA1c with IFCC value",
        "input": "[s0] HbA1c 58 mmol/mol.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "HbA1c", "lookup_term": "haemoglobin A1c", "semantic_tag": "observable entity", "assertion": "present", "value": "58", "unit": "mmol/mol", "reference_range": null}]}',
    },
    {
        "category": "observable",
        "model_scope": "any",
        "description": "eGFR with operator — use > symbol in value",
        "input": "[s0] eGFR >90 mL/min.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "eGFR", "lookup_term": "estimated glomerular filtration rate", "semantic_tag": "observable entity", "assertion": "present", "value": ">90", "unit": "mL/min", "reference_range": null}]}',
    },
    {
        "category": "observable",
        "model_scope": "any",
        "description": "INR within range — do NOT emit a disorder",
        "input": "[s0] INR 2.4 [2.0-3.0] - Within reference range.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "INR", "lookup_term": "international normalised ratio", "semantic_tag": "observable entity", "assertion": "present", "value": "2.4", "unit": null, "reference_range": "2.0-3.0"}]}',
    },
    # ── Observable: blood panel table rows ───────────────────────────────────
    {
        "category": "observable:blood_panel",
        "model_scope": "any",
        "description": "FBC row from Blood Results table",
        "input": "[s0] Hb 117.5 g/L, WCC 6.8 x10^9/L, Plts 465.0 x10^9/L, MCV 88.6 fL",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Hb", "lookup_term": "haemoglobin concentration", "semantic_tag": "observable entity", "assertion": "present", "value": "117.5", "unit": "g/L", "reference_range": null}, {"sentence_id": "s0", "text": "WCC", "lookup_term": "white blood cell count", "semantic_tag": "observable entity", "assertion": "present", "value": "6.8", "unit": "x10^9/L", "reference_range": null}, {"sentence_id": "s0", "text": "Plts", "lookup_term": "platelet count", "semantic_tag": "observable entity", "assertion": "present", "value": "465.0", "unit": "x10^9/L", "reference_range": null}, {"sentence_id": "s0", "text": "MCV", "lookup_term": "mean corpuscular volume", "semantic_tag": "observable entity", "assertion": "present", "value": "88.6", "unit": "fL", "reference_range": null}]}',
    },
    {
        "category": "observable:blood_panel",
        "model_scope": "any",
        "description": "U&E and LFT row from Blood Results table",
        "input": "[s0] Na 138.6 mmol/L, K 4.1 mmol/L, Creat 81.2 umol/L, ALT 68.8 U/L, Alk Phos 155.0 U/L, Bili 26.2 umol/L, Alb 31.2 g/L",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Na", "lookup_term": "sodium", "semantic_tag": "observable entity", "assertion": "present", "value": "138.6", "unit": "mmol/L", "reference_range": null}, {"sentence_id": "s0", "text": "K", "lookup_term": "potassium", "semantic_tag": "observable entity", "assertion": "present", "value": "4.1", "unit": "mmol/L", "reference_range": null}, {"sentence_id": "s0", "text": "Creat", "lookup_term": "creatinine", "semantic_tag": "observable entity", "assertion": "present", "value": "81.2", "unit": "umol/L", "reference_range": null}, {"sentence_id": "s0", "text": "ALT", "lookup_term": "alanine aminotransferase", "semantic_tag": "observable entity", "assertion": "present", "value": "68.8", "unit": "U/L", "reference_range": null}, {"sentence_id": "s0", "text": "Alk Phos", "lookup_term": "alkaline phosphatase", "semantic_tag": "observable entity", "assertion": "present", "value": "155.0", "unit": "U/L", "reference_range": null}, {"sentence_id": "s0", "text": "Bili", "lookup_term": "bilirubin", "semantic_tag": "observable entity", "assertion": "present", "value": "26.2", "unit": "umol/L", "reference_range": null}, {"sentence_id": "s0", "text": "Alb", "lookup_term": "albumin", "semantic_tag": "observable entity", "assertion": "present", "value": "31.2", "unit": "g/L", "reference_range": null}]}',
    },
    {
        "category": "observable:blood_panel",
        "model_scope": "any",
        "description": "Inflammation and endocrine row from Blood Results table",
        "input": "[s0] CRP 6.2 mg/L, ESR 14.5 mm/h, Ferritin 0 ug/L, Ca 2.9 mmol/L, HbA1c 45.0 mmol/mol",
        "output": '{"terms": [{"sentence_id": "s0", "text": "CRP", "lookup_term": "c reactive protein", "semantic_tag": "observable entity", "assertion": "present", "value": "6.2", "unit": "mg/L", "reference_range": null}, {"sentence_id": "s0", "text": "ESR", "lookup_term": "erythrocyte sedimentation rate", "semantic_tag": "observable entity", "assertion": "present", "value": "14.5", "unit": "mm/h", "reference_range": null}, {"sentence_id": "s0", "text": "Ferritin", "lookup_term": "ferritin", "semantic_tag": "observable entity", "assertion": "present", "value": "0", "unit": "ug/L", "reference_range": null}, {"sentence_id": "s0", "text": "Ca", "lookup_term": "calcium", "semantic_tag": "observable entity", "assertion": "present", "value": "2.9", "unit": "mmol/L", "reference_range": null}, {"sentence_id": "s0", "text": "HbA1c", "lookup_term": "haemoglobin A1c", "semantic_tag": "observable entity", "assertion": "present", "value": "45.0", "unit": "mmol/mol", "reference_range": null}]}',
    },
    {
        "category": "finding:investigation",
        "model_scope": "any",
        "description": "CA125 raised -- short finding, not full level sentence",
        "input": "[s0] CA125 level is raised at 92 U/mL (ref <35).",
        "output": '{"terms": [{"sentence_id": "s0", "text": "CA125 raised", "lookup_term": "CA125 raised", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "finding:investigation",
        "model_scope": "any",
        "description": "FIT checklist token only",
        "input": "[s0] FIT positive.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "FIT positive", "lookup_term": "faecal immunochemical test positive", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "finding:investigation",
        "model_scope": "any",
        "description": "Abnormal imaging phrase",
        "input": "[s0] I have arranged an abnormal MRI brain scan as an urgent investigation.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "abnormal MRI", "lookup_term": "abnormal magnetic resonance imaging", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Social history ───────────────────────────────────────────────────────
    {
        "category": "finding:lifestyle",
        "model_scope": "any",
        "description": "Alcohol consumption as finding",
        "input": "[s0] Drinks approximately 14 units of alcohol per week.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Drinks approximately 14 units of alcohol per week", "lookup_term": "alcohol consumption", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "finding:lifestyle",
        "model_scope": "any",
        "description": "Never smoked",
        "input": "[s0] Never smoked.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Never smoked", "lookup_term": "non-smoker", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── No codable entity (administrative / safety-netting text) ────────────
    {
        "category": "assertion:hypothetical",
        "model_scope": "any",
        "description": "Follow-up instruction — no clinical entity to extract",
        "input": "[s0] Follow up in 4 weeks.",
        "output": '{"terms": []}',
    },
    {
        "category": "assertion:hypothetical",
        "model_scope": "any",
        "description": "Return if worse — safety netting, no entity",
        "input": "[s0] Advised to return if symptoms worsen or fail to improve within 48 hours.",
        "output": '{"terms": []}',
    },
    # ── Physical examination findings ────────────────────────────────────────
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Examination finding with body site",
        "input": "[s0] Bilateral pitting oedema of the ankles.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Bilateral pitting oedema of the ankles", "lookup_term": "pitting oedema of ankle", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "multi-entity",
        "model_scope": "any",
        "description": "Procedure performed and its finding",
        "input": "[s0] ECG performed — normal sinus rhythm.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "ECG", "lookup_term": "electrocardiogram", "semantic_tag": "procedure", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "normal sinus rhythm", "lookup_term": "normal sinus rhythm", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Abbreviation: short single-word entry ────────────────────────────────
    {
        "category": "abbreviation",
        "model_scope": "any",
        "description": "SOB — expand common GP shorthand",
        "input": "[s0] SOB on exertion.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "SOB", "lookup_term": "shortness of breath", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "abbreviation",
        "model_scope": "any",
        "description": "COPD — expand, do not infer acute exacerbation",
        "input": "[s0] Known COPD, on salbutamol PRN.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "COPD", "lookup_term": "chronic obstructive pulmonary disease", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "salbutamol", "lookup_term": "salbutamol", "semantic_tag": "substance", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    # ── Disorder: imaging context (pleural pathology) ────────────────────────
    # Pleural effusion and pleural thickening are SNOMED disorders even when
    # described as imaging findings. Do NOT tag them as finding. Volume loss
    # and opacity descriptions are findings (or omitted if non-specific).
    {
        "category": "disorder:imaging",
        "model_scope": "any",
        "description": "Pleural effusion and thickening from radiology — both disorder",
        "input": "[s0] Moderate left pleural effusion with irregular left pleural thickening and mild left hemithoracic volume loss. CT chest with contrast advised.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Moderate left pleural effusion", "lookup_term": "pleural effusion", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "irregular left pleural thickening", "lookup_term": "pleural thickening", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "CT chest with contrast", "lookup_term": "CT chest with contrast", "semantic_tag": "procedure", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "disorder:imaging",
        "model_scope": "any",
        "description": "Nodular pleural thickening and effusion — both disorder; CT recommendation as procedure",
        "input": "[s0] Unilateral right pleural effusion with nodular pleural thickening along the lateral chest wall. Appearances warrant urgent CT assessment.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Unilateral right pleural effusion", "lookup_term": "pleural effusion", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "nodular pleural thickening", "lookup_term": "pleural thickening", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "CT assessment", "lookup_term": "CT chest", "semantic_tag": "procedure", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "disorder:imaging",
        "model_scope": "any",
        "description": "Pleural thickening as disorder; reduced lung volume as finding; blunting of angle not extracted separately",
        "input": "[s0] Diffuse left pleural thickening with blunting of the left costophrenic angle and reduced left lung volume. Further CT imaging recommended.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "Diffuse left pleural thickening", "lookup_term": "pleural thickening", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "reduced left lung volume", "lookup_term": "reduced lung volume", "semantic_tag": "finding", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "CT imaging", "lookup_term": "CT chest", "semantic_tag": "procedure", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
    },
    {
        "category": "disorder:imaging",
        "model_scope": "any",
        "description": "Pleural opacity: extract named pathologies as disorder; opacity descriptor not extracted separately",
        "input": "[s0] Right-sided pleural-based opacity with associated pleural effusion and diaphragmatic pleural thickening. Urgent respiratory review advised.",
        "output": '{"terms": [{"sentence_id": "s0", "text": "pleural effusion", "lookup_term": "pleural effusion", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}, {"sentence_id": "s0", "text": "diaphragmatic pleural thickening", "lookup_term": "pleural thickening", "semantic_tag": "disorder", "assertion": "present", "value": null, "unit": null, "reference_range": null}]}',
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
    EXTRACTION_EXAMPLES,
    {
        "precision:referral_scope",
        "precision:referral_scope:ng12_mri",
        "precision:referral_scope:lower_gi_fit",
        "precision:referral_scope:submitted",
        "precision:referral_scope:short_span",
        "precision:referral_scope:ers_reason",
        "finding:investigation",
        "assertion:absent",
        "negation:compound",
        "assertion:family",
        "assertion:historical",
        "assertion:planned",
        "observable",
        "observable:blood_panel",
        "multi-entity",
        "assertion:hypothetical",
        "abbreviation",
        "finding:lifestyle",
        "disorder:imaging",
    },
)
