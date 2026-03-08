"""Output schema for the guidance_rule_extraction prompt.

Seeded into Neo4j as the ``outputSchema`` field of the
'guidance_rule_extraction' and 'guidance_rule_extraction_default' PromptConfig
nodes.

The schema supports the ``criteria_groups`` format.  The old ``present`` /
``absent`` format is accepted by ``_parse_llm_output`` for backward compat
and is auto-converted to criteria_groups.

Consumed by:
- ``guidance_rule_generator.py`` — validates LLM output before writing rules
- Pathway canvas — understands what this step emits
"""

GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["criteria_groups", "action"],
    "properties": {
        "criteria_groups": {
            "type": "array",
            "description": (
                "List of criteria groups. Each group has 'mode' (ANY | ALL | NOT) and "
                "'terms' (list of plain clinical language strings). "
                "ALL groups AND together — every group must pass for the rule to fire. "
                "Use mode='ANY' for symptom lists where at least one must be present. "
                "Use mode='ALL' for demographics and mandatory prerequisites. "
                "Use mode='NOT' for exclusions and contraindications. "
                "Age MUST be expressed as 'age N and over' or 'age N and under'. "
                "Sex MUST be expressed as 'female sex' or 'male sex'. "
                "Maximum 5 terms per group."
            ),
            "items": {
                "type": "object",
                "required": ["mode", "terms"],
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["ANY", "ALL", "NOT"],
                        "description": (
                            "ANY = at least one term must be in the patient record. "
                            "ALL = every term must be in the patient record. "
                            "NOT = none of the terms may be in the patient record."
                        ),
                    },
                    "terms": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string"},
                        "description": "Plain clinical terms — no SNOMED IDs.",
                    },
                },
            },
        },
        "action": {
            "type": ["string", "null"],
            "description": (
                "The clinical procedure recommended — expressed as a short, searchable "
                "term for SNOMED CT lookup. Examples: "
                "'fast track referral for suspected lung cancer', "
                "'urgent chest X-ray', 'serum CA125 measurement', "
                "'quantitative faecal immunochemical test'. "
                "Null if the recommendation is an organisational standard with no "
                "specific clinical action."
            ),
        },
    },
}

# ── Few-shot examples ──────────────────────────────────────────────────────────

GUIDANCE_RULE_EXTRACTION_EXAMPLES: list[dict] = [
    {
        "id": "gre-ex-001",
        "description": "Lung: chest X-ray findings (single ALL group, no symptom list)",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.1: Refer people using a suspected cancer pathway referral "
            "for lung cancer if they have chest X-ray findings that suggest lung cancer.\n"
            "Urgency: urgent_2w  Strength: refer"
        ),
        "output": '{"criteria_groups": [{"mode": "ALL", "terms": ["chest X-ray findings suggestive of lung cancer"]}], "action": "fast track referral for suspected lung cancer"}',
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-002",
        "description": "Lung: age ALL + symptoms ANY (each listed separately, no qualifiers)",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.2: Offer an urgent chest X-ray (to be done within 2 weeks) "
            "to assess for lung cancer in people aged 40 and over if they have never smoked "
            "and have two or more of the following unexplained symptoms, or have ever smoked "
            "and have one or more of the following unexplained symptoms: cough, fatigue, "
            "shortness of breath, chest pain, weight loss, appetite loss.\n"
            "Urgency: urgent_2w  Strength: offer"
        ),
        "output": (
            '{"criteria_groups": ['
            '{"mode": "ALL", "terms": ["age 40 and over"]}, '
            '{"mode": "ANY", "terms": ["cough", "dyspnoea", "weight loss", "chest pain", "haemoptysis"]}'
            '], "action": "urgent chest X-ray"}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-003",
        "description": "Ovarian: sex + age ALL, symptoms ANY, investigation action",
        "input": (
            "Section: Ovarian cancer\n"
            "Recommendation 1.5.6: Measure serum CA125 in primary care in women aged 18 and "
            "over if they have any of the following symptoms and these are persistent or "
            "frequent (particularly more than 12 times per month): abdominal distension, "
            "feeling full or loss of appetite, pelvic or abdominal pain, increased urinary "
            "urgency or frequency.\n"
            "Urgency: routine  Strength: offer"
        ),
        "output": (
            '{"criteria_groups": ['
            '{"mode": "ALL", "terms": ["female sex", "age 18 and over"]}, '
            '{"mode": "ANY", "terms": ["abdominal distension", "pelvic pain", "urinary frequency", "loss of appetite"]}'
            '], "action": "serum CA125 measurement"}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-004",
        "description": "Bladder: age ALL + symptom ANY + exclusion NOT",
        "input": (
            "Section: Urological cancers\n"
            "Recommendation 1.6.1: Refer people using a suspected cancer pathway referral "
            "for bladder cancer if they are aged 45 years or over and have unexplained "
            "visible haematuria without urinary tract infection.\n"
            "Urgency: urgent_2w  Strength: refer"
        ),
        "output": (
            '{"criteria_groups": ['
            '{"mode": "ALL", "terms": ["age 45 and over"]}, '
            '{"mode": "ANY", "terms": ["haematuria"]}, '
            '{"mode": "NOT", "terms": ["urinary tract infection"]}'
            '], "action": "fast track referral for suspected urological cancer"}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-005",
        "description": "General service standard — no patient criteria",
        "input": (
            "Section: Service organisation\n"
            "Recommendation 2.1: Cancer services should be organised to ensure that "
            "patients have access to a clinical nurse specialist.\n"
            "Urgency: routine  Strength: ensure"
        ),
        "output": '{"criteria_groups": [], "action": null}',
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]
