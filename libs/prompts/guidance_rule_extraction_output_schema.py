"""Output schema for the exact guidance-rule extraction prompt.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")
"""

_TERM_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "properties": {
        "text": {"type": "string"},
        "source_text": {"type": ["string", "null"]},
        "search_terms": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "semantic_hint": {"type": ["string", "null"]},
        "ambiguity_reason": {"type": ["string", "null"]},
    },
}

_LOGIC_NODE_SCHEMA = {
    "type": "object",
    "required": ["kind"],
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "AND",
                "OR",
                "AT_LEAST",
                "NOT",
                "concept",
                "demographic",
                # Phase 6c: a numeric threshold on a lab value or
                # clinical reading. The LLM should emit this kind when
                # a NICE recommendation compares a named observable to
                # a number (e.g. "platelet count >= 400 x10*9/L",
                # "eGFR < 60 mL/min/1.73m2"). ``term`` carries the
                # observable name (resolved to SNOMED downstream);
                # ``operator`` / ``value`` / ``unit`` carry the
                # numeric threshold; ``within_days`` is optional and
                # defaults to 365.
                "observation",
                # Sprint 1: management-pathway leaf kinds.
                # Use "medication" when the recommendation depends on
                # what the patient is currently taking (e.g. "patient
                # taking an NSAID or aspirin"). drug_class carries the
                # class name (NSAID, PPI, H2RA, etc.).
                "medication",
                # Use "allergy" when the recommendation checks for a
                # documented drug allergy (e.g. "penicillin allergy").
                # substance_concept_id carries the SNOMED concept.
                "allergy",
                # Use "treatment_history" when the recommendation asks
                # whether a treatment has already been tried and failed
                # or was not tolerated (e.g. "failed PPI trial").
                # treatment_class carries the class; outcome carries
                # failed or not_tolerated; min_duration_days is optional.
                "treatment_history",
            ],
        },
        "children": {
            "type": "array",
            "items": {"type": "object"},
        },
        "min": {"type": ["integer", "null"]},
        "term": _TERM_SCHEMA,
        "field": {"type": ["string", "null"]},
        "operator": {"type": ["string", "null"]},
        "value": {
            # Permit a two-element array for "between" thresholds
            # (e.g. blood pressure 140-160 mmHg). Numeric / string
            # remain for back-compat with the demographic branch.
            "oneOf": [
                {"type": "number"},
                {"type": "string"},
                {"type": "null"},
                {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            ],
        },
        "unit": {"type": ["string", "null"]},
        "within_days": {"type": ["integer", "null"]},
        "raw_term": {"type": ["string", "null"]},
        # MEDICATION leaf fields
        "drug_class": {"type": ["string", "null"]},
        "concept_id": {"type": ["string", "null"]},
        # ALLERGY leaf fields
        "substance_concept_id": {"type": ["string", "null"]},
        "allergy_class": {"type": ["string", "null"]},
        # TREATMENT_HISTORY leaf fields
        "treatment_class": {"type": ["string", "null"]},
        "outcome": {"type": ["string", "null"]},
        "min_duration_days": {"type": ["integer", "null"]},
    },
}

#: Strength values a single recommended action can carry. Mirrors
#: STRENGTH_LABELS in
#: services/ui/src/app/admin/guidance/EditRuleDialog/copy.ts -- keep in sync.
_ACTION_STRENGTH_ENUM = [
    "offer",
    "consider",
    "refer",
    "discuss",
    "safety_net",
    "do_not_offer",
    "unspecified",
]

_ACTION_ITEM_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "properties": {
        "text": {"type": "string"},
        "search_terms": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "strength": {"type": "string", "enum": _ACTION_STRENGTH_ENUM},
    },
}

_SITUATION_SHELL_SCHEMA = {
    "type": "object",
    "required": ["text", "conditions"],
    "properties": {
        "text": {"type": "string"},
        "start": {"type": "integer"},
        "end": {"type": "integer"},
        "source": {
            "type": "string",
            "enum": ["structure", "heuristic", "tree", "single"],
        },
        "conditions": {
            "type": "array",
            "items": _LOGIC_NODE_SCHEMA,
        },
        "pathway_key": {"type": ["string", "null"]},
    },
}

GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA: dict = {
    "description": (
        "Return ONLY valid JSON — no explanation, no markdown, no preamble. "
        "Prefer SituationDraft (prerequisites + situations + actions). "
        "logic_tree alone is allowed for simple single-situation rules."
    ),
    "type": "object",
    "required": ["schema_version", "actions"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [2]},
        "prerequisites": {
            "type": "array",
            "items": _LOGIC_NODE_SCHEMA,
        },
        "situations": {
            "type": "array",
            "items": _SITUATION_SHELL_SCHEMA,
        },
        "logic_tree": {
            "anyOf": [
                _LOGIC_NODE_SCHEMA,
                {"type": "null"},
            ],
        },
        "actions": {
            "type": "array",
            "items": _ACTION_ITEM_SCHEMA,
        },
    },
}

GUIDANCE_RULE_EXTRACTION_EXAMPLES: list[dict] = [
    {
        "id": "gre-ex-010",
        "description": (
            "Upper GI: SituationDraft with shared age prerequisite and two "
            "structure-backed situations"
        ),
        "input": (
            "Section: Stomach cancer\n"
            "Recommendation 1.2.x: Consider endoscopy in people aged 55 or over with: "
            "treatment-resistant dyspepsia, or upper abdominal pain with low haemoglobin.\n"
            "SITUATION_SHELLS: "
            '[{"index":0,"text":"treatment-resistant dyspepsia","source":"structure"},'
            '{"index":1,"text":"upper abdominal pain with low haemoglobin","source":"structure"}]\n'
            "Urgency: routine  Strength: consider"
        ),
        "output": (
            '{"schema_version":2,'
            '"prerequisites":[{"kind":"demographic","field":"age","operator":">=",'
            '"value":55,"unit":"years","raw_term":"aged 55 or over"}],'
            '"situations":['
            '{"text":"treatment-resistant dyspepsia","source":"structure","conditions":['
            '{"kind":"concept","term":{"text":"dyspepsia","search_terms":["dyspepsia","treatment resistant dyspepsia"]}}]},'
            '{"text":"upper abdominal pain with low haemoglobin","source":"structure","conditions":['
            '{"kind":"AND","children":['
            '{"kind":"concept","term":{"text":"upper abdominal pain","search_terms":["upper abdominal pain"]}},'
            '{"kind":"observation","term":{"text":"Haemoglobin","search_terms":["haemoglobin"]},"operator":"<","value":110,"unit":"g/L","within_days":365}'
            "]}]}"
            '],"actions":[{"text":"direct access upper gastrointestinal endoscopy",'
            '"search_terms":["direct access upper gastrointestinal endoscopy","OGD"],'
            '"strength":"consider"}]}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-004",
        "description": "CG184 Dyspepsia: PPI trial failed -- management pathway rule using treatment_history and allergy leaves",
        "input": (
            "Section: Dyspepsia -- uninvestigated\n"
            "Recommendation 1.3.1: For patients aged 55 or over with unexplained dyspepsia "
            "who have already tried a full-dose PPI for 4 weeks and it has not worked or they "
            "could not tolerate it, consider testing for H. pylori. Do not offer a PPI to "
            "patients with a documented penicillin allergy.\n"
            "Urgency: routine  Strength: consider"
        ),
        "output": (
            '{"schema_version":2,"logic_tree":{"kind":"AND","children":['
            '{"kind":"demographic","field":"age","operator":">=","value":55,"unit":"years","raw_term":"aged 55 or over"},'
            '{"kind":"concept","term":{"text":"dyspepsia","source_text":"unexplained dyspepsia","search_terms":["dyspepsia","functional dyspepsia"]}},'
            '{"kind":"treatment_history","treatment_class":"PPI","outcome":"failed","min_duration_days":28,"term":"proton pump inhibitor"},'
            '{"kind":"NOT","children":['
            '{"kind":"allergy","substance_concept_id":"764146007","allergy_class":"penicillin","term":"penicillin allergy"}'
            "]}"
            ']},"actions":[{"text":"test for H. pylori","search_terms":["Helicobacter pylori testing","H pylori urea breath test"],"strength":"consider"}]}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-001",
        "description": "Lung: branch OR logic with chest X-ray finding or age plus haemoptysis",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.1: Refer people using a suspected cancer pathway referral "
            "for lung cancer if they have chest X-ray findings that suggest lung cancer "
            "or are aged 40 and over with unexplained haemoptysis.\n"
            "Urgency: urgent_2w  Strength: refer"
        ),
        "output": (
            '{"schema_version":2,"logic_tree":{"kind":"OR","children":['
            '{"kind":"concept","term":{"text":"chest X-ray findings suggestive of lung cancer","search_terms":["chest X-ray findings suggestive of lung cancer","lung cancer on chest X-ray"]}},'
            '{"kind":"AND","children":['
            '{"kind":"demographic","field":"age","operator":">=","value":40,"unit":"years","raw_term":"age 40 and over"},'
            '{"kind":"concept","term":{"text":"haemoptysis","source_text":"unexplained haemoptysis","search_terms":["haemoptysis"]}}'
            "]}"
            ']},"actions":[{"text":"fast track referral for suspected lung cancer","search_terms":["fast track referral for suspected lung cancer"],"strength":"refer"}]}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-002",
        "description": "Lung: threshold branch logic for smokers versus non-smokers",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.2: Offer an urgent chest X-ray (to be done within 2 weeks) "
            "to assess for lung cancer in people aged 40 and over if they have 2 or more "
            "of the following unexplained symptoms, or if they have ever smoked and have 1 "
            "or more of the following unexplained symptoms: cough fatigue shortness of breath "
            "chest pain weight loss appetite loss.\n"
            "Urgency: urgent_2w  Strength: offer"
        ),
        "output": (
            '{"schema_version":2,"logic_tree":{"kind":"OR","children":['
            '{"kind":"AND","children":['
            '{"kind":"demographic","field":"age","operator":">=","value":40,"unit":"years","raw_term":"age 40 and over"},'
            '{"kind":"AT_LEAST","min":2,"children":['
            '{"kind":"concept","term":{"text":"cough","search_terms":["cough"]}},'
            '{"kind":"concept","term":{"text":"fatigue","search_terms":["fatigue"]}},'
            '{"kind":"concept","term":{"text":"dyspnoea","source_text":"shortness of breath","search_terms":["dyspnoea","shortness of breath"]}},'
            '{"kind":"concept","term":{"text":"chest pain","search_terms":["chest pain"]}},'
            '{"kind":"concept","term":{"text":"weight loss","search_terms":["weight loss"]}},'
            '{"kind":"concept","term":{"text":"loss of appetite","source_text":"appetite loss","search_terms":["loss of appetite","appetite loss"]}}'
            "]}"
            "]},"
            '{"kind":"AND","children":['
            '{"kind":"concept","term":{"text":"ever smoked tobacco","source_text":"have ever smoked","search_terms":["ever smoked tobacco","smoker","history of tobacco smoking"]}},'
            '{"kind":"AT_LEAST","min":1,"children":['
            '{"kind":"concept","term":{"text":"cough","search_terms":["cough"]}},'
            '{"kind":"concept","term":{"text":"fatigue","search_terms":["fatigue"]}},'
            '{"kind":"concept","term":{"text":"dyspnoea","source_text":"shortness of breath","search_terms":["dyspnoea","shortness of breath"]}},'
            '{"kind":"concept","term":{"text":"chest pain","search_terms":["chest pain"]}},'
            '{"kind":"concept","term":{"text":"weight loss","search_terms":["weight loss"]}},'
            '{"kind":"concept","term":{"text":"loss of appetite","source_text":"appetite loss","search_terms":["loss of appetite","appetite loss"]}}'
            "]}"
            "]}"
            ']},"actions":[{"text":"urgent chest X-ray","search_terms":["urgent chest X-ray","plain X-ray of chest"],"strength":"offer"}]}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-003",
        "description": "Mesothelioma: asbestos exposure branch preserved exactly",
        "input": (
            "Section: Mesothelioma\n"
            "Recommendation 1.1.5: Offer an urgent chest X-ray (to be done within 2 weeks) "
            "to assess for mesothelioma in people aged 40 and over, if they have 2 or more "
            "of the following unexplained symptoms or they have 1 or more of the following "
            "unexplained symptoms and have ever smoked or they have 1 or more of the following "
            "unexplained symptoms and have been exposed to asbestos: cough fatigue shortness of "
            "breath chest pain weight loss appetite loss.\n"
            "Urgency: urgent_2w  Strength: offer"
        ),
        "output": (
            '{"schema_version":2,"logic_tree":{"kind":"OR","children":['
            '{"kind":"AND","children":['
            '{"kind":"demographic","field":"age","operator":">=","value":40,"unit":"years","raw_term":"age 40 and over"},'
            '{"kind":"AT_LEAST","min":2,"children":['
            '{"kind":"concept","term":{"text":"cough","search_terms":["cough"]}},'
            '{"kind":"concept","term":{"text":"fatigue","search_terms":["fatigue"]}},'
            '{"kind":"concept","term":{"text":"dyspnoea","source_text":"shortness of breath","search_terms":["dyspnoea","shortness of breath"]}},'
            '{"kind":"concept","term":{"text":"chest pain","search_terms":["chest pain"]}},'
            '{"kind":"concept","term":{"text":"weight loss","search_terms":["weight loss"]}},'
            '{"kind":"concept","term":{"text":"loss of appetite","source_text":"appetite loss","search_terms":["loss of appetite","appetite loss"]}}'
            "]}"
            "]},"
            '{"kind":"AND","children":['
            '{"kind":"concept","term":{"text":"ever smoked tobacco","source_text":"have ever smoked","search_terms":["ever smoked tobacco","smoker","history of tobacco smoking"]}},'
            '{"kind":"AT_LEAST","min":1,"children":['
            '{"kind":"concept","term":{"text":"cough","search_terms":["cough"]}},'
            '{"kind":"concept","term":{"text":"fatigue","search_terms":["fatigue"]}},'
            '{"kind":"concept","term":{"text":"dyspnoea","source_text":"shortness of breath","search_terms":["dyspnoea","shortness of breath"]}},'
            '{"kind":"concept","term":{"text":"chest pain","search_terms":["chest pain"]}},'
            '{"kind":"concept","term":{"text":"weight loss","search_terms":["weight loss"]}},'
            '{"kind":"concept","term":{"text":"loss of appetite","source_text":"appetite loss","search_terms":["loss of appetite","appetite loss"]}}'
            "]}"
            "]},"
            '{"kind":"AND","children":['
            '{"kind":"concept","term":{"text":"history of asbestos exposure","source_text":"have been exposed to asbestos","search_terms":["history of asbestos exposure","asbestos exposure"]}},'
            '{"kind":"AT_LEAST","min":1,"children":['
            '{"kind":"concept","term":{"text":"cough","search_terms":["cough"]}},'
            '{"kind":"concept","term":{"text":"fatigue","search_terms":["fatigue"]}},'
            '{"kind":"concept","term":{"text":"dyspnoea","source_text":"shortness of breath","search_terms":["dyspnoea","shortness of breath"]}},'
            '{"kind":"concept","term":{"text":"chest pain","search_terms":["chest pain"]}},'
            '{"kind":"concept","term":{"text":"weight loss","search_terms":["weight loss"]}},'
            '{"kind":"concept","term":{"text":"loss of appetite","source_text":"appetite loss","search_terms":["loss of appetite","appetite loss"]}}'
            "]}"
            "]}"
            ']},"actions":[{"text":"urgent chest X-ray","search_terms":["urgent chest X-ray","plain X-ray of chest"],"strength":"offer"}]}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-005",
        "description": (
            "RA cervical myelopathy: two distinct actions with different "
            "strengths -- offer an urgent MRI scan AND separately refer for a "
            "specialist surgical opinion"
        ),
        "input": (
            "Section: Rheumatoid arthritis in adults\n"
            "Recommendation 1.10.5: If an adult with RA develops any symptoms or signs "
            "that suggest cervical myelopathy (for example, paraesthesia, weakness, "
            "unsteadiness, reduced power, extensor plantars), request an urgent MRI "
            "scan, and refer for a specialist surgical opinion.\n"
            "Urgency: urgent  Strength: offer"
        ),
        "output": (
            '{"schema_version":2,"logic_tree":{"kind":"AND","children":['
            '{"kind":"concept","term":{"text":"rheumatoid arthritis","search_terms":["rheumatoid arthritis"]}},'
            '{"kind":"concept","term":{"text":"symptoms or signs suggestive of cervical myelopathy",'
            '"source_text":"symptoms or signs that suggest cervical myelopathy",'
            '"search_terms":["cervical myelopathy","paraesthesia","weakness","extensor plantars"]}}'
            ']},"actions":['
            '{"text":"urgent MRI scan of cervical spine","search_terms":["urgent MRI scan of cervical spine","MRI cervical spine"],"strength":"offer"},'
            '{"text":"referral for specialist surgical opinion","search_terms":["referral for specialist surgical opinion","referral to spinal surgery"],"strength":"refer"}'
            "]}"
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]
