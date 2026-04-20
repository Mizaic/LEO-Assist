"""Canonical JSON output schema for the label_verification prompt (v2).

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Seeded into Neo4j as the ``outputSchema`` field of the
'label_verification' PromptConfig node (version 2).

The response is a JSON object with a single "entities" array key.
"""

LABEL_VERIFICATION_OUTPUT_SCHEMA: dict = {
    "description": "Return JSON only — no markdown.",
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "description": "One entry per evaluated entity (existing or new).",
            "items": {
                "type": "object",
                "required": [
                    "entity_index",
                    "suggested_label",
                    "confidence",
                    "rule_triggered",
                    "rationale",
                    "is_new",
                    "new_text",
                ],
                "properties": {
                    "entity_index": {
                        "type": "integer",
                        "description": (
                            "Index of the entity from the input list. "
                            "Use -1 for newly suggested entities not in the input."
                        ),
                    },
                    "suggested_label": {
                        "type": "string",
                        "description": "The correct NER label selected from the allowed labels list.",
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
                        "description": "Confidence in the suggested label, from 0.0 to 1.0.",
                    },
                    "rule_triggered": {
                        "type": "string",
                        "description": "Short name of the decision-ladder rule that determined this label (e.g. symptom_observation, drug_administration, lab_result).",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Brief explanation, maximum 220 characters.",
                    },
                    "is_new": {
                        "type": "boolean",
                        "description": "True only for newly suggested spans not in the input entity list.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Exact text span from the encounter, populated only when is_new=true. Empty string otherwise.",
                    },
                },
            },
        }
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the label_verification output schema as a prompt section.

    Uses the same array-within-object pattern as the extraction schema renderer.
    """
    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    props = schema.get("properties", {})
    array_name = next(iter(props), "entities")
    items_props: dict = props.get(array_name, {}).get("items", {}).get("properties", {})
    required: list[str] = props.get(array_name, {}).get("items", {}).get("required", [])

    if items_props:
        lines.append(
            f'Return a JSON object with a single key "{array_name}" whose value is an array.'
        )
        lines.append(f"Each item in the array must be an object with these fields:")
        lines.append("")
        for field, defn in items_props.items():
            raw_type = defn.get("type", "string")
            base_type = (
                next((t for t in raw_type if t != "null"), "string")
                if isinstance(raw_type, list)
                else raw_type
            )
            nullable = isinstance(raw_type, list) and "null" in raw_type
            req_marker = " (required)" if field in required else " (optional)"
            desc = defn.get("description", "")

            if "enum" in defn:
                enum_vals = defn["enum"]
                allowed = ", ".join(f'"{v}"' for v in enum_vals)
                lines.append(f"  - **{field}**{req_marker}: one of {allowed}. {desc}")
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f"  - **{field}**{req_marker}: {type_label}. {desc}")

        lines.append("")
        lines.append(
            "For existing entities: set is_new=false and leave new_text as empty string. "
            "For new entities: set entity_index=-1, is_new=true, and provide the exact span in new_text."
        )

    return "\n".join(lines)
