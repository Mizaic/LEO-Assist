"""Output schema for the guidance_rule_extraction prompt.

Seeded into Neo4j as the ``outputSchema`` field of the
'guidance_rule_extraction' PromptConfig node.

Consumed by:
- ``guidance_rule_generator.py`` — validates LLM output before writing rules
- Pathway canvas — understands what this step emits
"""

GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["present", "absent", "action"],
    "properties": {
        "present": {
            "type": "array",
            "description": (
                "Clinical findings, disorders, observable entities, or demographics that "
                "must be present in the patient record for this recommendation to apply. "
                "Plain clinical language; no SNOMED IDs. Maximum 5 items."
            ),
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "absent": {
            "type": "array",
            "description": (
                "Clinical findings or conditions whose presence means this recommendation "
                "does NOT apply (contraindications, exclusions). "
                "Plain clinical language; no SNOMED IDs. Maximum 5 items."
            ),
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "action": {
            "type": ["string", "null"],
            "description": (
                "The clinical procedure recommended — expressed as a short, searchable "
                "term for SNOMED CT lookup. Examples: 'suspected cancer pathway referral', "
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
        "description": "2WW lung cancer recommendation (chest X-ray findings)",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.1: Refer people using a suspected cancer pathway referral "
            "for lung cancer if they have chest X-ray findings that suggest lung cancer.\n"
            "Urgency: 2WW  Strength: refer"
        ),
        "output": '{"present": ["chest X-ray findings suggestive of lung cancer"], "absent": [], "action": "suspected cancer pathway referral"}',
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-002",
        "description": "2WW lung cancer recommendation (age + symptom combination)",
        "input": (
            "Section: Lung cancer\n"
            "Recommendation 1.1.2: Offer an urgent chest X-ray (to be done within 2 weeks) "
            "to assess for lung cancer in people aged 40 and over if they have never smoked "
            "and have two or more of the following unexplained symptoms, or have ever smoked "
            "and have one or more of the following unexplained symptoms: cough, fatigue, "
            "shortness of breath, chest pain, weight loss, appetite loss.\n"
            "Urgency: 2WW  Strength: offer"
        ),
        "output": (
            '{"present": ["age 40 and over", "unexplained cough or fatigue or shortness of breath '
            'or chest pain or weight loss or appetite loss"], "absent": [], "action": "urgent chest X-ray"}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-003",
        "description": "Ovarian cancer CA125 test (symptom + age + sex)",
        "input": (
            "Section: Ovarian cancer\n"
            "Recommendation 1.5.6: Measure serum CA125 in primary care in women aged 18 and "
            "over if they have any of the following symptoms and these are persistent or "
            "frequent (particularly more than 12 times per month): abdominal distension, "
            "feeling full or loss of appetite, pelvic or abdominal pain, increased urinary "
            "urgency or frequency.\n"
            "Urgency: Routine  Strength: offer"
        ),
        "output": (
            '{"present": ["female sex", "age 18 and over", '
            '"persistent abdominal distension or pelvic pain or urinary urgency or loss of appetite"], '
            '"absent": [], "action": "serum CA125 measurement"}'
        ),
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "gre-ex-004",
        "description": "General standard with no patient criteria",
        "input": (
            "Section: Service organisation\n"
            "Recommendation 2.1: Cancer services should be organised to ensure that "
            "patients have access to a clinical nurse specialist.\n"
            "Urgency: Routine  Strength: ensure"
        ),
        "output": '{"present": [], "absent": [], "action": null}',
        "category": "guidance_rule_extraction",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]
