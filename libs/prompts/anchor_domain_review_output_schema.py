"""Canonical JSON output schema for the anchor_domain_review prompt.

Seeded into Neo4j as the ``outputSchema`` field of the
'anchor_domain_review' PromptConfig node (version 1).

The response is a JSON array — one object per input JSONL line.
"""

ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA: dict = {
    "description": "Return a JSON array — one object per input line, in the same order. No preamble, no explanation outside the array.",
    "type": "array",
    "items": {
        "type": "object",
        "required": [
            "line_number", "original_concept_id", "domain",
            "concept_correct", "suggested_concept_id", "suggested_concept_name",
            "assertion", "rationale", "target_rule",
        ],
        "properties": {
            "line_number": {
                "type": "integer",
                "description": "The integer index from the input line (do NOT renumber).",
            },
            "original_concept_id": {
                "type": "string",
                "description": "The concept_id from the input line, copied verbatim.",
            },
            "domain": {
                "type": "string",
                "enum": [
                    "CANCER_DIAGNOSIS",
                    "CANCER_DIAGNOSIS_EXCLUDED",
                    "2WW_REFERRAL",
                    "2WW_CLINIC_SEEN",
                    "2WW_REFERRAL_REJECTED",
                    "CANCER_TREATMENT",
                    "CANCER_TREATMENT_HISTORICAL",
                    "INVESTIGATION",
                    "METASTATIC_DISEASE",
                    "NON_CANCER",
                    "AMBIGUOUS",
                ],
                "description": "Assigned clinical domain from Step 1.",
            },
            "concept_correct": {
                "type": "boolean",
                "description": "True if the concept_id and concept_name are correct for the evidence text.",
            },
            "suggested_concept_id": {
                "type": ["string", "null"],
                "description": "Alternative concept ID only if you are certain from SNOMED knowledge. Do NOT guess.",
            },
            "suggested_concept_name": {
                "type": ["string", "null"],
                "description": "Plain English description of a better concept if concept_correct is false.",
            },
            "assertion": {
                "type": "string",
                "enum": ["present", "historical", "negated", "hypothetical", "family_history"],
                "description": "Clinical assertion status of the event described in the evidence text.",
            },
            "rationale": {
                "type": "string",
                "description": "One sentence explaining the domain assignment and any concept correction.",
            },
            "target_rule": {
                "type": "string",
                "description": (
                    "medspaCy TargetRule string for the key phrase pattern, e.g. "
                    "TargetRule('Fast track referral (procedure)', '2WW_REFERRAL', "
                    "pattern=[{'LOWER': 'fast'}, {'LOWER': 'track'}, {'LOWER': 'referral'}])"
                ),
            },
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the anchor_domain_review output schema as a prompt section (array style)."""
    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    item_props = schema.get("items", {}).get("properties", {})
    item_required = schema.get("items", {}).get("required", [])

    if item_props:
        lines.append("Each object in the array must have these fields:")
        lines.append("")
        for field, defn in item_props.items():
            req_marker = " (required)" if field in item_required else " (optional, null if not applicable)"
            desc = defn.get("description", "")
            raw_type = defn.get("type", "string")
            base_type = (
                next((t for t in raw_type if t != "null"), "string")
                if isinstance(raw_type, list)
                else raw_type
            )
            nullable = isinstance(raw_type, list) and "null" in raw_type
            if "enum" in defn:
                allowed = ", ".join(f'"{v}"' for v in defn["enum"])
                lines.append(f'  - **{field}**{req_marker}: one of {allowed}. {desc}')
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f'  - **{field}**{req_marker}: {type_label}. {desc}')

    return "\n".join(lines)
