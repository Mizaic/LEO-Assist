"""Output schema for verifier-backed guidance rule code selection."""

_LEAF_DECISION = {
    "type": "object",
    "required": ["node_id", "status", "selected_concept_id", "reason", "confidence", "retry_search_terms"],
    "properties": {
        "node_id": {"type": "string"},
        "status": {"type": "string", "enum": ["verified", "retry_search", "rejected"]},
        "selected_concept_id": {"type": ["string", "null"]},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
        "retry_search_terms": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
    },
}

_ACTION_DECISION = {
    "type": "object",
    "required": ["status", "selected_concept_id", "reason", "confidence", "retry_search_terms"],
    "properties": {
        "status": {"type": "string", "enum": ["verified", "retry_search", "rejected", "not_required"]},
        "selected_concept_id": {"type": ["string", "null"]},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
        "retry_search_terms": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
    },
}

GUIDANCE_RULE_CODE_VERIFIER_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["overall_status", "leaf_decisions", "action_decision"],
    "properties": {
        "overall_status": {"type": "string", "enum": ["verified", "retry_search", "rejected"]},
        "leaf_decisions": {"type": "array", "items": _LEAF_DECISION},
        "action_decision": _ACTION_DECISION,
    },
}

GUIDANCE_RULE_CODE_VERIFIER_EXAMPLES: list[dict] = [
    {
        "id": "grcv-ex-001",
        "description": "Approve exact concepts from supplied candidates",
        "input": (
            '{"recommendation":{"id":"NG12:v1:CH002:SEC000:R000","section_title":"Lung cancer"},'
            '"criteria_leaves":[{"node_id":"n2","term":"haemoptysis","candidates":'
            '[{"concept_id":"66857006","preferred_term":"Hemoptysis (finding)","semantic_tag":"finding","score":0.99}]},'
            '{"node_id":"n3","term":"chest X-ray findings suggestive of lung cancer","candidates":'
            '[{"concept_id":"424132000","preferred_term":"Abnormal chest X-ray (finding)","semantic_tag":"finding","score":0.92},'
            '{"concept_id":"399208008","preferred_term":"Suspected lung cancer (situation)","semantic_tag":"situation","score":0.55}]}],'
            '"action":{"term":"fast track referral for suspected lung cancer","candidates":'
            '[{"concept_id":"276281000000104","preferred_term":"Fast track referral for suspected lung cancer (procedure)",'
            '"semantic_tag":"procedure","score":0.99}]}}'
        ),
        "output": (
            '{"overall_status":"verified","leaf_decisions":['
            '{"node_id":"n2","status":"verified","selected_concept_id":"66857006","reason":"Exact symptom match.","confidence":0.99,"retry_search_terms":[]},'
            '{"node_id":"n3","status":"verified","selected_concept_id":"424132000","reason":"Broad imaging finding is safer than a cancer diagnosis concept.","confidence":0.9,"retry_search_terms":[]}'
            '],"action_decision":{"status":"verified","selected_concept_id":"276281000000104","reason":"Exact procedure/referral concept.","confidence":0.99,"retry_search_terms":[]}}'
        ),
        "category": "guidance_rule_code_verifier",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
    {
        "id": "grcv-ex-002",
        "description": "Request broader alternate search when candidates are too narrow",
        "input": (
            '{"recommendation":{"id":"NG12:v1:CH002:SEC000:R005","section_title":"Mesothelioma"},'
            '"criteria_leaves":[{"node_id":"n7","term":"chest signs compatible with pleural disease","candidates":'
            '[{"concept_id":"123","preferred_term":"Pleural effusion due to neoplastic disease (disorder)","semantic_tag":"disorder","score":0.86}]}],'
            '"action":{"term":"urgent chest X-ray","candidates":[{"concept_id":"399208008","preferred_term":"Plain X-ray of chest (procedure)","semantic_tag":"procedure","score":0.93}]}}'
        ),
        "output": (
            '{"overall_status":"retry_search","leaf_decisions":['
            '{"node_id":"n7","status":"retry_search","selected_concept_id":null,"reason":"Current candidate is too narrow and cancer-specific for the NICE phrase.","confidence":0.35,"retry_search_terms":["pleural disease","pleural abnormality","abnormal chest signs"]}'
            '],"action_decision":{"status":"verified","selected_concept_id":"399208008","reason":"Correct investigation procedure.","confidence":0.93,"retry_search_terms":[]}}'
        ),
        "category": "guidance_rule_code_verifier",
        "model_scope": "any",
        "core": True,
        "deidentified": True,
    },
]
