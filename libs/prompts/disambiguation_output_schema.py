"""Canonical JSON output schema for the disambiguation prompt.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Seeded into Neo4j as the ``outputSchema`` field of the
'disambiguation' PromptConfig node (version 1).
"""

DISAMBIGUATION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON -- no explanation, no markdown, no preamble.",
    "type": "object",
    "required": ["conceptId", "confidence", "reason"],
    "properties": {
        "conceptId": {
            "type": "string",
            "description": (
                "The SNOMED CT concept ID of the best-matching concept. "
                "Use 'NONE' if no candidate is a sufficiently close match."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "Confidence that this concept correctly represents the term, from 0.0 to 1.0.",
        },
        "reason": {
            "type": "string",
            "description": "One sentence explaining why this concept was selected or why no match was found.",
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the disambiguation output schema as a prompt section."""
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
        lines.append("")
        lines.append(
            'If no candidate fits, return {"conceptId": "NONE", "confidence": 0.0, "reason": "..."}'
        )

    return "\n".join(lines)
