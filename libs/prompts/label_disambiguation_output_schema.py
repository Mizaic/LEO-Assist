"""Canonical JSON output schema for the label_disambiguation prompt (v1).

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Seeded into Neo4j as the ``outputSchema`` field of the
'label_disambiguation' PromptConfig node (version 1).
"""

LABEL_DISAMBIGUATION_OUTPUT_SCHEMA: dict = {
    "description": "Return strict JSON only -- no markdown.",
    "type": "object",
    "required": ["resolved_label", "confidence", "reason"],
    "properties": {
        "resolved_label": {
            "type": "string",
            "description": "The chosen label from the allowed labels list.",
            "enum": [
                "disorder",
                "finding",
                "procedure",
                "observable_entity",
                "qualifier_value",
                "substance",
                "medicinal_product",
                "clinical_drug",
                "situation",
                "event",
                "body_structure",
                "tumor_staging",
                "assessment_scale",
                "staging_scale",
                "regime_therapy",
                "record_artifact",
                "physical_object",
                "organism",
                "morphologic_abnormality",
                "occupation",
                "attribute",
                "environment",
                "product",
                "X_TEMPORAL",
                "X_DOSAGE",
                "X_FREQUENCY",
                "X_ROUTE",
            ],
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in the resolved label, from 0.0 to 1.0.",
        },
        "reason": {
            "type": "string",
            "description": "Short explanation, maximum 220 characters. No extra keys, no markdown.",
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the label_disambiguation output schema as a prompt section."""
    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    props = schema.get("properties", {})
    required = schema.get("required", [])

    if props:
        lines.append("Return a JSON object with exactly these fields (no extra keys):")
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
                enum_vals = defn["enum"]
                allowed = ", ".join(f'"{v}"' for v in enum_vals)
                lines.append(f"  - **{field}**{req_marker}: one of {allowed}. {desc}")
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f"  - **{field}**{req_marker}: {type_label}. {desc}")

    return "\n".join(lines)
