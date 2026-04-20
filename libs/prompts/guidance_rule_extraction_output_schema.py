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
            "enum": ["AND", "OR", "AT_LEAST", "NOT", "concept", "demographic"],
        },
        "children": {
            "type": "array",
            "items": {"type": "object"},
        },
        "min": {"type": ["integer", "null"]},
        "term": _TERM_SCHEMA,
        "field": {"type": ["string", "null"]},
        "operator": {"type": ["string", "null"]},
        "value": {"type": ["number", "string", "null"]},
        "unit": {"type": ["string", "null"]},
        "raw_term": {"type": ["string", "null"]},
    },
}

GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["schema_version", "logic_tree", "action"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [2]},
        "logic_tree": {
            "anyOf": [
                _LOGIC_NODE_SCHEMA,
                {"type": "null"},
            ],
        },
        "action": {
            "type": ["object", "null"],
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "search_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
            },
        },
    },
}

GUIDANCE_RULE_EXTRACTION_EXAMPLES: list[dict] = [
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
            ']},"action":{"text":"fast track referral for suspected lung cancer","search_terms":["fast track referral for suspected lung cancer"]}}'
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
            ']},"action":{"text":"urgent chest X-ray","search_terms":["urgent chest X-ray","plain X-ray of chest"]}}'
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
            ']},"action":{"text":"urgent chest X-ray","search_terms":["urgent chest X-ray","plain X-ray of chest"]}}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]
