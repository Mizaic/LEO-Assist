"""Canonical JSON output schema for the exclusion_detect prompt.

Seeded into Neo4j as the ``outputSchema`` field of the
'exclusion_detect' PromptConfig node (version 1).
"""

EXCLUSION_DETECT_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown.",
    "type": "object",
    "required": ["outcome", "confidence", "evidence_text", "reasoning"],
    "properties": {
        "outcome": {
            "type": "string",
            "enum": [
                "cancer_excluded",
                "cancer_confirmed",
                "still_investigating",
                "pending_letter",
                "not_relevant",
            ],
            "description": (
                "cancer_excluded = cancer ruled out for this referral pathway; "
                "cancer_confirmed = positive cancer diagnosis made; "
                "still_investigating = investigations ongoing, no conclusion yet; "
                "pending_letter = a clinical letter received but content not quoted; "
                "not_relevant = encounter has no bearing on the cancer referral pathway."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in the outcome classification, from 0.0 to 1.0.",
        },
        "evidence_text": {
            "type": "string",
            "description": "The specific phrase(s) from the encounter that support the classification.",
        },
        "reasoning": {
            "type": "string",
            "description": "One sentence explaining the decision.",
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the exclusion_detect output schema as a prompt section."""
    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    props = schema.get("properties", {})
    required = schema.get("required", [])

    if props:
        lines.append("Return a JSON object with these fields:")
        lines.append("")
        for field, defn in props.items():
            req_marker = " (required)" if field in required else " (optional)"
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
                lines.append(f"  - **{field}**{req_marker}: one of {allowed}. {desc}")
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f"  - **{field}**{req_marker}: {type_label}. {desc}")

    return "\n".join(lines)
