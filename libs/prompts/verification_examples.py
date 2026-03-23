"""Few-shot example library for the verification prompt (v1)."""

from __future__ import annotations

VERIFICATION_EXAMPLES: list[dict] = [
    {
        "category": "verification:borderline-cppd",
        "model_scope": "any",
        "description": "Borderline CPPD label disagreement should not fail verification",
        "input": (
            'Encounter: "nil #s. medial CPPD. lateral osteophytes. good joint space."\n'
            'Entities: [{"entity_index": 0, "text": "medial CPPD", "label": "disorder", '
            '"assertion": "present", "lookup_term": "calcium pyrophosphate deposition disease"}]'
        ),
        "output": (
            '{"is_accurate": true, "confidence": 0.9, "issues": [], "corrections": []}'
        ),
    },
    {
        "category": "verification:drop-vague-progress",
        "model_scope": "any",
        "description": "Vague progress statement should be dropped, not normalized into pseudo-SNOMED",
        "input": (
            'Encounter: "The knee is improving."\n'
            'Entities: [{"entity_index": 0, "text": "knee is improving", "label": "finding", '
            '"assertion": "present", "lookup_term": "knee pain improving"}]'
        ),
        "output": (
            '{"is_accurate": false, "confidence": 0.94, "issues": '
            '["Entity 0 is a vague progress statement with no reliable SNOMED concept; drop it rather than infer pain."], '
            '"corrections": [{"entity_index": 0, "drop": true}]}'
        ),
    },
]
